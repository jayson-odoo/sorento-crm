"""Rename the `closed` planning-change row kind to `cancelled`.

`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`, Slice A rule 5:
`PLANNING_CHANGE_KIND_CLOSED` is renamed `PLANNING_CHANGE_KIND_CANCELLED`
(`app/models/planning_change.py`) so "closed" - which reads as a delivery outcome, not a
line change - is retired from `PlanningChangeRow.kind`; `PlanningChangeKind`
(`app/schemas/planning_change.py`) drops `"closed"` from its wire Literal in the same
change, so any row still carrying the old value would 500 on response validation without
this data-only rename.

Data-only and idempotent, same shape as `513_planning_gate_backfill.py`: built with
SQLAlchemy Core against the mapped `PlanningChangeRow.__table__`, never raw `text()` SQL
naming `projects.planning_change_rows` directly, for the identical reason that migration's
own Reviewer S2 note gives - a scratch-schema test's `schema_translate_map` rewrites the
`projects` schema on Core/ORM constructs only, and a raw string would silently write into
whichever real `projects` tables the test happens to run against.

Revision ID: 514_plan_change_kind_cancelled
Revises: 513_planning_gate_backfill
Create Date: 2026-09-13
"""
import sqlalchemy as sa
from alembic import op

from app.models.planning_change import PlanningChangeRow

# Shortened from the file's own name (`514_planning_change_kind_cancelled`) - the head
# revision id must be <= 32 chars (LESSONS-LEARNT.md); the filename stays descriptive
# because `tests/test_migration_514_planning_change_kind_cancelled.py` loads this module by
# PATH, not by revision id.
revision = "514_plan_change_kind_cancelled"
down_revision = "513_planning_gate_backfill"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    rows = PlanningChangeRow.__table__
    bind.execute(
        sa.update(rows).where(rows.c.kind == "closed").values(kind="cancelled")
    )


def revert(bind) -> None:
    rows = PlanningChangeRow.__table__
    bind.execute(
        sa.update(rows).where(rows.c.kind == "cancelled").values(kind="closed")
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
