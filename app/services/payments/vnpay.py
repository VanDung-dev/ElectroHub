"""VNPAY sandbox adapter: URL signing, callback verification and refunds."""

import hashlib
import hmac
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import httpx

from app.core.config import Settings
from app.services.payments.base import GatewayOutcome, PaymentGatewayError

VNPAY_VERSION = "2.1.0"
GMT7 = timezone(timedelta(hours=7))
_SAFE_TEXT = re.compile(r"[^A-Za-z0-9 ]+")


def _now_gmt7() -> datetime:
    return datetime.now(GMT7)


def _format_time(value: datetime) -> str:
    return value.astimezone(GMT7).strftime("%Y%m%d%H%M%S")


def normalize_order_info(value: str, limit: int = 255) -> str:
    """VNPAY rejects accented/special characters in vnp_OrderInfo."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"\s+", " ", _SAFE_TEXT.sub("", ascii_text)).strip()
    return (cleaned or "Thanh toan don hang ElectroHub")[:limit]


def hash_data(params: dict[str, str]) -> str:
    items = sorted((key, value) for key, value in params.items() if value not in (None, ""))
    return "&".join(f"{quote_plus(key)}={quote_plus(str(value))}" for key, value in items)


def sign_params(params: dict[str, str], secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), hash_data(params).encode("utf-8"), hashlib.sha512
    ).hexdigest()


def verify_callback(params: dict[str, str], secret: str) -> bool:
    received = params.get("vnp_SecureHash", "")
    unsigned = {
        key: value
        for key, value in params.items()
        if key not in {"vnp_SecureHash", "vnp_SecureHashType"}
    }
    return bool(received) and hmac.compare_digest(received.lower(), sign_params(unsigned, secret))


def callback_params(params: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in params.items() if key.startswith("vnp_")}


def build_payment_url(
    settings: Settings,
    *,
    txn_ref: str,
    amount_vnd: int,
    order_info: str,
    ip_addr: str,
) -> str:
    if amount_vnd <= 0:
        raise PaymentGatewayError("Số tiền thanh toán không hợp lệ")
    created = _now_gmt7()
    params = {
        "vnp_Version": VNPAY_VERSION,
        "vnp_Command": "pay",
        "vnp_TmnCode": settings.vnpay_tmn_code or "",
        "vnp_Amount": str(int(amount_vnd) * 100),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": normalize_order_info(order_info),
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_IpAddr": ip_addr or "127.0.0.1",
        "vnp_CreateDate": _format_time(created),
        "vnp_ExpireDate": _format_time(created + timedelta(minutes=settings.vnpay_expire_minutes)),
        "vnp_ReturnUrl": settings.vnpay_return_url,
    }
    secret = settings.vnpay_hash_secret.get_secret_value() if settings.vnpay_hash_secret else ""
    data = hash_data(params)
    signature = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha512).hexdigest()
    return f"{settings.vnpay_pay_url}?{data}&vnp_SecureHash={signature}"


def outcome_from_callback(params: dict[str, str]) -> GatewayOutcome:
    response_code = params.get("vnp_ResponseCode", "")
    transaction_status = params.get("vnp_TransactionStatus", "")
    paid = response_code == "00" and transaction_status == "00"
    amount = params.get("vnp_Amount")
    return GatewayOutcome(
        status="paid" if paid else "failed",
        provider_status=transaction_status or response_code or None,
        provider_txn_id=params.get("vnp_TransactionNo") or None,
        amount_minor=int(amount) if amount and amount.isdigit() else None,
        currency="VND",
        raw=dict(params),
    )


def _post(settings: Settings, payload: dict) -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(settings.vnpay_api_url, json=payload)
    except httpx.HTTPError as exc:
        raise PaymentGatewayError("Không kết nối được VNPAY") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise PaymentGatewayError("VNPAY trả dữ liệu không hợp lệ") from exc
    if response.status_code >= 400:
        raise PaymentGatewayError(
            f"VNPAY từ chối yêu cầu ({data.get('vnp_Message') or response.status_code})"
        )
    return data


def _request_id(prefix: str) -> str:
    return f"{prefix}{_now_gmt7().strftime('%H%M%S')}{secrets.token_hex(4)}"


def _querydr_signature(payload: dict[str, str]) -> str:
    return "|".join(
        payload[key]
        for key in (
            "vnp_RequestId",
            "vnp_Version",
            "vnp_Command",
            "vnp_TmnCode",
            "vnp_TxnRef",
            "vnp_TransactionDate",
            "vnp_CreateDate",
            "vnp_IpAddr",
            "vnp_OrderInfo",
        )
    )


def _refund_signature(payload: dict[str, str]) -> str:
    return "|".join(
        payload[key]
        for key in (
            "vnp_RequestId",
            "vnp_Version",
            "vnp_Command",
            "vnp_TmnCode",
            "vnp_TransactionType",
            "vnp_TxnRef",
            "vnp_Amount",
            "vnp_TransactionNo",
            "vnp_TransactionDate",
            "vnp_CreateBy",
            "vnp_CreateDate",
            "vnp_IpAddr",
            "vnp_OrderInfo",
        )
    )


def _signed_payload(settings: Settings, payload: dict[str, str], data: str) -> dict[str, str]:
    secret = settings.vnpay_hash_secret.get_secret_value() if settings.vnpay_hash_secret else ""
    payload["vnp_SecureHash"] = hmac.new(
        secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha512
    ).hexdigest()
    return payload


def query_transaction(
    settings: Settings, *, txn_ref: str, transaction_date: datetime, ip_addr: str = "127.0.0.1"
) -> dict:
    now = _now_gmt7()
    payload = {
        "vnp_RequestId": _request_id("QR"),
        "vnp_Version": VNPAY_VERSION,
        "vnp_Command": "querydr",
        "vnp_TmnCode": settings.vnpay_tmn_code or "",
        "vnp_TxnRef": txn_ref,
        "vnp_TransactionDate": _format_time(transaction_date),
        "vnp_CreateDate": _format_time(now),
        "vnp_IpAddr": ip_addr,
        "vnp_OrderInfo": "Doi soat giao dich ElectroHub",
    }
    return _post(settings, _signed_payload(settings, payload, _querydr_signature(payload)))


def refund(
    settings: Settings,
    *,
    txn_ref: str,
    amount_minor: int,
    transaction_no: str,
    transaction_date: datetime,
    ip_addr: str = "127.0.0.1",
    created_by: str = "ElectroHub",
) -> GatewayOutcome:
    now = _now_gmt7()
    payload = {
        "vnp_RequestId": _request_id("RF"),
        "vnp_Version": VNPAY_VERSION,
        "vnp_Command": "refund",
        "vnp_TmnCode": settings.vnpay_tmn_code or "",
        # 02 = full refund, 03 = partial refund.
        "vnp_TransactionType": "02",
        "vnp_TxnRef": txn_ref,
        "vnp_Amount": str(int(amount_minor)),
        "vnp_TransactionNo": transaction_no,
        "vnp_TransactionDate": _format_time(transaction_date),
        "vnp_CreateBy": created_by,
        "vnp_CreateDate": _format_time(now),
        "vnp_IpAddr": ip_addr,
        "vnp_OrderInfo": normalize_order_info(f"Hoan tien don {txn_ref}"),
    }
    data = _post(settings, _signed_payload(settings, payload, _refund_signature(payload)))
    code = str(data.get("vnp_ResponseCode", ""))
    succeeded = code == "00"
    return GatewayOutcome(
        status="refunded" if succeeded else "failed",
        provider_status=code or None,
        provider_txn_id=str(data.get("vnp_TransactionNo") or transaction_no),
        amount_minor=amount_minor,
        currency="VND",
        raw=data,
    )
