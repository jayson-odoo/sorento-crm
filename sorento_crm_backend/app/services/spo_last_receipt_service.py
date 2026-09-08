"""SPO allocations last received (A6, chatbot-growth-r1).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` AC-908, AC-911.

One focused module, same reason as `purchase_order_service.py` - this reads,
never writes.

Date fallback order, per the A0 measurement recorded in the UAC
(`chatbot-growth-r1-acceptance-criteria.md`, AC-908 note): `inbound_shipments.
warehouse_arrival_date` (label "Arrived"), then `.actual_arrival_date`
("Arrived (port)"), then `spo_allocations.created_at` ("Received
(recorded)") - NOT `updated_at`, which is never populated on this table
(measured 0% on 79,747 received rows, same as both shipment date columns
today). The presenter/route both label which column actually answered.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment, SPOAllocation
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
    """Most recently RECEIVED spo_allocations (`receipt_status='fully_received'` -
    the plan/UAC's "received" bucket; there is no literal 'received' value in
    the column, see the AC-908 measurement note)."""
    q = (
        db.query(SPOAllocation, Product, InboundShipment, Warehouse)
        .join(Product, Product.id == SPOAllocation.product_id)
        .outerjoin(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
        .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
        .filter(SPOAllocation.receipt_status == "fully_received")
    )
    if product_ids:
        q = q.filter(SPOAllocation.product_id.in_(product_ids))
    if warehouse_ids:
        q = q.filter(SPOAllocation.warehouse_id.in_(warehouse_ids))
    order_col = func.coalesce(
        InboundShipment.warehouse_arrival_date, InboundShipment.actual_arrival_date
    )
    rows = (
        q.order_by(order_col.desc().nulls_last(), SPOAllocation.created_at.desc())
        .limit(max(int(top_n or 1), 1))
        .all()
    )
    out: list[dict] = []
    for alloc, product, shipment, warehouse in rows:
        if shipment is not None and shipment.warehouse_arrival_date:
            date_value = shipment.warehouse_arrival_date
            date_label = "Arrived"
        elif shipment is not None and shipment.actual_arrival_date:
            date_value = shipment.actual_arrival_date
            date_label = "Arrived (port)"
        else:
            date_value = alloc.created_at.date() if alloc.created_at else None
            # The column is the allocation's recorded timestamp (`created_at`); the
            # customer-facing label lost its "(recorded)" on 8 Sep 2026 (owner, D5).
            date_label = "Received"
        out.append(
            {
                "spo_number": alloc.spo_number,
                "product_id": str(product.id),
                "product_code": product.product_code,
                "product_name": product.product_name,
                "quantity_received": _plain_number(alloc.quantity_received),
                "date": date_value.isoformat() if date_value else None,
                "date_label": date_label,
                "warehouse": warehouse.warehouse_code if warehouse else None,
            }
        )
    return out
