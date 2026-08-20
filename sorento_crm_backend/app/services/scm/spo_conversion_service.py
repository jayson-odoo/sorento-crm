""""Create SPO" - a shipment's uncovered lines become a real CRM purchase order.

`PLAN-scm-proforma-to-spo.md`'s Amendment, second decision: "Separate button after
packing-list apply. The shipment page gets a Create SPO action she presses when ready.
Suggestion logic as originally planned (match open PO lines by product / stated po_ref /
delivery date, net on hand + incoming SPO), but the BASE quantity is the PACKED qty, not the
invoice qty."

Two moves, two functions, the same shape as `container_request_service` (`build` / `send`)
and `proforma_invoice_service` (`convert_to_draft_shipment`):

  * `suggest` - a pure read. Per shipment line: the PACKED quantity (`quantity_shipped`,
    never the PI's invoiced figure - the Amendment's own correction), what an OPEN purchase
    order to the SAME supplier already covers (matched by product, PINNED to one PO when the
    line's originating PI line(s) stated a `po_ref`), and on hand + incoming SPO company-wide
    - same three figures `container_request_service._stock_context` reads, same reason: this
    is one company deciding what it still needs, not one warehouse's question. The suggested
    qty is `packed - po_covered - on_hand - incoming_spo`, floored at zero, editable. A line
    with nothing left to ask for reads as COVERED (unticked by default, one line saying why);
    a line with no supplier at all cannot convert (a container with an unattributed factory
    line, the n8n PDF path) and says so.
  * `create` - writes ONE `purchase_orders` header per SUPPLIER represented on the shipment
    (a container is routinely several factories' goods, and AutoCount POs are per supplier
    too), lines carrying the confirmed quantities, source-marked `SOURCE_SYSTEM` so it can
    never be mistaken for an AutoCount import. Idempotent by refusal: a shipment with ANY
    existing `ShipmentLineSpoLink` row is refused with a 409 naming the SPOs it already made,
    the same shape `proforma_invoice_service.convert_to_draft_shipment` uses for the PI
    convert this composes with.

**Where the new SPO counts as supply.** `scm.po_ordered_v` reads `purchase_order_lines`
by STATUS and LINE_STATUS only - no `source_system` predicate - so an `active` / `open` CRM
SPO line is counted as "ordered" the moment it is created, exactly like an AutoCount import
would be (migration 337's `PO_ORDERED_V`). `scm.on_order_v` reads `spo_allocations`
exclusively and is UNCHANGED by this module on purpose: an allocation is a WAREHOUSE decision
(which location this shipment's goods land in), a separate, later, explicit step
(`allocation_suggestion_service.approve` / `SPOAllocationService.create_allocation`) that
this action does not take for her - `po_history_service`'s own SPO-history rows draw the
identical line (deliberately NOT written to `spo_allocations` either). So a freshly created
CRM SPO shows as ORDERED on every book/reorder screen immediately; it becomes INCOMING SPO
supply only once somebody allocates it to a warehouse, same as any other SPO.

**Reconciliation** (the next AutoCount book import matching this SPO by number) is explicitly
OUT OF SCOPE here, per the plan's design notes - the worksheet is the handoff, and the office
keys it into AutoCount by hand.
"""
from __future__ import annotations

import uuid
from datetime import date as _date
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.scm import ProformaInvoiceLine, ProformaInvoiceShipmentLink, ShipmentLineSpoLink
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.scm.supplier_scope import is_uuid as _is_uuid

#: The CRM-originated marker on `purchase_orders.source_system` / `purchase_order_lines.
#: source_system`. Distinct from every AutoCount import stamp (`scm_po_history`,
#: `scm_spo_history`, `scm_upload`) and from the reorder engine's own draft marker
#: (`scm_recommendation`) - see the module docstring for every consumer this was checked
#: against (`po_ordered_v`, `on_order_v`, `purchase_order_service._source_label`,
#: `outstanding_import_service`'s history guard).
SOURCE_SYSTEM = "crm_spo"

