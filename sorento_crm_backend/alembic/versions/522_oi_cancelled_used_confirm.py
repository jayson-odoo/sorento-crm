"""Backfill: every live order inquiry row on a cancelled line, and every used row, goes
back to To confirm.

PLAN-oi-cancelled-line-used-confirm.md (3.5, AC-CL-10/14), owner rulings C1/C3, 20 Sep
2026. Purchasing never heard about a cancelled sales order line or a used row before this
lane's writers existed - measured on the 18 Sep 2026 prod copy: 344 live rows sit on a
cancelled line, 343 of them auto-acknowledged; 10 used rows, all auto-acknowledged. This
is the one-time catch-up for those rows; `flag_rows_for_cancelled_lines` and
`_redirect_row_if_received` (this lane's own writers) keep the count from growing again.

Data-only, no schema change. 3.5a (correction, 20 Sep 2026): the cutoff is this
migration's own RUN time, `datetime.utcnow()` at `upgrade()`, not a literal fixed at
authoring time. The sheet importer stamps `acknowledged_at` with the UPLOAD time on
every born-acknowledged row, and the owner rolled back and re-uploaded both books on
prod on 20 Sep after #1050 deployed - a literal written when this file was authored is
already older than those stamps, and older still than any upload between authoring and
deploy, so it would skip the very rows the owner reported. Idempotency does not depend
on a fixed cutoff: `backfill_to_confirm(connection, cutoff)` only touches a row whose
`acknowledged_at` is NULL or earlier than WHATEVER cutoff it is given, so a row
purchasing confirms after this migration runs carries a later `acknowledged_at` and is
never re-flagged by a later run at a later cutoff (AC-CL-10) - alembic applies a
revision once per database in any case, so nothing here actually replays.

Downgrade is a no-op: the rows this stamps `changed` are exactly the ones purchasing had
not yet been told about, and reverting the stamp would silently un-notify them of a
cancellation or a used row that is still true - there is no way back that is not itself a
guess, the same reasoning `oioh_0001_one_header_per_so.py` downgrades on.

Revision ID: 522_oi_cancelled_used_confirm
Revises: 521_sales_report_month_fix
Create Date: 2026-09-20
"""
from __future__ import annotations

from datetime import datetime

from alembic import op

from app.services.oi_cancelled_used_backfill import backfill_to_confirm

revision = "522_oi_cancelled_used_confirm"
down_revision = "521_sales_report_month_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 3.5a: the RUN time, not a literal fixed at authoring time - see the module
    # docstring for why an authoring-time literal would miss the owner's own 20 Sep
    # re-upload.
    connection = op.get_bind()
    changed = backfill_to_confirm(connection, cutoff=datetime.utcnow())
    print(f"522_oi_cancelled_used_confirm: flagged {changed} row(s) to To confirm")


def downgrade() -> None:
    # No-op by design - see the module docstring.
    pass
