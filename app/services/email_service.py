import hashlib
import hmac
import logging
import smtplib
import socket
from email.message import EmailMessage
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.core.config import ROOT, get_settings
from app.core.database import get_engine
from app.models.newsletter import EmailCampaign

logger = logging.getLogger("electrohub.email")

_jinja_env = Environment(
    loader=FileSystemLoader(str(ROOT / "app/templates")),
    autoescape=select_autoescape(["html", "xml"]),
)


def _resolve_smtp_host(host: str) -> str:
    """Fallback 'mailpit' to 'localhost' if running on host machine outside docker network."""
    if host == "mailpit":
        try:
            socket.gethostbyname("mailpit")
        except socket.gaierror:
            return "localhost"
    return host


def unsubscribe_token(email: str) -> str:
    """Generate an HMAC signature token for one-click unsubscribe links."""
    settings = get_settings()
    signature = hmac.new(
        settings.secret_key.get_secret_value().encode(), email.encode(), hashlib.sha256
    ).hexdigest()
    return f"{email}|{signature}"


def get_unsubscribe_url(email: str) -> str:
    settings = get_settings()
    token = unsubscribe_token(email)
    return f"{settings.site_url.rstrip('/')}/newsletter/unsubscribe?{urlencode({'token': token})}"


def render_welcome_email(email: str) -> tuple[str, str]:
    """Generate plain text and responsive HTML for the welcome email."""
    settings = get_settings()
    site_url = settings.site_url.rstrip("/")
    unsub_url = get_unsubscribe_url(email)
    voucher_code = "WELCOME10"

    template = _jinja_env.get_template("emails/welcome.html")
    html_content = template.render(
        site_url=site_url,
        unsubscribe_url=unsub_url,
        voucher_code=voucher_code,
        subject="Chào mừng bạn đến với ElectroHub! Tặng mã ưu đãi WELCOME10",
    )

    text_content = (
        f"Chào mừng bạn đến với ElectroHub!\n\n"
        f"Cảm ơn bạn đã đăng ký nhận bản tin từ ElectroHub.\n"
        f"Tặng bạn mã ưu đãi WELCOME10 giảm 10% cho đơn hàng đầu tiên tại {site_url}/collections/all.\n\n"
        f"Hủy nhận tin bất cứ lúc nào: {unsub_url}"
    )
    return text_content, html_content


def render_campaign_email(email: str, subject: str, body: str) -> tuple[str, str]:
    """Generate plain text and responsive HTML for a marketing campaign."""
    settings = get_settings()
    site_url = settings.site_url.rstrip("/")
    unsub_url = get_unsubscribe_url(email)

    paragraphs = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [body.strip()]

    template = _jinja_env.get_template("emails/campaign.html")
    html_content = template.render(
        site_url=site_url,
        unsubscribe_url=unsub_url,
        subject=subject.strip(),
        paragraphs=paragraphs,
    )

    text_content = (
        f"{subject.strip()}\n\n"
        f"{body.strip()}\n\n"
        f"Khám phá ngay tại: {site_url}/collections/all\n"
        f"Hủy nhận tin: {unsub_url}"
    )
    return text_content, html_content


def send_smtp_message(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str | None = None,
) -> bool:
    """Send an email using configured SMTP settings."""
    settings = get_settings()
    if not all((settings.smtp_host, settings.mail_from)):
        logger.warning("SMTP is not configured (smtp_host or mail_from missing). Skipping email.")
        return False

    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_content)
    if html_content:
        message.add_alternative(html_content, subtype="html")

    host = _resolve_smtp_host(settings.smtp_host)
    with smtplib.SMTP(host, settings.smtp_port, timeout=15) as smtp:
        if hasattr(smtp, "has_extn") and smtp.has_extn("starttls"):
            try:
                smtp.starttls()
            except Exception:
                pass
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
    return True


def send_welcome_background(email: str) -> None:
    """FastAPI Background task to safely send a welcome email."""
    try:
        text_content, html_content = render_welcome_email(email)
        send_smtp_message(
            to_email=email,
            subject="Chào mừng bạn đến với ElectroHub! Tặng mã ưu đãi WELCOME10",
            text_content=text_content,
            html_content=html_content,
        )
    except Exception as exc:
        logger.error("Failed to send welcome email to %s: %s", email, exc)


def send_campaign_background(
    campaign_id: int,
    subject: str,
    body: str,
    recipients: list[str],
) -> None:
    """FastAPI Background task to send a campaign to multiple recipients and update status."""
    sent_count = 0
    try:
        settings = get_settings()
        if not all((settings.smtp_host, settings.mail_from)):
            logger.warning("SMTP not configured for campaign %s", campaign_id)
            return

        host = _resolve_smtp_host(settings.smtp_host)
        with smtplib.SMTP(host, settings.smtp_port, timeout=30) as smtp:
            if hasattr(smtp, "has_extn") and smtp.has_extn("starttls"):
                try:
                    smtp.starttls()
                except Exception:
                    pass
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())

            for email in recipients:
                try:
                    text_content, html_content = render_campaign_email(email, subject, body)
                    message = EmailMessage()
                    message["From"] = settings.mail_from
                    message["To"] = email
                    message["Subject"] = subject.strip()
                    message.set_content(text_content)
                    if html_content:
                        message.add_alternative(html_content, subtype="html")
                    smtp.send_message(message)
                    sent_count += 1
                except Exception as sub_exc:
                    logger.error("Error sending campaign to %s: %s", email, sub_exc)

        # Update campaign in DB
        with Session(get_engine()) as db:
            campaign = db.get(EmailCampaign, campaign_id)
            if campaign:
                campaign.recipient_count = sent_count
                campaign.status = "sent"
                db.commit()
    except Exception as exc:
        logger.error("Fatal error during campaign %s dispatch: %s", campaign_id, exc)
        try:
            with Session(get_engine()) as db:
                campaign = db.get(EmailCampaign, campaign_id)
                if campaign:
                    campaign.status = "failed"
                    db.commit()
        except Exception:
            pass
