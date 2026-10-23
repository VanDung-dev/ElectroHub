"""Create platform users only; business schemas belong to P2/P3."""

import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

from alembic import op

revision = "0001_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Unicode(254), nullable=False),
        sa.Column("password_hash", sa.String(60), nullable=False),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(DATETIME2(), "mssql"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('admin', 'customer')", name=op.f("ck_users_role")),
    )


def downgrade() -> None:
    op.drop_table("users")
