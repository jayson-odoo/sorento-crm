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
    """Open PO lines for every pair the run planned, keyed ``product_id:warehouse_id``."""
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
