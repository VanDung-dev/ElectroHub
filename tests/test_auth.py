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
    assert client.get("/admin/products").status_code == 200
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


@pytest.mark.parametrize(
    "role,landing",
    [("customer", "/account/orders"), ("staff", "/staff/orders"), ("admin", "/manager")],
)
def test_each_role_can_login_and_open_its_workspace(client, database, role, landing):
    register(client)
    with Session(database) as db:
        db.scalar(select(User)).role = role
        db.commit()
    response = login(client)
    assert response.status_code == 200 and response.json()["role"] == role
    assert client.get("/api/v1/auth/me").json()["role"] == role
    assert client.get(landing).status_code == 200
    if role != "admin":
        assert client.get("/manager").status_code == 403
        assert client.get("/api/v1/admin/products").status_code == 403
    if role == "customer":
        assert client.get("/staff/orders").status_code == 403


def test_user_id_scoped_workspaces_and_permissions(client, database):
    # 1. Password toggle buttons present on auth pages
    res_login = client.get("/account/login")
    assert "btn-toggle-password" in res_login.text
    assert "password-field" in res_login.text

    res_reg = client.get("/account/register")
    assert "btn-toggle-password" in res_reg.text

    # 2. Register customer 1
    register(client, email="cust1@example.com", name="Khách 1")
    login(client, email="cust1@example.com")

    # Customer 1 can access account profile and orders pages
    res_acc = client.get("/account")
    assert res_acc.status_code == 200
    assert "data-account-sidebar" in res_acc.text
    assert "data-profile-form" in res_acc.text

    res_orders = client.get("/account/orders")
    assert res_orders.status_code == 200
    assert "data-account-sidebar" in res_orders.text
    assert "data-account-orders" in res_orders.text

    # Customer CANNOT access manager or staff pages
    assert client.get("/manager").status_code == 403
    assert client.get("/staff/orders").status_code == 403

    # 3. User can edit their own profile (name and password)
    headers = csrf_headers(client)
    res_update = client.put(
        "/api/v1/auth/me",
        json={
            "name": "Khách 1 Đã Đổi Tên",
            "current_password": "ExamplePassword123!",
            "new_password": "NewSecretPassword456!",
        },
        headers=headers,
    )
    assert res_update.status_code == 200
    assert res_update.json()["name"] == "Khách 1 Đã Đổi Tên"

    # Verify new password works
    client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://testserver", **csrf_headers(client)}
    )
    res_relogin = login(client, email="cust1@example.com", password="NewSecretPassword456!")
    assert res_relogin.status_code == 200

    # Wrong current password fails
    res_fail = client.put(
        "/api/v1/auth/me",
        json={
            "name": "Test",
            "current_password": "WrongPassword!",
            "new_password": "AnotherNewPass123!",
        },
        headers=csrf_headers(client),
    )
    assert res_fail.status_code == 400
    assert res_fail.json()["detail"] == "Mật khẩu hiện tại không chính xác"


def test_admin_permissions_blocking_and_revenue(client, database):
    # 1. Register customer 1 & customer 2
    register(client, email="user1@example.com", name="Khách 1")
    register(client, email="user2@example.com", name="Khách 2")

    # 2. Register admin user by promoting in db directly
    register(client, email="admin@example.com", name="Quản lý chính")
    with Session(database) as db:
        admin_u = db.scalar(select(User).where(User.email == "admin@example.com"))
        admin_u.role = "admin"
        cust1_u = db.scalar(select(User).where(User.email == "user1@example.com"))
        cust1_id = cust1_u.id
        db.commit()

    # 3. Customer 1 cannot access admin user list or revenue
    login(client, email="user1@example.com")
    assert client.get("/api/v1/auth/admin/users").status_code == 403
    assert client.get("/api/v1/auth/admin/revenue").status_code == 403
    assert client.get("/admin/users").status_code == 403

    # 4. Login as admin
    client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://testserver", **csrf_headers(client)}
    )
    login(client, email="admin@example.com")
    headers = csrf_headers(client)

    # Admin accesses users page and revenue API
    assert client.get("/admin/users").status_code == 200
    assert "data-admin-users" in client.get("/admin/users").text

    res_users = client.get("/api/v1/auth/admin/users")
    assert res_users.status_code == 200
    users_data = res_users.json()
    assert len(users_data) == 3
    assert any(u["email"] == "user1@example.com" and not u["is_blocked"] for u in users_data)

    res_rev = client.get("/api/v1/auth/admin/revenue")
    assert res_rev.status_code == 200
    assert "total_revenue" in res_rev.json()
    assert "paypal_revenue" in res_rev.json()
    assert "vnpay_revenue" in res_rev.json()

    # 5. Admin promotes customer 1 to staff
    res_promote = client.patch(
        f"/api/v1/auth/admin/users/{cust1_id}/role",
        json={"role": "staff"},
        headers=headers,
    )
    assert res_promote.status_code == 200
    assert res_promote.json()["role"] == "staff"

    # Admin cannot change own role
    me_admin = client.get("/api/v1/auth/me").json()
    res_self_role = client.patch(
        f"/api/v1/auth/admin/users/{me_admin['id']}/role",
        json={"role": "customer"},
        headers=headers,
    )
    assert res_self_role.status_code == 400

    # 6. Admin blocks customer 1
    res_block = client.patch(
        f"/api/v1/auth/admin/users/{cust1_id}/block",
        json={"is_blocked": True},
        headers=headers,
    )
    assert res_block.status_code == 200
    assert res_block.json()["is_blocked"] is True

    # Admin cannot block self
    res_self_block = client.patch(
        f"/api/v1/auth/admin/users/{me_admin['id']}/block",
        json={"is_blocked": True},
        headers=headers,
    )
    assert res_self_block.status_code == 400

    # 7. Customer 1 (now blocked) cannot login
    client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://testserver", **csrf_headers(client)}
    )
    res_blocked_login = login(client, email="user1@example.com")
    assert res_blocked_login.status_code == 403
    assert "khóa" in res_blocked_login.json()["detail"].lower()

    # 8. Admin unblocks customer 1
    login(client, email="admin@example.com")
    res_unblock = client.patch(
        f"/api/v1/auth/admin/users/{cust1_id}/block",
        json={"is_blocked": False},
        headers=csrf_headers(client),
    )
    assert res_unblock.status_code == 200
    assert res_unblock.json()["is_blocked"] is False

    # Customer 1 can now login again and is staff
    client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://testserver", **csrf_headers(client)}
    )
    res_relogin = login(client, email="user1@example.com")
    assert res_relogin.status_code == 200
    assert res_relogin.json()["role"] == "staff"
