"""Payment orchestration shared by routers, checkout and cancellation."""

import re
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cart import CartItem
from app.models.order import Order
from app.models.payment import Payment
from app.models.refund import Refund, utc_now
from app.models.user import User
from app.services.payments import paypal, vnpay
from app.services.payments.base import GatewayOutcome, PaymentGatewayError

SESSIONABLE = {"pending", "failed"}
SETTLED = {"paid", "refund_pending", "refunded"}


class InvalidSignature(Exception):
    pass


class PaymentNotFound(Exception):
    pass


class AmountMismatch(Exception):
    pass


def _txn_ref(order_code: str, attempt: int) -> str:
    # VNPAY wants an alphanumeric reference that is unique within a day.
    stem = re.sub(r"[^0-9A-Za-z]", "", order_code).upper() or "EH"
    return f"{stem}{attempt:02d}"


def create_session(db: Session, order: Order, payment: Payment, ip_addr: str) -> dict:
    settings = get_settings()
    if order.status == "cancelled":
        raise HTTPException(409, "Đơn hàng đã hủy")
    if payment.status not in SESSIONABLE:
        raise HTTPException(409, "Đơn hàng không chờ thanh toán")
    if settings.is_mock_payment:
        return {
            "provider": "mock",
            "url": f"/payments/{order.code}",
            "simulation": True,
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
        }

    provider = payment.method.lower()
    attempt = payment.attempt or 1
    if payment.status == "failed" or payment.txn_ref:
        attempt += 1
    payment.provider = provider
    payment.attempt = attempt
    payment.txn_ref = _txn_ref(order.code, attempt)

    if provider == "vnpay":
        payment.currency = "VND"
        payment.amount_minor = order.total * 100
        db.commit()
        try:
            url = vnpay.build_payment_url(
                settings,
                txn_ref=payment.txn_ref,
                amount_vnd=order.total,
                order_info=f"Thanh toan don hang {order.code}",
                ip_addr=ip_addr,
            )
        except PaymentGatewayError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {
            "provider": "vnpay",
            "url": url,
            "simulation": False,
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
        }

    payment.currency = settings.paypal_currency.upper()
    payment.amount_minor = paypal.vnd_to_usd_minor(settings, order.total)
    db.commit()
    try:
        gateway_order = paypal.create_order(
            settings,
            code=order.code,
            txn_ref=payment.txn_ref,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
        )
    except PaymentGatewayError as exc:
        raise HTTPException(502, str(exc)) from exc
    url = paypal.approve_url(gateway_order)
    if not url:
        raise HTTPException(502, "PayPal không trả liên kết thanh toán")
    payment.provider_order_id = gateway_order.get("id")
    payment.provider_status = gateway_order.get("status")
    payment.raw_payload = gateway_order
    db.commit()
    return {
        "provider": "paypal",
        "url": url,
        "simulation": False,
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
    }


def clear_purchased_items(db: Session, order: Order) -> None:
    """Remove only the bought quantities; items added after checkout stay in the cart."""
    for item in order.items:
        cart_item = db.scalar(
            select(CartItem).where(
                CartItem.user_id == order.user_id,
                CartItem.product_id == item.product_id,
            )
        )
        if cart_item is None:
            continue
        if cart_item.qty <= item.qty:
            db.delete(cart_item)
        else:
            cart_item.qty -= item.qty


def apply_result(
    db: Session,
    payment_id: int,
    outcome: GatewayOutcome,
    *,
    order_id: int | None = None,
) -> str:
    """Apply a provider result once. Returns applied | duplicate | ignored."""
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise PaymentNotFound
    if order_id is not None and payment.order_id != order_id:
        raise PaymentNotFound
    if payment.status in SETTLED:
        return "duplicate" if outcome.status == "paid" else "ignored"
    if (
        payment.amount_minor is not None
        and outcome.amount_minor is not None
        and int(payment.amount_minor) != int(outcome.amount_minor)
    ):
        raise AmountMismatch("Số tiền giao dịch không khớp đơn hàng")
    if (
        payment.currency
        and outcome.currency
        and payment.currency.upper() != outcome.currency.upper()
    ):
        raise AmountMismatch("Đơn vị tiền tệ không khớp đơn hàng")

    if outcome.status == "paid":
        payment.status = "paid"
        payment.paid_at = utc_now()
        order = db.get(Order, payment.order_id)
        if order is not None:
            clear_purchased_items(db, order)
    elif outcome.status == "pending":
        payment.status = "pending"
    elif outcome.status == "failed":
        payment.status = "failed"
    elif outcome.status == "refunded":
        payment.status = "refunded"
    else:
        raise PaymentGatewayError("Trạng thái giao dịch không hợp lệ")

    if outcome.provider_status:
        payment.provider_status = outcome.provider_status
    if outcome.provider_txn_id:
        payment.provider_txn_id = outcome.provider_txn_id
    payment.raw_payload = {**(payment.raw_payload or {}), **(outcome.raw or {})}
    db.commit()
    return "applied"


