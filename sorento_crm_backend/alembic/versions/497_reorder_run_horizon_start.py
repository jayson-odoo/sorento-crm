"""`scm.reorder_run` gains `plan_horizon_start` (S4, PLAN-reorder-feedback-9sep.md).

`plan_horizon_date` ("Plan until") has always been end-only. This adds the start-side
twin: demand needed BEFORE it is excluded from the run's netting, undated demand always
stays in (G2, 9 Sep ruling). Nullable, no backfill, no default - every existing run simply
carried no start, exactly as it carries none today.

Revision ID: 497_reorder_run_horizon_start
Revises: 496_sales_orders_source_ref_idx
"""
import sqlalchemy as sa
from alembic import op

revision = "497_reorder_run_horizon_start"
down_revision = "496_sales_orders_source_ref_idx"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE scm.reorder_run ADD COLUMN IF NOT EXISTS plan_horizon_start DATE"
        )
    )


def revert(bind) -> None:
    bind.execute(
        sa.text("ALTER TABLE scm.reorder_run DROP COLUMN IF EXISTS plan_horizon_start")
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
