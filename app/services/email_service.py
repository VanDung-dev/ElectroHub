import hashlib
import hmac
import logging
import re
import smtplib
import socket
from email.message import EmailMessage
from functools import lru_cache
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ROOT, get_settings
from app.core.database import get_engine
from app.models.newsletter import EmailCampaign
from app.models.product import Product

logger = logging.getLogger("electrohub.email")

_jinja_env = Environment(
    loader=FileSystemLoader(str(ROOT / "app/templates")),
    autoescape=select_autoescape(["html", "xml"]),
)


# ponytail: cache host check to prevent blocking DNS lookup timeouts per email outside Docker
@lru_cache(maxsize=8)
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
        f"Tặng bạn mã ưu đãi WELCOME10 giảm 10% cho đơn hàng đầu tiên tại "
        f"{site_url}/collections/all.\n\n"
        f"Hủy nhận tin bất cứ lúc nào: {unsub_url}"
    )
    return text_content, html_content


_PRODUCT_PLACEHOLDER_RE = re.compile(r"\[\[PRODUCT\s*:\s*([^\]]+)\]\]", re.IGNORECASE)
_PRODUCT_PLACEHOLDER_RE_ALT = re.compile(r"\[PRODUCT\s*:\s*([^\]]+)\]", re.IGNORECASE)
_PRODUCT_IMAGE_PLACEHOLDER_RE = re.compile(r"\[\[PRODUCT_IMAGE\s*:\s*([^\]]+)\]\]", re.IGNORECASE)
_PRODUCT_IMAGE_PLACEHOLDER_RE_ALT = re.compile(r"\[PRODUCT_IMAGE\s*:\s*([^\]]+)\]", re.IGNORECASE)
_PRODUCT_IMG_PLACEHOLDER_RE = re.compile(r"\[\[IMG_PRODUCT\s*:\s*([^\]]+)\]\]", re.IGNORECASE)


def _render_product_card_html(product: Product, site_url: str) -> str:
    product_url = f"{site_url.rstrip('/')}/products/{product.slug}"
    image_url = product.image_url
    if image_url and image_url.startswith("/"):
        image_url = f"{site_url.rstrip('/')}{image_url}"

    price_html = ""
    if product.sale_price is not None and product.sale_price < product.price:
        price_html = (
            f'<span style="text-decoration: line-through; color: #627264; font-size: 14px;">{product.price:,}₫</span> '
            f'<span style="color: #d97706; font-weight: 700; font-size: 16px;">{product.sale_price:,}₫</span>'
        )
    else:
        price_html = f'<span style="font-weight: 700; font-size: 16px; color: #12372a;">{product.price:,}₫</span>'

    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin: 6px 0; border: 1px solid #d8e2dc; border-radius: 8px; overflow: hidden;">
  <tr>
    <td style="width: 140px; padding: 12px; vertical-align: top;">
      <a href="{product_url}" style="text-decoration: none;">
        <img src="{image_url}" alt="{escape(product.name)}" width="116" style="display: block; width: 116px; height: 116px; object-fit: cover; border-radius: 6px; border: 1px solid #eaeaea;" />
      </a>
    </td>
    <td style="padding: 12px 16px 12px 8px; vertical-align: top;">
      <p style="margin: 0 0 8px 0; font-size: 16px; font-weight: 600; color: #12372a;">
        <a href="{product_url}" style="color: #12372a; text-decoration: none;">{escape(product.name)}</a>
      </p>
      <p style="margin: 0 0 12px 0;">{price_html}</p>
      <p style="margin: 0;">
        <a href="{product_url}" style="display: inline-block; background-color: #12372a; color: #ffffff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 14px; font-weight: 600;">Xem sản phẩm →</a>
      </p>
    </td>
  </tr>
