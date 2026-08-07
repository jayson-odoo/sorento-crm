"""L2 - absorbing the AutoCount sales-order listing as sales-order HISTORY.

The demand-side twin of `po_history_service`, and it obeys the same governing rule with the
sign flipped:

**History must never read as committed demand.** `scm.committed_v` counts a sales-order line
when it is OPEN and still has quantity to deliver, so history is written closed AND fully
delivered. It fails both halves, which means it is excluded by construction rather than by a
filter somebody has to remember to add to every future query. The client's export carries
11,275 documents and 81,361 lines going back to 2020; counted as commitments they would
demand three million units nobody owes, and the plan would try to buy them.

What history IS for: the demand record. Six years of what sold, when, to whom, from which
location, at what price, per line. `scm.consumption_v` reads delivery orders and the stock
ledger, which is the movement; this is the ORDER behind the movement, and it carries the
customer, the location and the requested date the ledger does not.

Three things this service refuses to do:

  * **Invent catalogue rows.** An item code the catalogue does not hold is counted and named,
    never created. Seventeen of the client's 3,357 codes do not resolve; building a product
    out of a 2020 sales report is how a catalogue stops meaning anything.
  * **Invent customers.** Unlike the purchase side - where a creditor named on a real order
    IS evidence the supplier exists and an order with no creditor cannot be reconciled - a
    sales order with an unresolved debtor is still a perfectly good demand record. It is
    written with no customer link, and the debtor code is kept on the order so the link can
    be made later. 472 of the client's 882 debtor codes are not in the CRM.
  * **Write an outstanding line.** Even when the file states one. See `outstanding_line_count`
    on the read result: those lines are counted and reported so the uploader is told to use
    the outstanding channel for them, rather than having this feed quietly create commitments
    from a file whose whole purpose is history.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.inventory import Warehouse
from app.models.product import Product
from app.services.import_alias_service import AliasResolver
from app.services.scm.so_listing_reader import (
    DOC_TYPE,
    SoListingResult,
    read_so_listing,
)
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

#: Written on every row this feed creates, so a later reader can tell absorbed history from
#: an order somebody raised in the system, and so a correction can find its own rows.
SOURCE_SYSTEM = "scm_so_history"
SOURCE_REF = "so_listing"

#: What a historical document carries. The exclusion from `committed_v` is done by the LINE
#: being closed and fully delivered, so the order's own status stays honest about what it is
#: rather than being bent to hide it.
_ORDER_STATUS = "closed"
_LINE_STATUS = "closed"


def _now() -> datetime:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


def _by_code(db: Session, model, code_col, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(code_col, model.id)
        .filter(code_col.in_(list(codes)))
        .all()
    )
    return {str(code): str(row_id) for code, row_id in rows}


def _summarise(db: Session, parsed: SoListingResult) -> dict:
    """What the uploader is told, before anything is written.

    Every figure here is a count of something specific rather than a pass/fail, because the
    decision the uploader makes is "is this the right file", and a single number cannot
    answer it.
    """
    stock_codes = {
        ln.item_code for o in parsed.orders for ln in o.lines if ln.is_stock_item
    }
    debtor_codes = {o.debtor_code for o in parsed.orders if o.debtor_code}
    locations = {ln.location for o in parsed.orders for ln in o.lines if ln.location}

    known_items = _by_code(db, Product, Product.product_code, stock_codes)
    known_debtors = _by_code(db, Customer, Customer.customer_code, debtor_codes)
    known_locations = _by_code(db, Warehouse, Warehouse.warehouse_code, locations)

    dates = [o.order_date for o in parsed.orders if o.order_date]
    return {
        "doc_type": DOC_TYPE,
        "orders": len(parsed.orders),
        "lines": parsed.line_count,
        "total_rows": parsed.total_rows,
        "layout_rows": parsed.layout_rows,
        "problems": [
            {"row": p.row_number, "reason": p.reason, "value": p.value}
            for p in parsed.problems
        ],
        "unmapped_headers": parsed.unmapped_headers,
        "missing_columns": parsed.missing_columns,
        "non_stock_lines": sum(
            1 for o in parsed.orders for ln in o.lines if not ln.is_stock_item
        ),
        # Named, not just counted: "17 unknown items" is a number, and the 17 codes are the
        # thing somebody can actually go and fix.
        "unknown_items": sorted(stock_codes - set(known_items))[:50],
        "unknown_item_count": len(stock_codes - set(known_items)),
        "unknown_debtors": sorted(debtor_codes - set(known_debtors))[:50],
        "unknown_debtor_count": len(debtor_codes - set(known_debtors)),
        "unknown_locations": sorted(locations - set(known_locations)),
        # The one figure that says "this file is not what you think it is".
        "outstanding_lines": parsed.outstanding_line_count,
        "date_from": min(dates) if dates else None,
        "date_to": max(dates) if dates else None,
    }


def _serialise_dates(summary: dict) -> dict:
    for key in ("date_from", "date_to"):
        if summary.get(key) is not None:
            summary[key] = summary[key].isoformat()
    return summary


def preview(db: Session, file_data: bytes) -> dict:
    """Read and describe, writing nothing."""
    resolver = AliasResolver.for_doc_type(db, DOC_TYPE)
    parsed = read_so_listing(file_data, resolver)
    return _serialise_dates(_summarise(db, parsed))


def apply(db: Session, file_data: bytes, actor: Optional[str] = None) -> dict:
    """Write the history. Idempotent on the document number.

    Re-uploading is normal - somebody re-exports a wider date range and sends the whole book
    again. Without idempotency the second upload doubles six years of demand, and because
    every line is closed nothing downstream would show it until somebody read a customer's
    order history and found it twice.

    Lines are keyed by their ORDINAL within the document, because the export carries no line
    number and one order routinely repeats the same item at the same location and price. Any
    content-based key would collapse those repeats into one line and lose real quantity.
    """
    resolver = AliasResolver.for_doc_type(db, DOC_TYPE)
    parsed = read_so_listing(file_data, resolver)
    summary = _summarise(db, parsed)
    summary.update({"orders_created": 0, "orders_updated": 0, "lines_created": 0})
    if not parsed.ok:
        return _serialise_dates(summary)

    stock_codes = {
        ln.item_code for o in parsed.orders for ln in o.lines if ln.is_stock_item
    }
    product_by_code = _by_code(db, Product, Product.product_code, stock_codes)
    customer_by_code = _by_code(
        db, Customer, Customer.customer_code,
        {o.debtor_code for o in parsed.orders if o.debtor_code},
    )
    warehouse_by_code = _by_code(
        db, Warehouse, Warehouse.warehouse_code,
        {ln.location for o in parsed.orders for ln in o.lines if ln.location},
    )

    numbers = [o.so_number for o in parsed.orders]
    existing = {
        row.so_number: row
        for row in db.query(SalesOrder).filter(SalesOrder.so_number.in_(numbers)).all()
    }

    orders_created = orders_updated = lines_created = 0

    for parsed_order in parsed.orders:
        order = existing.get(parsed_order.so_number)
        customer_id = customer_by_code.get(parsed_order.debtor_code)
        if order is None:
            order = SalesOrder(
                so_number=parsed_order.so_number,
                customer_id=customer_id,
                order_date=parsed_order.order_date,
                requested_delivery_date=parsed_order.requested_delivery_date,
                status=_ORDER_STATUS,
                source_system=SOURCE_SYSTEM,
                source_ref=SOURCE_REF,
                source_doc_no=parsed_order.so_number,
                # The debtor code and the customer's printed name are kept even when the
                # link fails, because "ROWENDA KITCHEN SDN BHD / 300-R009" is what makes the
                # link fixable later. Dropping it leaves an order nobody can attribute.
                internal_note=" / ".join(
                    p for p in (parsed_order.customer_name, parsed_order.debtor_code,
                                parsed_order.note) if p
                ) or None,
            )
            db.add(order)
            db.flush()
            existing[parsed_order.so_number] = order
            orders_created += 1
        else:
            # A document already held is refreshed, not duplicated: the file is the source of
            # truth for what was sold. An order raised IN the system is left alone - this
            # feed must not close a live commitment somebody is working.
            if order.source_system != SOURCE_SYSTEM:
                continue
            order.order_date = parsed_order.order_date or order.order_date
            order.requested_delivery_date = (
                parsed_order.requested_delivery_date or order.requested_delivery_date
            )
            if customer_id:
                order.customer_id = customer_id
            orders_updated += 1

        existing_lines = {
            ln.source_ref: ln
            for ln in db.query(SalesOrderLine)
            .filter(SalesOrderLine.sales_order_id == str(order.id))
            .all()
        }

        for parsed_line in parsed_order.lines:
            if not parsed_line.is_stock_item:
                # Real money on the order with no product behind it. Carried by the reader so
                # the document reconciles, and never written as a stock line: a quantity of 1
                # "TRANSPORT CHARGE" is not demand for anything.
                continue
            product_id = product_by_code.get(parsed_line.item_code)
            if product_id is None:
                # Counted and named in the summary. Never created.
                continue

            ref = str(parsed_line.ordinal)
            line = existing_lines.get(ref)
            # Fully delivered, whatever the file says. This feed records finished business;
            # a line still owed belongs to the outstanding channel, and `outstanding_lines`
            # in the summary tells the uploader when the file holds any.
            qty = parsed_line.qty_ordered
            if line is None:
                db.add(SalesOrderLine(
                    sales_order_id=str(order.id),
                    product_id=product_id,
                    warehouse_id=warehouse_by_code.get(parsed_line.location),
                    qty_ordered=qty,
                    qty_delivered=qty,
                    required_date=parsed_line.required_date,
                    line_status=_LINE_STATUS,
                    source_system=SOURCE_SYSTEM,
                    source_ref=ref,
                ))
                lines_created += 1
            else:
                line.product_id = product_id
                line.warehouse_id = warehouse_by_code.get(parsed_line.location)
                line.qty_ordered = qty
                line.qty_delivered = qty
                line.required_date = parsed_line.required_date
                line.line_status = _LINE_STATUS

    db.flush()
    summary.update({
        "orders_created": orders_created,
        "orders_updated": orders_updated,
        "lines_created": lines_created,
    })
    logger.info(
        "so history applied: %d orders created, %d updated, %d lines, actor=%s",
        orders_created, orders_updated, lines_created, actor,
    )
    return _serialise_dates(summary)
