"""Order lifecycle: orders, order_items and payments (one payment per order)."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0005_orders"
down_revision = "0004_vouchers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(12), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Integer(), nullable=False),
        sa.Column("shipping_fee", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("voucher_code", sa.String(32), nullable=True),
        sa.Column("address", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(DATETIME2(), "mssql"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_orders_user_id_users"),
        sa.UniqueConstraint("code", name="uq_orders_code"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'shipping', 'done', 'cancelled')",
            name=op.f("ck_orders_status"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount >= 0 AND shipping_fee >= 0 AND total >= 0",
            name=op.f("ck_orders_amounts"),
        ),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_order_items"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_order_items_order_id_orders", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_order_items_product_id_products"
        ),
        sa.CheckConstraint("qty BETWEEN 1 AND 99", name=op.f("ck_order_items_qty")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_order_items_price")),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_payments_order_id_orders", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("order_id", name="uq_payments_order_id"),
        sa.CheckConstraint(
            "method IN ('COD', 'CHUYEN_KHOAN_MOCK')", name=op.f("ck_payments_method")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'refunded')",
            name=op.f("ck_payments_status"),
        ),
    )


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_index("ix_order_items_product_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_table("orders")
