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

from sqlalchemy import func

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services.scm import upload_validation as val
from app.services.scm.order_inquiry_reader import OrderInquiryResult, read_order_inquiry
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

SOURCE = "order_inquiry"

#: Stamped on every sales order and line this feed CREATES. It is the ownership marker the
#: whole precedence rule turns on: the sheet may refresh what it wrote, and must not touch
#: what anybody else wrote.
SOURCE_SYSTEM = "scm_order_inquiry"


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


def validate(db: Session, file_data: bytes) -> dict:
    """The Test verdict: `{valid, errors, warnings, summary}`. Writes nothing.

    Only an unreadable sheet is an ERROR. A row naming an item we do not hold is a warning
    rather than a blocker, even though that row can never become demand: `product_id` is NOT
    NULL, so the alternative to skipping it is inventing a product, and refusing the whole
    sheet over it would throw away every row that IS resolvable.
    """
    out = preview(db, file_data)
    warnings = [
        val.named(
            len(out["unknown_locations"]), out["unknown_locations"],
            one="stock location we do not recognise",
            many="stock locations we do not recognise",
        ),
        (f"{out['not_ordered']:,} rows are marked ORDER - nothing has been placed for them "
         f"yet, so they carry no purchase-order link") if out["not_ordered"] else None,
        (f"{len(out['sheets_skipped']):,} sheets had no header row and were skipped: "
         f"{', '.join(out['sheets_skipped'][:12])}") if out["sheets_skipped"] else None,
    ]
    return val.envelope(
        ok=out["ok"], problems=out["problems"], warnings=warnings,
        summary={
            "total_rows": out["rows"],
            "would_update": out["lines_matched"],
            "error_count": 0 if out["ok"] else len(out["problems"]),
            "sheets_read": len(out["sheets_read"]),
            "po_links": out["po_claims"],
        },
    )


def _products_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(Product.product_code, Product.id)
        .filter(Product.product_code.in_(list(codes)))
        .all()
    )
    return {str(code): str(pid) for code, pid in rows}


def _orders_by_number(db: Session, numbers: set[str]) -> dict[str, SalesOrder]:
    if not numbers:
        return {}
    rows = db.query(SalesOrder).filter(SalesOrder.so_number.in_(list(numbers))).all()
    return {str(o.so_number): o for o in rows}


def _customers_by_name(db: Session, names: set[str]) -> dict[str, str]:
    """Existing customers only, matched case-insensitively on the exact name.

    Deliberately does NOT create. `customers` requires a `customer_code` and enforces
    uniqueness on `(lower(code), lower(name))`, so creating one from a project label means
    inventing a debtor code in a table Sales owns - where a guess either collides with a real
    account or silently duplicates it. Unmatched names are kept as text on the order instead.
    """
    if not names:
        return {}
    rows = (
        db.query(Customer.customer_name, Customer.id)
        .filter(func.lower(Customer.customer_name).in_([n.lower() for n in names]))
        .all()
    )
    return {str(name).lower(): str(cid) for name, cid in rows}


