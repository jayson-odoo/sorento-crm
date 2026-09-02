"""Order inquiry rows are born acknowledged; backfill every pre-existing awaiting row

Revision ID: 454_order_inquiry_born_ack
Revises: 453_shared_brand_attach
Create Date: 2026-09-01 09:00:00.000000

`PLAN-scm-reorder-oi-feedback-1sep.md` S1 (G4, captain 1 Sep 2026). The handshake
migration (428) shipped `ack_state` with NO backfill, because at the time nobody had
acknowledged anything and `awaiting` was the honest starting truth for every row. That
truth changes here: purchasing never presses Confirm any more (S1 retires the action),
so a row is born acknowledged at every creation site, and reject is the only manual gate
left. A pre-existing `awaiting` row is not a different case - it is exactly the backlog
this rule now treats as already read - so it is acknowledged too, with SYSTEM attribution
(`acknowledged_by IS NULL`) since no real actor pressed anything to get it there.

Scoped to `awaiting` only. A `changed` row is untouched: G4 also auto-acknowledges a
settle-in-place from this point forward, but a row already sitting on `changed` before
this migration ran carries a real `changed_at` a person may still want to see flagged, and
retro-acknowledging it would erase that signal for no reason - the next settle (or a
direct read) moves it forward exactly as any other `changed` row does. `acknowledged` and
`rejected` rows are already answered and are not touched either.

Two fixes from review (PR #471):

* `now()` is naive-UTC in this column, and the migration ran it BARE - on a session whose
  `timezone` GUC reads Asia/Kuala_Lumpur (MYT, UTC+8) `now()` returns wall-clock MYT, so
  every backfilled `acknowledged_at` would land eight hours in the future. `now() AT TIME
  ZONE 'utc'` is the fix already used for this exact class of column
  (`082_import_job_processor_seconds.py`).
* BEFORE the backfill, every link belonging to an ALREADY-`acknowledged`,
  actor-attributed row (a genuine pre-S1 human Confirm press) is stamped `auto = false`.
  Those rows' links were written by the SAME raise-time cascade every row's links are -
  `auto = true` regardless of who confirmed them - so post-deploy `_cascade_only` would
  read a legacy confirmed row exactly like a fresh draft nobody has touched, and Auto link
  all / a purchase-order confirm could re-deal or retire a document a real Confirm press
  already promised. This is NOT reversible piecemeal (there is no record of which `auto`
  flips this statement itself made versus a pre-existing manual `False`), so the downgrade
  stays a no-op like the ack_state backfill beside it.
"""
import sqlalchemy as sa
from alembic import op

revision = "454_order_inquiry_born_ack"
down_revision = "453_shared_brand_attach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # S2: freeze every legacy, actually-human-confirmed row's links as manual BEFORE the
    # backfill below - otherwise the row born by a Confirm press before this deploy reads
    # identically to a row born acknowledged automatically by it, and an automatic pass
    # would be free to move a document a person already promised.
    op.execute(
        sa.text(
            """
            UPDATE projects.order_inquiry_links l
            SET auto = false
            FROM projects.order_inquiry_rows r
            WHERE l.row_id = r.id
              AND r.ack_state = 'acknowledged'
              AND r.acknowledged_by IS NOT NULL
              AND l.auto = true
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE projects.order_inquiry_rows
            SET ack_state = 'acknowledged',
                acknowledged_at = now() AT TIME ZONE 'utc',
                acknowledged_by = NULL
            WHERE ack_state = 'awaiting'
            """
        )
    )


def downgrade() -> None:
    # Not reversible in principle - the migration cannot tell a row it acknowledged from
    # one a real acknowledge press already reached, and un-acknowledging the second would
    # be wrong; the same is true of which `auto = false` flip above was this statement's
    # own and which pre-dated it. Left as a no-op, the same choice 428's own downgrade
    # made for the columns it could not un-backfill either.
    pass
