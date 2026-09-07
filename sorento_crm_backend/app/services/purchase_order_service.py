"""Purchase orders placed but not yet received (A5, chatbot-growth-r1).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` AC-907, AC-909.

One focused module rather than growing `procurement_service.py` (already ~6,200
lines) - this reads two tables and writes nothing.

PO and SPO are never netted (`spo_allocations.po_line_id` is NULL on every row,
decision 6 Aug 2026, see `PLAN-chatbot-growth-r1.md` A5), so `outstanding_qty`
here is `qty_ordered - qty_received` ONLY - incoming SPO receipts never reduce
it.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product

PO_GROUP_BY_AXES: frozenset[str] = frozenset({"product", "supplier", "date"})


def _plain_number(v: Any) -> Any:
    if v is None:
        return None
    from decimal import Decimal

    try:
        d = Decimal(str(v))
    except Exception:  # noqa: BLE001
        return v
    return int(d) if d == d.to_integral_value() else float(d)


def purchase_orders_placed_rows(
    db: Session,
    *,
    product_ids: Optional[list[str]] = None,
    expected_date_from=None,
    expected_date_to=None,
    sort: str = "expected_date",
    dir: str = "asc",
    limit: int = 500,
) -> list[dict]:
    """Open PO lines: `qty_ordered - qty_received > 0`, `line_status='open'`.

    One row per line - PO number, product, outstanding qty, expected date
    (line, else header), supplier. `supplier` is ALWAYS populated here; the
    restricted-field drop that hides it from a dealer runs downstream in
    `output_structurer` (`restricted_fields`), never here - the MCP itself
    stays unfiltered (Slice A design).
    """
    delta = PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received
    q = (
        db.query(PurchaseOrderLine, PurchaseOrder, Product, Supplier)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .join(Product, Product.id == PurchaseOrderLine.product_id)
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(PurchaseOrderLine.line_status == "open", delta > 0)
    )
    if product_ids:
        q = q.filter(PurchaseOrderLine.product_id.in_(product_ids))
    # Line `expected_date` else header's - COALESCE, not a Python fallback, so
    # the date filter and the sort both see the same effective value.
    effective_date = func.coalesce(PurchaseOrderLine.expected_date, PurchaseOrder.expected_date)
    if expected_date_from is not None:
        q = q.filter(effective_date >= expected_date_from)
    if expected_date_to is not None:
        q = q.filter(effective_date <= expected_date_to)

    sort_col = {
        "expected_date": effective_date,
        "product": Product.product_code,
        "supplier": Supplier.supplier_name,
        "outstanding_qty": delta,
    }.get(sort, effective_date)
    order = sort_col.desc() if dir == "desc" else sort_col.asc()
    rows = (
        q.order_by(order.nulls_last(), PurchaseOrder.po_number.asc())
        .limit(limit)
        .all()
    )
    out: list[dict] = []
    for line, po, product, supplier in rows:
        expected = line.expected_date or po.expected_date
        out.append(
            {
                "po_number": po.po_number,
                "product_id": str(product.id),
                "product_code": product.product_code,
                "product_name": product.product_name,
                "outstanding_qty": _plain_number(line.qty_ordered - line.qty_received),
                "expected_date": expected.isoformat() if expected else None,
                "supplier": supplier.supplier_name if supplier else None,
            }
        )
    return out


def purchase_orders_placed_summary(
    db, *, product_ids: Optional[list[str]] = None
) -> dict:
    delta = PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received
    q = db.query(func.sum(delta), func.count(PurchaseOrderLine.id)).filter(
        PurchaseOrderLine.line_status == "open", delta > 0
    )
    if product_ids:
        q = q.filter(PurchaseOrderLine.product_id.in_(product_ids))
    qty, count = q.one()
    return {"po_placed_qty": _plain_number(qty) or 0, "po_placed_count": int(count or 0)}


def group_rows(rows: list[dict], *, group_by: str) -> list[dict]:
    axis_key = {"product": "product_code", "supplier": "supplier", "date": "expected_date"}.get(
        group_by
    )
    if axis_key is None:
        return []
    order: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        label = row.get(axis_key) or "Not specified"
        if label not in buckets:
            buckets[label] = []
            order.append(label)
        buckets[label].append(row)
    return [{"key": label, "label": label, "rows": buckets[label]} for label in order]
