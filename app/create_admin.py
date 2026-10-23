import argparse
from getpass import getpass

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.services.auth_service import create_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo admin; không đổi quyền tài khoản đã tồn tại")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass("Mật khẩu admin: ")
    if password != getpass("Nhập lại mật khẩu: "):
        raise SystemExit("Mật khẩu không khớp")
    try:
        data = RegisterRequest(email=args.email, password=password, name=args.name)
    except ValidationError:
        raise SystemExit(
            "Email/tên không hợp lệ hoặc mật khẩu không đủ 8 ký tự / quá 72 byte"
        ) from None
    with Session(get_engine()) as db:
        existing = db.scalar(select(User).where(User.email == str(data.email)))
        if existing:
            if existing.role != "admin":
                raise SystemExit("Email đã thuộc customer; không tự động nâng quyền")
            parser.exit(message="Admin đã tồn tại; không thay đổi mật khẩu\n")
        try:
            create_user(db, data, role="admin")
        except HTTPException as exc:
            raise SystemExit(exc.detail) from None
    parser.exit(message="Đã tạo admin\n")


if __name__ == "__main__":
    main()
