"""The loading plan's open-demand reads can use the `sales_order_lines.product_id` index.

`_project_open_need` and `_open_lines` (app/services/scm/container_request_service.py)
filtered `sol.product_id::text = ANY(:pids)`: casting the indexed uuid column to text means
Postgres cannot use `ix_sales_order_lines_product_id` for that predicate and reads every
sales-order line instead (crew's prod trace, API-NONBLOCKING 28 Oct). Comparing the column
itself against `CAST(:pids AS uuid[])` keeps the index usable and returns the same rows: the
ids are product ids read from the database upstream, so every one is a valid uuid.

Checked on the plan of the exact SQL each function runs, with sequential scans priced out
(`enable_seqscan = off`), so the answer does not depend on how many rows a scratch schema has.
"""
from __future__ import annotations

import uuid

from sqlalchemy import event, text

from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.scm import container_request_service as svc
from tests._pg_fixture import blank_session


def _plan_of(db, call) -> str:
    """EXPLAIN of the statement `call` runs against sales_order_lines."""
    seen: list[tuple[str, dict]] = []
    conn = db.connection()

    def capture(_conn, _cursor, statement, parameters, _context, _many):
        if "sales_order_lines" in statement:
            seen.append((statement, parameters))

    event.listen(conn, "before_cursor_execute", capture)
    try:
        call()
    finally:
        event.remove(conn, "before_cursor_execute", capture)
    assert seen, "the function ran no query over sales_order_lines"
    statement, parameters = seen[0]
    conn.exec_driver_sql("SET LOCAL enable_seqscan = off")
    rows = conn.exec_driver_sql("EXPLAIN " + statement, parameters).all()
    return "\n".join(r[0] for r in rows)


def _uses_product_index(plan: str) -> bool:
    """The product filter is an index CONDITION, not a filter applied to rows already read
    (with seq scans off the planner may still walk a whole index in place of the table)."""
    return any(
        "Index Cond" in line and "product_id = ANY" in line for line in plan.splitlines()
    )


def test_project_open_need_can_use_the_product_index():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        plan = _plan_of(db, lambda: svc._project_open_need(db, {str(uuid.uuid4())}))
        assert _uses_product_index(plan), plan


def test_open_lines_can_use_the_product_index():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        plan = _plan_of(db, lambda: svc._open_lines(db, [str(uuid.uuid4())], {}))
        assert _uses_product_index(plan), plan
