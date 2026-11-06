import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.models.order import Order
from app.models.payment import Payment
from app.schemas.payment import PaymentDetailsOut, PaymentSessionOut
from app.schemas.refund import RefundInfo
from app.services.payments import paypal
from app.services.payments import service as payment_service
from app.services.payments.base import PaymentGatewayError

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["paid", "failed"]


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "127.0.0.1"


def _owned_payment(code: str, user_id: int, db: DbSession) -> tuple[Order, Payment]:
    order = db.scalar(select(Order).where(Order.code == code, Order.user_id == user_id))
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None:
        raise HTTPException(404, "Không có thông tin thanh toán")
    return order, payment


def _details(db: DbSession, order: Order, payment: Payment) -> PaymentDetailsOut:
    refund = payment_service.refund_for_order(db, order.id)
    return PaymentDetailsOut(
        code=order.code,
        total=order.total,
        method=payment.method,
        status=payment.status,
        provider=payment.provider,
        currency=payment.currency,
        amount_minor=payment.amount_minor,
        attempt=payment.attempt,
        simulation=bool((payment.payload or {}).get("simulation")),
        refund=(
            RefundInfo(
                id=refund.id,
                status=refund.status,
                amount=refund.amount,
                currency=refund.currency,
                reason=refund.reason,
                requested_at=refund.requested_at,
                due_at=refund.due_at,
                confirmed_at=refund.confirmed_at,
                provider_refund_id=refund.provider_refund_id,
            )
            if refund is not None
            else None
        ),
    )


@router.get("/orders/{code}", response_model=PaymentDetailsOut)
def payment_details(code: str, user: CurrentUser, db: DbSession):
    order, payment = _owned_payment(code, user.id, db)
    return _details(db, order, payment)


@router.post("/orders/{code}/session", response_model=PaymentSessionOut)
def create_payment_session(code: str, request: Request, user: CurrentUser, db: DbSession):
    order, payment = _owned_payment(code, user.id, db)
    session = payment_service.create_session(db, order, payment, _client_ip(request))
    return PaymentSessionOut(**session)


@router.post("/orders/{code}/simulate", response_model=PaymentDetailsOut)
def simulate_payment(code: str, data: SimulationRequest, user: CurrentUser, db: DbSession):
    """Only available when PAYMENT_MODE=mock; sandbox traffic must use the gateway."""
    if not get_settings().is_mock_payment:
        raise HTTPException(409, "Thanh toán mô phỏng đã tắt ở chế độ sandbox")
    order, payment = _owned_payment(code, user.id, db)
    if order.status == "cancelled" or payment.status in {"refund_pending", "refunded"}:
        raise HTTPException(409, "Đơn hàng đã hủy hoặc hoàn tiền")
    if payment.status == "paid":
        if data.result == "paid":
            return _details(db, order, payment)
        raise HTTPException(409, "Đơn hàng đã thanh toán thành công")
    result = db.execute(
        update(Payment)
        .where(
            Payment.id == payment.id,
            Payment.status.in_(("pending", "failed")),
            Payment.order_id.in_(select(Order.id).where(Order.status != "cancelled")),
        )
        .values(status=data.result)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Trạng thái đơn hàng đã thay đổi; vui lòng tải lại")
    db.commit()
    db.refresh(payment)
    return _details(db, order, payment)


@router.get("/vnpay/ipn", include_in_schema=False)
def vnpay_ipn(request: Request, db: DbSession):
    params = {key: value for key, value in request.query_params.items()}
    try:
        result, _ = payment_service.apply_vnpay_callback(db, params)
    except payment_service.InvalidSignature:
        return {"RspCode": "97", "Message": "Invalid signature"}
    except payment_service.PaymentNotFound:
        return {"RspCode": "01", "Message": "Order not found"}
    except payment_service.AmountMismatch:
        return {"RspCode": "04", "Message": "Invalid amount"}
    except HTTPException:
        return {"RspCode": "99", "Message": "Unknown error"}
    except Exception:
        db.rollback()
        return {"RspCode": "99", "Message": "Unknown error"}
    if result == "duplicate":
        return {"RspCode": "02", "Message": "Order already confirmed"}
    return {"RspCode": "00", "Message": "Confirm Success"}


@router.post("/paypal/webhook", include_in_schema=False)
async def paypal_webhook(request: Request, db: DbSession):
    settings = get_settings()
    if settings.is_mock_payment or not settings.paypal_webhook_id:
        return {"status": "ignored"}
    try:
        event = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Payload không hợp lệ") from None
    headers = {key.lower(): value for key, value in request.headers.items()}
    try:
        verified = paypal.verify_webhook(settings, headers, event)
    except PaymentGatewayError as exc:
        raise HTTPException(502, f"Không xác minh được webhook: {exc}") from exc
    if not verified:
        raise HTTPException(400, "Chữ ký webhook không hợp lệ")
    result = payment_service.handle_paypal_webhook(db, event)
    return {"status": result}
