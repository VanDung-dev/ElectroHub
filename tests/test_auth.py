from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, create_access_token, verify_password
from app.models.user import User
from tests.conftest import csrf_headers, login, register


def test_register_stores_bcrypt_and_returns_only_public_fields(client, database):
    response = register(client, email="Customer@EXAMPLE.COM", name=" Nguyễn Lê Văn Dũng ")
    assert response.status_code == 201
    assert set(response.json()) == {"id", "email", "name", "role", "created_at"}
    assert response.json()["email"] == "customer@example.com"
    assert response.json()["name"] == "Nguyễn Lê Văn Dũng"
    assert response.json()["role"] == "customer"
    assert ACCESS_COOKIE not in client.cookies
    with Session(database) as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$2b$")
        assert verify_password("ExamplePassword123!", user.password_hash)


def test_duplicate_email_has_one_error_format_and_rolls_back(client):
    assert register(client).status_code == 201
    response = register(client, email="CUSTOMER@example.com")
    assert response.status_code == 409
    assert response.json() == {"detail": "Email đã được sử dụng"}
    assert register(client, email="other@example.com").status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "invalid"},
        {"password": "short"},
        {"password": "x" * 73},
        {"password": "ệ" * 25},
        {"name": "   "},
        {"name": "😀" * 51},
        {"role": "admin"},
    ],
)
def test_register_rejects_invalid_input_without_echoing_secrets(client, overrides):
    response = register(client, **overrides)
    assert response.status_code == 422
    assert response.json() == {"detail": "Dữ liệu không hợp lệ"}


def test_login_cookie_me_logout_and_csrf_rotation(client):
    register(client)
    old_csrf = csrf_headers(client)
    response = login(client)
    assert response.status_code == 200
    cookie = next(c for c in response.headers.get_list("set-cookie") if ACCESS_COOKIE in c)
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert "Max-Age=3600" in cookie
    assert "token" not in response.json()
    assert CSRF_COOKIE not in client.cookies
    assert client.get("/api/v1/auth/me").json()["email"] == "customer@example.com"
    assert client.post("/api/v1/auth/logout", headers=old_csrf).status_code == 403
    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 200
    assert ACCESS_COOKIE not in client.cookies and CSRF_COOKIE not in client.cookies
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("email", ["customer@example.com", "unknown@example.com"])
def test_login_rejects_wrong_credentials(client, email):
    register(client)
    response = login(client, email=email, password="IncorrectPassword123!")
    assert response.status_code == 401
    assert response.json() == {"detail": "Email hoặc mật khẩu không đúng"}
    assert ACCESS_COOKIE not in client.cookies


@pytest.mark.parametrize("token", [None, "forged", "expired", "unknown", "oversized"])
def test_me_rejects_missing_forged_expired_or_unknown_user(client, token):
    if token == "expired":
        token = jwt.encode(
            {
                "sub": "1",
                "iat": datetime.now(UTC) - timedelta(hours=2),
                "exp": datetime.now(UTC) - timedelta(hours=1),
                "jti": "expired",
                "iss": "electrohub",
                "aud": "electrohub-web",
            },
            get_settings().secret_key.get_secret_value(),
            algorithm="HS256",
        )
    elif token == "unknown":
        token = create_access_token(999)
    elif token == "oversized":
        token = create_access_token(2**100)
    if token:
        client.cookies.set(ACCESS_COOKIE, token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_admin_dependency_checks_current_database_role(client, database):
    assert client.get("/admin/products").status_code == 401
    register(client)
    login(client)
    assert client.get("/admin/products").status_code == 403
    with Session(database) as db:
        user = db.scalar(select(User))
        user.role = "admin"
        db.commit()
    assert client.get("/admin/products").status_code == 503  # P4 template is still empty.
    assert client.get("/api/v1/auth/me").json()["role"] == "admin"
    with Session(database) as db:
        db.scalar(select(User)).role = "customer"
        db.commit()
    assert client.get("/admin/products").status_code == 403


@pytest.mark.parametrize("path", ["register", "login", "logout"])
def test_all_auth_mutations_require_csrf(client, path):
    response = client.post(f"/api/v1/auth/{path}", json={})
    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token không hợp lệ"}


def test_csrf_rejects_tampering_and_cross_session_tokens(client):
    first = csrf_headers(client)
    assert csrf_headers(client) == first  # Multiple tabs may reuse the session's token.
    tampered = first["X-CSRF-Token"][:-1] + "z"
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": tampered}).status_code == 403
    client.cookies.set(CSRF_COOKIE, "0" * 64 + "." + "0" * 64)
    assert client.post("/api/v1/auth/logout", headers=first).status_code == 403
    client.cookies.clear()
    assert register(client).status_code == 201
    old = csrf_headers(client)
    assert login(client).status_code == 200
    client.cookies.set(CSRF_COOKIE, old["X-CSRF-Token"])
    assert client.post("/api/v1/auth/logout", headers=old).status_code == 403


def test_secure_cookie_setting(client, monkeypatch):
    register(client)
    client.base_url = "https://testserver"
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    response = login(client)
    assert response.status_code == 200
    assert all("Secure" in cookie for cookie in response.headers.get_list("set-cookie"))


def test_csrf_checks_browser_origin_even_with_valid_signed_token(client):
    headers = csrf_headers(client)
    assert (
        client.post(
            "/api/v1/auth/logout", headers={**headers, "Origin": "https://evil.testserver"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={**headers, "Origin": "http://testserver"}
        ).status_code
        == 200
    )
