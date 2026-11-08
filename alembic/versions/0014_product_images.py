"""Add product images gallery table."""

import sqlalchemy as sa

from alembic import op

revision = "0014_product_images"
down_revision = "0013_email_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("alt", sa.Unicode(length=200), server_default="", nullable=False),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_images_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_images")),
    )
    op.create_index(
        op.f("ix_product_images_product_id"),
        "product_images",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_images_product_id"), table_name="product_images")
    op.drop_table("product_images")
