"""What the demand split set aside, counted and named.

> "order inquiry is only for project side" - and the user's decision (2026-08-10) on the
> order that falls between the rules: a project SO no Order Inquiry names is "set aside and
> counted", NOT demand and NOT silently dropped.

`scm.committed_v` excludes those orders (the order-level rule in `demand.py`). This module
is the other half of that decision: the report that says how much was excluded, so a
planner looking at a smaller-than-expected plan can see WHY rather than distrusting the
engine. Same shape as `unplanned_demand_service` - totals plus a few named documents,
because a bare number is something the reader can do nothing with.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.demand import ORDER_INQUIRY_ORIGIN, PROJECT_CLASS

#: A few documents named so the reader can go and look at one.
SAMPLE_SIZE = 5

# The line-level half restated exactly as `scm.committed_v` applies it, so "set aside"
# means precisely "would have been demand but for the order-level rule" - nothing more.
_OPEN_QTY = ("GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
             "         - COALESCE(sol.qty_delivered, 0), 0)")
_OPEN_LINE = (
    "so.status = 'open' AND sol.line_status = 'open' "
    "AND sol.purchasing_status <> 'covered' "
    f"AND {_OPEN_QTY} > 0"
)
# The orders the split excludes: project class, not originated by the Order Inquiry.
_SET_ASIDE = (
    f"so.demand_class = '{PROJECT_CLASS}' "
    f"AND (so.demand_origin IS NULL OR so.demand_origin <> '{ORDER_INQUIRY_ORIGIN}')"
)


def set_aside_project_demand(
    db: Session, *, product_ids: Optional[Sequence[str]] = None
) -> dict[str, Any]:
    """Project-class open demand the plan did NOT count, because no inquiry named it.

    `product_ids` narrows the report to the products a caller is looking at (a run's own
    products, a test's marker set); None reports the whole book.
    """
    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="sap")
    clauses = [f"AND {co}"] if co else []
    params: dict[str, Any] = dict(co_params)
    if product_ids is not None:
        clauses.append("AND sol.product_id::text = ANY(:sap_pids)")
        params["sap_pids"] = [str(p) for p in product_ids]
    extra = " ".join(clauses)

    totals = db.execute(text(f"""
        SELECT count(DISTINCT so.id) AS orders,
               count(*) AS lines,
               COALESCE(sum({_OPEN_QTY}), 0) AS quantity
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        WHERE {_SET_ASIDE} AND {_OPEN_LINE} {extra}
    """), params).mappings().first()

    sample = db.execute(text(f"""
        SELECT so.so_number, COALESCE(c.customer_name, so.internal_note) AS who,
               SUM({_OPEN_QTY}) AS quantity
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        LEFT JOIN customers c ON c.id = so.customer_id
        WHERE {_SET_ASIDE} AND {_OPEN_LINE} {extra}
        GROUP BY so.so_number, COALESCE(c.customer_name, so.internal_note)
        ORDER BY SUM({_OPEN_QTY}) DESC
        LIMIT :sap_limit
    """), {**params, "sap_limit": SAMPLE_SIZE}).mappings().all()

    return {
        "orders": int(totals["orders"] or 0),
        "lines": int(totals["lines"] or 0),
        "quantity": float(totals["quantity"] or 0),
        "sample": [
            {
                "so_number": r["so_number"],
                "who": r["who"],
                "quantity": float(r["quantity"] or 0),
            }
            for r in sample
        ],
    }