def apply_vnpay_callback(db: Session, params: dict[str, str]) -> tuple[str, Order]:
    settings = get_settings()
    secret = settings.vnpay_hash_secret
    if not secret or not vnpay.verify_callback(params, secret.get_secret_value()):
        raise InvalidSignature
    if params.get("vnp_TmnCode") != settings.vnpay_tmn_code:
        raise InvalidSignature
    txn_ref = params.get("vnp_TxnRef", "")
    payment = db.scalar(select(Payment).where(Payment.txn_ref == txn_ref))
    if payment is None:
        raise PaymentNotFound
    order = db.get(Order, payment.order_id)
    if order is None:
        raise PaymentNotFound
    if order.status == "cancelled" and params.get("vnp_ResponseCode") == "00":
        raise HTTPException(409, "Đơn hàng đã hủy trước khi thanh toán")
    result = apply_result(db, payment.id, vnpay.outcome_from_callback(params), order_id=order.id)
    db.refresh(order)
    return result, order


def capture_paypal(db: Session, code: str, paypal_order_id: str | None) -> tuple[str, Order]:
    settings = get_settings()
    order = db.scalar(select(Order).where(Order.code == code.strip().upper()).with_for_update())
    if order is None or order.payment is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    payment = order.payment
    if payment.method != "PAYPAL" or payment.provider != "paypal":
        raise HTTPException(409, "Đơn hàng không thanh toán bằng PayPal")
    if (
        paypal_order_id
        and payment.provider_order_id
        and paypal_order_id != payment.provider_order_id
    ):
        raise HTTPException(409, "Mã giao dịch PayPal không khớp")
    paypal_order_id = paypal_order_id or payment.provider_order_id
    if not paypal_order_id:
        raise HTTPException(409, "Chưa có giao dịch PayPal để xác nhận")
    if payment.status in SETTLED:
        return "duplicate", order
    try:
        outcome = paypal.capture_order(settings, paypal_order_id, txn_ref=payment.txn_ref or code)
    except PaymentGatewayError as exc:
        raise HTTPException(502, str(exc)) from exc
    result = apply_result(db, payment.id, outcome, order_id=order.id)
    db.refresh(order)
    return result, order


def find_payment_by_paypal_order(db: Session, paypal_order_id: str) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.provider_order_id == paypal_order_id))


def handle_paypal_webhook(db: Session, event: dict) -> str:
    kind, status, txn_id, amount_minor, currency, paypal_order_id, raw = paypal.webhook_event(event)
    if kind == "ignore":
        return "ignored"
    payment = None
    if paypal_order_id:
        payment = find_payment_by_paypal_order(db, paypal_order_id)
    if payment is None and txn_id:
        payment = db.scalar(select(Payment).where(Payment.provider_txn_id == txn_id))
    if payment is None:
        return "ignored"

    if kind == "refund":
        payment.status = "refunded"
        payment.provider_status = status
        payment.raw_payload = {**(payment.raw_payload or {}), **raw}
        refund = db.scalar(select(Refund).where(Refund.payment_id == payment.id))
        if refund is not None:
            refund.status = "succeeded"
            refund.provider_refund_id = txn_id
            refund.raw_payload = {**(refund.raw_payload or {}), **raw}
            refund.updated_at = utc_now()
        db.commit()
        return "applied"

    outcome = GatewayOutcome(
        status=status,
        provider_status=str(raw.get("status") or status),
        provider_txn_id=txn_id,
        amount_minor=amount_minor,
        currency=currency,
        raw=raw,
    )
    return apply_result(db, payment.id, outcome, order_id=payment.order_id)


def request_refund(
    db: Session, order: Order, *, requested_by: int | None, reason: str | None
) -> Refund | None:
    """Create the held refund request. Stock is restored separately, immediately."""
    payment = order.payment
    if payment is None or payment.status not in {"paid", "refund_pending"}:
        return None
    existing = db.scalar(select(Refund).where(Refund.order_id == order.id))
    if existing is not None:
        payment.status = "refund_pending"
        return existing
    settings = get_settings()
    now = utc_now()
    refund = Refund(
        order_id=order.id,
        payment_id=payment.id,
        amount=payment.amount_minor if payment.amount_minor is not None else order.total * 100,
        currency=payment.currency or "VND",
        status="scheduled",
        reason=(reason or "").strip()[:255] or None,
        requested_by=requested_by,
        requested_at=now,
        due_at=now + timedelta(hours=settings.refund_hold_hours),
        created_at=now,
        updated_at=now,
    )
    db.add(refund)
    payment.status = "refund_pending"
    db.flush()
    return refund


def refund_for_order(db: Session, order_id: int) -> Refund | None:
    return db.scalar(select(Refund).where(Refund.order_id == order_id))


