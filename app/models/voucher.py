from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        CheckConstraint("percent BETWEEN 1 AND 100", name="percent"),
        CheckConstraint("max_discount >= 0", name="max_discount"),
        CheckConstraint("qty_left >= 0", name="qty_left"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    percent: Mapped[int] = mapped_column(Integer)
    max_discount: Mapped[int] = mapped_column(Integer)
    qty_left: Mapped[int] = mapped_column(Integer)
    expired_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
