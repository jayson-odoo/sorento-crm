"""SPO allocations last SPO line per product (A6, chatbot-growth-r1; reworded 8 Sep 2026,
chatbot-warehouse-entity-and-last-in).

`documentation/plans/chatbot/PLAN-chatbot-warehouse-entity-and-last-in.md` section "Last
in"; `chatbot-warehouse-entity-and-last-in-acceptance-criteria.md` AC-4..AC-8.

One focused module, same reason as `purchase_order_service.py` - this reads,
never writes.

Owner ruling verbatim, 8 Sep 2026: "last in should be per product, if we resolve to
entire family then return the latest receipt for each of the product"; "last in doesn't
relate to GR actually, it is purely last SPO ... based on the delivery date column at the
SPO"; "ignore GR entirely, i am okay with the gate allowed, yes expected date, yes one row
per product". GR (`receipt_status`, the inbound-shipment arrival columns) is therefore not
read here at all - those belong to the `incoming` domain.

Ordering key per line: `expected_date` (the SPO line's promised delivery), falling back to
`issue_date`, then `created_at::date` for the ~3% of lines with neither. `date_label` names
which column answered: "Expected" / "Issued" / "Recorded". `created_at DESC` is a
deterministic TIEBREAK only, for lines sharing the same date - it carries no business
meaning of its own.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Date, case, cast, func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import SPOAllocation
from app.models.product import Product


def _plain_number(v: Any) -> Any:
    if v is None:
        return None
    from decimal import Decimal

    try:
        d = Decimal(str(v))
    except Exception:  # noqa: BLE001
        return v
    return int(d) if d == d.to_integral_value() else float(d)


def last_receipt_rows(
    db: Session,
    *,
    product_ids: Optional[list[str]] = None,
    warehouse_ids: Optional[list[str]] = None,
    top_n: int = 1,
) -> list[dict]:
    """The last `top_n` SPO lines PER PRODUCT (default 1), GR ignored entirely.

    `warehouse_ids` filters lines to those warehouses BEFORE the per-product pick, so a
    line at an excluded warehouse never displaces one at an included warehouse. Rows are
    grouped product by product, in `product_code` order; within a product, newest key
    first, `created_at DESC` breaking a tie on the same date.
    """
    top_n = max(int(top_n or 1), 1)
    key_expr = func.coalesce(
        SPOAllocation.expected_date, SPOAllocation.issue_date, cast(SPOAllocation.created_at, Date)
    )
    label_expr = case(
        (SPOAllocation.expected_date.isnot(None), "Expected"),
        (SPOAllocation.issue_date.isnot(None), "Issued"),
        else_="Recorded",
    )
    rn = (
        func.row_number()
        .over(
            partition_by=SPOAllocation.product_id,
            order_by=(key_expr.desc().nulls_last(), SPOAllocation.created_at.desc()),
        )
        .label("rn")
    )

    numbered = db.query(
        SPOAllocation.id.label("allocation_id"),
        SPOAllocation.spo_number,
        SPOAllocation.product_id,
        SPOAllocation.warehouse_id,
        SPOAllocation.allocated_quantity,
        SPOAllocation.quantity_received,
        key_expr.label("date_key"),
        label_expr.label("date_label"),
        rn,
    )
    if product_ids:
        numbered = numbered.filter(SPOAllocation.product_id.in_(product_ids))
    if warehouse_ids:
        numbered = numbered.filter(SPOAllocation.warehouse_id.in_(warehouse_ids))
    sub = numbered.subquery()

    rows = (
        db.query(
            sub.c.spo_number,
            sub.c.allocated_quantity,
            sub.c.quantity_received,
            sub.c.date_key,
            sub.c.date_label,
            sub.c.rn,
            Product.id.label("product_id"),
            Product.product_code,
            Product.product_name,
            Warehouse.warehouse_code,
        )
        .join(Product, Product.id == sub.c.product_id)
        .outerjoin(Warehouse, Warehouse.id == sub.c.warehouse_id)
        .filter(sub.c.rn <= top_n)
        .order_by(Product.product_code.asc(), sub.c.rn.asc())
        .all()
    )

    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "spo_number": row.spo_number,
                "product_id": str(row.product_id),
                "product_code": row.product_code,
                "product_name": row.product_name,
                "quantity": _plain_number(row.allocated_quantity),
                "quantity_received": _plain_number(row.quantity_received),
                "date": row.date_key.isoformat() if row.date_key else None,
                "date_label": row.date_label,
                "warehouse": row.warehouse_code,
            }
        )
    return out
