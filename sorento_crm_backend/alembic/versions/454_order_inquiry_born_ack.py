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
"""
import sqlalchemy as sa
from alembic import op

revision = "454_order_inquiry_born_ack"
down_revision = "453_shared_brand_attach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE projects.order_inquiry_rows
            SET ack_state = 'acknowledged',
                acknowledged_at = now(),
                acknowledged_by = NULL
            WHERE ack_state = 'awaiting'
            """
        )
    )


def downgrade() -> None:
    # Not reversible in principle - the migration cannot tell a row it acknowledged from
    # one a real acknowledge press already reached, and un-acknowledging the second would
    # be wrong. Left as a no-op, the same choice 428's own downgrade made for the columns
    # it could not un-backfill either.
    pass
