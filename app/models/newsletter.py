from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Unicode
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Unicode(254), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
