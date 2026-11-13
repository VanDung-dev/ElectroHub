from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.newsletter import NewsletterSubscriber
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest

DUMMY_PASSWORD_HASH = hash_password("unused-password")


def create_user(
    db: Session, data: RegisterRequest, *, role: Literal["admin", "staff", "customer"] = "customer"
) -> User:
    email_clean = str(data.email).lower()
    user = User(
        email=email_clean,
        password_hash=hash_password(data.password.get_secret_value()),
        name=data.name,
        role=role,
    )
    db.add(user)
    if getattr(data, "is_subscribed_newsletter", False):
        sub = db.scalar(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == email_clean)
        )
        if not sub:
            db.add(NewsletterSubscriber(email=email_clean))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email đã được sử dụng") from None
    db.refresh(user)
    return user


def authenticate(db: Session, data: LoginRequest) -> User:
    user = db.scalar(select(User).where(User.email == str(data.email)))
    # Keep the bcrypt cost for unknown emails to avoid a cheap account timing probe.
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    if not verify_password(data.password.get_secret_value(), password_hash) or user is None:
        raise HTTPException(401, "Email hoặc mật khẩu không đúng")
    if user.is_blocked:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên.")
    return user
