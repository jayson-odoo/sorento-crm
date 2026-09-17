"""Board-raised order inquiry rows go back to To confirm at deploy

Revision ID: oicf_0001_board_rows_to_confirm
Revises: undo_0002_seed_undone
Create Date: 2026-09-17 00:00:00.000000

`PLAN-oi-confirm-per-so.md` S1 / R1 (owner ruling 17 Sep 2026). G4
(`454_order_inquiry_born_ack.py`) made every row born acknowledged and retired
purchasing's own Confirm press; this lane reverses that, so a row raised from the
fulfilment board is born `awaiting` again and purchasing's Confirm is what takes it on.

R1, the owner's own words: "Excel come in is confirmed, but those that flowed from
fulfilment planning shouldn't be confirmed yet; the user should go and confirm." Two very
different populations sit behind `ack_state = 'acknowledged'` at deploy:

* BOARD rows (`supply_decision_id IS NOT NULL`) - raised by a fulfilment-board confirm,
  the handshake this lane puts back. Measured on the 15 Sep copy: 74 open rows (36
  raised, 5 partly linked, 33 placed).
* SHEET rows (`supply_decision_id IS NULL`) - the one-off Excel migration
  (`project_order_inquiry_import_service.py`, `_confirmed_order_row`) and book-change
  derived rows with no decision either, which the owner names as Excel-origin for this
  backfill too. Measured the same day: 11,809 rows. These already went through
  purchasing's real process before this system existed; nothing here asks them to
  re-confirm it.

Scoped to OPEN board rows only - `state NOT IN ('cancelled', 'actioned')` - the same
carve-out `_retire_uncovered_rows` and `_only_cascade_links` already read for "is this row
still somebody's live work": a cancelled row was called off and an actioned one was
answered elsewhere, and asking either to be re-confirmed would be asking purchasing to
take on work that no longer exists or was already dealt with by a different door.
"""
import sqlalchemy as sa
from alembic import op

revision = "oicf_0001_board_rows_to_confirm"
down_revision = "undo_0002_seed_undone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE projects.order_inquiry_rows
            SET ack_state = 'awaiting',
                acknowledged_by = NULL,
                acknowledged_at = NULL
            WHERE supply_decision_id IS NOT NULL
              AND ack_state = 'acknowledged'
              AND state NOT IN ('cancelled', 'actioned')
            """
        )
    )


def downgrade() -> None:
    # Restores the acknowledgement this upgrade cleared, system-attributed
    # (`acknowledged_by IS NULL`) - the same convention `454_order_inquiry_born_ack.py`
    # uses for its own backfill, since no real actor is on record for either direction of
    # this flip. Scoped to what the upgrade itself could have touched: a board row still
    # `awaiting` with a `supply_decision_id`. A row purchasing has genuinely confirmed
    # SINCE the upgrade ran is left alone - it already reads `acknowledged` and this
    # would not find it.
    op.execute(
        sa.text(
            """
            UPDATE projects.order_inquiry_rows
            SET ack_state = 'acknowledged',
                acknowledged_at = now() AT TIME ZONE 'utc',
                acknowledged_by = NULL
            WHERE supply_decision_id IS NOT NULL
              AND ack_state = 'awaiting'
              AND state NOT IN ('cancelled', 'actioned')
            """
        )
    )
