import hmac
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query
from sqlalchemy import desc, func, select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, require_admin
from app.models.newsletter import EmailCampaign, NewsletterSubscriber
from app.schemas.auth import DetailResponse
from app.schemas.newsletter import (
    CampaignItem,
    CampaignListResponse,
    CampaignRequest,
    PreviewEmailRequest,
    PreviewEmailResponse,
    SubscriberItem,
    SubscriberListResponse,
    SubscribeRequest,
)
from app.services import email_service

router = APIRouter(prefix="/api/v1/newsletter", tags=["newsletter"])
admin_router = APIRouter(
    prefix="/api/v1/admin/newsletter",
    tags=["admin_newsletter"],
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": DetailResponse},
        403: {"model": DetailResponse},
        404: {"model": DetailResponse},
    },
)


def _unsubscribe_token(email: str) -> str:
    return email_service.unsubscribe_token(email)


@router.post("/subscribe", response_model=DetailResponse, status_code=201)
def subscribe(data: SubscribeRequest, db: DbSession, background_tasks: BackgroundTasks):
    email = str(data.email).lower()
    if db.scalar(select(NewsletterSubscriber.id).where(NewsletterSubscriber.email == email)):
        return DetailResponse(detail="Email đã đăng ký nhận tin")
    subscriber = NewsletterSubscriber(email=email)
    db.add(subscriber)
    db.commit()
    background_tasks.add_task(email_service.send_welcome_background, email)
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
def send_campaign(
    data: CampaignRequest,
    db: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    if user.role != "admin":
        raise HTTPException(403, "Bạn không có quyền gửi email marketing")
    settings = get_settings()
    if not all((settings.smtp_host, settings.mail_from)):
        raise HTTPException(503, "Cần cấu hình SMTP_HOST và MAIL_FROM để gửi email")
    recipients = list(
        db.scalars(select(NewsletterSubscriber.email).order_by(NewsletterSubscriber.id)).all()
    )
    if not recipients:
        return DetailResponse(detail="Chưa có người đăng ký nhận tin")

    campaign = EmailCampaign(
        subject=data.subject.strip(),
        body=data.body.strip(),
        recipient_count=len(recipients),
        status="sending",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    background_tasks.add_task(
        email_service.send_campaign_background,
        campaign.id,
        data.subject,
        data.body,
        recipients,
    )
    return DetailResponse(detail=f"Đã bắt đầu gửi email marketing tới {len(recipients)} người nhận")


@admin_router.get("/subscribers", response_model=SubscriberListResponse)
def list_subscribers(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100, description="Tìm theo email")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    stmt = select(NewsletterSubscriber)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(NewsletterSubscriber.email.ilike(needle))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    subscribers = db.scalars(
        stmt.order_by(desc(NewsletterSubscriber.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return SubscriberListResponse(
        total=total,
        items=[
            SubscriberItem(id=s.id, email=s.email, created_at=s.created_at) for s in subscribers
        ],
    )


@admin_router.delete("/subscribers/{subscriber_id}", response_model=DetailResponse)
def delete_subscriber(subscriber_id: int, db: DbSession):
    subscriber = db.get(NewsletterSubscriber, subscriber_id)
    if not subscriber:
        raise HTTPException(404, "Không tìm thấy người đăng ký nhận tin")
    db.delete(subscriber)
    db.commit()
    return DetailResponse(detail="Đã xóa người đăng ký nhận tin")


@admin_router.get("/campaigns", response_model=CampaignListResponse)
def list_campaigns(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    stmt = select(EmailCampaign)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    campaigns = db.scalars(
        stmt.order_by(desc(EmailCampaign.id)).offset((page - 1) * page_size).limit(page_size)
    ).all()

    return CampaignListResponse(
        total=total,
        items=[
            CampaignItem(
                id=c.id,
                subject=c.subject,
                body=c.body,
                recipient_count=c.recipient_count,
                sent_at=c.sent_at,
                status=c.status,
            )
            for c in campaigns
        ],
    )


@admin_router.post("/preview", response_model=PreviewEmailResponse)
def preview_campaign(data: PreviewEmailRequest):
    _, html_content = email_service.render_campaign_email(
        email="preview@electrohub.vn",
        subject=data.subject,
        body=data.body,
    )
    return PreviewEmailResponse(subject=data.subject, html=html_content)