#: A CRM SPO counts as "ordered" the moment it exists (the module docstring) - so it is
#: created ACTIVE + OPEN, never a draft a later Confirm step would have to promote. Mirrors
#: `purchase_order_service._ON_ORDER_STATUSES` / `_OPEN_LINE_STATUS`.
_STATUS = "active"
_LINE_STATUS = "open"

#: `NumberingService` doc_type for the CRM SPO's own series, kept distinct from every
#: AutoCount pattern (`######-S####`, `SPO-####/##-####`) and from the CRM's own canonical
#: PO series (`PO-{year}/{month}-####`, `decision_service`) so an AutoCount import can never
#: collide with a number this module minted. Falls back to a random suffix when no numbering
#: rule is configured, same shape as `proforma_invoice_service._draft_shipment_number`.
_NUMBER_DOC_TYPE = "purchase_order_crm_spo"
_NUMBER_PREFIX = "CRM-SPO"

_REASON_NO_SUPPLIER = "No supplier recorded on this shipment line, so it cannot be added to an SPO."
_REASON_NOT_SELECTED = "Not selected."


def _uuid() -> str:
    return str(uuid.uuid4())


def _f(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _shipment_or_404(db: Session, shipment_id: str) -> InboundShipment:
    if not _is_uuid(shipment_id):
        raise AppException(404, "Inbound shipment not found")
    row = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).one_or_none()
    if row is None:
        raise AppException(404, "Inbound shipment not found")
    return row


def _existing_links(db: Session, shipment_id: str) -> list[ShipmentLineSpoLink]:
    return (
        db.query(ShipmentLineSpoLink)
        .filter(ShipmentLineSpoLink.inbound_shipment_id == shipment_id)
        .all()
    )


def _existing_spos(db: Session, shipment_id: str) -> list[dict]:
    rows = (
        db.query(PurchaseOrder)
        .join(ShipmentLineSpoLink, ShipmentLineSpoLink.purchase_order_id == PurchaseOrder.id)
        .filter(ShipmentLineSpoLink.inbound_shipment_id == shipment_id)
        .distinct()
        .all()
    )
    return [
        {
            "purchase_order_id": str(po.id),
            "po_number": po.po_number,
            "supplier_id": str(po.supplier_id) if po.supplier_id else None,
            "supplier_name": po.supplier.supplier_name if po.supplier else None,
        }
        for po in rows
    ]


def _po_refs_for_line(db: Session, shipment_line_id: str) -> set[str]:
    """The `po_ref`(s) named on the PI line(s) this shipment line was drafted from, if any.

    A shipment line reached through the draft-from-PI convert can aggregate several PI
    lines (same product, same supplier, across invoices - `proforma_invoice_service`'s own
    grouping); a shipment reached from a real packing-list upload has none at all, and this
    returns empty for it.
    """
    rows = (
        db.query(ProformaInvoiceLine.po_ref)
        .join(
            ProformaInvoiceShipmentLink,
            ProformaInvoiceShipmentLink.proforma_invoice_line_id == ProformaInvoiceLine.id,
        )
        .filter(
            ProformaInvoiceShipmentLink.inbound_shipment_line_id == shipment_line_id,
            ProformaInvoiceLine.po_ref.isnot(None),
        )
        .all()
    )
    return {r[0].strip() for r in rows if r[0] and r[0].strip()}


def _po_ref_match(db: Session, po_ref: str, supplier_id: str, product_id: str) -> Optional[float]:
    """Open quantity still outstanding on the PINNED PO for this product, or None when the
    stated document does not resolve to one - the plan's "a stated po_ref outranks
    inference", so a miss here does NOT fall back to product-only matching."""
    row = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrder.po_number == po_ref,
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.notin_(("draft", "draft_recommendation")),
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrderLine.line_status == "open",
        )
        .all()
    )
    if not row:
        return None
    return sum(
        max(float(ln.qty_ordered or 0) - float(ln.qty_received or 0), 0.0) for ln in row
    )


