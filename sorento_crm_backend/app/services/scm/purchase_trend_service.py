"""The mirror of the order trend, on the buy side: what we have actually purchased.

> "similar to SO - what is the trend of purchase, then the list of supplier, purchase
>  date, purchase quantity, purchase cost" (user markup, 2026-08-11)

The PO column on the plan is a bare number today - what the AutoCount book shows still
on order. It answers "how much is coming", never "who did we buy this from, and when".
This module answers that second question, from the same purchase ledger
`price_history_service` already reads, but keyed by product alone: the buyer wants the
whole purchase story for the item, not narrowed to one supplier pair.

Two facts, both stated plainly rather than judged:

- a monthly trend statement (`recent_qty` vs `previous_qty`, over a small window) so the
  reader can see at a glance whether buying has picked up or slowed down;
- the recent purchase lines themselves - who, when, how much, at what cost - capped to a
  handful so the popup stays a receipt, not a ledger dump.

A draft PO this run itself proposed is excluded, same as `price_history_service`: reading
the plan's own suggestion back as "what we bought" would let the system cite itself.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.trajectory import month_shift as _month_shift

#: The window the trend sentence compares: the last N months against the N before them.
#: Deliberately short - the buyer is asking "has this changed lately", not "over the year".
WINDOW_MONTHS = 3

#: Recent purchase lines shown per product. A receipt to verify, not the whole ledger.
LINE_CAP = 8

#: Statuses that are NOT evidence of a purchase, mirroring `price_history_service`: a
#: draft recommendation is this planner's own proposal, never something we actually bought.
_NOT_A_PURCHASE = ("draft_recommendation", "cancelled", "void")


_TREND_SQL = """
WITH pairs AS (
    SELECT DISTINCT r.product_id
    FROM scm.reorder_recommendation r
    WHERE r.run_id = CAST(:run_id AS uuid)
)
SELECT pol.product_id::text AS product_id,
       po.issue_date AS issue_date,
       pol.qty_ordered::numeric AS qty
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
JOIN pairs pr ON pr.product_id = pol.product_id
WHERE po.issue_date >= :since AND po.issue_date < :until
  AND po.status NOT IN :not_a_purchase
  {wh}
  {co}
"""

_LINES_SQL = """
WITH pairs AS (
    SELECT DISTINCT r.product_id
    FROM scm.reorder_recommendation r
    WHERE r.run_id = CAST(:run_id AS uuid)
),
purchases AS (
    SELECT pol.product_id::text AS product_id,
           s.supplier_code, s.supplier_name,
           po.po_number, po.issue_date, po.expected_date, po.status,
           pol.qty_ordered::numeric AS qty,
           pol.unit_cost::numeric AS unit_cost,
           COALESCE(pol.currency, po.currency) AS currency,
           ROW_NUMBER() OVER (
               PARTITION BY pol.product_id
               -- NULLS LAST: an undated line is the weakest evidence of "most recent".
               ORDER BY po.issue_date DESC NULLS LAST, pol.created_at DESC
           ) AS rn
    FROM purchase_order_lines pol
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    LEFT JOIN suppliers s ON s.id = po.supplier_id
    JOIN pairs pr ON pr.product_id = pol.product_id
    WHERE po.status NOT IN :not_a_purchase
      {wh}
      {co}
)
SELECT product_id, supplier_code, supplier_name, po_number, issue_date, expected_date,
       status, qty, unit_cost, currency
FROM purchases
WHERE rn <= :cap
ORDER BY product_id, issue_date DESC NULLS LAST
"""


def purchase_trend_for_run(
    db: Session, run_id: str, *, as_of: Optional[date] = None,
    warehouse_id: Optional[str] = None,
) -> dict[str, Any]:
    """Purchase facts for every product the run planned, keyed by product id.

    Unlike `price_history_service` (keyed by product+supplier, for "should we reuse this
    supplier's price"), this is the whole buy-side story for the item across every
    supplier - the question the popup answers is "what have we been buying", not "is this
    one supplier's price still good".

    `warehouse_id` (R15) narrows to ONE destination: the plan row's site pool. The PO cell
    the dialog explains counts that location and nothing else - not its project bins, whose
    stock an Order Inquiry already claims - so the receipts behind the number have to be
    narrowed the same way. A line with no destination at all is excluded by the same test,
    which is deliberate: it cannot be shown to have been bought for this pool. Omitting the
    argument leaves the existing whole-product read byte-identical.
    """
    as_of = as_of or date.today()
    # The month the run sits in is excluded, same reasoning as the order trend: a window
    # ending mid-month compares a partial month against whole ones.
    until = _month_shift(as_of, 0)
    recent_start = _month_shift(until, -WINDOW_MONTHS)
    prev_start = _month_shift(recent_start, -WINDOW_MONTHS)

    co, co_params = company_sql_predicate(db, "po.company_id", param_prefix="pht")
    co_clause = f"AND {co}" if co else ""
    wh_clause = "AND pol.warehouse_id = CAST(:warehouse_id AS uuid)" if warehouse_id else ""
    wh_params = {"warehouse_id": warehouse_id} if warehouse_id else {}
    trend_params = {
        "run_id": run_id, "since": prev_start, "until": until,
        "not_a_purchase": _NOT_A_PURCHASE, **wh_params, **co_params,
    }

    products = {
        r[0]: {"product_id": r[0]}
        for r in db.execute(text(
            "SELECT DISTINCT r.product_id::text FROM scm.reorder_recommendation r "
            "WHERE r.run_id = CAST(:run_id AS uuid)"
        ), {"run_id": run_id})
    }

    recent: dict[str, float] = {}
    previous: dict[str, float] = {}
    for r in db.execute(text(_TREND_SQL.format(co=co_clause, wh=wh_clause)),
                        trend_params).mappings().all():
        qty = float(r["qty"] or 0)
        bucket = recent if r["issue_date"] >= recent_start else previous
        bucket[r["product_id"]] = bucket.get(r["product_id"], 0.0) + qty

    lines: dict[str, list[dict[str, Any]]] = {}
    line_params = {
        "run_id": run_id, "not_a_purchase": _NOT_A_PURCHASE, "cap": LINE_CAP,
        **wh_params, **co_params,
    }
    for r in db.execute(text(_LINES_SQL.format(co=co_clause, wh=wh_clause)),
                        line_params).mappings().all():
        lines.setdefault(r["product_id"], []).append({
            "supplier_code": r["supplier_code"],
            "supplier_name": r["supplier_name"],
            "po_number": r["po_number"],
            "order_date": r["issue_date"].isoformat() if r["issue_date"] else None,
            # The two columns the PO dialog's History tab shows beside the price: when it
            # was promised, and what the document says it is now.
            "expected_date": r["expected_date"].isoformat() if r["expected_date"] else None,
            "status": r["status"],
            "qty": float(r["qty"] or 0),
            "unit_cost": float(r["unit_cost"]) if r["unit_cost"] is not None else None,
            "currency": r["currency"],
        })

    out: dict[str, Any] = {}
    for pid in products:
        out[pid] = {
            "recent_qty": recent.get(pid, 0.0),
            "previous_qty": previous.get(pid, 0.0),
            "lines": lines.get(pid, []),
        }

    return {"window_months": WINDOW_MONTHS, "products": out}
