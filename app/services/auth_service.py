from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest

DUMMY_PASSWORD_HASH = hash_password("unused-password")


def create_user(
    db: Session, data: RegisterRequest, *, role: Literal["admin", "customer"] = "customer"
) -> User:
    user = User(
        email=str(data.email),
        password_hash=hash_password(data.password.get_secret_value()),
        name=data.name,
        role=role,
    )
    db.add(user)
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
    return user
