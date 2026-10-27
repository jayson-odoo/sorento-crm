"""Who a product was last bought from: the ONE "last PO supplier" rule (owner ruling 27 Oct 2026,
STOCK-POSITION-REPORT Q4: "supplier = the LAST PO supplier, using the SAME function Stock Debt and
the low stock report already use").

The supplier on the product's NEWEST purchase-order line:

* newest = `purchase_orders.issue_date` desc (an undated PO last), then the line's `created_at`
  desc, then `po_number` desc, then the line id desc. The last two are STOCKDEBT-PERF's
  tiebreak (#1901): an exact tie never falls to the query plan;
* a cancelled PO does not exist for this lookup (PLAN-product-supplier-all-po.md ruling 3), and
  neither does a PO with no supplier: the next-newest PO names it (the low stock report's rule,
  whose SQL inner-joined `suppliers`);
* a removed line counts in nothing (AC-REMOVED-KEEP-CANCELLED);
* a product with no PO line gets no entry. `product_suppliers` plays no part: on the live data
  nearly every link names the DEFAULT supplier (`summary_order_service._last_po_supplier_map`'s
  docstring has the measurement), so a link fallback is the caller's choice, never this rule's.

Readers: the stock position report, the low stock report's Supplier column
(`summary_order_service._last_po_supplier_map`). Stock Debt's `_last_supplier_map` asks the same
question with this ordering (#1901) and moves onto this helper once #1901 merges (it then skips a
supplier-less PO as well, where today it would answer "no supplier" for that product).

Not yet on this rule (named, not changed in this lane): `supply_origin` and
`scripts/backfill_product_supplier_from_last_po.py`, which repeat the older
`po.created_at, supplier_id` tiebreak in their own SQL.
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.company_scope import build_company_predicate


def last_po_supplier_ids(db: Session, product_ids: Optional[Sequence[str]]) -> dict[str, str]:
    """`{product_id: supplier_id}` for these products (None = every product) that have a PO line."""
    if product_ids is not None and not product_ids:
        return {}
    rn = (
        func.row_number()
        .over(
            partition_by=PurchaseOrderLine.product_id,
            order_by=(
                PurchaseOrder.issue_date.desc().nulls_last(),
                PurchaseOrderLine.created_at.desc(),
                PurchaseOrder.po_number.desc(),
                PurchaseOrderLine.id.desc(),
            ),
        )
        .label("rn")
    )
    numbered = (
        db.query(PurchaseOrderLine.product_id, PurchaseOrder.supplier_id, rn)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrder.status != "cancelled",
            PurchaseOrder.supplier_id.isnot(None),
            PurchaseOrderLine.removed_unreferenced.is_(False),
        )
    )
    if product_ids is not None:
        numbered = numbered.filter(PurchaseOrderLine.product_id.in_(list(product_ids)))
    # Company scope stated on both tables, as Stock Debt's `_last_supplier_map` does: the session
    # listener scopes this query today, and the explicit predicate keeps the rule independent of it.
    for model in (PurchaseOrderLine, PurchaseOrder):
        predicate = build_company_predicate(model, get_company_scope(db))
        if predicate is not None:
            numbered = numbered.filter(predicate)
    numbered = numbered.subquery()
    return {
        str(pid): str(sid)
        for pid, sid in db.query(numbered.c.product_id, numbered.c.supplier_id)
        .filter(numbered.c.rn == 1)
        .all()
    }
