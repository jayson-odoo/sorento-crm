"""OI-DATE-WAS-FIX: give back the told date the oiod_0001 backfill took from rows whose
SO line still has a PENDING delayed/advanced planning change.

oiod_0001 moved every live row's told date (``delivery_date``) to its SO line date, including
rows whose line move was still waiting for CS Confirm. At that Confirm the row already
carries the new date, so ``_stamp_date_move``, ``handover_moves`` and the planning change
notice all see no move, and purchasing gets no DELAY / ADVANCE email. This puts those rows
back on the date purchasing was last told, so the next Confirm emails as normal.

A row is restored when it is logged in ``projects.oi_delivery_date_backfill``, is a live
buy row (ORDER / ORDER_BACK, not cancelled, not redirected to the pool: the only rows a
Confirm stamps), still sits on the date the backfill gave it (told date differs from the
logged old one and its Was still equals that old one: no Confirm has moved it since), and
its SO line has a ``planning_change_rows`` row in ``applied_state`` pending whose from and
to ``required_date`` are both set and differ. That is every pending date move, whatever its
kind: a later upload that only changed the qty supersedes a ``delayed`` row with a
``qty_up`` one that carries the original from date forward
(``planning_change_service.build_batch``). It gets ``delivery_date`` and
``previous_delivery_date`` back exactly as logged. The screen normally does not change: the
shown date is the SO line date and the Was reads the told date first
(``app/services/oi_delivery_date.py`` ``was_of``); it can differ only on the rare row whose
old told date was blank or whose line has since moved back to it.

Each restored row is logged first in ``projects.oi_delivery_date_pending_restore`` (row id,
the date and Was it had before this ran) so the downgrade puts them back exactly. Raw SQL:
no audit row, no planning change, no email. The same read-only selection for DBeaver is
``documentation/plans/scm/SQL-oi-date-was-fix-count-04nov.sql``.

Revision ID: oiod_0002_pending_restore
Revises: cer_0001_client_error_report
"""
from alembic import op


revision = "oiod_0002_pending_restore"
down_revision = "cer_0001_client_error_report"
branch_labels = None
depends_on = None

#: Rows the backfill moved whose line move is still pending CS Confirm.
_SWALLOWED = """
    SELECT r.id AS row_id,
           r.delivery_date AS from_delivery_date,
           r.previous_delivery_date AS from_previous_delivery_date
    FROM projects.oi_delivery_date_backfill b
    JOIN projects.order_inquiry_rows r ON r.id = b.row_id
    WHERE r.state <> 'cancelled'
      AND r.verb IN ('ORDER', 'ORDER_BACK')
      AND NOT COALESCE(r.redirected_to_pool, false)
      AND r.delivery_date IS DISTINCT FROM b.old_delivery_date
      AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_delivery_date
      AND EXISTS (
            SELECT 1 FROM projects.planning_change_rows pc
            WHERE pc.project_line_id = r.so_line_id
              AND pc.applied_state = 'pending'
              AND pc.from_json ->> 'required_date' IS NOT NULL
              AND pc.to_json ->> 'required_date' IS NOT NULL
              AND pc.from_json ->> 'required_date' <> pc.to_json ->> 'required_date'
          )
"""


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS projects.oi_delivery_date_pending_restore ("
        "row_id uuid PRIMARY KEY, "
        "from_delivery_date date, "
        "from_previous_delivery_date date, "
        "restored_at timestamp NOT NULL DEFAULT now())"
    )
    op.execute(
        "INSERT INTO projects.oi_delivery_date_pending_restore "
        "(row_id, from_delivery_date, from_previous_delivery_date) "
        f"SELECT s.row_id, s.from_delivery_date, s.from_previous_delivery_date FROM ({_SWALLOWED}) s "
        "ON CONFLICT (row_id) DO NOTHING"
    )
    op.execute(
        "UPDATE projects.order_inquiry_rows r "
        "SET delivery_date = b.old_delivery_date, "
        "previous_delivery_date = b.old_previous_delivery_date "
        f"FROM ({_SWALLOWED}) s "
        "JOIN projects.oi_delivery_date_backfill b ON b.row_id = s.row_id "
        "WHERE r.id = s.row_id"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE projects.order_inquiry_rows r "
        "SET delivery_date = p.from_delivery_date, "
        "previous_delivery_date = p.from_previous_delivery_date "
        "FROM projects.oi_delivery_date_pending_restore p "
        "JOIN projects.oi_delivery_date_backfill b ON b.row_id = p.row_id "
        "WHERE r.id = p.row_id "
        # Only a row still as the upgrade left it: a Confirm since then is real news.
        "AND r.delivery_date IS NOT DISTINCT FROM b.old_delivery_date "
        "AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_previous_delivery_date"
    )
    op.execute("DROP TABLE IF EXISTS projects.oi_delivery_date_pending_restore")
