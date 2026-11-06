"""PayPal sandbox adapter: OAuth, orders, capture, webhooks and refunds."""

import threading
import time
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.core.config import Settings
from app.services.payments.base import GatewayOutcome, PaymentGatewayError

_token_lock = threading.Lock()
_token_cache: dict[str, tuple[str, float]] = {}


def vnd_to_usd_minor(settings: Settings, total_vnd: int) -> int:
    """Convert integer VND to USD cents using a configured fixed rate."""
    value = (Decimal(total_vnd) / settings.paypal_vnd_per_usd).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if value <= 0:
        value = Decimal("0.01")
    return int(value * 100)


def minor_to_value(amount_minor: int) -> str:
    return f"{Decimal(amount_minor) / 100:.2f}"


def _amount_minor(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    return int(Decimal(str(value)) * 100)


def access_token(settings: Settings, *, force: bool = False) -> str:
    client_id = settings.paypal_client_id or ""
    secret = (
        settings.paypal_client_secret.get_secret_value() if settings.paypal_client_secret else ""
    )
    cache_key = f"{settings.paypal_api_base}|{client_id}"
    with _token_lock:
        cached = _token_cache.get(cache_key)
        if cached and not force and cached[1] > time.monotonic():
            return cached[0]
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    f"{settings.paypal_api_base.rstrip('/')}/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    auth=(client_id, secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            raise PaymentGatewayError("Không kết nối được PayPal") from exc
        if response.status_code >= 400:
            raise PaymentGatewayError("PayPal từ chối thông tin xác thực")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise PaymentGatewayError("PayPal không trả access token")
        # Refresh a minute early to avoid using a token that expires mid-request.
        expires_in = int(payload.get("expires_in", 300))
        _token_cache[cache_key] = (token, time.monotonic() + expires_in - 60)
        return token


def _request(
    settings: Settings,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    request_id: str | None = None,
) -> dict:
    base = settings.paypal_api_base.rstrip("/")
    for attempt in range(2):
        token = access_token(settings, force=attempt == 1)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        try:
            with httpx.Client(timeout=25) as client:
                response = client.request(method, f"{base}{path}", json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError("Không kết nối được PayPal") from exc
        if response.status_code == 401 and attempt == 0:
            continue
        try:
            data = response.json()
        except ValueError as exc:
            raise PaymentGatewayError("PayPal trả dữ liệu không hợp lệ") from exc
        if response.status_code >= 400:
            debug_id = data.get("debug_id")
            detail = data.get("message") or data.get("name") or "PayPal từ chối yêu cầu"
            raise PaymentGatewayError(str(detail), debug_id=debug_id)
        return data
    raise PaymentGatewayError("Không xác thực được PayPal")


def create_order(
    settings: Settings,
    *,
    code: str,
    txn_ref: str,
    amount_minor: int,
    currency: str,
) -> dict:
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": code,
                "invoice_id": txn_ref,
                "description": f"ElectroHub order {code}",
                "amount": {
                    "currency_code": currency,
                    "value": minor_to_value(amount_minor),
                },
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "return_url": f"{settings.base_url}/payments/paypal/return?code={code}",
                    "cancel_url": f"{settings.base_url}/payments/{code}?payment=cancelled",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                }
            }
        },
    }
    return _request(
        settings,
        "POST",
        "/v2/checkout/orders",
        json=payload,
        request_id=f"create-{txn_ref}",
    )


def approve_url(order: dict) -> str | None:
    for link in order.get("links", []):
        if link.get("rel") in {"payer-action", "approve"}:
            return link.get("href")
    return None


def _capture_fields(data: dict) -> tuple[str | None, int | None, str | None]:
    units = data.get("purchase_units") or []
    unit = units[0] if units else {}
    captures = (unit.get("payments") or {}).get("captures") or []
    capture = captures[0] if captures else {}
    amount = capture.get("amount") or unit.get("amount") or {}
    return (
        capture.get("id"),
        _amount_minor(amount.get("value")),
        amount.get("currency_code"),
    )


