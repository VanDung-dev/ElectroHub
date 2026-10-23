import os
import secrets

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command

# Never connect tests to the developer's .env database.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["COOKIE_SECURE"] = "false"

from app.core.config import ROOT, get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = get_engine()
    yield engine
    engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client(database):
    with TestClient(create_app()) as client:
        yield client


def csrf_headers(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def register(client, **overrides):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "password": "ExamplePassword123!",
            "name": "Nguyễn Lê Văn Dũng",
            **overrides,
        },
        headers=csrf_headers(client),
    )


def login(client, **overrides):
    return client.post(
        "/api/v1/auth/login",
        json={"email": "customer@example.com", "password": "ExamplePassword123!", **overrides},
        headers=csrf_headers(client),
    )
