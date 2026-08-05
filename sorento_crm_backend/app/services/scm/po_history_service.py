"""L2 - writing purchase-order HISTORY from the AutoCount listing export.

The reader next door is pure; this is the write path. One rule governs everything else:

**History must never read as incoming supply.** `scm.on_order_v` counts a line when it is
OPEN and still has quantity to come, so history is written closed AND fully received. It
fails both halves, which means it is excluded by construction rather than by a filter
somebody has to remember to add to every future query. 1,586 closed 2020 orders counted as
on-order would inflate every position in the system, suppress the buys those positions feed,
and look perfectly plausible while doing it.

What history IS for, per the user: the purchase date. An order placed years ago against stock
still on hand is the strongest evidence there is that an item does not sell - stronger than
demand variance, because it is a fact about this stock rather than a statistic about a
window. That evidence only exists if the date is imported rather than stamped as today.

Two things this service refuses to do:

  * **Invent catalogue rows.** An item code the catalogue does not hold is counted and named,
    never created. Building a product catalogue out of a 2020 purchase report is how a
    catalogue stops meaning anything.
  * **Guess a line-level SO link.** The `**SO:174830**` notes are order-level (see the
    reader), so the claims written here carry no item code.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services.scm.po_listing_reader import PoListingResult, read_po_listing
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

#: Written on every row this feed creates, so a later reader can tell imported history from
#: an order somebody raised in the system.
SOURCE_SYSTEM = "scm_po_history"

#: The status a historical order carries. `closed` is in `on_order_v`'s status list, which is
#: deliberate: the exclusion is done by the LINE being closed and fully received, so the
#: order's own status stays honest about what it is rather than being bent to hide it.
_ORDER_STATUS = "closed"


def _now() -> datetime:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


def _products_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(Product.product_code, Product.id)
        .filter(Product.product_code.in_(list(codes)))
        .all()
    )
    return {str(code): str(pid) for code, pid in rows}


def _suppliers_by_code(db: Session, codes: set[str]) -> dict[str, Supplier]:
    if not codes:
        return {}
    rows = db.query(Supplier).filter(Supplier.supplier_code.in_(list(codes))).all()
    return {str(s.supplier_code): s for s in rows}


def _summarise(db: Session, parsed: PoListingResult) -> dict:
    """Counts both entry points report, computed once so they cannot disagree."""
    stock_codes = {
        l.item_code for o in parsed.orders for l in o.lines if l.is_stock_item
    }
    known = _products_by_code(db, stock_codes)
    unmatched = sorted(stock_codes - set(known))
    existing = {
        n
        for (n,) in db.query(PurchaseOrder.po_number)
        .filter(PurchaseOrder.po_number.in_([o.po_number for o in parsed.orders]))
        .all()
    } if parsed.orders else set()

    return {
        "ok": parsed.ok,
        "problems": list(parsed.problems),
        "orders": len(parsed.orders),
        "orders_new": sum(1 for o in parsed.orders if o.po_number not in existing),
        "orders_existing": sum(1 for o in parsed.orders if o.po_number in existing),
        "lines": parsed.line_count,
        "charge_lines": sum(
            1 for o in parsed.orders for l in o.lines if not l.is_stock_item
        ),
        "unmatched_items": len(unmatched),
        # Named, not just counted: a count tells somebody there is a problem, the codes tell
        # them which one, and the list is what they take to whoever owns the catalogue.
        "unmatched_item_codes": unmatched[:200],
        "so_claims": sum(len(o.so_numbers) for o in parsed.orders),
        "date_from": min(
            (o.order_date for o in parsed.orders if o.order_date), default=None
        ),
        "date_to": max((o.order_date for o in parsed.orders if o.order_date), default=None),
    }


def preview(db: Session, file_data: bytes) -> dict:
    """What this file would write. Writes nothing."""
    parsed = read_po_listing(file_data)
    out = _summarise(db, parsed)
    out["date_from"] = out["date_from"].isoformat() if out["date_from"] else None
    out["date_to"] = out["date_to"].isoformat() if out["date_to"] else None
    return out


def apply(db: Session, file_data: bytes, actor: Optional[str] = None) -> dict:
    """Write the history. Idempotent on the document number.

    Re-uploading is normal - somebody re-exports a wider date range and sends the whole book
    again. Without idempotency the second upload doubles every historical quantity, and
    because the lines are closed nothing downstream would show it until a supplier's cost
    history was read and found twice.
    """
    parsed = read_po_listing(file_data)
    summary = _summarise(db, parsed)
    if not parsed.ok:
        summary["orders_created"] = 0
        summary["lines_created"] = 0
        summary["date_from"] = None
        summary["date_to"] = None
        return summary

    stock_codes = {l.item_code for o in parsed.orders for l in o.lines if l.is_stock_item}
    product_by_code = _products_by_code(db, stock_codes)

    supplier_codes = {o.supplier_code for o in parsed.orders if o.supplier_code}
    supplier_by_code = _suppliers_by_code(db, supplier_codes)

    existing_orders = {
        o.po_number: o
        for o in db.query(PurchaseOrder)
        .filter(PurchaseOrder.po_number.in_([o.po_number for o in parsed.orders]))
        .all()
    }

    orders_created = 0
    lines_created = 0
    now = _now()

    for parsed_order in parsed.orders:
        supplier = supplier_by_code.get(parsed_order.supplier_code)
        if supplier is None and parsed_order.supplier_code:
            # Created from the creditor code, which IS the supplier's identity in AutoCount.
            # Unlike a product, a supplier named on a real purchase order is evidence the
            # supplier exists - and a purchase order with no creditor cannot be reconciled.
            # `suppliers` carries no source columns, so the provenance of an imported
            # creditor lives on the orders that name it rather than on the supplier row.
            supplier = Supplier(
                supplier_code=parsed_order.supplier_code,
                supplier_name=parsed_order.supplier_name or parsed_order.supplier_code,
            )
            db.add(supplier)
            db.flush()
            supplier_by_code[parsed_order.supplier_code] = supplier

        order = existing_orders.get(parsed_order.po_number)
        if order is None:
            order = PurchaseOrder(
                po_number=parsed_order.po_number,
                supplier_id=str(supplier.id) if supplier else None,
                issue_date=parsed_order.order_date,
                status=_ORDER_STATUS,
                currency=parsed_order.currency or None,
                source_system=SOURCE_SYSTEM,
                source_ref="po_listing",
            )
            db.add(order)
            db.flush()
            existing_orders[parsed_order.po_number] = order
            orders_created += 1
        else:
            # A re-upload of a document already held is not an error and not a second copy:
            # the file is the source of truth for what was ordered, so the header is refreshed
            # and the lines below are keyed by line number.
            order.issue_date = parsed_order.order_date or order.issue_date
            order.currency = parsed_order.currency or order.currency
            if supplier is not None:
                order.supplier_id = str(supplier.id)

        existing_lines = {
            (int(l.source_ref) if (l.source_ref or "").isdigit() else None): l
            for l in db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == str(order.id))
            .all()
        }

        for parsed_line in parsed_order.lines:
            if not parsed_line.is_stock_item:
                # Real money on the order, no product behind it. Carried by the reader so the
                # order total reconciles, and NOT written as a stock line: a quantity of 1
                # "HANDLING CHARGES" is not inventory, and the code would sit in the
                # unmatched list for ever.
                continue
            product_id = product_by_code.get(parsed_line.item_code)
            if product_id is None:
                # Counted in the summary and named there. Never created.
                continue

            line = existing_lines.get(parsed_line.line_no)
            if line is None:
                line = PurchaseOrderLine(
                    purchase_order_id=str(order.id),
                    product_id=product_id,
                    warehouse_id=None,  # the export names no location; L3 supplies it
                    qty_ordered=parsed_line.qty_ordered,
                    # Fully received, so `on_order_v` cannot count it however the line
                    # status is later edited.
                    qty_received=parsed_line.qty_ordered,
                    unit_cost=parsed_line.unit_price,
                    currency=parsed_order.currency or None,
                    line_status="closed",
                    source_system=SOURCE_SYSTEM,
                    source_ref=str(parsed_line.line_no) if parsed_line.line_no else None,
                )
                db.add(line)
                lines_created += 1
            else:
                line.qty_ordered = parsed_line.qty_ordered
                line.qty_received = parsed_line.qty_ordered
                line.unit_cost = parsed_line.unit_price
                line.line_status = "closed"

        _claim_so_links(db, parsed_order.po_number, parsed_order.so_numbers, now)

    db.flush()
    summary["orders_created"] = orders_created
    summary["lines_created"] = lines_created
    summary["date_from"] = summary["date_from"].isoformat() if summary["date_from"] else None
    summary["date_to"] = summary["date_to"].isoformat() if summary["date_to"] else None
    return summary


def _claim_so_links(
    db: Session, po_number: str, so_numbers: tuple[str, ...], now: datetime
) -> None:
    """Record the sales orders this purchase order's notes name.

    A CLAIM, not a link: the sales order may not have been uploaded yet, which is exactly the
    case the user described. No item code, because a note sits between lines and nothing in
    the file says which side it describes.
    """
    for so_number in so_numbers:
        exists = (
            db.query(OrderLinkClaim.id)
            .filter(
                OrderLinkClaim.so_number == so_number,
                OrderLinkClaim.po_number == po_number,
                OrderLinkClaim.item_code.is_(None),
            )
            .first()
        )
        if exists:
            continue
        db.add(
            OrderLinkClaim(
                so_number=so_number,
                po_number=po_number,
                item_code=None,
                source="po_history",
                claimed_at=now,
            )
        )
