"""SCM purchase-order service - list/read + the M4 Slice B draft→confirm→GR flow.

The PO is the inbound-supply record feeding on-order / incoming into the net
position views. M1 was read-only; M4 Slice B adds:

  * ``bulk_confirm`` - flips ``draft_recommendation`` → ``active`` and assigns the
    CANONICAL ``PO-{year}/{month:02d}-####`` number via the shared ``NumberingService``
    (the same rule that stamps SO/PO numbers, mig 274). Only then does the PO count as
    on-order (``scm.on_order_v`` - M4-D5/D6). Idempotent: non-draft ids are skipped.
  * ``create_gr`` - creates a goods receipt (``picking_headers`` /
    ``picking_lines`` with ``picking_type='goods_received'``) from an active/partial PO,
    stamping ``qty_received`` onto the PO lines (M4-D6).

po_number + supplier / warehouse codes are surfaced (never UUIDs).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.models.inventory import Warehouse
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

log = logging.getLogger(__name__)


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


_MONEY_PLACES = Decimal("0.01")


def _money(value) -> Optional[Decimal]:
    """`value` as a Decimal, or None when it is not a number at all."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _line_amount(ln: PurchaseOrderLine) -> Optional[Decimal]:
    """What this line is worth, or None when nobody priced it.

    The supplier's own stated total wins when the book carries one - it is what we were
    actually charged, tax and rounding included, and recomputing it from the parts would
    quietly disagree with the invoice. Failing that, the arithmetic the parts support.
    `None` rather than 0, for the reason `unit_cost` is nullable: a zero is a price OF zero.

    The identical rule the sales book's `_line_amount` follows, so the two screens cannot
    total the same shape of document two different ways.
    """
    stated = _money(ln.line_total)
    if stated is not None:
        return stated
    cost = _money(ln.unit_cost)
    if cost is None:
        return None
    qty = _money(ln.qty_ordered) or Decimal(0)
    discount = _money(ln.discount) or Decimal(0)
    return cost * qty - discount


