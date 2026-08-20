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

from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from app.models.procurement import (
    PickingHeader,
    PickingLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.scm.history_sources import PO_HISTORY_SOURCE, SPO_HISTORY_SOURCE
from app.services.scm.spo_conversion_service import SOURCE_SYSTEM as CRM_SPO_SOURCE

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
#: order came from is owed the real answer. Both document families are listed - the channel
#: writes shipping orders under their own stamp (`po_history_service.SPO_SOURCE_SYSTEM`), and
#: an unlisted stamp would read as "somebody keyed this by hand".
_IMPORT_SOURCES = (PO_HISTORY_SOURCE, SPO_HISTORY_SOURCE)


def _source_label(source_system: Optional[str]) -> str:
    if source_system == _REC_SOURCE:
        return "recommendation"
    if source_system == CRM_SPO_SOURCE:
        return "crm"
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
                # Location is a LINE fact (captain, 20 Aug) - the header field is gone
                # from the detail page, so each line states its own destination.
                "warehouse_code": ln.warehouse.warehouse_code if ln.warehouse else None,
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
             query: Optional[str], status: Optional[str], supplier: Optional[str],
             *, product_code: Optional[str] = None,
             outstanding: Optional[bool] = None) -> dict:
        q = self._base_query()
        if status:
            q = q.filter(PurchaseOrder.status == status)
        if outstanding is not None:
            # The buyer's "at a glance" question (the captain, 20 Aug). The EXACT
            # predicate `_is_on_order` answers per row, so this filter and that row's own
            # badge can never disagree - mirrors `scm.po_ordered_v` (mig 337).
            still_open = (
                self.db.query(PurchaseOrderLine.id)
                .filter(
                    PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
                    PurchaseOrderLine.line_status == _OPEN_LINE_STATUS,
                    PurchaseOrderLine.qty_ordered > PurchaseOrderLine.qty_received,
                )
                .exists()
            )
            is_outstanding = PurchaseOrder.status.in_(_ON_ORDER_STATUSES) & still_open
            q = q.filter(is_outstanding if outstanding else ~is_outstanding)
        if product_code:
            # EXISTS, not a join: an order that carries the item on two lines is one order,
            # and a join would list it twice and count it twice.
            code = product_code.strip().lower()
            q = q.filter(
                self.db.query(PurchaseOrderLine.id)
                .join(Product, Product.id == PurchaseOrderLine.product_id)
                .filter(
                    PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
                    func.lower(func.btrim(Product.product_code)) == code,
                )
                .exists()
            )
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
        # Default surfaces the currently RELEVANT orders (the captain, 20 Aug), not the
        # most recently IMPORTED ones: `created_at` is the upload timestamp, and a bulk
        # outstanding-book upload stamps hundreds of historical orders with the same
        # minute, burying today's real activity under them. The order's own document
        # date - `issue_date`, falling back to `expected_date` for the rare order missing
        # one - is what "current" means to the buyer reading this list.
        col = sort_cols.get(sort) if sort else None
        if col is None:
            col = func.coalesce(PurchaseOrder.issue_date, PurchaseOrder.expected_date)
        ordering = col.desc().nulls_last() if direction != "asc" else col.asc().nulls_last()
        q = q.order_by(ordering)
        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        gr_refs = self._gr_refs_for([po.id for po in rows])
        return {
            "data": [self.serialize(po, gr_refs.get(po.id)) for po in rows],
            "empty": total == 0,
            "pagination": {"total": total, "page": page},
            # "which orders" and "what did we pay" are one question. Answered beside the
            # list rather than left for the reader to work out from the rows, which they
            # cannot do anyway once the orders spill past the first page.
            "product_cost": self._last_purchase(product_code) if product_code else None,
        }

    def _last_purchase(self, product_code: str) -> Optional[dict]:
        """The most recent priced line for this SKU, from any supplier.

        A recorded 0 is a price and is returned as 0. Only the absence of a line is
        unknown, and unknown is None - the two are different answers and this screen is
        where a buyer tells them apart.
        """
        row = (
            self.db.query(
                PurchaseOrderLine.unit_cost,
                PurchaseOrderLine.currency,
                PurchaseOrder.po_number,
                PurchaseOrder.issue_date,
                Supplier.supplier_name,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .join(Product, Product.id == PurchaseOrderLine.product_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .filter(
                func.lower(func.btrim(Product.product_code)) == product_code.strip().lower(),
                PurchaseOrderLine.unit_cost.isnot(None),
            )
            .order_by(
                PurchaseOrder.issue_date.desc().nullslast(),
                PurchaseOrderLine.created_at.desc(),
            )
            .first()
        )
        if row is None:
            return None
        return {
            "unit_cost": float(row.unit_cost),
            "currency": row.currency,
            "po_number": row.po_number,
            "issue_date": row.issue_date.isoformat() if row.issue_date else None,
            "supplier_name": row.supplier_name,
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

    def bulk_delete(self, ids: list[str], actor: Optional[str] = None) -> dict:
        """Hard delete purchase orders (captain, 20 Aug: "give me an option to bulk
        delete purchase orders ... maybe need to recreate").

        ``purchase_order_lines`` cascades with its header (``ondelete="CASCADE"``), and
        every OTHER dependent on a line either cascades too (loading-plan lines) or is
        ``SET NULL`` (picking lines, plan exceptions, the SO<->PO audit claim). Only one
        of those needs more than the FK: ``projects.order_inquiry_rows.po_line_id`` is
        ``SET NULL`` as well, but a row still carrying ``state = 'placed'`` after that
        would silently point at nothing while staying OUT of the reorder engine - the
        exact supply it was placed against just vanished. So every row placed on one of
        these POs' lines is explicitly UNPLACED first, the same way "Untag" does it
        (``project_order_inquiry_service.unplace`` - `state` back to `raised`, `po_ref`
        / `po_line_id` cleared, the SO<->PO audit claim removed), except the note it
        appends: "Unplaced" reads like a person did it, and this was the purchase order
        disappearing out from under the row, not a person changing their mind. The
        prior note is preserved and re-stamped with what actually happened.

        Ids not found (already deleted, or another company's) are skipped rather than
        failing the batch - a stale row in the caller's selection must not block the
        rest of a genuinely-selected batch.
        """
        if not ids:
            raise AppException(
                status_code=422, message="Select at least one purchase order to delete."
            )

        pos = self._base_query().filter(PurchaseOrder.id.in_(ids)).all()
        if not pos:
            return {"deleted": 0, "unplaced_rows": 0}

        po_ids = [po.id for po in pos]
        line_ids = [
            str(r[0])
            for r in (
                self.db.query(PurchaseOrderLine.id)
                .filter(PurchaseOrderLine.purchase_order_id.in_(po_ids))
                .all()
            )
        ]

        unplaced_rows = 0
        if line_ids:
            # Local import: this is the one write path in this service that reaches
            # into project-sales territory, and keeping it here instead of a
            # module-level import keeps that visible to whoever reads this method.
            from app.models.project_so import INQUIRY_PLACED, OrderInquiryRow
            from app.services.project_order_inquiry_service import (
                ProjectOrderInquiryService,
            )

            placed_rows = (
                self.db.query(OrderInquiryRow)
                .filter(
                    OrderInquiryRow.po_line_id.in_(line_ids),
                    OrderInquiryRow.state == INQUIRY_PLACED,
                )
                .all()
            )
            if placed_rows:
                inquiry_service = ProjectOrderInquiryService(self.db)
                stamp = "PO deleted - back on the board"
                for row in placed_rows:
                    prior_note = row.note
                    # Does everything Untag does - clears po_ref/po_line_id, resets
                    # state to `raised`, drops the audit claim, refreshes the parent
                    # inquiry's state - and its own "Unplaced from ..." note, which is
                    # overwritten below with the note this deletion actually earns.
                    inquiry_service.unplace(str(row.id), actor_user_id=actor)
                    row.note = f"{prior_note}; {stamp}" if prior_note else stamp
                    unplaced_rows += 1

        for po in pos:
            self.db.delete(po)
        self.db.commit()
        return {"deleted": len(pos), "unplaced_rows": unplaced_rows}