</table>
""".strip()


def _render_product_image_html(product: Product, site_url: str) -> str:
    product_url = f"{site_url.rstrip('/')}/products/{product.slug}"
    image_url = product.image_url
    if image_url and image_url.startswith("/"):
        image_url = f"{site_url.rstrip('/')}{image_url}"
    return (
        f'<p style="text-align: center; margin: 6px 0;">'
        f'<a href="{product_url}" style="text-decoration: none;">'
        f'<img src="{image_url}" alt="{escape(product.name)}" width="520" style="max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #eaeaea;" />'
        f'</a></p>'
    )


def _lookup_product(key: str) -> Product | None:
    try:
        with Session(get_engine()) as db:
            if key.isdigit():
                product = db.get(Product, int(key))
                if product:
                    return product
            product = db.scalar(select(Product).where(Product.slug == key))
            if product:
                return product
            product = db.scalar(select(Product).where(Product.sku == key))
            if product:
                return product
    except Exception:
        return None
    return None


def _process_product_placeholders(body: str, site_url: str) -> str:
    def replace_product(match: re.Match) -> str:
        key = match.group(1).strip()
        product = _lookup_product(key)
        if product is None:
            return match.group(0)
        try:
            return _render_product_card_html(product, site_url)
        except Exception:
            return match.group(0)

    def replace_product_image(match: re.Match) -> str:
        key = match.group(1).strip()
        product = _lookup_product(key)
        if product is None:
            return match.group(0)
        try:
            return _render_product_image_html(product, site_url)
        except Exception:
            return match.group(0)

    # Try both formats
    body = _PRODUCT_PLACEHOLDER_RE.sub(replace_product, body)
    body = _PRODUCT_PLACEHOLDER_RE_ALT.sub(replace_product, body)
    body = _PRODUCT_IMAGE_PLACEHOLDER_RE.sub(replace_product_image, body)
    body = _PRODUCT_IMAGE_PLACEHOLDER_RE_ALT.sub(replace_product_image, body)
    body = _PRODUCT_IMG_PLACEHOLDER_RE.sub(replace_product_image, body)

    # Also support comma-separated list: [[PRODUCTS:slug1,slug2,...]]
    products_list_re = re.compile(r"\[\[PRODUCTS\s*:\s*([^\]]+)\]\]", re.IGNORECASE)

    def replace_products_list(match: re.Match) -> str:
        keys_str = match.group(1)
        keys = [k.strip() for k in re.split(r"[,\s]+", keys_str) if k.strip()]
        cards = []
        for key in keys:
            product = _lookup_product(key)
            if product:
                try:
                    card = _render_product_card_html(product, site_url)
                    # Remove margins for tight vertical layout
                    card = card.replace('style="margin: 12px 0; ', 'style="margin: 4px 0; ')
                    card = card.replace('margin: 12px 0;', 'margin: 4px 0;')
                    cards.append(card)
                except Exception:
                    continue
        if not cards:
            return match.group(0)
        # Render stacked vertically with minimal spacing
        stack_html = '<div style="margin: 8px 0;">' + "\n".join(cards) + '</div>'
        return stack_html

    body = products_list_re.sub(replace_products_list, body)
    return body


def _format_campaign_paragraphs(body: str, site_url: str | None = None) -> tuple[str, list[Markup]]:
    settings = get_settings() if site_url is None else None
    resolved_site_url = site_url or (settings.site_url.rstrip("/") if settings else "")

    # Process product placeholders first
    processed_body = _process_product_placeholders(body, resolved_site_url)
    normalized = processed_body.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Split by double newlines, but be careful not to break HTML tables
    raw_parts = re.split(r"\n\s*\n", normalized)
    formatted = []
    for p in raw_parts:
        p_stripped = p.strip()
        if not p_stripped:
            continue
        # If it's HTML (contains tags like <table, <div, <img), don't escape - it's already safe HTML we generated
        if re.search(r"<(table|div|img|a|tr|td)\b", p_stripped, re.IGNORECASE):
            # For HTML blocks, don't add extra <br> tags
            formatted.append(Markup(p_stripped))
        else:
            formatted.append(Markup("<br>\n".join(str(escape(line)) for line in p_stripped.split("\n"))))
    if not formatted and normalized:
        # Fallback
        if re.search(r"<(table|div|img|a)\b", normalized, re.IGNORECASE):
            formatted = [Markup(normalized)]
        else:
            formatted = [Markup("<br>\n".join(str(escape(line)) for line in normalized.split("\n")))]
    return normalized, formatted


def render_campaign_email(
    email: str,
    subject: str,
    body: str,
    *,
    precomputed: tuple[str, list[Markup]] | None = None,
) -> tuple[str, str]:
    """Generate plain text and responsive HTML for a marketing campaign."""
    settings = get_settings()
    site_url = settings.site_url.rstrip("/")
    unsub_url = get_unsubscribe_url(email)
    normalized_body, formatted_paragraphs = precomputed or _format_campaign_paragraphs(body, site_url)

    template = _jinja_env.get_template("emails/campaign.html")
    html_content = template.render(
        site_url=site_url,
        unsubscribe_url=unsub_url,
        subject=subject.strip(),
        paragraphs=formatted_paragraphs,
    )

    text_content = (
        f"{subject.strip()}\n\n"
        f"{normalized_body}\n\n"
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

            # ponytail: parse and format campaign content once instead of per-recipient
            site_url = settings.site_url.rstrip("/")
            precomputed = _format_campaign_paragraphs(body, site_url)
            for email in recipients:
                try:
                    text_content, html_content = render_campaign_email(
                        email, subject, body, precomputed=precomputed
                    )
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
