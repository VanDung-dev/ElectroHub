from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("method IN ('PAYPAL', 'VNPAY')", name="method"),
        CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'refund_pending', 'refunded')",
            name="status",
        ),
        # A plain UNIQUE constraint allows only one NULL on SQL Server, and legacy
        # payments legitimately have no gateway reference.
        Index(
            "uq_payments_txn_ref",
            "txn_ref",
            unique=True,
            sqlite_where=text("txn_ref IS NOT NULL"),
            mssql_where=text("txn_ref IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    method: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Gateway bookkeeping. ``provider`` separates the legacy simulated rows from
    # real gateway traffic; ``txn_ref`` is what IPN/webhook payloads reference.
    provider: Mapped[str] = mapped_column(String(16), default="mock")
    txn_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_txn_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    # VND * 100 for VNPAY, USD cents for PayPal.
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"), nullable=True
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
