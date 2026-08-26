"""Project demand that is AWAITING CS - counted and named, never netted.

> "order inquiry is only for project side" - and, since P3 (captain, 26 Aug 2026), only
> the Order Inquiry: project demand is the un-linked remainder of raised OI rows and
> nothing else counts.

So a project-class sales-order line becomes plan demand only once CS has decided it on the
fulfilment board and raised the Buy. Until then it is set aside, and this module is the
report that says how much - so a planner looking at a smaller-than-expected plan sees WHY
rather than distrusting the engine, and so the work sitting on CS's desk has a number.

Two kinds of order land here, and P3 is what joined them:

* a project SO no Order Inquiry ever named (the original S13b case, 2026-08-10);
* a SHEET-ORIGIN project SO - `demand_origin = 'scm_order_inquiry'`, the old Joey feed -
  that nobody has confirmed on the board. It used to be netted through `committed_v`'s
  sheet leg, which is how M310-CR-PJ showed 16 units at BRW-BB with every one of its
  inquiry rows already placed. QP3 ruled there is no backfill: those orders wait for CS.

The test is therefore the DECISION, not the origin stamp: a project line an active supply
decision covers is CS's, and every other open project line is waiting for them. Same shape
as `unplanned_demand_service` - totals plus a few named documents, because a bare number is
something the reader can do nothing with.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.demand import PLAN_DEMAND_LINE_SQL, PROJECT_CLASS

#: A few documents named so the reader can go and look at one.
SAMPLE_SIZE = 5

# The line-level half restated exactly as `scm.committed_v` applies it, so "set aside"
# means precisely "would have been demand but for the order-level rule" - nothing more.
_OPEN_QTY = ("GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
             "       - COALESCE(sol.qty_delivered, 0), 0)")
_OPEN_LINE = (
    "so.status = 'open' AND sol.line_status = 'open' "
    "AND sol.purchasing_status <> 'covered' "
    f"AND {_OPEN_QTY} > 0"
)
# What the split excludes: a project-class line no active supply decision covers.
# `PLAN_DEMAND_LINE_SQL` is imported rather than restated, so "set aside" means precisely
# "a line the fulfilment board has not decided" and the two cannot drift - it is the same
# predicate the board itself reads as NOT covered.
_SET_ASIDE = f"so.demand_class = '{PROJECT_CLASS}' AND {PLAN_DEMAND_LINE_SQL}"


def set_aside_project_demand(
    db: Session, *, product_ids: Optional[Sequence[str]] = None
) -> dict[str, Any]:
    """Project-class open demand the plan did NOT count, because CS has not decided it.

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
