"""Backfill for the held-or-inquiry planning-change gate.

`documentation/plans/scm/PLAN-scm-planning-change-gate-held-or-inquiry.md`: `build_batch`
used to keep a changed line the instant it was adopted onto `projects.sales_orders`, with
no ask whether anyone had decided anything for it. On the 10 Sep 2026 live copy, 1,307 of
1,308 pending `projects.planning_change_rows` sat on lines with no held decision
(`held_json` null) and no Order Inquiry row (`inquiry_rows_json` empty) - the "Changed"
pill sent the reader to a board with nothing left to re-decide.

This is data-only and idempotent: no row or batch is DELETED, ever (AC-R10, "the batch is
a record", still holds). A pending row with nothing to re-decide becomes `superseded` with
a reason naming this migration; a batch left with no `pending` row AND no `failed` row
after that gets `applied_at` stamped (no `applied_by` - the frontend already renders that
as applied with no actor) and a `result_json` note. `build_batch` itself already stops
raising this shape of row going forward (`app/services/planning_change_service.py`); this
migration only closes out the rows and batches the OLD code already wrote before this
deploy.

**Reviewer S1:** a `failed` row is not `pending`, but it is not resolved either - `apply()`
(`planning_change_service.py`) deliberately leaves an all-failed batch's `applied_at` NULL
so it stays retryable, and a stamped batch refuses `set_row_decision` and
`apply(refuse_if_applied=True)`. The batch-closing predicate below excludes `failed`
alongside `pending`, so this migration never stamps a batch that still needs a retry.

**Reviewer S2:** the two statements are built with SQLAlchemy Core against the mapped
`PlanningChangeRow.__table__` / `PlanningChangeBatch.__table__`, not raw `text()` SQL naming
`projects.planning_change_rows` directly. `tests/test_migration_513_planning_gate_backfill.py`
drives `apply(connection)` against a scratch-schema Postgres connection whose
`schema_translate_map` rewrites the `projects` schema on Core/ORM constructs only - a raw
string naming the schema resolves through `search_path` instead and would silently write
into the REAL `projects` tables of whichever database the test happens to run against.
`upgrade()` calls `apply(op.get_bind())`, where the schema is genuinely `projects` and the
translate map is a no-op.

Revision ID: 513_planning_gate_backfill
Revises: 512_integration_ref_company
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import func

from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow

revision = "513_planning_gate_backfill"
down_revision = "512_integration_ref_company"
branch_labels = None
depends_on = None

_CLOSED_BY = "513_planning_gate_backfill"
_REASON = (
    f"Gate narrowed on 12 Sep 2026 ({_CLOSED_BY}): the line had no held decision and no "
    "inquiry row, so there was nothing to re-decide; the board reads its new value "
    "directly."
)

# Rows that leave a batch with something still to re-decide - `pending` (undecided) and
# `failed` (a retry is still owed, reviewer S1). Only `superseded` / `applied` close it out.
_UNRESOLVED_STATES = ("pending", "failed")


def apply(bind) -> None:
    """Supersede a pending row with nothing to re-decide, then close a batch left with
    neither a pending nor a failed row. Idempotent: a row already `superseded` no longer
    matches the first UPDATE's `applied_state == 'pending'`, and a batch already stamped no
    longer matches the second UPDATE's `applied_at IS NULL`."""
    rows = PlanningChangeRow.__table__
    batches = PlanningChangeBatch.__table__

    no_held = rows.c.held_json.is_(None) | (func.jsonb_typeof(rows.c.held_json) == "null")
    no_inquiry = (
        rows.c.inquiry_rows_json.is_(None)
        | (func.jsonb_typeof(rows.c.inquiry_rows_json) == "null")
        | (rows.c.inquiry_rows_json == [])
    )
    on_an_open_batch = rows.c.batch_id.in_(
        sa.select(batches.c.id).where(batches.c.applied_at.is_(None))
    )

    bind.execute(
        sa.update(rows)
        .where(rows.c.applied_state == "pending")
        .where(no_held)
        .where(no_inquiry)
        .where(on_an_open_batch)
        .values(applied_state="superseded", applied_reason=_REASON)
    )

    nothing_left_to_decide = ~sa.exists().where(
        (rows.c.batch_id == batches.c.id)
        & rows.c.applied_state.in_(_UNRESOLVED_STATES)
    )
    bind.execute(
        sa.update(batches)
        .where(batches.c.applied_at.is_(None))
        .where(nothing_left_to_decide)
        .values(
            applied_at=func.now(),
            result_json=func.coalesce(batches.c.result_json, sa.text("'{}'::jsonb")).op("||")(
                func.jsonb_build_object("closed_by", _CLOSED_BY)
            ),
        )
    )


def revert(bind) -> None:
    """No-op - see the module docstring for why (`superseded` is a fact about those rows at
    the moment the gate narrowed; reverting it would re-raise 1,307 rows with nothing to
    re-decide, exactly the noise this migration exists to close out)."""


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
