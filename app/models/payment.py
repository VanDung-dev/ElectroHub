from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("method IN ('COD', 'CHUYEN_KHOAN_MOCK')", name="method"),
        CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'refunded')",
            name="status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    method: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
