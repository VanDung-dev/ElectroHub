"""Cart items: one row per user/product, qty 1..99 (contract qty)."""

import sqlalchemy as sa

from alembic import op

revision = "0003_cart_items"
down_revision = "0002_products_minimal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cart_items"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_cart_items_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_cart_items_product_id_products"
        ),
        sa.UniqueConstraint("user_id", "product_id", name="uq_cart_items_user_id"),
        sa.CheckConstraint("qty BETWEEN 1 AND 99", name=op.f("ck_cart_items_qty")),
    )
    op.create_index("ix_cart_items_user_id", "cart_items", ["user_id"])
    op.create_index("ix_cart_items_product_id", "cart_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_cart_items_product_id", table_name="cart_items")
    op.drop_index("ix_cart_items_user_id", table_name="cart_items")
    op.drop_table("cart_items")
