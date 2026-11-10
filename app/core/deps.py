import hmac
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, decode_access_token, valid_csrf
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]
access_cookie = APIKeyCookie(name=ACCESS_COOKIE, auto_error=False)

# PayPal posts without a browser CSRF token. Exempt only this exact path; VNPAY IPN
# is a GET and is already covered by the method check below.
PUBLIC_CALLBACK_PATHS = {"/api/v1/payments/paypal/webhook"}


async def require_csrf(
    request: Request,
    csrf_header: Annotated[
        str | None,
        Header(
            alias="X-CSRF-Token",
            description="Token từ GET /api/v1/auth/csrf; cần cho POST/PUT/PATCH/DELETE",
        ),
    ] = None,
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.url.path in PUBLIC_CALLBACK_PATHS:
        return
    origin = request.headers.get("origin")
    allowed_origins = {str(request.base_url).rstrip("/"), get_settings().base_url}
    if origin and origin.rstrip("/") not in allowed_origins:
        raise HTTPException(403, "Origin không hợp lệ")
    token = csrf_header or ""
    if not token and request.headers.get("content-type", "").split(";")[0] in {
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    }:
        token = (await request.form()).get("csrf_token", "")
    if (
        not isinstance(token, str)
        or not valid_csrf(token, request)
        or not hmac.compare_digest(token.encode(), request.cookies.get(CSRF_COOKIE, "").encode())
    ):
        raise HTTPException(403, "CSRF token không hợp lệ")


def get_current_user(db: DbSession, token: Annotated[str | None, Security(access_cookie)]) -> User:
    try:
        user_id = decode_access_token(token or "")
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, "Bạn cần đăng nhập") from None
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Bạn cần đăng nhập")
    if user.is_blocked:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Bạn không có quyền admin")
    return user


def require_staff(user: CurrentUser) -> User:
    if user.role not in {"staff", "admin"}:
        raise HTTPException(403, "Bạn không có quyền nhân viên")
    return user
