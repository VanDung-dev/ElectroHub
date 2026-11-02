from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.seeds.accounts import DEMO_ACCOUNTS, DEMO_PASSWORD, seed_accounts
from tests.conftest import login


def test_demo_accounts_are_created_once_and_can_login(client, database):
    with Session(database) as db:
        assert seed_accounts(db) == 3
        users = db.scalars(select(User).order_by(User.id)).all()
        original = [(user.id, user.password_hash, user.role) for user in users]
        assert all(verify_password(DEMO_PASSWORD, user.password_hash) for user in users)
        assert seed_accounts(db) == 0
        db.expire_all()
        users = db.scalars(select(User).order_by(User.id)).all()
        assert [(user.id, user.password_hash, user.role) for user in users] == original
    for email, role, _ in DEMO_ACCOUNTS:
        response = login(client, email=email, password=DEMO_PASSWORD)
        assert response.status_code == 200
        assert response.json()["role"] == role


def test_seed_preserves_customized_existing_account_and_adds_missing(database):
    with Session(database) as db:
        password_hash = hash_password("ChangedPassword123!")
        db.add(
            User(
                email="manager.demo@example.com",
                name="Existing",
                role="customer",
                password_hash=password_hash,
            )
        )
        db.commit()
        assert seed_accounts(db) == 2
        existing = db.scalar(select(User).where(User.email == "manager.demo@example.com"))
        assert (existing.name, existing.role, existing.password_hash) == (
            "Existing",
            "customer",
            password_hash,
        )
