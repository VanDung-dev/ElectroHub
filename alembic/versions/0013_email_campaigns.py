"""Record email marketing campaign history."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0013_email_campaigns"
down_revision = "0012_order_vat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.Unicode(200), nullable=False),
        sa.Column("body", sa.UnicodeText(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime().with_variant(DATETIME2(), "mssql"), nullable=False),
        sa.Column("status", sa.Unicode(20), nullable=False, server_default="sent"),
        sa.PrimaryKeyConstraint("id", name="pk_email_campaigns"),
    )


def downgrade() -> None:
    op.drop_table("email_campaigns")
