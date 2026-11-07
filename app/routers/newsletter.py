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
    SubscribeRequest,
    SubscriberItem,
    SubscriberListResponse,
    TemplateItem,
    TemplateListResponse,
)
from app.services import email_service

router = APIRouter(prefix="/api/v1/newsletter", tags=["newsletter"])
# ponytail: alias to email_service instead of maintaining a wrapper function
_unsubscribe_token = email_service.unsubscribe_token
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
    # ponytail: call email_service directly without single-line wrapper function
    expected = email_service.unsubscribe_token(email).rsplit("|", 1)[1]
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
        stmt.order_by(desc(NewsletterSubscriber.id)).offset((page - 1) * page_size).limit(page_size)
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


CAMPAIGN_PRESETS: list[dict[str, str]] = [
    {
        "id": "flash_sale",
        "name": "⚡ Khuyến mãi / Flash Sale cuối tuần",
        "subject": "⚡ [ElectroHub] FLASH SALE CUỐI TUẦN: Giảm tới 30% linh kiện & thiết bị điện tử!",
        "body": (
            "Kính gửi quý khách hàng,\n\n"
            "Cuối tuần này, ElectroHub mang đến chương trình FLASH SALE bùng nổ với hàng loạt ưu đãi hấp dẫn dành riêng cho cộng đồng kỹ thuật & DIY:\n\n"
            "🔥 GIẢM TỚI 30% các dòng vi điều khiển: ESP32-WROOM, Arduino Uno R3, STM32 Blue Pill.\n"
            "🔥 ĐỒNG GIÁ linh kiện cảm biến: Cảm biến nhiệt ẩm DHT11, cảm biến khoảng cách HC-SR04, module Relay 5V.\n"
            "🔥 MIỄN PHÍ VẬN CHUYỂN cho tất cả đơn hàng từ 300.000₫.\n\n"
            "⏰ Thời gian áp dụng: Từ Thứ Sáu đến hết Chủ Nhật tuần này.\n"
            "Số lượng linh kiện khuyến mãi có hạn, hãy nhanh tay đặt hàng ngay hôm nay để nhận ưu đãi!\n\n"
            "ElectroHub rất hân hạnh được đồng hành cùng những dự án sáng tạo của bạn."
        ),
    },
    {
        "id": "new_arrival",
        "name": "🚀 Hàng mới về / Sản phẩm mới",
        "subject": "🚀 [ElectroHub] HÀNG MỚI VỀ: Khám phá các dòng module vi điều khiển & cảm biến thế hệ mới!",
        "body": (
            "Chào bạn,\n\n"
            "ElectroHub xin thông báo kho hàng vừa cập bến các sản phẩm và linh kiện điện tử mới nhất phục vụ cho các dự án IoT, Robotics và tự động hóa:\n\n"
            "✨ Module ESP32-S3 Dual-Core hiệu năng cao, tích hợp AI & kết nối không dây mạnh mẽ.\n"
            "✨ Mạch sạc nhanh Type-C và module hạ áp Buck đa năng thế hệ mới.\n"
            "✨ Cảm biến môi trường độ chính xác cao BME280 và module đo dòng INA219.\n\n"
            "Tất cả sản phẩm đều được kiểm tra chất lượng kỹ lưỡng và có sẵn số lượng lớn tại kho.\n\n"
            "👉 Xem ngay danh mục sản phẩm mới để không bỏ lỡ linh kiện cho dự án của bạn!"
        ),
    },
    {
        "id": "voucher_gift",
        "name": "🎁 Tặng mã giảm giá tri ân khách hàng",
        "subject": "🎁 [ElectroHub] TẶNG BẠN VOUCHER ĐẶC QUYỀN: Giảm ngay 15% cho đơn hàng tiếp theo!",
        "body": (
            "Kính gửi quý khách hàng thân thiết,\n\n"
            "Để cảm ơn sự tin tưởng và đồng hành của bạn cùng ElectroHub trong suốt thời gian qua, chúng tôi xin gửi tặng bạn món quà tri ân đặc biệt:\n\n"
            "🎟 Mã giảm giá: TRIAN2026\n"
            "💰 Ưu đãi: Giảm 15% trên tổng giá trị đơn hàng (tối đa 100.000₫).\n"
            "📅 Hạn sử dụng: Đến hết ngày 30 của tháng này.\n\n"
            "Mã ưu đãi áp dụng cho tất cả sản phẩm đang có tại website ElectroHub: từ bo mạch phát triển, cảm biến, linh kiện thụ động đến phụ kiện nguồn.\n\n"
            "Hãy nhập mã TRIAN2026 tại bước giỏ hàng hoặc thanh toán để nhận ưu đãi nhé!"
        ),
    },
    {
        "id": "store_notice",
        "name": "📢 Thông báo cửa hàng / Dịch vụ & Bảo hành",
        "subject": "📢 [ElectroHub] THÔNG BÁO: Cập nhật chính sách giao hàng và bảo hành linh kiện",
        "body": (
            "Kính gửi quý khách hàng,\n\n"
            "Nhằm nâng cao chất lượng dịch vụ và mang lại trải nghiệm mua sắm tốt nhất, ElectroHub xin trân trọng thông báo một số cập nhật mới:\n\n"
            "📦 Thời gian giao hàng: Giao hàng hỏa tốc trong 2-4 giờ tại nội thành và 1-3 ngày trên toàn quốc.\n"
            "🛡 Chính sách bảo hành: Hỗ trợ 1 đổi 1 trong vòng 7 ngày đối với các bo mạch, module phát hiện lỗi từ nhà sản xuất.\n"
            "💬 Kênh hỗ trợ trực tuyến: Đội ngũ kỹ thuật hỗ trợ tư vấn linh kiện và sơ đồ đấu nối 24/7.\n\n"
            "Mọi thắc mắc cần hỗ trợ, quý khách vui lòng liên hệ qua fanpage hoặc hotline của ElectroHub.\n\n"
            "Trân trọng cảm ơn sự đồng hành của quý khách!"
        ),
    },
]


@admin_router.get("/templates", response_model=TemplateListResponse)
def get_campaign_templates():
    return TemplateListResponse(items=[TemplateItem(**t) for t in CAMPAIGN_PRESETS])