def _product_covered_qty(db: Session, supplier_id: str, product_id: str) -> tuple[float, Optional[str]]:
    """Open quantity across EVERY open PO to this supplier for this product (no po_ref
    named), earliest-issued first for the PO number reported - same candidate shape as
    `allocation_suggestion_service._candidates`, aggregated rather than ranked because this
    screen asks one question ("how much is already on order") not "which line exactly"."""
    rows = (
        db.query(PurchaseOrderLine, PurchaseOrder.po_number)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.notin_(("draft", "draft_recommendation")),
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrderLine.line_status == "open",
        )
        .order_by(PurchaseOrder.issue_date.asc().nullslast(), PurchaseOrder.po_number.asc())
        .all()
    )
    if not rows:
        return 0.0, None
    covered = sum(
        max(float(ln.qty_ordered or 0) - float(ln.qty_received or 0), 0.0) for ln, _n in rows
    )
    return covered, rows[0][1]


def _stock_context(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """On hand + incoming SPO, company-wide, per product - COPIED from
    `container_request_service._stock_context` rather than imported (same reasoning that
    module gives for copying `loading_plan_service._catalogue_cbm`: two lanes touching the
    same file is a worse cost than a few duplicated lines). Same figures, same views, so this
    screen and the container request can never disagree about what is already covered."""
    if not product_ids:
        return {}
    prod_scope, prod_params = company_sql_predicate(db, "p.company_id", param_prefix="scp")
    wh_scope, wh_params = company_sql_predicate(db, "w.company_id", param_prefix="scw")
    where = ["np.product_id::text = ANY(:pids)"]
    if prod_scope:
        where.append(prod_scope)
    if wh_scope:
        where.append(wh_scope)
    sql = f"""
        SELECT np.product_id::text AS product_id,
               SUM(COALESCE(np.quantity_on_hand, 0)) AS on_hand,
               SUM(COALESCE(np.on_order, 0)) AS incoming_spo
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN warehouses w ON w.id = np.warehouse_id
        WHERE {' AND '.join(where)}
        GROUP BY np.product_id
    """
    rows = db.execute(
        text(sql), {"pids": product_ids, **prod_params, **wh_params}
    ).mappings().all()
    return {
        r["product_id"]: {
            "on_hand": float(r["on_hand"] or 0),
            "incoming_spo": float(r["incoming_spo"] or 0),
        }
        for r in rows
    }


def suggest(db: Session, shipment_id: str) -> dict:
    """What "Create SPO" would ask for, per shipment line. Pure read - persists nothing."""
    shipment = _shipment_or_404(db, shipment_id)
    lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment.id)
        .all()
    )

    already = _existing_links(db, shipment.id)
    if already:
        return {
            "shipment_id": str(shipment.id),
            "shipment_number": shipment.shipment_number,
            "shipment_status": shipment.shipment_status,
            "already_converted": True,
            "existing_spos": _existing_spos(db, shipment.id),
            "lines": [],
        }

    product_ids = [str(ln.product_id) for ln in lines if ln.product_id]
    supplier_ids = {str(ln.supplier_id) for ln in lines if ln.supplier_id}
    products = {
        str(pid): (code, name)
        for pid, code, name in db.query(*_product_cols()).filter(_product_id_in(product_ids)).all()
    } if product_ids else {}
    suppliers = (
        {str(s.id): s.supplier_name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
        if supplier_ids
        else {}
    )
    stock = _stock_context(db, product_ids)

    out_lines: list[dict] = []
    for ln in sorted(lines, key=lambda l: (products.get(str(l.product_id), (None, None))[0] or "", str(l.id))):
        packed = float(ln.quantity_shipped or 0)
        product = products.get(str(ln.product_id))
        item_code, product_name = product if product else (None, None)
        supplier_id = str(ln.supplier_id) if ln.supplier_id else None

        if supplier_id is None:
            out_lines.append({
                "shipment_line_id": str(ln.id),
                "product_id": str(ln.product_id),
                "item_code": item_code,
                "product_name": product_name,
                "supplier_id": None,
                "supplier_name": None,
                "packed_qty": packed,
                "po_covered_qty": 0.0,
                "matched_po_number": None,
                "matched_by": None,
                "on_hand": 0.0,
                "incoming_spo": 0.0,
                "suggested_qty": 0.0,
                "covered": False,
                "cannot_convert": True,
                "reason": _REASON_NO_SUPPLIER,
                "unit_cost": _f(ln.unit_cost),
                "currency": ln.currency,
            })
            continue

        po_refs = _po_refs_for_line(db, str(ln.id))
        matched_by: Optional[str] = None
        po_covered = 0.0
        matched_po_number: Optional[str] = None
        if len(po_refs) == 1:
            pinned = _po_ref_match(db, next(iter(po_refs)), supplier_id, str(ln.product_id))
            if pinned is not None:
                po_covered = pinned
                matched_po_number = next(iter(po_refs))
                matched_by = "po_ref"
        if matched_by is None:
            po_covered, matched_po_number = _product_covered_qty(db, supplier_id, str(ln.product_id))
            if matched_po_number:
                matched_by = "product"

        ctx = stock.get(str(ln.product_id), {"on_hand": 0.0, "incoming_spo": 0.0})
        suggested = max(packed - po_covered - ctx["on_hand"] - ctx["incoming_spo"], 0.0)
        covered = suggested <= 0
        reason = None
        if covered:
            parts = []
            if po_covered > 0:
                parts.append(f"already ordered on {matched_po_number}")
            if ctx["on_hand"] > 0 or ctx["incoming_spo"] > 0:
                parts.append("covered by stock/incoming")
            reason = "Fully covered - " + "; ".join(parts) + "." if parts else "Nothing packed on this line."

        out_lines.append({
            "shipment_line_id": str(ln.id),
            "product_id": str(ln.product_id),
            "item_code": item_code,
            "product_name": product_name,
            "supplier_id": supplier_id,
            "supplier_name": suppliers.get(supplier_id),
            "packed_qty": packed,
            "po_covered_qty": po_covered,
            "matched_po_number": matched_po_number,
            "matched_by": matched_by,
            "on_hand": ctx["on_hand"],
            "incoming_spo": ctx["incoming_spo"],
            "suggested_qty": suggested,
            "covered": covered,
            "cannot_convert": False,
            "reason": reason,
            "unit_cost": _f(ln.unit_cost),
            "currency": ln.currency,
        })

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "shipment_status": shipment.shipment_status,
        "already_converted": False,
        "existing_spos": [],
        "lines": out_lines,
    }


