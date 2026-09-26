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

P8 is RETIRED (PLAN-reorder-one-formula.md, 11 Sep 2026): every row's own PO is netted
ONCE, by the engine, since #828 - project demand is inside `net` the same way retail is,
so a project-only row still needs its "Use PO" part shown, or the Suggestion's own
identity (`Stock + PO + Buy = need`) breaks for exactly that row. Receipts are served for
EVERY pair the run planned now, project-only or not.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.pool_predicate import ACTIVE_SITE_POOL_SQL

#: PLAN-po-spo-site-pool-and-order-sheet-downloads.md, S2 (AC-9). `pairs` still keys off
#: the run's own recommendation rows, but a PAIR's own line-matching rule differs by
#: grain: a PRODUCT-grain pair
#: (`warehouse_id IS NULL`) serves every open line to ANY active site-pool warehouse for
#: the product - product-wide, the same rule the cell itself sums (`site_pool_supply.
#: open_po_by_product`) - while a LOCATION-grain pair serves lines to its OWN warehouse,
#: and only when that warehouse is itself an active site pool (a rec sitting at a project
#: bin therefore serves nothing, same as the cell reads 0 there). Before this, `pr.
#: warehouse_id IS NOT DISTINCT FROM pol.warehouse_id` required a NULL pair to match a
#: NULL line warehouse - which real PO lines essentially never carry - so the product-
#: grain key never matched a receipt at all.
#:
#: Company-scoped by hand (security S2, review fix round A): `purchase_order_lines` is
#: raw SQL here, so the ORM isolation filter never sees it - without `{co_clause}` another
#: company's open PO line for the same product id would print as "Use PO" on this one.
def _po_book_sql(co_clause: str) -> str:
    return f"""
    WITH pairs AS (
        SELECT DISTINCT rr.product_id, rr.warehouse_id
        FROM scm.reorder_recommendation rr
        WHERE rr.run_id = :run_id
        -- P8 is retired (PLAN-reorder-one-formula.md): the engine nets the open PO book
        -- for every row since #828, so a project-only cell hiding its own receipts broke
        -- the identity Stock + PO + Buy = need for exactly that row. The PO part shows
        -- whenever the row carries one, project-only or not.
    )
    SELECT pr.product_id::text AS product_id,
           pr.warehouse_id::text AS pair_warehouse_id,
           po.po_number,
           po.status,
           po.expected_date,
           (pol.qty_ordered - pol.qty_received) AS remaining
    FROM pairs pr
    JOIN purchase_order_lines pol ON pol.product_id = pr.product_id
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    JOIN warehouses w ON w.id = pol.warehouse_id
    WHERE po.status = ANY(ARRAY['active', 'received', 'partial', 'closed'])
      AND pol.line_status = 'open'
      AND pol.qty_ordered > pol.qty_received
      {co_clause}
      AND (
            (pr.warehouse_id IS NULL AND {ACTIVE_SITE_POOL_SQL})
            OR (pr.warehouse_id IS NOT NULL AND pol.warehouse_id = pr.warehouse_id
                AND {ACTIVE_SITE_POOL_SQL})
          )
    ORDER BY po.expected_date NULLS LAST, po.po_number
"""


def po_book_for_run(db: Session, run_id: str) -> dict[str, Any]:
    """Open PO lines for every pair the run planned, keyed ``product_id:warehouse_id``
    (P8 retired, PLAN-reorder-one-formula.md - a project-only cell is served too)."""
    co, co_params = company_sql_predicate(db, "pol.company_id", param_prefix="pbk")
    co_clause = f"AND {co}" if co else ""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in db.execute(
        text(_po_book_sql(co_clause)), {"run_id": run_id, **co_params}
    ).mappings().all():
        key = f"{r['product_id']}:{r['pair_warehouse_id'] or ''}"
        out.setdefault(key, []).append({
            "po_number": r["po_number"],
            "status": r["status"],
            "expected_date": r["expected_date"].isoformat() if r["expected_date"] else None,
            "remaining": float(r["remaining"]),
        })
    return {"po_book": out, "count": len(out)}
