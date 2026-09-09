"""`scm.order_summary_row` gains the sheet's site-pool columns (S14,
PLAN-reorder-feedback-9sep.md Round 3, AC-S14.1).

`write_rows` already freezes `on_hand` (network-wide) and reads `inputs.reorder_level` off
each run's own recommendations without storing it. This adds two more frozen facts, both
additive and nullable, no backfill: `pool_on_hand` (site-pool stock only - the sheet's "BRW
on hand") and `reorder_level` (the run's own frozen level, first recommendation carrying
one). Neither replaces `on_hand`, which the grid still reads.

Revision ID: 504_order_summary_pool_cols
Revises: 503_product_exclude_planning_flt
"""
import sqlalchemy as sa
from alembic import op

revision = "504_order_summary_pool_cols"
down_revision = "503_product_exclude_planning_flt"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("pool_on_hand", "NUMERIC"),
    ("reorder_level", "NUMERIC"),
)


def apply(bind) -> None:
    for name, sql_type in _COLUMNS:
        bind.execute(
            sa.text(
                f"ALTER TABLE scm.order_summary_row ADD COLUMN IF NOT EXISTS "
                f"{name} {sql_type}"
            )
        )


def revert(bind) -> None:
    for name, _sql_type in reversed(_COLUMNS):
        bind.execute(
            sa.text(f"ALTER TABLE scm.order_summary_row DROP COLUMN IF EXISTS {name}")
        )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