def list_refunds(
    db: Session, *, status: str | None = None, due_only: bool = False
) -> list[tuple[Refund, Order, Payment]]:
    statement = (
        select(Refund, Order, Payment)
        .join(Order, Order.id == Refund.order_id)
        .join(Payment, Payment.id == Refund.payment_id)
        .order_by(Refund.due_at, Refund.id)
    )
    if status:
        statement = statement.where(Refund.status == status)
    if due_only:
        statement = statement.where(Refund.due_at <= utc_now())
    return list(db.execute(statement).all())


def _vnpay_transaction_date(payment: Payment) -> datetime:
    raw = payment.raw_payload or {}
    value = raw.get("vnp_PayDate")
    if value:
        try:
            return datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(tzinfo=vnpay.GMT7)
        except ValueError:
            pass
    if payment.paid_at:
        return payment.paid_at.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _run_gateway_refund(settings, refund: Refund, payment: Payment) -> GatewayOutcome:
    if settings.is_mock_payment or payment.provider == "mock":
        return GatewayOutcome(
            status="refunded",
            provider_status="SIMULATED",
            provider_txn_id=f"mock-refund-{refund.id}",
            amount_minor=refund.amount,
            currency=refund.currency,
            raw={"simulated": True},
        )
    if payment.provider == "vnpay":
        if not payment.txn_ref or not payment.provider_txn_id:
            raise PaymentGatewayError("Thiếu mã giao dịch VNPAY để hoàn tiền")
        return vnpay.refund(
            settings,
            txn_ref=payment.txn_ref,
            amount_minor=refund.amount,
            transaction_no=payment.provider_txn_id,
            transaction_date=_vnpay_transaction_date(payment),
        )
    if payment.provider == "paypal":
        if not payment.provider_txn_id:
            raise PaymentGatewayError("Thiếu mã capture PayPal để hoàn tiền")
        return paypal.refund(
            settings,
            capture_id=payment.provider_txn_id,
            amount_minor=refund.amount,
            currency=refund.currency,
            request_id=f"refund-{refund.id}",
        )
    raise PaymentGatewayError("Không xác định được cổng hoàn tiền")


def confirm_refund(db: Session, refund_id: int, admin: User) -> Refund:
    settings = get_settings()
    refund = db.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if refund is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu hoàn tiền")
    if refund.status not in {"scheduled", "failed", "processing"}:
        raise HTTPException(409, "Yêu cầu hoàn tiền không thể xác nhận")
    now = utc_now()
    if refund.due_at > now:
        remaining = refund.due_at - now
        raise HTTPException(
            409,
            "Chưa đủ thời gian giữ tiền; còn "
            f"{max(1, int(remaining.total_seconds() // 3600))} giờ nữa",
        )
    payment = db.scalar(select(Payment).where(Payment.id == refund.payment_id).with_for_update())
    if payment is None or payment.status not in {"paid", "refund_pending"}:
        raise HTTPException(409, "Thanh toán không ở trạng thái có thể hoàn tiền")

    refund.status = "processing"
    refund.confirmed_by = admin.id
    refund.confirmed_at = now
    refund.updated_at = now
    db.commit()

    try:
        outcome = _run_gateway_refund(settings, refund, payment)
    except PaymentGatewayError as exc:
        refund.status = "failed"
        refund.raw_payload = {"error": str(exc)}
        refund.updated_at = utc_now()
        db.commit()
        raise HTTPException(502, f"Hoàn tiền thất bại: {exc}") from exc

    refund.raw_payload = outcome.raw
    refund.provider_refund_id = outcome.provider_txn_id
    refund.updated_at = utc_now()
    if outcome.status == "refunded":
        refund.status = "succeeded"
        payment.status = "refunded"
        payment.provider_status = outcome.provider_status or payment.provider_status
        payment.raw_payload = {**(payment.raw_payload or {}), **outcome.raw}
    else:
        refund.status = "failed"
    db.commit()
    db.refresh(refund)
    return refund


def reject_refund(db: Session, refund_id: int, admin: User, reason: str) -> Refund:
    refund = db.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if refund is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu hoàn tiền")
    if refund.status not in {"scheduled", "failed", "processing"}:
        raise HTTPException(409, "Yêu cầu hoàn tiền không thể từ chối")
    payment = db.scalar(select(Payment).where(Payment.id == refund.payment_id))
    if payment is None:
        raise HTTPException(404, "Không tìm thấy thông tin thanh toán")
    refund.status = "rejected"
    refund.reason = (reason or "").strip()[:255] or refund.reason
    refund.confirmed_by = admin.id
    refund.confirmed_at = utc_now()
    refund.updated_at = utc_now()
    # No money moved, so the captured payment returns to its settled state.
    if payment.status == "refund_pending":
        payment.status = "paid"
    db.commit()
    db.refresh(refund)
    return refund
