"""Add gateway bookkeeping columns to payments."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0010_payment_gateway"
down_revision = "0009_simulated_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.add_column(
            sa.Column("provider", sa.String(16), nullable=False, server_default="mock")
        )
        batch.add_column(sa.Column("txn_ref", sa.String(64), nullable=True))
        batch.add_column(sa.Column("provider_order_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("provider_txn_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("provider_status", sa.String(32), nullable=True))
        batch.add_column(
            sa.Column("currency", sa.String(3), nullable=False, server_default="VND")
        )
        batch.add_column(sa.Column("amount_minor", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "paid_at",
                sa.DateTime().with_variant(DATETIME2(), "mssql"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("raw_payload", sa.JSON(), nullable=True))

    # Every legacy row was a simulated payment.
    op.execute(sa.text("UPDATE payments SET provider = 'mock' WHERE provider IS NULL"))
    op.execute(
        sa.text(
            "UPDATE payments SET amount_minor = "
            "(SELECT orders.total * 100 FROM orders WHERE orders.id = payments.order_id) "
            "WHERE amount_minor IS NULL"
        )
    )

    # SQL Server only permits one NULL in a plain UNIQUE constraint, while mock and
    # legacy rows legitimately have no gateway reference. Use filtered indexes.
    op.create_index(
        "uq_payments_txn_ref",
        "payments",
        ["txn_ref"],
        unique=True,
        sqlite_where=sa.text("txn_ref IS NOT NULL"),
        mssql_where=sa.text("txn_ref IS NOT NULL"),
    )
    op.create_index("ix_payments_provider_order_id", "payments", ["provider_order_id"])
    op.create_index("ix_payments_provider_txn_id", "payments", ["provider_txn_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_provider_txn_id", table_name="payments")
    op.drop_index("ix_payments_provider_order_id", table_name="payments")
    op.drop_index("uq_payments_txn_ref", table_name="payments")
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("raw_payload")
        batch.drop_column("paid_at")
        batch.drop_column("attempt")
        batch.drop_column("amount_minor")
        batch.drop_column("currency")
        batch.drop_column("provider_status")
        batch.drop_column("provider_txn_id")
        batch.drop_column("provider_order_id")
        batch.drop_column("txn_ref")
        batch.drop_column("provider")
