"""Browser-facing return URLs for VNPAY and PayPal."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.core.deps import DbSession
from app.models.order import Order
from app.services.payments import service as payment_service

router = APIRouter(prefix="/payments", include_in_schema=False)


@router.get("/vnpay/return")
def vnpay_return(request: Request, db: DbSession):
    params = {key: value for key, value in request.query_params.items()}
    try:
        _, order = payment_service.apply_vnpay_callback(db, params)
    except payment_service.InvalidSignature:
        return RedirectResponse("/cart/tracking?payment=invalid", status_code=303)
    except payment_service.PaymentNotFound:
        return RedirectResponse("/cart/tracking?payment=notfound", status_code=303)
    except payment_service.AmountMismatch:
        return RedirectResponse("/cart/tracking?payment=amount", status_code=303)
    except Exception:
        db.rollback()
        return RedirectResponse("/cart/tracking?payment=error", status_code=303)
    return RedirectResponse(f"/payments/{order.code}", status_code=303)


@router.get("/paypal/return")
def paypal_return(
    db: DbSession,
    code: str | None = Query(None, max_length=12),
    token: str | None = Query(None, max_length=64),
):
    if not code and token:
        payment = payment_service.find_payment_by_paypal_order(db, token)
        if payment is not None:
            order = db.get(Order, payment.order_id)
            code = order.code if order is not None else None
    if not code:
        return RedirectResponse("/cart/tracking?payment=notfound", status_code=303)
    try:
        _, order = payment_service.capture_paypal(db, code, token)
    except Exception:
        db.rollback()
        # The payment page reads the authoritative state from the database.
        return RedirectResponse(f"/payments/{code}?payment=error", status_code=303)
    return RedirectResponse(f"/payments/{order.code}", status_code=303)


@router.get("/{code}/paypal/cancel")
def paypal_cancel(code: str, db: DbSession):
    order = db.scalar(select(Order).where(Order.code == code.strip().upper()))
    if order is None:
        return RedirectResponse("/cart/tracking?payment=notfound", status_code=303)
    return RedirectResponse(f"/payments/{order.code}?payment=cancelled", status_code=303)
