"""Refund requests held for shop confirmation, and the refund_pending state."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0011_refund_hold"
down_revision = "0010_payment_gateway"
branch_labels = None
depends_on = None

PAYMENT_STATUSES = "'pending', 'paid', 'failed', 'refund_pending', 'refunded'"
OLD_PAYMENT_STATUSES = "'pending', 'paid', 'failed', 'refunded'"


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint(op.f("ck_payments_status"), type_="check")
        batch.create_check_constraint(op.f("ck_payments_status"), f"status IN ({PAYMENT_STATUSES})")

    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime().with_variant(DATETIME2(), "mssql"),
            nullable=False,
        ),
        sa.Column(
            "due_at",
            sa.DateTime().with_variant(DATETIME2(), "mssql"),
            nullable=False,
        ),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime().with_variant(DATETIME2(), "mssql"),
            nullable=True,
        ),
        sa.Column("provider_refund_id", sa.String(64), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(DATETIME2(), "mssql"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(DATETIME2(), "mssql"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refunds"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_refunds_order_id_orders", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name="fk_refunds_payment_id_payments"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name="fk_refunds_requested_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"], ["users.id"], name="fk_refunds_confirmed_by_users"
        ),
        sa.UniqueConstraint("order_id", name="uq_refunds_order_id"),
        sa.CheckConstraint(
            "status IN ('scheduled', 'processing', 'succeeded', 'failed', 'rejected')",
            name=op.f("ck_refunds_status"),
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_refunds_amount")),
    )
    op.create_index("ix_refunds_order_id", "refunds", ["order_id"])
    op.create_index("ix_refunds_status", "refunds", ["status"])
    op.create_index("ix_refunds_due_at", "refunds", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_refunds_due_at", table_name="refunds")
    op.drop_index("ix_refunds_status", table_name="refunds")
    op.drop_index("ix_refunds_order_id", table_name="refunds")
    op.drop_table("refunds")
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint(op.f("ck_payments_status"), type_="check")
        batch.create_check_constraint(
            op.f("ck_payments_status"), f"status IN ({OLD_PAYMENT_STATUSES})"
        )
