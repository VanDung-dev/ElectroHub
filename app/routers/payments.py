from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from app.core.deps import CurrentUser, DbSession
from app.models.order import Order
from app.models.payment import Payment
from app.schemas.cart import OrderPayment

router = APIRouter(prefix="/api/v1/payments", tags=["payments-demo"])


class PaymentSession(BaseModel):
    url: str


class PaymentDetails(OrderPayment):
    code: str
    total: int
    simulation: Literal[True] = True


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["paid", "failed"]


def _owned_payment(code: str, user_id: int, db: DbSession) -> tuple[Order, Payment]:
    order = db.scalar(select(Order).where(Order.code == code, Order.user_id == user_id))
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None:
        raise HTTPException(404, "Không có thông tin thanh toán")
    if not (payment.payload or {}).get("simulation"):
        raise HTTPException(409, "Đơn hàng này không thuộc luồng thanh toán mô phỏng")
    return order, payment


def _details(order: Order, payment: Payment) -> PaymentDetails:
    return PaymentDetails(
        code=order.code, total=order.total, method=payment.method, status=payment.status
    )


@router.get("/orders/{code}", response_model=PaymentDetails)
def payment_details(code: str, user: CurrentUser, db: DbSession):
    order, payment = _owned_payment(code, user.id, db)
    return _details(order, payment)


@router.post("/orders/{code}/session", response_model=PaymentSession)
def create_payment_session(code: str, user: CurrentUser, db: DbSession):
    order, payment = _owned_payment(code, user.id, db)
    if order.status == "cancelled" or payment.status not in {"pending", "failed"}:
        raise HTTPException(409, "Đơn hàng không chờ thanh toán")
    return PaymentSession(url=f"/payments/{order.code}")


@router.post("/orders/{code}/simulate", response_model=PaymentDetails)
def simulate_payment(code: str, data: SimulationRequest, user: CurrentUser, db: DbSession):
    order, payment = _owned_payment(code, user.id, db)
    if order.status == "cancelled" or payment.status == "refunded":
        raise HTTPException(409, "Đơn hàng đã hủy hoặc hoàn tiền")
    if payment.status == "paid":
        if data.result == "paid":
            return _details(order, payment)
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
    return _details(order, payment)
