"""Add is_blocked column to users table."""

import sqlalchemy as sa

from alembic import op

revision = "0015_user_block"
down_revision = "0014_product_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_blocked", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_blocked")
