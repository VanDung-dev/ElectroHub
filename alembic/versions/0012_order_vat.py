"""Store the VAT portion of each order total."""

import sqlalchemy as sa

from alembic import op

revision = "0012_order_vat"
down_revision = "0011_refund_hold"
branch_labels = None
depends_on = None

AMOUNTS = "subtotal >= 0 AND discount >= 0 AND vat >= 0 AND shipping_fee >= 0 AND total >= 0"
OLD_AMOUNTS = "subtotal >= 0 AND discount >= 0 AND shipping_fee >= 0 AND total >= 0"


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint(op.f("ck_orders_amounts"), type_="check")
        batch.add_column(sa.Column("vat", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint(op.f("ck_orders_amounts"), AMOUNTS)


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint(op.f("ck_orders_amounts"), type_="check")
        batch.drop_column("vat")
        batch.create_check_constraint(op.f("ck_orders_amounts"), OLD_AMOUNTS)
