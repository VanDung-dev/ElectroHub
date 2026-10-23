"""Run inside the app container against a disposable SQL Server test database."""

import json
import secrets
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main() -> None:
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    base = "http://127.0.0.1:8000"

    def request(path, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-CSRF-Token"] = token
        body = json.dumps(data).encode() if data is not None else None
        with client.open(Request(base + path, data=body, headers=headers), timeout=10) as response:
            return json.load(response)

    def csrf():
        return request("/api/v1/auth/csrf")["csrf_token"]

    assert request("/api/v1/health") == {"detail": "ok"}
    email = f"smoke-{secrets.token_hex(8)}@example.com"
    credentials = {"email": email, "password": secrets.token_urlsafe(24)}
    user = request("/api/v1/auth/register", {**credentials, "name": "Kiểm thử Dũng"}, csrf())
    assert user["role"] == "customer" and user["name"] == "Kiểm thử Dũng"
    assert "password_hash" not in user
    request("/api/v1/auth/login", credentials, csrf())
    assert request("/api/v1/auth/me")["id"] == user["id"]
    try:
        request("/api/v1/auth/logout", {})
    except HTTPError as exc:
        assert exc.code == 403
    else:
        raise AssertionError("Mutation accepted without CSRF")
    request("/api/v1/auth/logout", {}, csrf())
    try:
        request("/api/v1/auth/me")
    except HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("Logged-out browser still authenticated")
    print("SQL Server auth smoke passed")


if __name__ == "__main__":
    main()
