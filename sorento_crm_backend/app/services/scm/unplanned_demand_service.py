"""Demand the plan cannot see, and why.

Planning nets stock against demand per product AND location. A sales-order line that names
no warehouse therefore has nothing to net against: it is real, committed, and invisible to
every recommendation. On the customer's own book that is 8,011 of 8,136 open lines.

Nothing here decides where that demand SHOULD land - that is a business rule about which
location serves an order nobody located, and it is not the engine's to invent. This module
only counts it and says so, because a plan that quietly omits 97% of the demand is worse
than one that admits it.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate

# The same filter `scm.committed_v` applies, so the count is of exactly the demand the plan
# would have used had it carried a location. Restated rather than read from the view because
# the view has already grouped away the line-level detail.
_OPEN_LINE = (
    "so.status = 'open' AND sol.line_status = 'open' "
    "AND sol.purchasing_status <> 'covered' "
    "AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
    "             - COALESCE(sol.qty_delivered, 0), 0) > 0"
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
