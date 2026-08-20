"""scm.reorder_run.plan_horizon_date - the "Plan until" cutoff a manual run can set (captain, 20 Aug).

> "SOs needed in 2030 distort a plan the captain only wants through December."

`plan_horizon_date` is NULLABLE and NOT backfilled: NULL means "no horizon", which is the
only behaviour every run before this column existed ever had, so an existing run's frozen
recommendations describe exactly what they always described. Stamped once at
`reorder_run_service.create_run`, like `decision_grain` - a per-RUN choice, not a live
policy, so it cannot move under a run already planned.

Reads/writes live in `reorder_run_service._planning_rows` (netting) and the reorder-runs
API schemas (`app/schemas/scm_reorder.py`) - this migration only adds the column.

Revision ID: 403_reorder_run_plan_horizon
Revises: 402_attachments_entity_type_allow_supplier_stock_list
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


revision = "403_reorder_run_plan_horizon"
down_revision = "402_attachments_entity_type_allow_supplier_stock_list"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_run",
        sa.Column("plan_horizon_date", sa.Date(), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_run", "plan_horizon_date", schema="scm")
