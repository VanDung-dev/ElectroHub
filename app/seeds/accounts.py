"""Create the three local demo accounts without changing existing users."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.services.auth_service import create_user

DEMO_PASSWORD = "Demo@2026!"
DEMO_ACCOUNTS = (
    ("customer.demo@example.com", "customer", "Khách hàng Demo"),
    ("staff.demo@example.com", "staff", "Nhân viên Demo"),
    ("manager.demo@example.com", "admin", "Quản lý Demo"),
)


def seed_accounts(db: Session) -> int:
    created = 0
    for email, role, name in DEMO_ACCOUNTS:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            continue
        create_user(db, RegisterRequest(email=email, password=DEMO_PASSWORD, name=name), role=role)
        created += 1
    return created


def main() -> None:
    with Session(get_engine()) as db:
        created = seed_accounts(db)
    print(f"Demo accounts: created {created}; existing accounts left unchanged.")


if __name__ == "__main__":
    main()