def _product_cols():
    from app.models.product import Product

    return (Product.id, Product.product_code, Product.product_name)


def _product_id_in(ids: list[str]):
    from app.models.product import Product

    return Product.id.in_(ids)


def _spo_number(db: Session) -> str:
    number = NumberingService(db).get_next_number(_NUMBER_DOC_TYPE, _date.today(), commit_rule=False)
    return number or f"{_NUMBER_PREFIX}-{uuid.uuid4().hex[:8]}"


def create(
    db: Session,
    shipment_id: str,
    lines: list[dict],
    *,
    actor: Optional[str] = None,
) -> dict:
    """Confirm the screen `suggest` drew. One `purchase_orders` header per supplier.

    `lines` is `[{shipment_line_id, qty, include}]` - every shipment line, per the "same
    structure on read and write" screen shape: a line the buyer left unticked or a covered
    line still needs a row here so the whole shipment is accounted for in ONE action, not a
    part of it silently left for later.
    """
    shipment = _shipment_or_404(db, shipment_id)

    if _existing_links(db, shipment.id):
        existing = _existing_spos(db, shipment.id)
        names = ", ".join(sorted({s["po_number"] or "?" for s in existing}))
        raise AppException(
            409,
            f"An SPO has already been created from this shipment: {names}.",
            detail="already_converted",
        )

    shipment_lines = {
        str(ln.id): ln
        for ln in db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment.id)
        .all()
    }
    if not shipment_lines:
        raise AppException(422, "This shipment has no lines to create an SPO from.")

    by_line = {str(item.get("shipment_line_id") or ""): item for item in (lines or [])}
    missing = [lid for lid in shipment_lines if lid not in by_line]
    if missing:
        raise AppException(
            422,
            "Every line on this shipment must be accounted for.",
            detail=f"{len(missing)} line(s) missing from the request",
        )

    groups: dict[str, dict[str, Any]] = {}
    skipped: list[tuple[str, str]] = []

    for line_id, ln in shipment_lines.items():
        item = by_line[line_id]
        include = bool(item.get("include"))
        qty = float(item.get("qty") or 0)
        supplier_id = str(ln.supplier_id) if ln.supplier_id else None

        if supplier_id is None:
            skipped.append((line_id, _REASON_NO_SUPPLIER))
            continue
        if not include or qty <= 0:
            skipped.append((line_id, _REASON_NOT_SELECTED))
            continue

        group = groups.setdefault(
            supplier_id,
            {"lines": [], "currency": ln.currency},
        )
        group["lines"].append((ln, qty))

    if not groups:
        raise AppException(
            422,
            "Nothing was selected to create an SPO from.",
            detail="nothing_selected",
        )

    supplier_names = {
        str(s.id): s.supplier_name
        for s in db.query(Supplier).filter(Supplier.id.in_(list(groups.keys()))).all()
    }

    created_spos: list[dict] = []
    line_links: dict[str, tuple[str, str]] = {}  # shipment_line_id -> (po_id, po_line_id)

    for supplier_id, group in groups.items():
        po = PurchaseOrder(
            id=_uuid(),
            po_number=_spo_number(db),
            supplier_id=supplier_id,
            issue_date=_date.today(),
            expected_date=shipment.eta_delay_date or shipment.estimated_arrival_date,
            status=_STATUS,
            currency=group["currency"],
            source_system=SOURCE_SYSTEM,
            source_ref=str(shipment.id),
        )
        db.add(po)
        db.flush()

        total_qty = 0.0
        for ln, qty in group["lines"]:
            po_line = PurchaseOrderLine(
                id=_uuid(),
                purchase_order_id=po.id,
                product_id=ln.product_id,
                qty_ordered=Decimal(str(qty)),
                qty_received=0,
                unit_cost=ln.unit_cost,
                currency=ln.currency,
                expected_date=po.expected_date,
                line_status=_LINE_STATUS,
                source_system=SOURCE_SYSTEM,
                source_ref=str(ln.id),
            )
            db.add(po_line)
            db.flush()
            line_links[str(ln.id)] = (po.id, po_line.id)
            total_qty += qty

        created_spos.append({
            "purchase_order_id": str(po.id),
            "po_number": po.po_number,
            "supplier_id": supplier_id,
            "supplier_name": supplier_names.get(supplier_id),
            "currency": po.currency,
            "lines": len(group["lines"]),
            "qty": total_qty,
        })

    for line_id, (po_id, po_line_id) in line_links.items():
        db.add(ShipmentLineSpoLink(
            id=_uuid(),
            inbound_shipment_id=shipment.id,
            inbound_shipment_line_id=line_id,
            purchase_order_id=po_id,
            purchase_order_line_id=po_line_id,
        ))
    for line_id, reason in skipped:
        db.add(ShipmentLineSpoLink(
            id=_uuid(),
            inbound_shipment_id=shipment.id,
            inbound_shipment_line_id=line_id,
            purchase_order_id=None,
            purchase_order_line_id=None,
            unmatched_reason=reason,
        ))
    db.flush()

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "created_spos": created_spos,
        "skipped": [
            {
                "shipment_line_id": lid,
                "item_code": None,
                "reason": reason,
            }
            for lid, reason in skipped
        ],
    }