def _order_amount(lines: list[PurchaseOrderLine]) -> Optional[Decimal]:
    """The order's own total, or None when not one of its lines carries money."""
    amounts = [a for a in (_line_amount(ln) for ln in lines) if a is not None]
    if not amounts:
        return None
    return sum(amounts, Decimal(0)).quantize(_MONEY_PLACES, rounding=ROUND_HALF_UP)


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

    def serialize(self, po: PurchaseOrder, gr_reference: Optional[str] = None, *,
                  allocated_qty: float = 0.0,
                  allocations: Optional[list[dict]] = None) -> dict:
        # Warehouse is carried at the line level; surface the first line's warehouse
        # as the PO's warehouse (M1 POs are effectively single-destination).
        wh_code = None
        wh_name = None
        total_qty = 0.0
        open_qty = 0.0
        open_lines = 0
        outstanding_qty = 0.0
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
            # STILL TO ARRIVE on this line, which is a third figure again: `open_qty` above is
            # what the PO contributes as SUPPLY (the whole open line, as `scm.on_order_v`
            # counts it), while this is net of what has been received. 0 on a CLOSED line
            # whatever the two quantities say - a book re-upload closes a line by absence
            # without knowing what arrived, so `qty_received` stays 0 and `ordered - received`
            # alone would report the whole quantity as still coming. `qty_received` is
            # deliberately NOT back-filled: that would be inventing a receipt.
            line_outstanding = (
                0.0 if not _is_open_line(ln)
                else max(float(ln.qty_ordered or 0) - float(ln.qty_received or 0), 0.0)
            )
            outstanding_qty += line_outstanding
            if wh_code is None and ln.warehouse is not None:
                wh_code = ln.warehouse.warehouse_code
                wh_name = ln.warehouse.warehouse_name or ln.warehouse.warehouse_code
            lines.append({
                "id": ln.id,
                "sku": ln.product.product_code if ln.product else "",
                "product_name": ln.product.product_name if ln.product else "",
                "qty_ordered": float(ln.qty_ordered or 0),
                "qty_received": float(ln.qty_received or 0),
                "outstanding_qty": line_outstanding,
                "line_status": ln.line_status,
                # The line's own override when the book stated one; otherwise the product's
                # base unit, exactly as the sales book does it. A purchase order written in
                # cartons must not read in pieces.
                "uom": ln.uom or (
                    ln.product.base_uom.uom_code
                    if (ln.product and ln.product.base_uom) else ""
                ),
                # The money, as stored. Not folded into one figure here: the detail page
                # shows all three columns, and a screen that could only print a total would
                # not answer "at what price". `unit_price` is the `unit_cost` COLUMN under
                # the name the sales screen uses for the same fact - see the schema.
                "unit_price": ln.unit_cost,
                "discount": ln.discount,
                "line_total": ln.line_total,
                "currency": ln.currency or po.currency,
                # Location is a LINE fact (captain, 20 Aug) - the header field is gone
                # from the detail page, so each line states its own destination.
                "warehouse_code": ln.warehouse.warehouse_code if ln.warehouse else None,
                "expected_date": (
                    ln.expected_date.isoformat() if ln.expected_date else None
                ),
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
            # What is still to ARRIVE across the order, summed off the same per-line rule the
            # grid prints, so the Totals card and the footer of the table under it cannot
            # disagree. Distinct from `open_qty`, which is supply and ignores receipts.
            "outstanding_qty": outstanding_qty,
            # What the order is worth, summed from the SAME line figures the Lines tab
            # prints, so the header total and the column under it cannot disagree.
            "total_amount": _order_amount(list(po.lines)),
            # The currency the order is written IN. The header's own, or the first line
            # that names one - the import states it per row and older orders carry none.
            "currency": po.currency or next(
                (ln.currency for ln in po.lines if ln.currency), None
            ),
            "lines": lines,
            # What order inquiries have OCCUPIED on this order (section 3.G). The SUM is on
            # every row, list included, because "is this order already spoken for" is a
            # list question; WHO is on it is the detail page's own panel and is left None
            # there, so a page of 50 orders does not pay for 50 placement queries.
            "allocated_qty": allocated_qty,
            "allocations": allocations if allocations is not None else [],
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

    # -- occupancy (section 3.G) ---------------------------------------------

    def _allocated_by_po(self, po_ids: list[str]) -> dict[str, float]:
        """What order inquiries have linked to each of these orders, summed. One query.

        The captain, 25 August 2026: a purchase order has to say how much of its outstanding
        is already occupied. This is that figure per DOCUMENT, for the list column and the
        detail header; `_allocations_for` breaks it down per line and names who is on it.

        Read off `projects.order_inquiry_links` - the truth since section 3.I - and never off
        `order_inquiry_rows.po_line_id`, which is now only the DERIVED display of the first
        link and would under-count every row sitting on two lines.

        A CANCELLED row's links are history, not an answer to "where does this quantity sit":
        the quantity is not owed any more. The same predicate `links_for_rows` applies for the
        worklist and the sales-order detail, so the three readers cannot disagree.
        """
        if not po_ids:
            return {}
        from app.models.project_so import (
            INQUIRY_CANCELLED,
            OrderInquiryLink,
            OrderInquiryRow,
        )

        rows = (
            self.db.query(
                PurchaseOrderLine.purchase_order_id,
                func.coalesce(func.sum(OrderInquiryLink.qty), 0),
            )
            .join(PurchaseOrderLine, PurchaseOrderLine.id == OrderInquiryLink.po_line_id)
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .filter(
                PurchaseOrderLine.purchase_order_id.in_(po_ids),
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .group_by(PurchaseOrderLine.purchase_order_id)
            .all()
        )
        return {str(po_id): float(total or 0) for po_id, total in rows}

    def _spo_takes_of(self, line_ids: list[str]) -> dict[str, list[dict]]:
        """Every CRM SPO that pulled from one of these lines, per line (AC-G7).

        Read off the SPO line's own `source_ref` - the JSON `[{po_line_id, qty}]` that
        `spo_conversion_service.create` writes to record which open line each pull drew from
        (its fifth amendment, "why this is JSON rather than a new link table"). So this is a
        READ of a fact already recorded, not a second table to keep in step.

        The container is named because that is what the buyer is actually being told: this
        line's quantity is already on the water, on THAT packing list, landing at THOSE
        warehouses. Everything on the row is a name; nothing is an id.
        """
        import json

        from app.models.procurement import InboundShipment, SPOAllocation
        from app.services.scm.spo_conversion_service import SOURCE_SYSTEM

        if not line_ids:
            return {}
        spo_lines = (
            self.db.query(PurchaseOrderLine, PurchaseOrder)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(
                PurchaseOrderLine.source_system == SOURCE_SYSTEM,
                PurchaseOrderLine.source_ref.isnot(None),
            )
            .all()
        )
        if not spo_lines:
            return {}

        wanted = set(line_ids)
        interesting = []
        for spo_line, spo in spo_lines:
            try:
                pulls = json.loads(spo_line.source_ref or "[]")
            except (TypeError, ValueError):
                continue
            if not isinstance(pulls, list):
                continue
            for pull in pulls:
                source_id = str((pull or {}).get("po_line_id") or "")
                if source_id in wanted:
                    interesting.append((source_id, spo_line, spo, float(pull.get("qty") or 0)))
        if not interesting:
            return {}

        # Where each SPO line's goods are landing, and on which container - one query for
        # the lot rather than one per take.
        alloc_rows = (
            self.db.query(
                SPOAllocation.po_line_id,
                Warehouse.warehouse_code,
                SPOAllocation.allocated_quantity,
                InboundShipment.shipment_number,
                InboundShipment.shipping_container_number,
                func.coalesce(
                    InboundShipment.actual_arrival_date,
                    InboundShipment.estimated_arrival_date,
                ),
            )
            .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
            .outerjoin(
                InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
            )
            .filter(
                SPOAllocation.po_line_id.in_([str(l.id) for _s, l, _p, _q in interesting])
            )
            .all()
        )
        landing: dict[str, dict] = {}
        for po_line_id, code, qty, shipment_number, container, arrival in alloc_rows:
            entry = landing.setdefault(
                str(po_line_id),
                {"warehouses": [], "packing_list": None, "arrival_date": None},
            )
            if code:
                entry["warehouses"].append({"warehouse_code": code, "qty": float(qty or 0)})
            entry["packing_list"] = entry["packing_list"] or container or shipment_number
            entry["arrival_date"] = entry["arrival_date"] or (
                arrival.isoformat() if arrival else None
            )

        out: dict[str, list[dict]] = {}
        for source_id, spo_line, spo, qty in interesting:
            place = landing.get(str(spo_line.id), {})
            out.setdefault(source_id, []).append({
                "kind": "spo",
                "spo_number": spo.po_number,
                "qty": qty,
                "packing_list": place.get("packing_list"),
                "warehouses": place.get("warehouses") or [],
                "arrival_date": place.get("arrival_date"),
                # The panel prints one shape; an SPO take has no inquiry, customer or agent
                # behind it, and stating None is how the row says so rather than borrowing
                # the fields above.
                "inquiry_no": None,
                "so_number": None,
                "customer": None,
                "agent": None,
                "needed_at": None,
                "location_differs": False,
            })
        return out

    def _allocations_for(self, po: PurchaseOrder) -> list[dict]:
        """One block per LINE that carries a placement, each naming who is waiting on it.

        Everything a person reads is a NAME - the inquiry by its number, the sales order by
        its document number, the customer and the agent by the labels the order-inquiry
        worklist already prints. `project_customer_label` is imported rather than restated so
        the same order does not read one way here and another way there.

        `location_differs` is the whole reason the panel exists: the PO line says DC1 and the
        demand is at BRW-BB, and that difference IS the split instruction the buyer re-keys in
        AutoCount. Marked on the row, never filtered - hiding it would remove the finding.

        Nothing here writes (AC-G5). The buyer's re-upload is the writer of
        `purchase_order_lines`, and a read that stamped a figure onto a line would be
        overwritten by that upload having moved supply in the meantime.
        """
        from app.models.order import Customer, SalesOrder
        from app.models.project_so import (
            INQUIRY_CANCELLED,
            OrderInquiry,
            OrderInquiryLink,
            OrderInquiryRow,
            ProjectSalesOrder,
        )
        from app.models.projects import Project, ProjectParty, ProjectPurchaseOrder
        from app.models.sales_agent import SalesAgent
        from app.services.project_order_inquiry_service import project_customer_label

        lines = {str(ln.id): ln for ln in po.lines}
        if not lines:
            return []

        rows = (
            self.db.query(
                OrderInquiryLink.po_line_id,
                OrderInquiryLink.qty,
                OrderInquiryLink.linked_at,
                OrderInquiryLink.id,
                OrderInquiryRow.stock_location,
                OrderInquiry.inquiry_no,
                ProjectSalesOrder.autocount_doc_no,
                ProjectSalesOrder.provisional_ref,
                ProjectSalesOrder.is_pre_order,
                Project.title,
                Customer.customer_name,
                SalesAgent.person_label,
                SalesAgent.sales_agent,
            )
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
            )
            .outerjoin(Project, Project.id == ProjectSalesOrder.project_id)
            .outerjoin(
                ProjectPurchaseOrder,
                ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
            )
            .outerjoin(ProjectParty, ProjectParty.id == ProjectPurchaseOrder.issuing_party_id)
            .outerjoin(SalesOrder, SalesOrder.id == ProjectSalesOrder.so_id)
            # ONE join through a coalesce rather than two aliases of `customers`: the
            # company-scope listener emits an UNALIASED `customers.company_id` into an
            # aliased ON clause, which Postgres refuses outright.
            .outerjoin(
                Customer,
                Customer.id
                == func.coalesce(ProjectParty.customer_id, SalesOrder.customer_id),
            )
            .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
            .filter(
                OrderInquiryLink.po_line_id.in_(list(lines)),
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .order_by(OrderInquiryLink.linked_at.asc(), OrderInquiryLink.id.asc())
            .all()
        )

        placements: dict[str, list[dict]] = {}
        allocated: dict[str, float] = {}
        for row in rows:
            line = lines[str(row.po_line_id)]
            line_location = line.warehouse.warehouse_code if line.warehouse else None
            needed_at = (row.stock_location or "").strip() or None
            qty = float(row.qty or 0)
            allocated[str(row.po_line_id)] = allocated.get(str(row.po_line_id), 0.0) + qty
            placements.setdefault(str(row.po_line_id), []).append({
                # WHICH kind of placement this row is. The order-inquiry ones are the
                # original panel; `spo` rows (F7) are a CRM SPO that pulled from this line.
                "kind": "inquiry",
                "inquiry_no": row.inquiry_no,
                # The AutoCount number where the order has one; the reference this system
                # minted where it does not. Never the id.
                "so_number": row.autocount_doc_no or row.provisional_ref,
                "customer": project_customer_label(
                    row.customer_name, row.title, row.is_pre_order
                ),
                # The person label a human would say, falling back to the agent code.
                "agent": row.person_label or row.sales_agent,
                "qty": qty,
                "needed_at": needed_at,
                # Both sides have to STATE a location for them to differ. A row that names
                # none is not a mismatch, it is a fact nobody recorded, and marking it would
                # send the buyer to split a line against an instruction that is not there.
                "location_differs": bool(
                    needed_at and line_location
                    and needed_at.upper() != line_location.strip().upper()
                ),
            })

        for line_id, spo_rows in self._spo_takes_of(list(lines)).items():
            for spo_row in spo_rows:
                allocated[line_id] = allocated.get(line_id, 0.0) + spo_row["qty"]
            placements.setdefault(line_id, []).extend(spo_rows)

        # In the order the DOCUMENT numbers its lines, so the panel reads down the same way
        # the grid above it does. `source_ref` carries the book's own line number where it
        # stated one; the rest fall back to insertion order, and never to whatever order the
        # relationship happened to load in.
        def _line_order(line):
            raw = (line.source_ref or "").strip()
            return (0, int(raw)) if raw.isdigit() else (1, 0)

        blocks = []
        for line in sorted(po.lines, key=lambda ln: (_line_order(ln), str(ln.id))):
            found = placements.get(str(line.id))
            if not found:
                continue
            outstanding = (
                0.0 if not _is_open_line(line)
                else max(float(line.qty_ordered or 0) - float(line.qty_received or 0), 0.0)
            )
            claimed = allocated.get(str(line.id), 0.0)
            blocks.append({
                "line_id": str(line.id),
                "sku": line.product.product_code if line.product else "",
                "warehouse_code": (
                    line.warehouse.warehouse_code if line.warehouse else None
                ),
                "outstanding": outstanding,
                "allocated": claimed,
                # Floored at 0: a line promised more than it has left is over-committed,
                # which is a finding for the buyer, not a credit they may spend again.
                "free": max(outstanding - claimed, 0.0),
                "placements": found,
            })
        return blocks

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
             outstanding: Optional[bool] = None,
             allocated: Optional[bool] = None) -> dict:
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
        if allocated is not None:
            # "Is this purchase order already spoken for" (AC-G4). EXISTS rather than a
            # join for the same reason `product_code` uses one: an order carrying two
            # placements is one order, and a join would list it twice.
            #
            # The EXACT predicate the Allocated column sums, so the filter and the figure
            # beside it can never disagree - a cancelled row's links are history and count
            # for neither.
            from app.models.project_so import (
                INQUIRY_CANCELLED,
                OrderInquiryLink,
                OrderInquiryRow,
            )

            is_allocated = (
                self.db.query(OrderInquiryLink.id)
                .join(
                    PurchaseOrderLine,
                    PurchaseOrderLine.id == OrderInquiryLink.po_line_id,
                )
                .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
                .filter(
                    PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
                    OrderInquiryRow.state != INQUIRY_CANCELLED,
                )
                .exists()
            )
            q = q.filter(is_allocated if allocated else ~is_allocated)
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
        # One query for the page, not one per row: the column is a sum over a child table
        # and an N+1 here is 50 statements per keystroke of the search box.
        occupied = self._allocated_by_po([str(po.id) for po in rows])
        return {
            "data": [
                self.serialize(
                    po,
                    gr_refs.get(po.id),
                    allocated_qty=occupied.get(str(po.id), 0.0),
                )
                for po in rows
            ],
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
        return self.serialize(
            po,
            gr_refs.get(po.id),
            allocated_qty=self._allocated_by_po([str(po.id)]).get(str(po.id), 0.0),
            allocations=self._allocations_for(po),
        )

    def list_supplier_options(
        self, query: Optional[str], limit: int, offset: int
    ) -> list[dict]:
        """Suppliers for the detail page's Supplier select, searched on the SERVER.

        Two columns, not the ORM row: the procurement master's own `/suppliers/select`
        returns whole supplier records (credit terms included) and takes no `limit`/`offset`
        at all, so a paged picker could not page it. Ordered by code so two pages neither
        repeat nor skip a row - without an ORDER BY, `offset` walks an arbitrary order.
        """
        q = self.db.query(Supplier.supplier_code, Supplier.supplier_name).filter(
            Supplier.is_active.is_(True)
        )
        if query and query.strip():
            needle = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Supplier.supplier_code.ilike(needle),
                    Supplier.supplier_name.ilike(needle),
                )
            )
        rows = q.order_by(Supplier.supplier_code).offset(offset).limit(limit).all()
        return [
            {"supplier_code": code, "supplier_name": name or code} for code, name in rows
        ]

    # -- writes --------------------------------------------------------------

    def _get_or_404(self, po_id: str) -> PurchaseOrder:
        po = self._base_query().filter(PurchaseOrder.id == po_id).first()
        if po is None:
            raise AppException(status_code=404, message="Purchase order not found.")
        return po

    def _parse_date(self, value: str, field: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            raise AppException(
                status_code=400, message=f"{field} must be a date as yyyy-mm-dd."
            )

    def _supplier(self, code: str) -> Supplier:
        supplier = (
            self.db.query(Supplier).filter(Supplier.supplier_code == code).first()
        )
        if supplier is None:
            raise AppException(status_code=404, message=f"No supplier with code {code}.")
        return supplier

    def _product(self, sku: str) -> Product:
        product = self.db.query(Product).filter(Product.product_code == sku).first()
        if product is None:
            raise AppException(status_code=404, message=f"No product with code {sku}.")
        return product

    def _warehouse(self, code: str) -> Warehouse:
        warehouse = (
            self.db.query(Warehouse).filter(Warehouse.warehouse_code == code).first()
        )
        if warehouse is None:
            raise AppException(status_code=404, message=f"No location with code {code}.")
        return warehouse

    def update(self, po_id: str, data) -> dict:
        """Correct a purchase order in place, header and lines.

        The supply-side twin of `SalesOrderService.update`, and it follows the identical
        rules, because the two screens are one click apart and a planner must not have to
        learn two behaviours for one gesture:

        * `model_fields_set`, not `is not None` - an omitted key leaves the stored value
          alone, one sent as an explicit `null` CLEARS it. Both arrive as `None` on the
          Pydantic model, and only the second means "unset this";
        * `lines` sent at all upserts the WHOLE array, matching by `id` first and SKU
          otherwise, so a matched line keeps its id, its `qty_received` and its
          `source_system`;
        * a counterparty, product or location code that resolves to nothing is a 404, never
          a silent unlink.
        """
        po = self._get_or_404(po_id)

        if "supplier_code" in data.model_fields_set:
            po.supplier_id = (
                self._supplier(data.supplier_code).id if data.supplier_code else None
            )
        if "order_date" in data.model_fields_set:
            po.issue_date = (
                self._parse_date(data.order_date, "order_date") if data.order_date else None
            )
        if "expected_date" in data.model_fields_set:
            po.expected_date = (
                self._parse_date(data.expected_date, "expected_date")
                if data.expected_date else None
            )
        if data.lines is not None:
            self._upsert_lines(po, data.lines)
        self.db.commit()
        # Re-read rather than serialize the in-memory instance: the commit expired it, and
        # a line the upsert added has no product/warehouse loaded on it yet. `_get_or_404`
        # rather than `get_one`, which answers `None` for a missing order - by here the
        # order provably exists, so a `dict | None` return would be a lie the caller has to
        # unpack.
        po = self._get_or_404(po_id)
        gr_refs = self._gr_refs_for([po.id])
        return self.serialize(po, gr_refs.get(po.id))

    def _upsert_lines(self, po: PurchaseOrder, incoming: list) -> None:
        """Reconcile ``po.lines`` against the payload IN PLACE, never delete + recreate.

        A delete-and-reinsert resets `qty_received` to 0, forces `source_system` back to
        nothing on every line, and mints new line ids - which severs every goods receipt
        (`picking_lines.po_line_id`), every SO<->PO claim and every placed order-inquiry row
        pointing at the old id (all `ondelete="SET NULL"`), silently dropping a received
        order's receipt trail on an ordinary quantity edit. Instead: match each payload line
        to an existing row, update only what the payload actually says, and leave
        `qty_received`, `source_system`, `line_status` and the id untouched.

        Matched by `id` when the payload carries one (this screen does); otherwise by SKU,
        first-unmatched-row-wins when a SKU repeats within the order. A payload line that
        matches nothing existing is a new line. An existing line that nothing in the payload
        claims is REMOVED - unless goods have already been received against it, or a sales
        order still claims it through an `OrderLinkClaim`, in which case the whole update is
        refused with a 409 rather than erasing a receipt or orphaning that claim.

        `warehouse_code` / `expected_date` / `uom` / `unit_price` / `discount` are applied via
        `model_fields_set`, not a plain `is not None` check, exactly as the sales side does.
        `line_total` is not in that list on purpose - it is what the supplier's document
        charged, and rewriting it from an edited cost would replace the invoice with our own
        arithmetic.
        """
        existing_lines = list(po.lines)
        matched_ids: set[str] = set()

        for ln in incoming:
            ln_id = getattr(ln, "id", None)
            target = None
            if ln_id and ln_id not in matched_ids:
                target = next((l for l in existing_lines if l.id == ln_id), None)
            if target is None:
                sku_norm = ln.sku.strip().lower()
                target = next(
                    (
                        l for l in existing_lines
                        if l.id not in matched_ids
                        and l.product is not None
                        and l.product.product_code.lower() == sku_norm
                    ),
                    None,
                )
            prod = self._product(ln.sku)
            fields_set = ln.model_fields_set
            warehouse_id = (
                self._warehouse(ln.warehouse_code).id if ln.warehouse_code else None
            ) if "warehouse_code" in fields_set else None
            expected_date = (
                self._parse_date(ln.expected_date, "expected_date")
                if ln.expected_date else None
            ) if "expected_date" in fields_set else None
            uom = (ln.uom or None) if "uom" in fields_set else None
            # `unit_price` on the wire is the `unit_cost` column - the two screens speak one
            # word for one fact, and the storage keeps the name the plan's costing reads.
            money = {}
            if "unit_price" in fields_set:
                money["unit_cost"] = ln.unit_price
            if "discount" in fields_set:
                money["discount"] = ln.discount

            if target is not None:
                matched_ids.add(target.id)
                target.product_id = prod.id
                target.qty_ordered = ln.qty_ordered
                if "warehouse_code" in fields_set:
                    target.warehouse_id = warehouse_id
                if "expected_date" in fields_set:
                    target.expected_date = expected_date
                if "uom" in fields_set:
                    target.uom = uom
                for col, value in money.items():
                    setattr(target, col, value)
            else:
                self.db.add(PurchaseOrderLine(
                    id=str(uuid.uuid4()),
                    purchase_order_id=po.id,
                    product_id=prod.id,
                    qty_ordered=ln.qty_ordered,
                    qty_received=0,
                    line_status="open",
                    warehouse_id=warehouse_id,
                    expected_date=expected_date,
                    uom=uom,
                    currency=po.currency,
                    **money,
                ))

        removed = [l for l in existing_lines if l.id not in matched_ids]
        if not removed:
            return

        # Received goods first, and off the rows already in memory: a line that has taken
        # delivery is a receipt, and dropping it erases the observation
        # `scm.receipt_lead_v` measures this supplier's lead time from. A wrong lead time is
        # worse than none, because it is trusted.
        received = next((l for l in removed if float(l.qty_received or 0) > 0), None)
        if received is not None:
            raise AppException(
                status_code=409,
                message=(
                    "Cannot remove a line that has already received goods "
                    f"({received.product.product_code if received.product else 'unknown item'})."
                ),
                code="PO_LINE_RECEIVED",
            )

        removed_ids = [l.id for l in removed]
        picking = (
            self.db.query(PickingLine.id)
            .filter(PickingLine.po_line_id.in_(removed_ids))
            .first()
        )
        if picking:
            raise AppException(
                status_code=409,
                message="Cannot remove a line a goods receipt was recorded against.",
                code="PO_LINE_HAS_RECEIPT",
            )

        # Local import: the SO<->PO claim lives in the module schema and this is the one
        # read in this service that reaches for it, so keeping it here rather than at module
        # level keeps that visible to whoever reads this method.
        from app.models.scm import OrderLinkClaim

        claim = (
            self.db.query(OrderLinkClaim)
            .filter(OrderLinkClaim.po_line_id.in_(removed_ids))
            .first()
        )
        if claim:
            raise AppException(
                status_code=409,
                message=(
                    f"Cannot remove a line sales order {claim.so_number} is waiting on "
                    f"(purchase order {claim.po_number})."
                ),
                code="PO_LINE_LINKED_TO_CLAIM",
            )

        for l in removed:
            self.db.delete(l)

    # -- M4 Slice B writes ---------------------------------------------------

    def bulk_confirm(self, ids: list[str], actor: Optional[str] = None) -> dict:
        """Confirm draft POs -> active + canonical number (M4-D6). Idempotent: a PO not
        in ``draft_recommendation`` is skipped, so re-confirming is a no-op.

        Confirming is also one of the moments the order-inquiry auto-place cascade
        runs (captain, 21 Aug): a line an internal draft PO just opened may already
        have a RAISED buy row waiting on exactly this product, so placement should not
        wait on someone clicking a separate button - the same idempotent cascade
        ``project_supply_service._auto_place_after_confirm`` runs on a decision
        confirm, a THIRD trigger of it rather than a mirror of that function's own
        shape: it runs a SAVEPOINT (``begin_nested``) inside the SAME transaction as
        its caller's writes, because that caller has not committed yet; this one runs
        commit-then-try, its own separate best-effort transaction AFTER the confirm's
        own commit, because the confirm here already IS the commit point - the confirm
        itself has already succeeded by the time this runs, so a failure here must not
        turn that success into a 500 the retry cannot repair (CLAUDE.md - post-commit
        side effects are best-effort, never raise).

        The cascade runs in TWO passes (P7, captain 26 Aug 2026). A purchase order raised
        off the plan is a buy for particular plan ROWS, and a plan row is a
        `(product, location)` cell whose Project figure is the un-linked remainder of the
        inquiry rows sitting at it. Pass one names exactly those rows
        (``rows_needed_at``), so the confirm links back to the rows that asked for it; pass
        two is the ordinary product-wide cascade, which finishes anything left over. Before
        this, one pass walked the earliest open row by expected date, so a confirm could
        satisfy a row at the other end of the country while the row that sized the buy
        stayed raised and the PO's "Allocated to" panel named a stranger.

        ``actor`` (a real user id) is REQUIRED for the auto-place pass, never
        substituted: ``OrderInquiryRow.actioned_by`` is a genuine FK to ``users.id``,
        so a placeholder like ``"system"`` would violate the constraint, the
        IntegrityError would be swallowed by the very try/except that makes this
        best-effort, and the whole placement batch would silently roll back (code
        review, 21 Aug, S1). A confirm with no real actor (the API-key/system
        principal) simply skips the pass and logs why - the confirm itself is
        unaffected either way."""
        confirmed = 0
        numbering = NumberingService(self.db)
        product_ids: set[str] = set()
        # The plan cells this confirm bought for: the (product, warehouse) of every line it
        # lifted. A line with no warehouse contributes a None, which matches an inquiry row
        # that resolves to no location either - the same NULL `scm.committed_v` emits.
        cells: set[tuple[str, str | None]] = set()
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
                if ln.product_id:
                    product_ids.add(str(ln.product_id))
                    cells.add((str(ln.product_id),
                               str(ln.warehouse_id) if ln.warehouse_id else None))
            confirmed += 1
        self.db.commit()

        if not product_ids:
            return {"confirmed_count": confirmed}

        if not actor:
            log.warning(
                "purchase order(s) confirmed, but auto-place was skipped: no real "
                "actor to attribute the placement to",
            )
            return {"confirmed_count": confirmed}

        try:
            from app.services.project_order_inquiry_service import (
                ProjectOrderInquiryService,
            )

            service = ProjectOrderInquiryService(self.db)
            # Pass one: the rows that sized these plan cells, first claim on the lines
            # this confirm just opened.
            # Sorted only so the pass is deterministic, and sorted with a KEY because a
            # bare `sorted` compares the tuples element by element: one line of a product
            # with a warehouse and another without gives `str < None`, a TypeError, inside
            # the best-effort try - which would swallow the WHOLE cascade and leave one log
            # line behind.
            sized_by = service.rows_needed_at(
                sorted(cells, key=lambda cell: (cell[0], cell[1] or ""))
            )
            if sized_by:
                service.auto_place_for_products(
                    None, actor_user_id=actor, trigger="po_confirm", row_ids=sized_by,
                )
            # Pass two: everybody else waiting on these products. Idempotent - a row pass
            # one fully linked is no longer raised, so it drops out of this query.
            service.auto_place_for_products(
                list(product_ids), actor_user_id=actor, trigger="po_confirm",
            )
            self.db.commit()
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            log.warning(
                "purchase order(s) confirmed, but the order-inquiry auto-place "
                "pass failed (%s)", exc,
            )

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
