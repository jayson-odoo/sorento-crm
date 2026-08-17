"""The Sorento packing list: one container, every factory that loaded it.

A container is routinely filled by two or three factories, each of which sends its own list.
Ms Tee used to retype all of them into one sheet, work out what each factory owed against the
loading plan we sent it, and split the whole thing between SORENTO and MOCHA by hand. This is
that sheet, derived.

Nothing here is typed in. The factory is the supplier the line was uploaded as, the company is
the product's brand, the volume is what the supplier stated or what our own catalogue measures,
and the remarks are the difference between what the supplier was asked for and what arrived.
Reads only: `build` never writes, and `to_xlsx` is a pure function of what `build` returned.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.product import Brand, Product
from app.models.supplier_notice import SupplierNotice, SupplierNoticeLine
from app.services.error_handler import AppException

#: The captain's own file counts SANDEL / CABANA / blank under SORENTO, so this is a single
#: named brand rather than a lookup table: MOCHA is the one that is invoiced separately.
MOCHA = "MOCHA"
SORENTO = "SORENTO"
COMPANIES = (SORENTO, MOCHA)

#: What a factory with no name is called on the sheet. It sorts last.
UNASSIGNED = "Unassigned"

#: Catalogue dimensions are millimetres; volume is cubic metres.
_MM3_PER_M3 = 1_000_000_000.0

_COLUMNS = ["FACTORY", "NO", "MODEL", "DESCRIPTION", "QTY", "CTN QTY", "CBM", "LOGO", "REMARKS"]

NOT_ON_PLAN = "Not on the loading plan"


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _qty(v: float):
    """A quantity as a person writes it: 500, not 500.0, unless it really has a fraction."""
    return int(v) if float(v).is_integer() else float(v)


def _num(v: float) -> str:
    return str(_qty(v))


def _catalogue_cbm(product: Product, qty: float) -> Optional[float]:
    """Volume from the catalogue when the packing list did not state one.

    The formula is COPIED from `loading_plan_service._catalogue_cbm` rather than imported:
    that module is being changed by another lane, and two lines of arithmetic are a smaller
    cost than a merge conflict across the two features. Same mm^3 basis, times the quantity
    on the line (the loading plan wants a per-unit figure; a packing list wants the line's).
    """
    l, w, h = product.dimensions_length, product.dimensions_width, product.dimensions_height
    if l is None or w is None or h is None:
        return None
    return round(float(l) * float(w) * float(h) / _MM3_PER_M3 * float(qty), 6)


def _totals(lines: list[dict]) -> dict:
    """Sum a set of lines, and say how much of the volume it actually knows.

    `cbm_known_lines` is not decoration. A container planned against a volume that only two
    thirds of its lines contributed to is planned against a number nobody measured, and a
    partial figure printed as a full one is exactly how that happens.
    """
    known = [l["cbm"] for l in lines if l["cbm"] is not None]
    return {
        "lines": len(lines),
        "qty": sum(int(l["qty"]) for l in lines),
        "cartons": sum(int(l["cartons"] or 0) for l in lines),
        "cbm": round(sum(known), 6),
        "cbm_known_lines": len(known),
    }


def _shipment_or_404(db: Session, shipment_id: str) -> InboundShipment:
    row = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).one_or_none()
    if row is None:
        raise AppException(404, "Inbound shipment not found")
    return row


def _latest_notices(db: Session, supplier_ids: set[str]) -> dict[str, SupplierNotice]:
    """The most recent notice per supplier, on any channel.

    One notice row exists PER CHANNEL, so "the latest" is by `created_at` across all of them:
    an email and a chat sent from the same approval say the same thing, and either is the
    document the factory was working from.
    """
    if not supplier_ids:
        return {}
    rows = (
        db.query(SupplierNotice)
        .filter(SupplierNotice.supplier_id.in_(supplier_ids))
        .order_by(SupplierNotice.created_at.desc())
        .all()
    )
    latest: dict[str, SupplierNotice] = {}
    for row in rows:
        latest.setdefault(str(row.supplier_id), row)
    return latest


def _planned(db: Session, notice_ids: set[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """What each notice asked to be PACKED, per notice, summed by product.

    `produce` lines are excluded: they are stock the factory still has to make, so their
    absence from a container is the plan working rather than a discrepancy. Item code and
    name come off the notice line, which copied them on the day it was sent - a product
    renamed since must not rewrite a document the supplier already holds.
    """
    if not notice_ids:
        return {}
    rows = (
        db.query(SupplierNoticeLine)
        .filter(
            SupplierNoticeLine.notice_id.in_(notice_ids),
            SupplierNoticeLine.kind == "pack",
            SupplierNoticeLine.product_id.isnot(None),
        )
        .order_by(SupplierNoticeLine.sort_order)
        .all()
    )
    planned: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_product = planned.setdefault(str(row.notice_id), {})
        entry = by_product.get(str(row.product_id))
        if entry is None:
            by_product[str(row.product_id)] = {
                "product_id": str(row.product_id),
                "product_code": row.item_code,
                "product_name": row.product_name,
                "qty": float(row.qty or 0),
            }
        else:
            entry["qty"] += float(row.qty or 0)
    return planned


def _discrepancies(planned_qty: Optional[float], qty: float, has_plan: bool) -> list[str]:
    """Where this line differs from what the factory was asked for, in words.

    A factory that was never sent a plan is compared against nothing: marking every one of
    its lines "Not on the loading plan" would read as a container full of mistakes.
    """
    if not has_plan:
        return []
    if planned_qty is None:
        return [NOT_ON_PLAN]
    if planned_qty == qty:
        return []
    diff = abs(planned_qty - qty)
    direction = "short" if planned_qty > qty else "over"
    return [
        f"Loading plan asked {_num(planned_qty)}, packed {_num(qty)} "
        f"({direction} {_num(diff)})"
    ]


def build(db: Session, shipment_id: str) -> dict:
    """The consolidated list for one container. 404 only when the container is unknown.

    A container with no lines is a container that has been read but not unpacked, which the
    screen has to be able to draw - so it is an empty list of factories, not an error.
    """
    shipment = _shipment_or_404(db, shipment_id)

    # One query per table. The product and its brand travel with the line because every line
    # needs both: the model number to print and the brand to split the company by.
    rows = (
        db.query(InboundShipmentLine, Product, Brand)
        .join(Product, Product.id == InboundShipmentLine.product_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .filter(InboundShipmentLine.shipment_id == str(shipment.id))
        .all()
    )

    supplier_ids = {str(line.supplier_id) for line, _p, _b in rows if line.supplier_id}
    suppliers = (
        {
            str(s.id): s
            for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
        }
        if supplier_ids
        else {}
    )
    notices = _latest_notices(db, supplier_ids)
    planned = _planned(db, {str(n.id) for n in notices.values()})

    grouped: dict[Optional[str], list[dict]] = {}
    for line, product, brand in rows:
        brand_code = (brand.brand_code or "").strip() if brand else None
        qty = int(line.quantity_shipped or 0)
        cbm = _f(line.cbm)
        if cbm is None:
            cbm = _catalogue_cbm(product, qty)
        grouped.setdefault(str(line.supplier_id) if line.supplier_id else None, []).append(
            {
                "line_id": str(line.id),
                "product_id": str(product.id),
                "product_code": product.product_code,
                "product_name": product.product_name,
                "brand": brand_code or None,
                "company": MOCHA if (brand_code or "").upper() == MOCHA else SORENTO,
                "qty": qty,
                "cartons": int(line.cartons_count or 0),
                "cbm": cbm,
                "remarks": line.remarks,
                "discrepancies": [],
            }
        )

    factories: list[dict] = []
    for supplier_id, lines in grouped.items():
        supplier = suppliers.get(supplier_id) if supplier_id else None
        notice = notices.get(supplier_id) if supplier_id else None
        plan_lines = planned.get(str(notice.id), {}) if notice else {}
        lines.sort(key=lambda l: (l["product_code"] or "", l["line_id"]))

        shipped_ids = set()
        for line in lines:
            shipped_ids.add(line["product_id"])
            entry = plan_lines.get(line["product_id"])
            line["discrepancies"] = _discrepancies(
                entry["qty"] if entry else None, float(line["qty"]), notice is not None
            )

        not_packed = [
            {
                "product_id": entry["product_id"],
                "product_code": entry["product_code"],
                "product_name": entry["product_name"],
                "planned_qty": _qty(entry["qty"]),
            }
            for entry in plan_lines.values()
            if entry["product_id"] not in shipped_ids
        ]

        factories.append(
            {
                "supplier_id": supplier_id,
                "supplier_code": supplier.supplier_code if supplier else None,
                "supplier_name": supplier.supplier_name if supplier else UNASSIGNED,
                "loading_plan_id": str(notice.loading_plan_id)
                if notice and notice.loading_plan_id
                else None,
                "notice_id": str(notice.id) if notice else None,
                "lines": lines,
                "not_packed": not_packed,
                "subtotal": _totals(lines),
            }
        )

    # By factory name, with the one we were never told last: an unnamed group at the top
    # would be the first thing read and the least useful.
    factories.sort(key=lambda f: (f["supplier_id"] is None, (f["supplier_name"] or "").upper()))

    all_lines = [line for factory in factories for line in factory["lines"]]
    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "container_no": shipment.shipping_container_number,
        "bl_no": shipment.bill_of_lading_number,
        "status": shipment.shipment_status,
        "factories": factories,
        "total": _totals(all_lines),
        # Both rows always, zeros included: an absent company reads as a missing figure
        # rather than as nothing having shipped under it.
        "split": [
            {"company": company, **_totals([l for l in all_lines if l["company"] == company])}
            for company in COMPANIES
        ],
    }


# --------------------------------------------------------------------------- #
# the workbook
# --------------------------------------------------------------------------- #


_WIDTHS = [28, 6, 22, 40, 10, 10, 10, 12, 46]


def _container_label(payload: dict) -> str:
    return payload.get("container_no") or payload.get("shipment_number") or ""


def _remarks(line: dict) -> str:
    """The supplier's own note and the derived difference, in that order.

    Kept in one cell because the sheet Ms Tee built by hand had one remarks column, and a
    second column would be empty on most rows.
    """
    parts = [p for p in [line.get("remarks")] + list(line.get("discrepancies") or []) if p]
    return "; ".join(parts)


def to_xlsx(payload: dict) -> bytes:
    """The same list as the file that used to be typed by hand, as an in-memory workbook."""
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active or wb.create_sheet()
    ws.title = "PACKING LIST"
    bold = Font(bold=True)

    factory_names = ", ".join(
        f["supplier_name"] for f in payload["factories"] if f.get("supplier_name")
    )
    for label, value in (
        ("CONTAINER", _container_label(payload)),
        ("BL", payload.get("bl_no")),
        ("STATUS", payload.get("status")),
        ("FACTORY", factory_names),
    ):
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = bold
    ws.append([])

    ws.append(list(_COLUMNS))
    for col in range(1, len(_COLUMNS) + 1):
        ws.cell(row=ws.max_row, column=col).font = bold

    for factory in payload["factories"]:
        name = factory.get("supplier_name") or UNASSIGNED
        for i, line in enumerate(factory["lines"], start=1):
            ws.append(
                [
                    name if i == 1 else None,
                    i,
                    line["product_code"],
                    line["product_name"],
                    line["qty"],
                    line["cartons"],
                    line["cbm"],
                    line.get("brand"),
                    _remarks(line),
                ]
            )
        subtotal = factory["subtotal"]
        ws.append(
            [
                f"{name} subtotal",
                None,
                None,
                None,
                subtotal["qty"],
                subtotal["cartons"],
                subtotal["cbm"],
                None,
                None,
            ]
        )
        for col in range(1, len(_COLUMNS) + 1):
            ws.cell(row=ws.max_row, column=col).font = bold
        # What was asked for and never came, under the factory that owed it. QTY is left
        # empty on purpose: a zero here would be summed as a quantity that shipped.
        for missing in factory.get("not_packed") or []:
            ws.append(
                [
                    None,
                    None,
                    missing["product_code"],
                    missing["product_name"],
                    None,
                    None,
                    None,
                    None,
                    f"Not packed - loading plan asked {_num(missing['planned_qty'])}",
                ]
            )

    total = payload["total"]
    ws.append(
        ["TOTAL", None, None, None, total["qty"], total["cartons"], total["cbm"], None, None]
    )
    for col in range(1, len(_COLUMNS) + 1):
        ws.cell(row=ws.max_row, column=col).font = bold

    for row in payload["split"]:
        ws.append(
            [
                row["company"],
                None,
                None,
                None,
                row["qty"],
                row["cartons"],
                row["cbm"],
                None,
                None,
            ]
        )
        ws.cell(row=ws.max_row, column=1).font = bold

    for i, width in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_filename(payload: dict) -> str:
    """`<container>-packing-list.xlsx`, with anything a filesystem would argue about removed."""
    stem = _container_label(payload) or payload["shipment_id"]
    stem = re.sub(r"[^A-Za-z0-9._-]", "", str(stem)) or str(payload["shipment_id"])
    return f"{stem}-packing-list.xlsx"
