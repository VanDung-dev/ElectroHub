"""add staff role"""

from alembic import op

revision = "0008_staff_role"
down_revision = "0007_online_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(op.f("ck_users_role"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_users_role"), "role IN ('admin', 'staff', 'customer')"
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(op.f("ck_users_role"), type_="check")
        batch_op.create_check_constraint(op.f("ck_users_role"), "role IN ('admin', 'customer')")
