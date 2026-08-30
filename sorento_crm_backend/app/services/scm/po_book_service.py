"""S15: the open PO lines behind a plan row's "Use PO" suggestion.

> "if there is outstanding PO already then why should i buy ... I was expecting the system
>  to suggest me to use the PO quantity and don't need to order"

The engine's netting does NOT count the PO book (incoming = SPO allocation, the standing
rule; the book is an AutoCount import that can be stale, and quietly netting it would
silently unbuy every row). What the buyer needs instead is the RECEIPTS: which purchase
orders already carry this product to this warehouse, how much of each is still to come,
and when it was promised - so "Use PO, don't order" is a decision they can verify, not a
figure they must trust.

The openness predicate here MUST stay identical to `scm.po_ordered_v` (the checklist
column the plan already shows), or the popup's receipts would not sum to the number on
the row.

RETAIL ONLY (P8, `PLAN-scm-purchasing-uat-journey.md`; captain: "why does reorder planning
consider outstanding PO again when the OI already links to it"). A project row's purchase
order is consumed by the ORDER INQUIRY: the raised row links to the PO line and the plan's
Project figure drops by exactly that much. Offering the same PO again on the plan is the
same quantity twice, and the buyer handles it twice. So a row whose demand is entirely
project-class serves no receipts here and the plan shows it no "Use PO" - while retail,
which has no Order Inquiry at all, keeps it: the plan is the only place a retail demand and
a purchase order ever meet.

Entirely project-class is the test, not "has any project demand". A cell carrying both
channels has a retail need that nothing else nets against a PO, and hiding the receipts
there would leave that half of the row buying what is already ordered.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Mirrors scm.po_ordered_v exactly - one definition of "still to come" per screen.
_PO_BOOK_SQL = """
    WITH pairs AS (
        SELECT DISTINCT rr.product_id, rr.warehouse_id
        FROM scm.reorder_recommendation rr
        WHERE rr.run_id = :run_id
          -- P8: a cell whose demand is ALL project gets no receipts. A run frozen before
          -- the channel split states neither figure, so both COALESCE to 0, the row is not
          -- project-only, and its receipts are served exactly as they always were.
          AND NOT (COALESCE((rr.inputs ->> 'project_committed')::numeric, 0) > 0
                   AND COALESCE((rr.inputs ->> 'retail_committed')::numeric, 0) = 0)
    )
    SELECT pol.product_id::text AS product_id,
           pol.warehouse_id::text AS warehouse_id,
           po.po_number,
           po.status,
           po.expected_date,
           (pol.qty_ordered - pol.qty_received) AS remaining
    FROM purchase_order_lines pol
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    JOIN pairs pr ON pr.product_id = pol.product_id
              AND pr.warehouse_id IS NOT DISTINCT FROM pol.warehouse_id
    WHERE po.status = ANY(ARRAY['active', 'received', 'partial', 'closed'])
      AND pol.line_status = 'open'
      AND pol.qty_ordered > pol.qty_received
    ORDER BY po.expected_date NULLS LAST, po.po_number
"""


def po_book_for_run(db: Session, run_id: str) -> dict[str, Any]:
    """Open PO lines for every RETAIL-facing pair the run planned, keyed
    ``product_id:warehouse_id``. A project-only cell is absent, which is what removes
    "Use PO" from a project row (P8)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in db.execute(text(_PO_BOOK_SQL), {"run_id": run_id}).mappings().all():
        key = f"{r['product_id']}:{r['warehouse_id'] or ''}"
        out.setdefault(key, []).append({
            "po_number": r["po_number"],
            "status": r["status"],
            "expected_date": r["expected_date"].isoformat() if r["expected_date"] else None,
            "remaining": float(r["remaining"]),
        })
    return {"po_book": out, "count": len(out)}
