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
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.inventory import Warehouse
from app.models.product import Product
from app.services import import_outcome_codes as oc
from app.services.import_outcome import ImportOutcome
from app.services.import_alias_service import AliasResolver
from app.services.scm.history_sources import SO_HISTORY_SOURCE
from app.services.scm.so_listing_reader import (
    DOC_TYPE,
    SoListingResult,
    read_so_listing,
)
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

#: Written on every row this feed creates, so a later reader can tell absorbed history from
#: an order somebody raised in the system, and so a correction can find its own rows.
SOURCE_SYSTEM = SO_HISTORY_SOURCE
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


def _has_foreign_lines(db: Session, order_id: str) -> bool:
    """Does this document already carry lines written by a different feed?

    Asked per document rather than resolved by a join up front, because the answer is needed
    only for documents that already exist - 269 of the client's 11,275 - and the query is an
    index hit on `sales_order_id`.
    """
    return db.query(SalesOrderLine.id).filter(
        SalesOrderLine.sales_order_id == order_id,
        SalesOrderLine.source_system.isnot(None),
        SalesOrderLine.source_system != SOURCE_SYSTEM,
    ).first() is not None


def _has_open_quantity(db: Session, order_id: str) -> bool:
    """Does this document still owe anything today?

    Asked BEFORE the upload settles it, because afterwards the answer is always no and the
    count would be silently zero.
    """
    return db.query(SalesOrderLine.id).filter(
        SalesOrderLine.sales_order_id == order_id,
        SalesOrderLine.line_status == "open",
        SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
    ).first() is not None


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
        # Same field and same meaning as the other upload channels, so the dialog gates on
        # one thing everywhere: a file that could not be read shows its problems, one that
        # could shows its counts.
        "ok": parsed.ok,
        "orders": len(parsed.orders),
        "lines": parsed.line_count,
        "total_rows": parsed.total_rows,
        "layout_rows": parsed.layout_rows,
        # Rendered strings, matching the other channels. The row number leads because it is
        # what somebody opens the spreadsheet to, and the value follows because "missing
        # item_code" alone does not say which order to look at.
        "problems": [
            f"row {p.row_number}: {p.reason}" + (f" ({p.value})" if p.value else "")
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


def apply(db: Session, file_data: bytes, actor: Optional[str] = None,
          outcome: Optional[ImportOutcome] = None,
          on_total_rows: Optional[Callable[[int], None]] = None) -> dict:
    """Write the history. Idempotent on the document number.

    Re-uploading is normal - somebody re-exports a wider date range and sends the whole book
    again. Without idempotency the second upload doubles six years of demand, and because
    every line is closed nothing downstream would show it until somebody read a customer's
    order history and found it twice.

    Lines are keyed by their ORDINAL within the document, because the export carries no line
    number and one order routinely repeats the same item at the same location and price. Any
    content-based key would collapse those repeats into one line and lose real quantity.

    `outcome` records what happened to each source LINE for the job detail. Optional so a
    direct caller keeps the old signature; a throwaway non-persisting recorder stands in when
    it is absent.
    """
    outcome = outcome or ImportOutcome(None, persist=False)
    resolver = AliasResolver.for_doc_type(db, DOC_TYPE)
    parsed = read_so_listing(file_data, resolver)
    if on_total_rows is not None:
        # Every non-blank row of the file, the 9,144 package captions included. They are not
        # lines and are never written, but they ARE rows somebody uploaded, so each carries
        # its own `not_a_line` outcome below and the total they are counted in is reachable.
        # One definition of "total" across all five channels: the source rows.
        on_total_rows(parsed.total_rows)
    summary = _summarise(db, parsed)
    summary.update({
        "orders_created": 0, "orders_updated": 0, "orders_unchanged": 0,
        "lines_created": 0, "lines_updated": 0, "lines_unchanged": 0,
        "orders_with_open_lines_closed": 0,
        "conflicted_orders": [], "conflicted_order_count": 0,
    })
    if not parsed.ok:
        return _serialise_dates(summary)

    # Captions, spacers and the package headings this export puts above each block. Their own
    # code rather than a failure: 9,144 of them in the client's file would bury the handful of
    # rows that really did fail, and dropping them silently leaves the job unable to say what
    # became of them.
    for row_number in parsed.layout_row_numbers:
        outcome.skip(row=row_number, code=oc.NOT_A_LINE)

    # Rows the reader could not turn into a line at all. Recorded before the write loop so
    # every row in the file is accounted for exactly once.
    for problem in parsed.problems:
        outcome.skip(row=problem.row_number or None,
                     code=oc.MISSING_REQUIRED_FIELD if problem.reason.startswith("missing")
                     else oc.ROW_ERROR,
                     message=problem.reason, value=problem.value or None)

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

    orders_created = orders_updated = orders_unchanged = 0
    #: Documents another feed already owns lines on. Named, not just counted: the uploader
    #: has to go and decide which of the two exports is current.
    conflicted_orders: list[str] = []
    lines_created = lines_updated = lines_unchanged = 0
    #: Documents this upload settled that still had quantity owed. The cost of treating the
    #: export as the source of truth, counted so it is never a surprise.
    orders_with_open_lines_closed = 0

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
            # Same -> skip, different -> update, new -> create. The house rule for every
            # feed, applied here to the document header. "Skip" is a real outcome and is
            # counted, not folded into "updated": an upload reporting 11,275 updates when it
            # changed nothing tells the uploader nothing about what their file did.
            #
            # The rule governs what this feed OWNS. A document already carrying lines from
            # ANOTHER feed is not a same-or-different question, it is two AutoCount exports
            # disagreeing, and the disagreement is real: on the client's own data, 269
            # documents are open in the Order Inquiry sheet with 430,108 units still owed
            # while this listing reports every one of them fully delivered. One of the two
            # exports is stale, and which one is a question about their data, not ours.
            #
            # Answering it by upload order is the worst option available. Settling those
            # headers removed 430,108 units of committed demand from the plan and left each
            # document holding two sets of lines - the original open ones and the imported
            # closed ones - and both effects looked exactly like a successful import.
            #
            # So the document is reported as a CONFLICT and left completely untouched. The
            # uploader is told which documents and how many units hang on the answer.
            if _has_foreign_lines(db, str(order.id)):
                conflicted_orders.append(parsed_order.so_number)
                # Per LINE, not per document: the count the job reports is a count of source
                # rows, and a document skipped whole means every one of its rows was skipped.
                for parsed_line in parsed_order.lines:
                    outcome.skip(
                        row=parsed_line.row_number, code=oc.DOCUMENT_OWNED_ELSEWHERE,
                        identity={"doc_no": parsed_order.so_number,
                                  "item_code": parsed_line.item_code},
                        value=parsed_order.so_number,
                    )
                continue

            changed = False
            if parsed_order.order_date and order.order_date != parsed_order.order_date:
                order.order_date = parsed_order.order_date
                changed = True
            if (parsed_order.requested_delivery_date
                    and order.requested_delivery_date
                    != parsed_order.requested_delivery_date):
                order.requested_delivery_date = parsed_order.requested_delivery_date
                changed = True
            if customer_id and order.customer_id != customer_id:
                order.customer_id = customer_id
                changed = True
            if order.status != _ORDER_STATUS:
                if _has_open_quantity(db, str(order.id)):
                    orders_with_open_lines_closed += 1
                order.status = _ORDER_STATUS
                changed = True
            if order.source_system != SOURCE_SYSTEM:
                # Stamped so a later run can tell this document has been through the feed,
                # while `source_doc_no` keeps whatever raised it originally.
                order.source_system = SOURCE_SYSTEM
                changed = True
            if changed:
                orders_updated += 1
            else:
                orders_unchanged += 1

        existing_lines = {
            ln.source_ref: ln
            for ln in db.query(SalesOrderLine)
            .filter(SalesOrderLine.sales_order_id == str(order.id))
            .all()
        }

        for parsed_line in parsed_order.lines:
            identity = {"doc_no": parsed_order.so_number,
                        "item_code": parsed_line.item_code,
                        "location": parsed_line.location or ""}
            if not parsed_line.is_stock_item:
                # Real money on the order with no product behind it. Carried by the reader so
                # the document reconciles, and never written as a stock line: a quantity of 1
                # "TRANSPORT CHARGE" is not demand for anything.
                outcome.skip(row=parsed_line.row_number, code=oc.CHARGE_LINE,
                             identity=identity)
                continue
            product_id = product_by_code.get(parsed_line.item_code)
            if product_id is None:
                # Counted and named in the summary. Never created.
                outcome.skip(row=parsed_line.row_number, code=oc.PRODUCT_NOT_FOUND,
                             identity=identity, value=parsed_line.item_code)
                continue

            ref = str(parsed_line.ordinal)
            line = existing_lines.get(ref)
            warehouse_id = warehouse_by_code.get(parsed_line.location)
            # Fully delivered, whatever the file says. This feed records finished business;
            # a line still owed belongs to the outstanding channel, and `outstanding_lines`
            # in the summary tells the uploader when the file holds any.
            qty = parsed_line.qty_ordered
            if line is None:
                db.add(SalesOrderLine(
                    sales_order_id=str(order.id),
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    qty_ordered=qty,
                    qty_delivered=qty,
                    required_date=parsed_line.required_date,
                    line_status=_LINE_STATUS,
                    source_system=SOURCE_SYSTEM,
                    source_ref=ref,
                ))
                lines_created += 1
                outcome.success(row=parsed_line.row_number, code=oc.CREATED,
                                identity=identity, value=parsed_order.so_number)
            else:
                # Same -> skip, different -> update. Compared field by field rather than
                # written unconditionally, because "updated" has to mean something changed:
                # a second upload of an unchanged book must report zero updates, and an
                # `updated_at` touched on 64,526 rows that did not change is a lie the audit
                # trail then carries for ever.
                want = (str(product_id), warehouse_id, float(qty), float(qty),
                        parsed_line.required_date, _LINE_STATUS)
                have = (str(line.product_id), line.warehouse_id,
                        float(line.qty_ordered or 0), float(line.qty_delivered or 0),
                        line.required_date, line.line_status)
                if want == have:
                    lines_unchanged += 1
                    outcome.unchanged(row=parsed_line.row_number, identity=identity,
                                      value=parsed_order.so_number,
                                      entity_type="order_line", entity_id=line.id)
                else:
                    line.product_id = product_id
                    line.warehouse_id = warehouse_id
                    line.qty_ordered = qty
                    line.qty_delivered = qty
                    line.required_date = parsed_line.required_date
                    line.line_status = _LINE_STATUS
                    lines_updated += 1
                    outcome.updated(row=parsed_line.row_number, identity=identity,
                                    value=parsed_order.so_number,
                                    entity_type="order_line", entity_id=line.id)

    db.flush()
    summary.update({
        "orders_created": orders_created,
        "orders_updated": orders_updated,
        "orders_unchanged": orders_unchanged,
        "lines_created": lines_created,
        "lines_updated": lines_updated,
        "lines_unchanged": lines_unchanged,
        "orders_with_open_lines_closed": orders_with_open_lines_closed,
        "conflicted_orders": sorted(conflicted_orders)[:50],
        "conflicted_order_count": len(conflicted_orders),
    })
    logger.info(
        "so history applied: orders +%d ~%d =%d, lines +%d ~%d =%d, "
        "settled-with-open-quantity %d, conflicts %d, actor=%s",
        orders_created, orders_updated, orders_unchanged,
        lines_created, lines_updated, lines_unchanged,
        orders_with_open_lines_closed, len(conflicted_orders), actor,
    )
    return _serialise_dates(summary)
