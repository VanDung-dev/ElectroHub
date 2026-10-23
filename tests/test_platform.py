from io import StringIO

import pytest
from alembic.config import Config
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import ROOT, Settings, get_settings
from app.core.database import get_db
from app.core.pages import page_endpoint, templates
from app.create_admin import main as create_admin
from app.models.user import User
from tests.conftest import csrf_headers


def test_health_swagger_html_and_static(client):
    assert client.get("/api/v1/health").json() == {"detail": "ok"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/api/v1/health",
        "/api/v1/auth/csrf",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/cart",
        "/api/v1/cart/items",
        "/api/v1/cart/items/{item_id}",
        "/api/v1/cart/apply-voucher",
        "/api/v1/orders",
        "/api/v1/orders/{code}",
        "/api/v1/orders/{code}/pay",
        "/api/v1/admin/orders",
        "/api/v1/admin/orders/{code}",
    }
    assert schema["components"]["schemas"]["RegisterRequest"]["examples"]
    assert schema["paths"]["/api/v1/auth/login"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("DetailResponse")
    for path in ["/", "/collections/all", "/products/demo", "/account/login"]:
        response = client.get(path)
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("text/html")
    assert client.get("/static/js/api.js").status_code == 200
    assert client.get("/missing").json() == {"detail": "Not Found"}


def test_template_context_and_form_csrf(client, monkeypatch, tmp_path):
    from jinja2 import DictLoader

    monkeypatch.setattr(
        templates.env,
        "loader",
        DictLoader(
            {
                "ready.html": (
                    '<form><input name="csrf_token" value="{{ csrf_token }}"></form>{{ slug }}'
                )
            }
        ),
    )
    monkeypatch.setattr("app.core.pages.ROOT", tmp_path)
    (tmp_path / "app/templates").mkdir(parents=True)
    (tmp_path / "app/templates/ready.html").write_text("ready")
    client.app.add_api_route("/ready/{slug}", page_endpoint("ready.html"), methods=["GET"])

    @client.app.post("/form-probe")
    async def form_probe(request: Request):
        return {"value": (await request.form())["value"]}

    response = client.get("/ready/demo")
    assert response.status_code == 200
    assert "demo" in response.text
    token = csrf_headers(client)["X-CSRF-Token"]
    assert token in response.text
    assert response.headers["Cache-Control"] == "no-store"
    response = client.post("/form-probe", data={"csrf_token": token, "value": "preserved"})
    assert response.status_code == 200
    assert response.json() == {"value": "preserved"}
    assert client.post("/form-probe", data={"value": "missing csrf"}).status_code == 403


def test_database_error_does_not_expose_connection_credentials(client):
    def broken_db():
        raise OperationalError("secret SQL", {"password": "hidden"}, Exception("hidden"))

    client.app.dependency_overrides[get_db] = broken_db
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dịch vụ dữ liệu chưa sẵn sàng"}


def test_users_migration_downgrade_upgrade_and_metadata(database):
    cfg = Config(str(ROOT / "alembic.ini"))
    assert "users" in inspect(database).get_table_names()
    command.check(cfg)
    command.downgrade(cfg, "base")
    assert "users" not in inspect(database).get_table_names()
    command.upgrade(cfg, "head")
    assert "users" in inspect(database).get_table_names()


def test_mssql_migration_compiles_with_unicode_identity_datetime(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "mssql+pyodbc://host/ElectroHub?driver=ODBC+Driver+18+for+SQL+Server"
    )
    get_settings.cache_clear()
    output = StringIO()
    command.upgrade(Config(str(ROOT / "alembic.ini"), output_buffer=output), "head", sql=True)
    sql = output.getvalue()
    assert "IDENTITY" in sql and "NVARCHAR(100)" in sql and "DATETIME2" in sql
    assert "uq_users_email" in sql and "ck_users_role" in sql


def test_config_requires_secret_and_handles_special_password():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="short", database_url="sqlite://")
    settings = Settings(
        _env_file=None, secret_key="s" * 48, database_url=None, mssql_sa_password="a@b:c/%!;{}"
    )
    assert settings.db_url.password == "a@b:c/%!;{}"
    assert settings.db_url.query["Encrypt"] == "yes"
    assert "a@b:c" not in repr(settings)


def test_create_admin_is_repeatable_and_does_not_promote_customer(database, monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["create_admin", "--email", "admin@example.com", "--name", "Dũng"]
    )
    monkeypatch.setattr("app.create_admin.getpass", lambda prompt: "ExamplePassword123!")
    with pytest.raises(SystemExit) as first:
        create_admin()
    assert first.value.code == 0
    with pytest.raises(SystemExit) as repeated:
        create_admin()
    assert repeated.value.code == 0
    with Session(database) as db:
        user = db.get(User, 1)
        assert user.role == "admin"
        original_hash = user.password_hash
        user.role = "customer"
        db.commit()
    with pytest.raises(SystemExit, match="không tự động nâng quyền"):
        create_admin()
    with Session(database) as db:
        user = db.get(User, 1)
        assert user.role == "customer" and user.password_hash == original_hash
