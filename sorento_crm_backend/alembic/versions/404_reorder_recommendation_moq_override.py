"""scm.reorder_recommendation.moq_override - the buyer's own MoQ, in place of the frozen master figure (captain, 20 Aug live test).

> "user feedback that MoQ is varying from time to time so they don't maintain it, so we
>  need a place for the user to input MoQ in this table, we can default from master data
>  but allow change, and when they change, our calculation should recalculate."

`product_suppliers.moq` is frozen into each recommendation's `inputs.supplier` /
`inputs.moq` at run time (`reorder_engine.load_supplier_candidates`) and used to round the
suggested quantity up (`round_order_qty`). Master data drifts and the buyer has no way to
correct a stale figure without re-running the whole plan, so this column lets them override
it PER ROW without touching `product_suppliers` or the frozen `inputs` (AC-M3.11 stays
intact - the freeze still describes what the engine actually computed).

NULLABLE, NOT backfilled: NULL means "use the frozen master figure", which is every row's
behaviour before this column existed. Set/cleared via
`PUT /api/v1/scm/recommendations/{rec_id}/moq` (`reorder_run_service.set_moq_override`),
which re-derives `rounded_qty` (and `cash_impact`) through the SAME `round_order_qty` /
`_cash_impact_in_base` helpers the engine itself uses, live at read time - it never
rewrites the persisted `rounded_qty` column, so a fresh run of the same plan (no override)
still reproduces byte-for-byte.

Revision ID: 404_reorder_rec_moq_override
Revises: 403_reorder_run_plan_horizon
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


revision = "404_reorder_rec_moq_override"
down_revision = "403_reorder_run_plan_horizon"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_recommendation",
        sa.Column("moq_override", sa.Numeric(), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_recommendation", "moq_override", schema="scm")
