"""SCM M1 purchase-order service — read-only list + lines.

The PO is the inbound-supply record feeding on-order / incoming into the net
position views. Create / confirm / receive land in M4; M1 only reads. po_number
and supplier / warehouse codes are surfaced (never UUIDs).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.procurement import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db

    def serialize(self, po: PurchaseOrder) -> dict:
        # Warehouse is carried at the line level; surface the first line's warehouse
        # as the PO's warehouse (M1 POs are effectively single-destination).
        wh_code = None
        wh_name = None
        total_qty = 0.0
        lines = []
        for ln in po.lines:
            total_qty += float(ln.qty_ordered or 0)
            if wh_code is None and ln.warehouse is not None:
                wh_code = ln.warehouse.warehouse_code
                wh_name = ln.warehouse.warehouse_name or ln.warehouse.warehouse_code
            lines.append({
                "id": ln.id,
                "sku": ln.product.product_code if ln.product else "",
                "product_name": ln.product.product_name if ln.product else "",
                "qty_ordered": float(ln.qty_ordered or 0),
                "qty_received": float(ln.qty_received or 0),
                "uom": ln.product.base_uom.uom_code if (ln.product and ln.product.base_uom) else "",
            })
        return {
            "id": po.id,
            "po_number": po.po_number,
            "supplier_code": po.supplier.supplier_code if po.supplier else "",
            "supplier_name": po.supplier.supplier_name if po.supplier else "",
            "warehouse_code": wh_code,
            "warehouse_name": wh_name,
            "status": po.status,
            "order_date": po.issue_date.isoformat() if po.issue_date else (
                po.created_at.date().isoformat() if po.created_at else ""
            ),
            "expected_date": po.expected_date.isoformat() if po.expected_date else None,
            "total_qty": total_qty,
            "line_count": len(po.lines),
            "lines": lines,
            "created_at": po.created_at.isoformat() if po.created_at else "",
        }

    def list(self, page: int, limit: int, sort: Optional[str], direction: str,
             query: Optional[str], status: Optional[str], supplier: Optional[str]) -> dict:
        from app.models.procurement import Supplier

        q = self.db.query(PurchaseOrder).options(
            joinedload(PurchaseOrder.lines).joinedload(PurchaseOrderLine.product),
            joinedload(PurchaseOrder.lines).joinedload(PurchaseOrderLine.warehouse),
            joinedload(PurchaseOrder.supplier),
        )
        if status:
            q = q.filter(PurchaseOrder.status == status)
        if supplier:
            q = q.filter(PurchaseOrder.supplier.has(Supplier.supplier_code == supplier))
        if query:
            like = f"%{query}%"
            q = q.filter(
                (PurchaseOrder.po_number.ilike(like))
                | (PurchaseOrder.supplier.has(Supplier.supplier_name.ilike(like)))
            )
        sort_cols = {
            "po_number": PurchaseOrder.po_number,
            "status": PurchaseOrder.status,
            "issue_date": PurchaseOrder.issue_date,
            "order_date": PurchaseOrder.issue_date,
            "expected_date": PurchaseOrder.expected_date,
            "created_at": PurchaseOrder.created_at,
        }
        col = sort_cols.get(sort or "", PurchaseOrder.created_at)
        q = q.order_by(col.desc() if direction != "asc" else col.asc())
        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        return {
            "data": [self.serialize(po) for po in rows],
            "empty": total == 0,
            "pagination": {"total": total, "page": page},
        }
