"""Minimal product projection owned by P2.

Sales (P3) needs product price/stock to quote and checkout a cart. P2 has not landed
the catalog model/migration yet, so this minimal definition and the matching
`0002_products_minimal` migration exist only to unblock the sales domain.
P2 extends this model and replaces the migration with the full catalog schema;
sales code only relies on `id, slug, name, price, sale_price, stock`.
"""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Unicode
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price"),
        CheckConstraint("sale_price IS NULL OR sale_price >= 0", name="sale_price"),
        CheckConstraint("stock >= 0", name="stock"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Unicode(200), unique=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(Unicode(200))
    price: Mapped[int] = mapped_column(Integer)
    sale_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME2(), "mssql"),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
