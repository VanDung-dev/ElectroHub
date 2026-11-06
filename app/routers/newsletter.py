import hashlib
import hmac
import smtplib
from email.message import EmailMessage
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.models.newsletter import NewsletterSubscriber
from app.schemas.auth import DetailResponse

router = APIRouter(prefix="/api/v1/newsletter", tags=["newsletter"])


class SubscribeRequest(BaseModel):
    email: EmailStr
    consent: Literal[True]


class CampaignRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=5000)

    @field_validator("subject")
    @classmethod
    def valid_subject(cls, value: str) -> str:
        value = value.strip()
        if "\r" in value or "\n" in value:
            raise ValueError("Tiêu đề không được chứa xuống dòng")
        return value


def _unsubscribe_token(email: str) -> str:
    settings = get_settings()
    signature = hmac.new(
        settings.secret_key.get_secret_value().encode(), email.encode(), hashlib.sha256
    ).hexdigest()
    return f"{email}|{signature}"


@router.post("/subscribe", response_model=DetailResponse, status_code=201)
def subscribe(data: SubscribeRequest, db: DbSession):
    email = str(data.email).lower()
    if db.scalar(select(NewsletterSubscriber.id).where(NewsletterSubscriber.email == email)):
        return DetailResponse(detail="Email đã đăng ký nhận tin")
    db.add(NewsletterSubscriber(email=email))
    db.commit()
    return DetailResponse(detail="Đăng ký nhận tin thành công")


@router.post("/unsubscribe", response_model=DetailResponse)
def unsubscribe(db: DbSession, token: str = Form()):
    try:
        email, signature = token.rsplit("|", 1)
    except ValueError:
        raise HTTPException(400, "Liên kết hủy đăng ký không hợp lệ") from None
    expected = _unsubscribe_token(email).rsplit("|", 1)[1]
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(400, "Liên kết hủy đăng ký không hợp lệ")
    subscriber = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == email))
    if subscriber:
        db.delete(subscriber)
        db.commit()
    return DetailResponse(detail="Đã hủy đăng ký nhận tin")


@router.post("/send", response_model=DetailResponse)
def send_campaign(data: CampaignRequest, db: DbSession, user: CurrentUser):
    if user.role != "admin":
        raise HTTPException(403, "Bạn không có quyền gửi email marketing")
    settings = get_settings()
    if not all((settings.smtp_host, settings.mail_from)):
        raise HTTPException(503, "Cần cấu hình SMTP_HOST và MAIL_FROM để gửi email")
    recipients = db.scalars(
        select(NewsletterSubscriber.email).order_by(NewsletterSubscriber.id)
    ).all()
    if not recipients:
        return DetailResponse(detail="Chưa có người đăng ký nhận tin")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            for email in recipients:
                message = EmailMessage()
                message["From"] = settings.mail_from
                message["To"] = email
                message["Subject"] = data.subject.strip()
                unsubscribe = (
                    f"{settings.site_url.rstrip('/')}/newsletter/unsubscribe?"
                    f"{urlencode({'token': _unsubscribe_token(email)})}"
                )
                message.set_content(f"{data.body.strip()}\n\nHủy nhận tin: {unsubscribe}")
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(503, "Không gửi được email qua SMTP") from exc
    return DetailResponse(detail=f"Đã gửi email tới {len(recipients)} người đăng ký")
