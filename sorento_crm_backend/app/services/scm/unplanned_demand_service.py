"""Demand that arrived with no stated location, and how much of the plan rests on it.

Planning nets stock against demand per product AND location, so a sales-order line naming
no warehouse once had nothing to net against and vanished. On the customer's own book that
is 8,011 of 8,136 open lines.

It is planned now: ``reorder_run_service._apply_unlocated_demand`` lands it on the location
holding the most of each item. This module is what lets the page SAY so, because a plan
part-built on demand nobody located should not present all of it as equally confirmed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.demand import PLAN_DEMAND_LINE_SQL, PLAN_DEMAND_ORDER_SQL

# The same filter `scm.committed_v` applies, so the count is of exactly the demand the plan
# would have used had it carried a location. Restated rather than read from the view because
# the view has already grouped away the line-level detail.
_OPEN_LINE = (
    "so.status = 'open' AND sol.line_status = 'open' "
    "AND sol.purchasing_status <> 'covered' "
    "AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
    "             - COALESCE(sol.qty_delivered, 0), 0) > 0 "
    # S13b plus front planning 13.4: the same order-level AND line-level rules
    # committed_v applies, restated for the same reason the open-line rule already is -
    # this reports the demand the plan WOULD have used, so a line CS has already decided
    # is no more part of it here than it is there.
    f"AND {PLAN_DEMAND_ORDER_SQL} AND {PLAN_DEMAND_LINE_SQL}"
)
_OPEN_QTY = ("GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
             "         - COALESCE(sol.qty_delivered, 0), 0)")

# The banner names a few products so the reader can go and look at one, rather than being
# handed a number they can do nothing with.
SAMPLE_SIZE = 5


def unlocated_demand(db: Session) -> dict[str, Any]:
    """How much open demand carries no stock location, with a few products named."""
    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="uld")
    co_clause = f"AND {co}" if co else ""

    totals = db.execute(text(f"""
        SELECT count(*) AS lines,
               count(DISTINCT sol.product_id) AS products,
               COALESCE(sum({_OPEN_QTY}), 0) AS quantity
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        WHERE sol.warehouse_id IS NULL
          AND {_OPEN_LINE}
          {co_clause}
    """), co_params).mappings().first()

    sample = db.execute(text(f"""
        SELECT p.product_code, SUM({_OPEN_QTY}) AS quantity
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        JOIN products p ON p.id = sol.product_id
        WHERE sol.warehouse_id IS NULL
          AND {_OPEN_LINE}
          {co_clause}
        GROUP BY p.product_code
        ORDER BY SUM({_OPEN_QTY}) DESC, p.product_code
        LIMIT :limit
    """), {**co_params, "limit": SAMPLE_SIZE}).mappings().all()

    return {
        "lines": int(totals["lines"] or 0),
        "products": int(totals["products"] or 0),
        "quantity": float(totals["quantity"] or 0),
        "sample": [
            {"product_code": r["product_code"], "quantity": float(r["quantity"] or 0)}
            for r in sample
        ],
    }
