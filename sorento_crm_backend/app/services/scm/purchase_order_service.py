"""SCM purchase-order service — list/read + the M4 Slice B draft→confirm→GR flow.

The PO is the inbound-supply record feeding on-order / incoming into the net
position views. M1 was read-only; M4 Slice B adds:

  * ``bulk_confirm`` — flips ``draft_recommendation`` → ``active`` and assigns the
    CANONICAL ``PO-{year}/{month:02d}-####`` number via the shared ``NumberingService``
    (the same rule that stamps SO/PO numbers, mig 274). Only then does the PO count as
    on-order (``scm.on_order_v`` — M4-D5/D6). Idempotent: non-draft ids are skipped.
  * ``create_gr`` — creates a goods receipt (``picking_headers`` /
    ``picking_lines`` with ``picking_type='goods_received'``) from an active/partial PO,
    stamping ``qty_received`` onto the PO lines (M4-D6).

po_number + supplier / warehouse codes are surfaced (never UUIDs).
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.models.procurement import (
    PickingHeader,
    PickingLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService

# Mirror of ``scm.on_order_v``'s status filter (M4-D5/D6): a PO counts as incoming
# supply only in these statuses AND while it still has an unreceived OPEN line.
_ON_ORDER_STATUSES = {"active", "received", "partial", "closed"}
# The other half of that view's predicate. A line whose status is not ``open`` has left the
# order book (cancelled, or dropped from the outstanding extract) and is no longer incoming,
# so it must not appear in this PO's own totals either - two readers disagreeing about "on
# order" is what makes a planning report untrustworthy.
_OPEN_LINE_STATUS = "open"
_DRAFT_STATUS = "draft_recommendation"
_REC_SOURCE = "scm_recommendation"
#: Orders that arrived through the purchase-history upload. Reported as `import` rather than
#: folded into `manual`: nobody keyed 1,586 orders by hand, and a buyer asking where a 2020
#: order came from is owed the real answer.
_IMPORT_SOURCES = ("scm_po_history",)


def _source_label(source_system: Optional[str]) -> str:
    if source_system == _REC_SOURCE:
        return "recommendation"
    if source_system in _IMPORT_SOURCES:
        return "import"
    return "manual"


def _is_open_line(line) -> bool:
    return (line.line_status or "") == _OPEN_LINE_STATUS


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db

    # -- serialization -------------------------------------------------------

    def _is_on_order(self, po: PurchaseOrder) -> bool:
        if po.status not in _ON_ORDER_STATUSES:
            return False
        return any(
            _is_open_line(ln) and float(ln.qty_ordered or 0) > float(ln.qty_received or 0)
            for ln in po.lines
        )

    def serialize(self, po: PurchaseOrder, gr_reference: Optional[str] = None) -> dict:
        # Warehouse is carried at the line level; surface the first line's warehouse
        # as the PO's warehouse (M1 POs are effectively single-destination).
        wh_code = None
        wh_name = None
        total_qty = 0.0
        open_qty = 0.0
        open_lines = 0
        lines = []
        for ln in po.lines:
            # TWO figures, because there are two questions and one number cannot answer both.
            #
            # ``total_qty`` / ``line_count`` are what the ORDER SAYS - every line of it. The
            # columns are labelled "Total qty" and "Lines", and a 2020 order for 450 units
            # reading 0 because its lines are closed is the label lying about the row. That
            # is what the imported purchase history made visible: 1,586 orders, every one of
            # them showing an empty order.
            #
            # ``open_qty`` / ``open_line_count`` are what the PO contributes as SUPPLY, and
            # count open lines only, exactly as ``scm.on_order_v`` does. Every line is listed
            # either way, each carrying its ``line_status``, so the screen can show a closed
            # line as closed instead of rendering it as one still coming.
            total_qty += float(ln.qty_ordered or 0)
            if _is_open_line(ln):
                open_qty += float(ln.qty_ordered or 0)
                open_lines += 1
            if wh_code is None and ln.warehouse is not None:
                wh_code = ln.warehouse.warehouse_code
                wh_name = ln.warehouse.warehouse_name or ln.warehouse.warehouse_code
            lines.append({
                "id": ln.id,
                "sku": ln.product.product_code if ln.product else "",
                "product_name": ln.product.product_name if ln.product else "",
                "qty_ordered": float(ln.qty_ordered or 0),
                "qty_received": float(ln.qty_received or 0),
                "line_status": ln.line_status,
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
            "open_qty": open_qty,
            "open_line_count": open_lines,
            "lines": lines,
            "created_at": po.created_at.isoformat() if po.created_at else "",
            "is_on_order": self._is_on_order(po),
            "source": _source_label(po.source_system),
            "gr_reference": gr_reference,
        }

    def _gr_refs_for(self, po_ids: list[str]) -> dict[str, str]:
        """Latest goods-receipt reference per PO id (one query, no N+1)."""
        if not po_ids:
            return {}
        rows = self.db.execute(text("""
            SELECT DISTINCT ON (source_entity_id) source_entity_id::text AS po_id, picking_number
            FROM picking_headers
            WHERE picking_type = 'goods_received'
              AND source_entity_type = 'purchase_order'
              AND source_entity_id::text = ANY(:ids)
            ORDER BY source_entity_id, created_at DESC
        """), {"ids": po_ids}).mappings().all()
        return {r["po_id"]: r["picking_number"] for r in rows}

    # -- reads ---------------------------------------------------------------

    def _base_query(self):
        return self.db.query(PurchaseOrder).options(
            joinedload(PurchaseOrder.lines).joinedload(PurchaseOrderLine.product),
            joinedload(PurchaseOrder.lines).joinedload(PurchaseOrderLine.warehouse),
            joinedload(PurchaseOrder.supplier),
        )

    def list(self, page: int, limit: int, sort: Optional[str], direction: str,
             query: Optional[str], status: Optional[str], supplier: Optional[str]) -> dict:
        from app.models.procurement import Supplier

        q = self._base_query()
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
        gr_refs = self._gr_refs_for([po.id for po in rows])
        return {
            "data": [self.serialize(po, gr_refs.get(po.id)) for po in rows],
            "empty": total == 0,
            "pagination": {"total": total, "page": page},
        }

    def get_one(self, po_id: str) -> Optional[dict]:
        po = self._base_query().filter(PurchaseOrder.id == po_id).first()
        if po is None:
            return None
        gr_refs = self._gr_refs_for([po.id])
        return self.serialize(po, gr_refs.get(po.id))

    # -- M4 Slice B writes ---------------------------------------------------

    def bulk_confirm(self, ids: list[str], actor: Optional[str] = None) -> dict:
        """Confirm draft POs → active + canonical number (M4-D6). Idempotent: a PO not
        in ``draft_recommendation`` is skipped, so re-confirming is a no-op."""
        confirmed = 0
        numbering = NumberingService(self.db)
        for pid in ids or []:
            po = (
                self._base_query()
                .filter(PurchaseOrder.id == pid, PurchaseOrder.status == _DRAFT_STATUS)
                .first()
            )
            if po is None:
                continue
            po.po_number = numbering.get_next_number(
                "purchase_order", date.today(), commit_rule=False
            ) or po.po_number
            po.status = "active"
            if po.expected_date is None:
                dates = [ln.expected_date for ln in po.lines if ln.expected_date]
                po.expected_date = max(dates) if dates else None
            for ln in po.lines:
                ln.line_status = "open"
            confirmed += 1
        self.db.commit()
        return {"confirmed_count": confirmed}

    def create_gr(self, po_id: str, actor: Optional[str] = None) -> dict:
        """Create a goods receipt from an active/partial PO (M4-D6): a full receipt
        stamps ``qty_received = qty_ordered`` on every open line, moves the PO to
        ``received``, and returns the GR reference. Drafts are rejected."""
        po = self._base_query().filter(PurchaseOrder.id == po_id).first()
        if po is None:
            raise AppException(status_code=404, message="Purchase order not found.")
        if po.status not in ("active", "partial"):
            raise AppException(
                status_code=422,
                message="A goods receipt can only be created from an active purchase order.",
            )
        gr_number = NumberingService(self.db).get_next_number(
            "goods_received", date.today(), commit_rule=False
        ) or f"GR-{uuid.uuid4().hex[:8]}"

        header = PickingHeader(
            id=str(uuid.uuid4()),
            picking_number=gr_number,
            picking_type="goods_received",
            source_entity_type="purchase_order",
            source_entity_id=po.id,
            picking_date=date.today(),
            # picking_status check constraint allows draft|submitted|approved|posted|rejected|closed;
            # existing goods_received headers use "posted" (stock posted to inventory).
            picking_status="posted",
            picked_by_user_id=actor,
        )
        self.db.add(header)
        self.db.flush()

        for ln in po.lines:
            if ln.line_status == "closed":
                # Goods that were cancelled never arrive, so receiving them invents inventory
                # AND hands ``scm.receipt_lead_v`` a fabricated lead-time observation, which
                # then skews the supplier's measured lead time and every safety stock and
                # reorder point computed from it. A wrong lead time is worse than none,
                # because it is trusted.
                continue
            ordered = float(ln.qty_ordered or 0)
            received = float(ln.qty_received or 0)
            remaining = ordered - received
            if remaining <= 0:
                continue
            self.db.add(PickingLine(
                id=str(uuid.uuid4()),
                picking_header_id=header.id,
                po_line_id=ln.id,
                product_id=ln.product_id,
                quantity_expected=int(round(ordered)),
                quantity_picked=int(round(remaining)),
                qty_accepted=int(round(remaining)),
                qty_rejected=0,
                destination_warehouse_id=ln.warehouse_id,
                unit_cost=ln.unit_cost,
            ))
            ln.qty_received = ln.qty_ordered
            ln.line_status = "received"

        po.status = "received"
        self.db.commit()
        return {"gr_reference": gr_number}
