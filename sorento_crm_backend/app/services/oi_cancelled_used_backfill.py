"""Backfill: cancelled-line and used order inquiry rows go to To confirm.

PLAN-oi-cancelled-line-used-confirm.md (3.5, AC-CL-10/14): 344 rows measured live on a
cancelled line and 10 used rows were all auto-acknowledged before this lane's writers
existed to flag them going forward - `backfill_to_confirm` is the one-time catch-up, run
from the migration below (and driven directly by
`tests/test_oi_cancelled_line_used_confirm.py` against a scratch-schema Postgres
connection).

Built with SQLAlchemy Core against the mapped `OrderInquiryRow.__table__` /
`ProjectSalesOrderLine.__table__` / `SalesOrderLine.__table__`, never a raw `text()`
string naming a schema by hand: `ProjectSalesOrderLine` and `SalesOrderLine` share the
bare table name `sales_order_lines` in two different schemas (`projects` and the core
`public`), so an unqualified string is genuinely ambiguous, and a hand-qualified one
would bypass a scratch-schema test's `schema_translate_map` and reach the REAL tables
(the precedent `513_planning_gate_backfill.py` already established for the same reason).
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from app.models.order import SalesOrderLine
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)


def backfill_to_confirm(connection, cutoff: datetime) -> int:
    """Every acknowledged LIVE row (state not `cancelled`) on a cancelled line, and
    every acknowledged USED row whatever its line's own status, goes `changed` with
    `changed_at` set - the same handshake the lane's own writers stamp going forward.

    Only a row whose `acknowledged_at` is NULL or earlier than `cutoff` is touched
    (AC-CL-10): a row purchasing confirms AFTER this runs carries a later
    `acknowledged_at`, so re-running this at the same cutoff never re-flags it. A row
    already `awaiting`, `changed` or `rejected`, or one on an open/closed line that is
    not used, is left exactly as it is. Returns the number of rows changed.
    """
    rows = OrderInquiryRow.__table__
    mirrors = ProjectSalesOrderLine.__table__
    core_lines = SalesOrderLine.__table__

    on_a_cancelled_line = sa.exists().where(
        mirrors.c.id == rows.c.so_line_id,
        mirrors.c.core_sales_order_line_id == core_lines.c.id,
        core_lines.c.line_status == "cancelled",
    )
    target = (
        (rows.c.state != INQUIRY_CANCELLED)
        & (rows.c.ack_state == ACK_ACKNOWLEDGED)
        & (rows.c.acknowledged_at.is_(None) | (rows.c.acknowledged_at < cutoff))
        & (rows.c.redirected_to_pool.is_(True) | on_a_cancelled_line)
    )
    now = datetime.utcnow()
    result = connection.execute(
        sa.update(rows).where(target).values(ack_state=ACK_CHANGED, changed_at=now)
    )
    return result.rowcount
