"""Allow configured Stripe and VNPAY payment methods."""

from alembic import op

revision = "0007_online_payments"
down_revision = "0006_storefront_newsletter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint(op.f("ck_payments_method"), type_="check")
        batch.create_check_constraint(
            op.f("ck_payments_method"), "method IN ('COD', 'CHUYEN_KHOAN_MOCK', 'STRIPE', 'VNPAY')"
        )


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint(op.f("ck_payments_method"), type_="check")
        batch.create_check_constraint(
            op.f("ck_payments_method"), "method IN ('COD', 'CHUYEN_KHOAN_MOCK')"
        )
