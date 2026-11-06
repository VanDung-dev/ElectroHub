from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.payment import Payment


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Refund(Base):
    """A refund request that only becomes actionable after the hold period."""

    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'processing', 'succeeded', 'failed', 'rejected')",
            name="status",
        ),
        CheckConstraint("amount >= 0", name="amount"),
        UniqueConstraint("order_id", name="uq_refunds_order_id"),
        Index("ix_refunds_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"), default=utc_now
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"), index=True
    )
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"), nullable=True
    )
    provider_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"), default=utc_now, onupdate=utc_now
    )

    order: Mapped["Order"] = relationship(back_populates="refund")
    payment: Mapped["Payment"] = relationship()