def outcome_from_order(data: dict) -> GatewayOutcome:
    status = str(data.get("status") or "")
    capture_id, amount_minor, currency = _capture_fields(data)
    units = data.get("purchase_units") or []
    capture_status = None
    if units:
        captures = (units[0].get("payments") or {}).get("captures") or []
        if captures:
            capture_status = captures[0].get("status")
    if status == "COMPLETED":
        local = "paid"
    elif status in {"PENDING", "APPROVED", "CREATED", "SAVED"}:
        local = "pending"
    else:
        local = "failed"
    return GatewayOutcome(
        status=local,
        provider_status=capture_status or status or None,
        provider_txn_id=capture_id,
        amount_minor=amount_minor,
        currency=currency,
        raw=data,
    )


def get_order(settings: Settings, paypal_order_id: str) -> dict:
    """Read the authoritative gateway state; used when capture itself fails."""
    return _request(settings, "GET", f"/v2/checkout/orders/{paypal_order_id}")


def capture_order(settings: Settings, paypal_order_id: str, *, txn_ref: str) -> GatewayOutcome:
    data = _request(
        settings,
        "POST",
        f"/v2/checkout/orders/{paypal_order_id}/capture",
        json={},
        request_id=f"capture-{txn_ref}",
    )
    return outcome_from_order(data)


def read_outcome(settings: Settings, paypal_order_id: str) -> GatewayOutcome:
    return outcome_from_order(get_order(settings, paypal_order_id))


def verify_webhook(settings: Settings, headers: dict[str, str], event: dict) -> bool:
    if not settings.paypal_webhook_id:
        return False
    payload = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "webhook_id": settings.paypal_webhook_id,
        "webhook_event": event,
    }
    if not all(
        payload[key]
        for key in (
            "auth_algo",
            "cert_url",
            "transmission_id",
            "transmission_sig",
            "transmission_time",
        )
    ):
        return False
    data = _request(settings, "POST", "/v1/notifications/verify-webhook-signature", json=payload)
    return data.get("verification_status") == "SUCCESS"


def webhook_event(
    event: dict,
) -> tuple[str, str, str | None, int | None, str | None, str | None, dict]:
    """Return (kind, local_status, txn_id, amount_minor, currency, order_id, raw)."""
    event_type = str(event.get("event_type") or "")
    resource = event.get("resource") or {}
    related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    paypal_order_id = related.get("order_id")
    amount = resource.get("amount") or {}
    txn_id = resource.get("id")
    amount_minor = _amount_minor(amount.get("value"))
    currency = amount.get("currency_code")

    if event_type in {"PAYMENT.CAPTURE.COMPLETED"}:
        return "payment", "paid", txn_id, amount_minor, currency, paypal_order_id, resource
    if event_type in {"PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"}:
        return "payment", "failed", txn_id, amount_minor, currency, paypal_order_id, resource
    if event_type in {"PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"}:
        return "refund", "refunded", txn_id, amount_minor, currency, paypal_order_id, resource
    if event_type == "CHECKOUT.PAYMENT-APPROVAL.REVERSED":
        return (
            "payment",
            "failed",
            None,
            None,
            None,
            resource.get("id") or paypal_order_id,
            resource,
        )
    return "ignore", "", None, None, None, paypal_order_id, resource


def refund(
    settings: Settings,
    *,
    capture_id: str,
    amount_minor: int,
    currency: str,
    request_id: str,
) -> GatewayOutcome:
    payload = {"amount": {"currency_code": currency, "value": minor_to_value(amount_minor)}}
    data = _request(
        settings,
        "POST",
        f"/v2/payments/captures/{capture_id}/refund",
        json=payload,
        request_id=request_id,
    )
    status = str(data.get("status") or "")
    local = "refunded" if status in {"COMPLETED", "PENDING"} else "failed"
    return GatewayOutcome(
        status=local,
        provider_status=status or None,
        provider_txn_id=data.get("id"),
        amount_minor=amount_minor,
        currency=currency,
        raw=data,
    )
