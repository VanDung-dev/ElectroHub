"""Use only PayPal and VNPAY simulations for new payments."""

from alembic import op

revision = "0009_simulated_payments"
down_revision = "0008_staff_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint(op.f("ck_payments_method"), type_="check")
        batch.create_check_constraint(op.f("ck_payments_method"), "method IN ('PAYPAL', 'VNPAY')")


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint(op.f("ck_payments_method"), type_="check")
        batch.create_check_constraint(
            op.f("ck_payments_method"), "method IN ('COD', 'CHUYEN_KHOAN_MOCK', 'STRIPE', 'VNPAY')"
        )
