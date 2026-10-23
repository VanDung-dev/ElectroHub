"""Minimal products table so sales FKs (cart/order) can be created.

P2 owns the catalog schema and replaces this migration with the full product model
(category, brand, images, specs). Sales only reads id/slug/name/price/sale_price/stock.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0002_products_minimal"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.Unicode(200), nullable=False),
        sa.Column("sku", sa.String(32), nullable=False),
        sa.Column("name", sa.Unicode(200), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("sale_price", sa.Integer(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(DATETIME2(), "mssql"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
        sa.CheckConstraint("price >= 0", name=op.f("ck_products_price")),
        sa.CheckConstraint(
            "sale_price IS NULL OR sale_price >= 0", name=op.f("ck_products_sale_price")
        ),
        sa.CheckConstraint("stock >= 0", name=op.f("ck_products_stock")),
    )


def downgrade() -> None:
    op.drop_table("products")
