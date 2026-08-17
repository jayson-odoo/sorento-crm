"""Plan-grain policy + the run stamp that freezes it (front planning 5.1 / 5.4).

Two halves of one contract:

* `system_settings.plan_grain` - the ADMIN policy, `product` or `location`, rollout
  default `product`. It is not a per-run selector and it is not the buyer's Planning mode:
  Auto / Manual, which it neither renames nor replaces. NOT NULL with a default, because
  the singleton row already exists and "no policy" has no meaning.
* `scm.reorder_run.decision_grain` + `.front_planning_contract_version` - the STAMP each
  new run takes at creation from that policy. Both NULLABLE and deliberately NOT
  backfilled: a NULL contract version is precisely what marks a run as legacy, and legacy
  runs stay read-only in both grains (`plan_grain.assert_decision_grain`). Guessing which
  grain a historical run meant is the one change that could make an old decision
  actionable a second time.

Nothing is written to existing rows here beyond the settings default, so the migration is
a no-op on an empty database and cheap on a full one.

Revision ID: 375_plan_grain_run_stamp
Revises: 374_uom_decimal_places
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa


revision = "375_plan_grain_run_stamp"
down_revision = "374_uom_decimal_places"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "plan_grain",
            sa.String(length=20),
            nullable=False,
            server_default="product",
        ),
    )
    op.add_column(
        "reorder_run",
        sa.Column("decision_grain", sa.String(length=20), nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_run",
        sa.Column("front_planning_contract_version", sa.SmallInteger(), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_run", "front_planning_contract_version", schema="scm")
    op.drop_column("reorder_run", "decision_grain", schema="scm")
    op.drop_column("system_settings", "plan_grain")
