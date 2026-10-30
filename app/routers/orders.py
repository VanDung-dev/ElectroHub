from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Query, Security
from fastapi.security import APIKeyCookie

from app.core.deps import CurrentUser, DbSession
from app.core.security import ACCESS_COOKIE, decode_access_token
from app.models.user import User
from app.schemas.auth import DetailResponse
from app.schemas.cart import CheckoutRequest, OrderListResponse, OrderResponse, PayRequest
from app.services import order_service

router = APIRouter(
    prefix="/api/v1/orders",
    tags=["orders"],
    responses={
        400: {"model": DetailResponse},
        401: {"model": DetailResponse},
        404: {"model": DetailResponse},
        409: {"model": DetailResponse},
    },
)

_optional_cookie = APIKeyCookie(name=ACCESS_COOKIE, auto_error=False)


def _optional_user(
    db: DbSession, token: Annotated[str | None, Security(_optional_cookie)]
) -> User | None:
    # Tracking stays public with code + phone; a valid session skips the phone check.
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None
    return db.get(User, user_id)


OptionalUser = Annotated[User | None, Depends(_optional_user)]


@router.post("", response_model=OrderResponse, status_code=201)
def checkout(data: CheckoutRequest, user: CurrentUser, db: DbSession):
    """Tạo đơn từ giỏ trong một transaction: trừ kho, trừ voucher, xóa giỏ."""
    return order_service.checkout(db, user, data)


@router.get("", response_model=OrderListResponse)
def list_orders(
    user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """Lịch sử đơn của chính người dùng đang đăng nhập."""
    return order_service.list_user_orders(db, user.id, page, page_size)


@router.get("/{code}", response_model=OrderResponse)
def track_order(
    code: str,
    user: OptionalUser,
    db: DbSession,
    phone: str | None = Query(None, pattern=r"^0\d{9}$"),
):
    """Tra cứu công khai bằng mã đơn + số điện thoại; owner/admin không cần số điện thoại."""
    return order_service.get_order_for_tracking(db, code, user, phone)


@router.post("/{code}/pay", response_model=OrderResponse)
def pay_order(code: str, data: PayRequest, user: CurrentUser, db: DbSession):
    """COD xác nhận (chờ thu khi giao) hoặc thanh toán chuyển khoản mock."""
    return order_service.pay_order(db, user.id, code, data)
