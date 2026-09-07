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
    # the date filter, the sort and the SUMMARY all see the same effective value.
    effective_date = _effective_expected_date()
    q = _apply_expected_date_window(q, expected_date_from, expected_date_to)

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
                # The PO DOCUMENT date (`purchase_orders.issue_date`, the header's own
                # date; `expected_date` above is the line's else the header's arrival
                # estimate). Owner ruling 8 Sep 2026: the chatbot's PO rung says when the
                # PO was raised, not only when the goods are due. Additive; every field
                # above is byte-identical.
                "po_date": po.issue_date.isoformat() if po.issue_date else None,
            }
        )
    return out


#: The effective expected date: the LINE's, else the header's. COALESCE rather than a
#: Python fallback so the filter, the sort and the summary all read one value.
def _effective_expected_date():
    return func.coalesce(PurchaseOrderLine.expected_date, PurchaseOrder.expected_date)


def _apply_expected_date_window(q, expected_date_from, expected_date_to):
    """The `expected_date_from/to` window, on any query that has both tables joined.

    ONE helper, called by the rows query and by the summary, because the review found the
    summary with no window at all and a second hand-written copy is how they drift again.
    """
    effective_date = _effective_expected_date()
    if expected_date_from is not None:
        q = q.filter(effective_date >= expected_date_from)
    if expected_date_to is not None:
        q = q.filter(effective_date <= expected_date_to)
    return q


def purchase_orders_placed_summary(
    db,
    *,
    product_ids: Optional[list[str]] = None,
    expected_date_from: Optional[str] = None,
    expected_date_to: Optional[str] = None,
) -> dict:
    """`po_placed_qty` / `po_placed_count` over EXACTLY the rows the list returned.

    The date window is applied here too (review, should-fix 6). Without it, "PO for X
    arriving this month" listed the month's lines and summarised the whole open book, so
    the summary contradicted the list it sat under - the one failure mode a summary has.
    The window is built by the same `_expected_date_window` the rows use, so the two
    cannot read one date differently.
    """
    delta = PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received
    q = (
        db.query(func.sum(delta), func.count(PurchaseOrderLine.id))
        # JOINED even when no window is asked for: the effective date COALESCEs the
        # header's column, so the join has to be there for the filter to resolve, and a
        # conditional join would make the unfiltered count depend on whether a date was
        # passed. Every line has a header (FK, not null), so the join drops no row.
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(PurchaseOrderLine.line_status == "open", delta > 0)
    )
    if product_ids:
        q = q.filter(PurchaseOrderLine.product_id.in_(product_ids))
    q = _apply_expected_date_window(q, expected_date_from, expected_date_to)
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
