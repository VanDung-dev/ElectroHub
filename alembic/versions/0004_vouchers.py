"""Sales domain tables. Cart/voucher quote logic is implemented in services/order_service.py."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0004_vouchers"
down_revision = "0003_cart_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vouchers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("max_discount", sa.Integer(), nullable=False),
        sa.Column("qty_left", sa.Integer(), nullable=False),
        sa.Column("expired_at", sa.DateTime().with_variant(DATETIME2(), "mssql"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_vouchers"),
        sa.UniqueConstraint("code", name="uq_vouchers_code"),
        sa.CheckConstraint("percent BETWEEN 1 AND 100", name=op.f("ck_vouchers_percent")),
        sa.CheckConstraint("max_discount >= 0", name=op.f("ck_vouchers_max_discount")),
        sa.CheckConstraint("qty_left >= 0", name=op.f("ck_vouchers_qty_left")),
    )


def downgrade() -> None:
    op.drop_table("vouchers")