def _create_orders(db: Session, parsed, now: datetime) -> dict:
    """Turn the sheet's rows into sales orders, under the ownership rule.

    The rule, in one place because it is the whole design:

    * no such order -> create it, header and lines, stamped with this feed.
    * an order THIS feed created -> refresh its lines, keyed by (order, item).
    * an order anybody else created -> leave every figure alone. The caller still writes the
      stock location and the purchase-order claim, which is all this sheet did before.

    "Last writer wins" across two feeds with different refresh rhythms is how a quantity
    silently reverts, so the owner is recorded rather than inferred.
    """
    by_number: dict[str, list] = {}
    for row in parsed.rows:
        by_number.setdefault(row.so_number, []).append(row)

    existing = _orders_by_number(db, set(by_number))
    products = _products_by_code(db, {r.item_code for r in parsed.rows if r.item_code})
    warehouses = _warehouses_by_code(db, {r.location for r in parsed.rows if r.location})
    customers = _customers_by_name(db, {r.project for r in parsed.rows if r.project})

    orders_created = lines_created = lines_refreshed = 0
    orders_owned_elsewhere = 0
    unmatched_items: set[str] = set()

    for number, rows in by_number.items():
        order = existing.get(number)
        if order is not None and (order.source_system or "") != SOURCE_SYSTEM:
            # Somebody else's order. The caller still annotates it; nothing here touches it.
            orders_owned_elsewhere += 1
            continue

        buildable = [r for r in rows if r.item_code and r.item_code in products]
        unmatched_items.update(r.item_code for r in rows if r.item_code not in products)
        if order is None and not buildable:
            # An order with no line we can build is not an order. Creating an empty header
            # would put a phantom sales order in the list that no plan can ever read.
            continue

        if order is None:
            project = next((r.project for r in rows if r.project), "")
            dates = [r.delivery_date for r in rows if r.delivery_date]
            order = SalesOrder(
                so_number=number,
                customer_id=customers.get(project.lower()) if project else None,
                # The project stays legible even when no customer matches it.
                internal_note=f"Order Inquiry project: {project}" if (
                    project and not customers.get(project.lower())
                ) else None,
                order_date=next((r.so_date for r in rows if r.so_date), None),
                requested_delivery_date=min(dates) if dates else None,
                order_type="project" if project else None,
                demand_class="project" if project else None,
                status="open",
                source_system=SOURCE_SYSTEM,
                source_ref=SOURCE,
            )
            db.add(order)
            db.flush()
            existing[number] = order
            orders_created += 1
            current: dict[str, SalesOrderLine] = {}
        else:
            current = {
                str(pc): ln
                for pc, ln in db.query(Product.product_code, SalesOrderLine)
                .join(SalesOrderLine, SalesOrderLine.product_id == Product.id)
                .filter(SalesOrderLine.sales_order_id == str(order.id))
                .all()
            }

        for row in buildable:
            line = current.get(row.item_code)
            qty = float(row.qty or 0)
            warehouse_id = warehouses.get(row.location) if row.location else None
            if line is None:
                db.add(SalesOrderLine(
                    sales_order_id=str(order.id),
                    product_id=products[row.item_code],
                    warehouse_id=warehouse_id,
                    qty_ordered=qty,
                    qty_delivered=0,
                    line_status="open",
                    required_date=row.delivery_date,
                    source_system=SOURCE_SYSTEM,
                    source_ref=SOURCE,
                ))
                lines_created += 1
            else:
                # Its own line, so the file is the truth for it: a quantity corrected in the
                # sheet has to reach the plan, and the alternative is a second line.
                line.qty_ordered = qty
                line.required_date = row.delivery_date or line.required_date
                if warehouse_id:
                    line.warehouse_id = warehouse_id
                lines_refreshed += 1

    db.flush()
    return {
        "orders_created": orders_created,
        "lines_created": lines_created,
        "lines_refreshed": lines_refreshed,
        "orders_owned_elsewhere": orders_owned_elsewhere,
        "unmatched_item_codes": sorted(unmatched_items)[:200],
        "unmatched_items": len(unmatched_items),
    }


def apply(db: Session, file_data: bytes, actor: Optional[str] = None) -> dict:
    """Create the demand the sheet carries, then write locations and claim the PO links."""
    parsed = read_order_inquiry(file_data)
    summary = _summarise(db, parsed)
    summary["locations_written"] = 0
    summary["claims_written"] = 0
    summary["orders_created"] = 0
    summary["lines_created"] = 0
    summary["lines_refreshed"] = 0
    summary["orders_owned_elsewhere"] = 0
    if not parsed.ok:
        return summary

    now = _now()
    # Create first: the annotate loop below reads sales-order lines, and the ones this call
    # just wrote are exactly the ones the sheet has a location for.
    created = _create_orders(db, parsed, now)
    summary.update(created)

    known_lines = _so_lines(db, {r.so_number for r in parsed.rows})
    warehouses = _warehouses_by_code(
        db, {r.location for r in parsed.rows if r.location}
    )
    # Re-derived AFTER creating, because `_summarise` ran against the state before this
    # upload: it counted 15,787 rows as "sales order not found" and the very next step
    # created most of those orders. Reporting the earlier figure would have the result
    # contradict itself on the same screen.
    matched_now = sum(
        1 for r in parsed.rows if (r.so_number, r.item_code) in known_lines
    )
    summary["lines_matched"] = matched_now
    summary["lines_unmatched"] = len(parsed.rows) - matched_now
    summary["sales_orders_not_found"] = sorted({
        r.so_number for r in parsed.rows if (r.so_number, r.item_code) not in known_lines
    })[:200]
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
