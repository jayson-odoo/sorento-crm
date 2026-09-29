"""Describe the configurable scope on the seeded `scm_reorder_run` task (#1340).

The scheduled reorder run now takes warehouses, demand, the sales-order window, products,
budget and market insight from its config page, so the description seeded by
`284_seed_scm_reorder_run_task` (all warehouses, market off, fixed) no longer tells the truth.
Only the row still carrying that seeded wording is updated: a description an admin already
rewrote on the page is theirs and stays. Data only, no schema change.

Revision ID: scm_reorder_run_scope_desc
Revises: merge_28sep_batch3
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "scm_reorder_run_scope_desc"
down_revision = "merge_28sep_batch3"
branch_labels = None
depends_on = None

OLD_DESCRIPTION = (
    "Daily reorder planning run across all active warehouses with market "
    "insight off, then funds everything (full budget) so the morning "
    "snapshot opens fully within-budget. Anchored to 06:00 (Asia/Kuala_Lumpur); "
    "time + cadence configurable. metadata: {budget:null => full budget, "
    "include_market:false}."
)

NEW_DESCRIPTION = (
    "Daily reorder planning run, funded in full unless a budget is set, then sends the low "
    "stock report for that run. Anchored to 06:00 (Asia/Kuala_Lumpur); time + cadence "
    "configurable. Scope is set on this page: warehouses (empty = every active warehouse), "
    "demand All / Project / Dealer, sales orders needed From / To in days from the run day "
    "(empty = every open order), products (empty = all), budget (empty = full budget) and "
    "market insight (default off)."
)


def _swap(old: str, new: str) -> None:
    op.get_bind().execute(
        text(
            "UPDATE scheduled_tasks SET description = :new "
            "WHERE key = 'scm_reorder_run' AND description = :old"
        ),
        {"old": old, "new": new},
    )


def upgrade() -> None:
    _swap(OLD_DESCRIPTION, NEW_DESCRIPTION)


def downgrade() -> None:
    _swap(NEW_DESCRIPTION, OLD_DESCRIPTION)
