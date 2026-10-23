import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Request, Response

from app.core.config import get_settings

ACCESS_COOKIE = "electrohub_access"
CSRF_COOKIE = "electrohub_csrf"
CSRF_PATTERN = re.compile(r"[0-9a-f]{64}\.[0-9a-f]{64}")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, UnicodeError):
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "jti": secrets.token_hex(16),
            "iss": "electrohub",
            "aud": "electrohub-web",
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str) -> int:
    claims = jwt.decode(
        token,
        get_settings().secret_key.get_secret_value(),
        algorithms=["HS256"],
        issuer="electrohub",
        audience="electrohub-web",
        options={"require": ["sub", "iat", "exp", "jti"]},
    )
    user_id = int(claims["sub"])
    if not 1 <= user_id <= 2147483647:
        raise ValueError("Invalid user ID")
    return user_id


def set_cookie(response: Response, name: str, value: str) -> None:
    settings = get_settings()
    response.set_cookie(
        name,
        value,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        name, path="/", httponly=True, secure=get_settings().cookie_secure, samesite="lax"
    )


def csrf_signature(nonce: str, access_token: str) -> str:
    return hmac.new(
        get_settings().secret_key.get_secret_value().encode(),
        f"csrf:{nonce}:{access_token}".encode(),
        hashlib.sha256,
    ).hexdigest()


def valid_csrf(token: str, request: Request) -> bool:
    if not CSRF_PATTERN.fullmatch(token):
        return False
    nonce, signature = token.split(".")
    return hmac.compare_digest(
        signature, csrf_signature(nonce, request.cookies.get(ACCESS_COOKIE, ""))
    )


def issue_csrf(request: Request, response: Response) -> str:
    token = request.cookies.get(CSRF_COOKIE, "")
    if not valid_csrf(token, request):
        nonce = secrets.token_hex(32)
        token = f"{nonce}.{csrf_signature(nonce, request.cookies.get(ACCESS_COOKIE, ''))}"
    set_cookie(response, CSRF_COOKIE, token)
    return token
