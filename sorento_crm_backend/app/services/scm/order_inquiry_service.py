"""L3 - writing what the Order Inquiry sheet knows.

The sheet supplies the two things the sales-order and purchase-order books do not, and this
service writes each to the place that reads it:

  * **the stock location** onto the sales-order line, because netting is per warehouse and a
    line with no location reaches no pool's timeline at all;
  * **the purchase order the line waits on**, as a CLAIM, because the purchase order may not
    have been uploaded yet.

Two honest limits, both counted and named rather than smoothed over.

**A location can only be written onto a line that exists.** Where the sales order has not
been uploaded yet the location has nowhere to go, so those rows are counted and their sales
orders named. Re-uploading the sheet after the SO book lands applies them - which is what the
customer does anyway. (The PO pairing does NOT have this limit: that is exactly what the
claim table is for.)

**A warehouse code the system does not hold is not created.** `BRW-IB` has to be a warehouse
somebody has configured, with a pool and an availability flag; inventing one from a
spreadsheet cell would put stock in a location that takes part in no pool and belongs to
nobody.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services.scm.order_inquiry_reader import OrderInquiryResult, read_order_inquiry
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

SOURCE = "order_inquiry"


def _now() -> datetime:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


def _warehouses_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(Warehouse.warehouse_code, Warehouse.id)
        .filter(Warehouse.warehouse_code.in_(list(codes)))
        .all()
    )
    return {str(code).upper(): str(wid) for code, wid in rows}


def _so_lines(db: Session, so_numbers: set[str]) -> dict[tuple[str, str], SalesOrderLine]:
    """Sales-order lines keyed by (SO number, item code) - the user's chosen match key.

    Per line, not per order: one purchase order covering lines from more than one sales order
    is visible in the customer's data, so matching on the number alone would attach the whole
    order to whichever sales order was seen first.
    """
    if not so_numbers:
        return {}
    rows = (
        db.query(SalesOrder.so_number, Product.product_code, SalesOrderLine)
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .filter(SalesOrder.so_number.in_(list(so_numbers)))
        .all()
    )
    return {(str(so), str(code)): line for so, code, line in rows}


def _summarise(db: Session, parsed: OrderInquiryResult) -> dict:
    so_numbers = {r.so_number for r in parsed.rows}
    known_lines = _so_lines(db, so_numbers)
    codes = {r.location for r in parsed.rows if r.location}
    known_warehouses = _warehouses_by_code(db, codes)

    matched = sum(1 for r in parsed.rows if (r.so_number, r.item_code) in known_lines)
    unknown_locations = sorted(codes - set(known_warehouses))
    missing_orders = sorted(
        {
            r.so_number
            for r in parsed.rows
            if (r.so_number, r.item_code) not in known_lines
        }
    )
    return {
        "ok": parsed.ok,
        "problems": list(parsed.problems),
        "rows": len(parsed.rows),
        "sheets_read": list(parsed.sheets_read),
        "sheets_skipped": list(parsed.sheets_skipped),
        "lines_matched": matched,
        "lines_unmatched": len(parsed.rows) - matched,
        # Named, so somebody can see WHICH sales orders have not been uploaded yet rather
        # than only that some have not.
        "sales_orders_not_found": missing_orders[:200],
        "with_location": parsed.with_location,
        "unknown_locations": unknown_locations,
        "po_claims": parsed.po_claims,
        "not_ordered": sum(1 for r in parsed.rows if r.not_ordered),
    }


def preview(db: Session, file_data: bytes) -> dict:
    """What this sheet would write. Writes nothing."""
    return _summarise(db, read_order_inquiry(file_data))


def apply(db: Session, file_data: bytes, actor: Optional[str] = None) -> dict:
    """Write the locations and claim the purchase-order links."""
    parsed = read_order_inquiry(file_data)
    summary = _summarise(db, parsed)
    summary["locations_written"] = 0
    summary["claims_written"] = 0
    if not parsed.ok:
        return summary

    known_lines = _so_lines(db, {r.so_number for r in parsed.rows})
    warehouses = _warehouses_by_code(
        db, {r.location for r in parsed.rows if r.location}
    )
    now = _now()
    locations_written = 0
    claims_written = 0
    seen_claims: set[tuple[str, str, str]] = set()

    for row in parsed.rows:
        line = known_lines.get((row.so_number, row.item_code))
        if line is not None and row.location:
            warehouse_id = warehouses.get(row.location)
            if warehouse_id and str(line.warehouse_id or "") != warehouse_id:
                # The sheet is the source of truth for where a line ships from: it is
                # maintained by the people who decide it, and the SO book does not carry it.
                line.warehouse_id = warehouse_id
                locations_written += 1

        for po_number in row.po_numbers:
            key = (row.so_number, po_number, row.item_code)
            if key in seen_claims:
                continue
            seen_claims.add(key)
            exists = (
                db.query(OrderLinkClaim.id)
                .filter(
                    OrderLinkClaim.so_number == row.so_number,
                    OrderLinkClaim.po_number == po_number,
                    OrderLinkClaim.item_code == row.item_code,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                OrderLinkClaim(
                    so_number=row.so_number,
                    po_number=po_number,
                    # Per LINE here, unlike the PO notes: this sheet states the item outright,
                    # so there is nothing to guess.
                    item_code=row.item_code,
                    source=SOURCE,
                    claimed_at=now,
                )
            )
            claims_written += 1

    db.flush()
    summary["locations_written"] = locations_written
    summary["claims_written"] = claims_written
    return summary
