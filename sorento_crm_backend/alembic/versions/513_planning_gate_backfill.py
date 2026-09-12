"""Backfill for the held-or-inquiry planning-change gate.

`documentation/plans/scm/PLAN-scm-planning-change-gate-held-or-inquiry.md`: `build_batch`
used to keep a changed line the instant it was adopted onto `projects.sales_orders`, with
no ask whether anyone had decided anything for it. On the 10 Sep 2026 live copy, 1,307 of
1,308 pending `projects.planning_change_rows` sat on lines with no held decision
(`held_json` null) and no Order Inquiry row (`inquiry_rows_json` empty) - the "Changed"
pill sent the reader to a board with nothing left to re-decide.

This is data-only and idempotent: no row or batch is DELETED, ever (AC-R10, "the batch is
a record", still holds). A pending row with nothing to re-decide becomes `superseded` with
a reason naming this migration; a batch left with no pending row after that gets
`applied_at` stamped (no `applied_by` - the frontend already renders that as applied with
no actor) and a `result_json` note. `build_batch` itself already stops raising this shape
of row going forward (`app/services/planning_change_service.py`); this migration only
closes out the rows and batches the OLD code already wrote before this deploy.

Revision ID: 513_planning_gate_backfill
Revises: 512_hidden_by_default_col
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op

revision = "513_planning_gate_backfill"
down_revision = "512_hidden_by_default_col"
branch_labels = None
depends_on = None

_SCHEMA = "projects"
_REASON = (
    "Gate narrowed on 12 Sep 2026 (513_planning_gate_backfill): the line had no held "
    "decision and no inquiry row, so there was nothing to re-decide; the board reads its "
    "new value directly."
)


def upgrade() -> None:
    op.execute(sa.text(
        f"""
        UPDATE {_SCHEMA}.planning_change_rows r
        SET applied_state = 'superseded',
            applied_reason = :reason
        FROM {_SCHEMA}.planning_change_batches b
        WHERE b.id = r.batch_id
          AND b.applied_at IS NULL
          AND r.applied_state = 'pending'
          AND (r.held_json IS NULL OR jsonb_typeof(r.held_json) = 'null')
          AND (
                r.inquiry_rows_json IS NULL
                OR jsonb_typeof(r.inquiry_rows_json) = 'null'
                OR r.inquiry_rows_json = '[]'::jsonb
              )
        """
    ).bindparams(reason=_REASON))

    op.execute(sa.text(
        f"""
        UPDATE {_SCHEMA}.planning_change_batches b
        SET applied_at = now(),
            result_json = coalesce(b.result_json, '{{}}'::jsonb)
                || '{{"closed_by": "513_planning_gate_backfill"}}'::jsonb
        WHERE b.applied_at IS NULL
          AND NOT EXISTS (
                SELECT 1 FROM {_SCHEMA}.planning_change_rows r
                WHERE r.batch_id = b.id AND r.applied_state = 'pending'
              )
        """
    ))


def downgrade() -> None:
    # No-op: `superseded` is a fact about those rows at the moment the gate narrowed - a
    # line that genuinely had no held decision and no inquiry row when this ran. Reverting
    # it would re-raise 1,307 rows with nothing to re-decide, exactly the noise this
    # migration exists to close out.
    pass
