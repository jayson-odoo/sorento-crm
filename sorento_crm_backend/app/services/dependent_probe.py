"""Who points at this row? Asked of `pg_catalog`, never discovered by failing.

Two callers need the same answer for opposite reasons, so it is written once
here rather than twice in either of them:

* `deletion_service` asks before removing a record the ESB says is gone
  upstream. Half the foreign keys pointing at these tables are `ON DELETE SET
  NULL` - `sales_orders.customer_id` is one - so a bare `DELETE` of a customer
  with a hundred orders SUCCEEDS and leaves a hundred orders belonging to
  nobody. The data is not gone, it is silently detached, and the sync reports a
  clean removal.
* `document_ingest_service` asks before removing a document LINE the pushed
  payload no longer carries. `scm.loading_plan_line.po_line_id` is `ON DELETE
  CASCADE`, so deleting a purchase-order line destroys loading-plan rows
  outright, and five more referrers (`stock_transfers.so_line_id`,
  `scm.order_link_claim`, `projects.order_inquiry_rows.po_line_id`,
  `spo_allocations`, `picking_lines`) are SET NULL and would be orphaned.

Resolved through the CURRENT `search_path` via `to_regclass`, never
`public.`-qualified: `sales_orders`, `sales_order_lines` and their purchase
twins exist a SECOND time in the `projects` schema, and the test substrate is a
scratch schema entirely - a hard-coded `public.` would have every probe read the
REAL database.

A composite foreign key contributes one row per column, so a two-column key is
probed as two independent single-column matches. That can only ever over-report
a dependent, which costs a hard delete and gives a cancellation instead; the
reverse mistake - removing a row something points at - is the one that loses
data.

The referrer list is NOT cached. One catalogue query per row is cheap at these
batch sizes; the trigger for caching it is a batch showing up in the slow-query
log, and this sentence is where that decision is written down rather than built.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_REFERRERS_SQL = text(
    """
    SELECT c.conrelid::regclass::text AS referrer, a.attname AS col
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
    WHERE c.contype = 'f' AND c.confrelid = to_regclass(:table)
    """
)


def referrers_of(db: Session, table: str) -> list[tuple[str, str]]:
    """(referring relation, column) for every foreign key pointing at ``table``.

    The relation name comes back the way the catalogue renders it: qualified
    exactly when it is NOT what the bare name resolves to under the current
    `search_path`. Compare it with `relation_name` below, never with a bare
    string.
    """
    rows = db.execute(_REFERRERS_SQL, {"table": table}).fetchall()
    return [(row[0], row[1]) for row in rows]


def relation_name(db: Session, table: str) -> Optional[str]:
    """What a bare table name resolves to under the current ``search_path``."""
    return db.execute(text("SELECT to_regclass(:t)::text"), {"t": table}).scalar()


def row_exists_referencing(db: Session, referrer: str, column: str, row_id) -> bool:
    """Whether ``referrer.column`` holds ``row_id``.

    The relation and column names come from the catalogue, never from a payload;
    the id is always bound.
    """
    return bool(
        db.execute(
            text(f'SELECT EXISTS (SELECT 1 FROM {referrer} WHERE "{column}" = :id)'),
            {"id": str(row_id)},
        ).scalar()
    )


def is_referenced(
    db: Session, table: str, row_id, *, skip_relation: Optional[str] = None
) -> bool:
    """Whether anything at all points at one row of ``table``.

    ``skip_relation`` names a referrer that is part of the row rather than a
    dependent on it - a document's own line table, which cascades with its
    header. Give it a value from `relation_name`, not a bare table name.
    """
    for referrer, column in referrers_of(db, table):
        if skip_relation is not None and referrer == skip_relation:
            continue
        if row_exists_referencing(db, referrer, column, row_id):
            logger.info(
                "dependent_probe.found table=%s id=%s referrer=%s.%s",
                table,
                row_id,
                referrer,
                column,
            )
            return True
    return False
