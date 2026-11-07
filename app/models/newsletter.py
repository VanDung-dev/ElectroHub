from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Unicode, UnicodeText
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


class EmailCampaign(Base):
    __tablename__ = "email_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    body: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
    status: Mapped[str] = mapped_column(Unicode(20), nullable=False, default="sent")