# --------------------------------------------------------------------------- #
# the AutoCount handoff worksheet
# --------------------------------------------------------------------------- #

_COLUMNS = ["SUPPLIER", "MODEL", "DESCRIPTION", "QTY", "UNIT COST", "CURRENCY", "CRM SPO NO"]


def worksheet_payload(db: Session, shipment_id: str) -> dict:
    """What the office keys into AutoCount, read back from what `create` wrote. 404 when
    this shipment has never had "Create SPO" run - there is nothing to hand off yet."""
    shipment = _shipment_or_404(db, shipment_id)
    rows = (
        db.query(ShipmentLineSpoLink, InboundShipmentLine, PurchaseOrder)
        .join(InboundShipmentLine, InboundShipmentLine.id == ShipmentLineSpoLink.inbound_shipment_line_id)
        .outerjoin(PurchaseOrder, PurchaseOrder.id == ShipmentLineSpoLink.purchase_order_id)
        .filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id,
            ShipmentLineSpoLink.purchase_order_id.isnot(None),
        )
        .all()
    )
    if not rows:
        raise AppException(
            404,
            "No SPO has been created from this shipment yet.",
            detail="not_converted",
        )

    product_ids = [str(l.product_id) for _link, l, _po in rows]
    products = {
        str(pid): (code, name)
        for pid, code, name in db.query(*_product_cols()).filter(_product_id_in(product_ids)).all()
    }
    supplier_ids = {str(po.supplier_id) for _l, _sl, po in rows if po and po.supplier_id}
    suppliers = {
        str(s.id): s.supplier_name
        for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}

    lines = []
    for link, ship_line, po in rows:
        code, name = products.get(str(ship_line.product_id), (None, None))
        po_line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.id == link.purchase_order_line_id)
            .one_or_none()
        )
        lines.append({
            "supplier_name": suppliers.get(str(po.supplier_id)) if po else None,
            "product_code": code,
            "product_name": name,
            "qty": _f(po_line.qty_ordered) if po_line else None,
            "unit_cost": _f(po_line.unit_cost) if po_line else None,
            "currency": po_line.currency if po_line else None,
            "po_number": po.po_number if po else None,
        })
    lines.sort(key=lambda l: (l["supplier_name"] or "", l["product_code"] or ""))

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "container_no": shipment.shipping_container_number,
        "lines": lines,
    }


def to_xlsx(payload: dict) -> bytes:
    """The worksheet as a workbook - same pattern as `consolidated_packing_list.to_xlsx`."""
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active or wb.create_sheet()
    ws.title = "SPO WORKSHEET"
    bold = Font(bold=True)

    for label, value in (
        ("CONTAINER", payload.get("container_no") or payload.get("shipment_number")),
        ("SHIPMENT", payload.get("shipment_number")),
    ):
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = bold
    ws.append([])

    ws.append(list(_COLUMNS))
    for col in range(1, len(_COLUMNS) + 1):
        ws.cell(row=ws.max_row, column=col).font = bold

    for line in payload["lines"]:
        ws.append([
            line["supplier_name"],
            line["product_code"],
            line["product_name"],
            line["qty"],
            line["unit_cost"],
            line["currency"],
            line["po_number"],
        ])

    for i, width in enumerate([28, 18, 34, 10, 12, 10, 20], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_filename(payload: dict) -> str:
    import re

    stem = payload.get("container_no") or payload.get("shipment_number") or payload["shipment_id"]
    stem = re.sub(r"[^A-Za-z0-9._-]", "", str(stem)) or str(payload["shipment_id"])
    return f"{stem}-spo-worksheet.xlsx"
