"""Storefront metadata and opted-in newsletter subscribers."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0006_storefront_newsletter"
down_revision = "0005_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("description", sa.Unicode(1000), nullable=False, server_default="")
    )
    op.add_column(
        "products",
        sa.Column(
            "image_url",
            sa.String(500),
            nullable=False,
            server_default="/static/img/product-placeholder.svg",
        ),
    )
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Unicode(254), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(DATETIME2(), "mssql"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_newsletter_subscribers"),
        sa.UniqueConstraint("email", name="uq_newsletter_subscribers_email"),
    )


def downgrade() -> None:
    op.drop_table("newsletter_subscribers")
    op.drop_column("products", "image_url")
    op.drop_column("products", "description")
