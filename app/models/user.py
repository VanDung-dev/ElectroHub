from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Unicode
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'customer')", name="role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Unicode(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(Unicode(100))
    role: Mapped[str] = mapped_column(String(16), default="customer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
