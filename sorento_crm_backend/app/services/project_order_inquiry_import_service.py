"""L3 - writing what the Order Inquiry sheet knows.

**Project Sales module code.** Ownership moved here from `app/services/scm/` per ADR 0010:
the whole Order Inquiry loop - derive, export, human edit, import - belongs to Project Sales,
and SCM keeps the role it already had, reader of core `sales_orders`. Only the service layer
moved: the route path `/api/v1/scm/order-inquiry/*` and the permission `scm.reorder.run` are
deliberately unchanged so the FE upload dialog keeps working (the route file now holds a thin
shim onto this module).

`SOURCE_SYSTEM` below stays the literal `'scm_order_inquiry'` even though the owning module is
no longer SCM. The string is baked into raw SQL (`scm/demand.py`), into migration 346's
backfill and into the `OrderLinkClaim` CHECK constraint, so renaming it would be a data
migration that buys no correctness. The mismatch between the string and this file's home is a
decision, not a leftover.

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
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from sqlalchemy import func

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services import import_outcome_codes as oc
from app.services.import_outcome import ImportOutcome
from app.services.project_order_inquiry_reader import OrderInquiryResult, read_order_inquiry
from app.services.scm import upload_validation as val
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


def _so_lines(
    db: Session, so_numbers: set[str]
) -> dict[tuple[str, str, Optional[date]], SalesOrderLine]:
    """Sales-order lines keyed by the INSTALMENT: (SO number, item code, required date).

    Per line, not per order: one purchase order covering lines from more than one sales order
    is visible in the customer's data, so matching on the number alone would attach the whole
    order to whichever sales order was seen first.

    And per DATE, not per item: one sales-order line is called off across several dates and
    each call-off is its own row here, so keying on the item alone would collapse six
    instalments onto whichever one the query returned last.
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
    return {(str(so), str(code), line.required_date): line for so, code, line in rows}


def _summarise(db: Session, parsed: OrderInquiryResult, collapsed=None) -> dict:
    """Counts the uploader is told, before anything is written.

    `collapsed` is the `(instalments, absorbed)` pair when the caller has already computed
    it. Collapsing a 15,797-row book is not free, and `apply` needs the same pair three times
    over - here, to write, and to record the restating rows - so it is computed once per call
    and passed down rather than re-derived per reader.
    """
    instalments, absorbed = collapsed if collapsed is not None else _instalments(parsed)
    so_numbers = {r.so_number for r in instalments}
    known_lines = _so_lines(db, so_numbers)
    codes = {r.location for r in instalments if r.location}
    known_warehouses = _warehouses_by_code(db, codes)

    def _key(row) -> tuple[str, str, Optional[date]]:
        return (row.so_number, row.item_code, row.delivery_date)

    matched = sum(1 for r in instalments if _key(r) in known_lines)
    unknown_locations = sorted(codes - set(known_warehouses))
    missing_orders = sorted({r.so_number for r in instalments if _key(r) not in known_lines})
    return {
        "ok": parsed.ok,
        "problems": list(parsed.problems),
        "rows": len(parsed.rows),
        # The book states one instalment on several tabs on purpose. Both figures are shown
        # so a drop from 15,797 to 8,272 reads as the collapse it is, not as loss.
        "instalments": len(instalments),
        "rows_restating_an_instalment": len(absorbed),
        "sheets_read": list(parsed.sheets_read),
        "sheets_skipped": list(parsed.sheets_skipped),
        "lines_matched": matched,
        "lines_unmatched": len(instalments) - matched,
        # Named, so somebody can see WHICH sales orders have not been uploaded yet rather
        # than only that some have not.
        "sales_orders_not_found": missing_orders[:200],
        "with_location": sum(1 for r in instalments if r.location),
        "unknown_locations": unknown_locations,
        "po_claims": sum(len(r.po_numbers) for r in instalments),
        "not_ordered": sum(1 for r in instalments if r.not_ordered),
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


@dataclass
class _Instalment:
    """One scheduled call-off of a sales-order line: `(so number, item, delivery date)`.

    That triple is the identity of a row, and getting it wrong is what made demand read about
    three times real. The workbook states the same instalment more than once by design - a
    month tab, a roll-up tab covering that month, and a dated working snapshot can all carry
    it - so a repeat is the same instalment, not another one.
    """

    so_number: str
    item_code: str
    delivery_date: Optional[date]
    qty: float = 0.0
    so_date: Optional[date] = None
    project: str = ""
    location: str = ""
    po_numbers: tuple[str, ...] = ()
    not_ordered: bool = False
    #: The first sheet row that stated this delivery. Carried so a queued import can point an
    #: outcome at a row somebody can open the workbook to; the other rows that restate it are
    #: reported separately (see `_instalments`).
    source_row: Optional[int] = None
    #: The tab that row is on. Row numbers restart per sheet, so "row 42" alone names four
    #: different rows in a book of monthly tabs - the identity on the job carries the tab so a
    #: drill-down can point at one of them.
    sheet: str = ""


def _sheet_rank(parsed) -> dict[str, int]:
    """Later sheet wins where two disagree, ranked by workbook order.

    Not by any period parsed out of the tab name. The customer's tabs are `JAN 26`,
    `JAN - APR 26`, `21.7.26` and `Sheet3` in no chronological order, so a parsed period would
    make `DEC 26` beat a snapshot taken last week. Workbook order is what the person
    maintaining the book actually controls: they append.
    """
    return {name: i for i, name in enumerate(getattr(parsed, "sheets_read", []) or [])}


def _instalments(parsed) -> tuple[list[_Instalment], list[int]]:
    """Collapse the sheet's rows to one per instalment. Returns the rows it absorbed too.

    Within ONE tab a repeat is a second call-off and the quantities add: `SO324252 /
    BRP60391N` is written as 80 and 40 on the same date inside `JAN 26`, and that is 120 due
    that day. ACROSS tabs a repeat is a restatement and the later tab replaces the earlier
    one outright.

    The absorbed rows come back as ROW NUMBERS rather than a count, because a queued import
    records an outcome per source row: with a count alone a 15,797-row book would report 8,272
    rows processed and leave 7,525 unexplained.
    """
    rank = _sheet_rank(parsed)
    # (key, sheet) -> instalment, so a within-tab repeat accumulates and a cross-tab one does
    # not.
    per_sheet: dict[tuple[tuple, str], _Instalment] = {}
    order: dict[tuple, list[str]] = {}
    #: Every source row that landed in each (key, sheet) bucket, in file order.
    rows_seen: dict[tuple[tuple, str], list[int]] = {}

    for row in parsed.rows:
        key = (row.so_number, row.item_code, row.delivery_date)
        sheet = getattr(row, "sheet", "") or ""
        rows_seen.setdefault((key, sheet), []).append(getattr(row, "source_row", 0) or 0)
        seen = per_sheet.get((key, sheet))
        if seen is None:
            seen = _Instalment(
                so_number=row.so_number,
                item_code=row.item_code,
                delivery_date=row.delivery_date,
                so_date=row.so_date,
                project=row.project,
                location=row.location,
                source_row=getattr(row, "source_row", None),
                sheet=sheet,
            )
            per_sheet[(key, sheet)] = seen
            order.setdefault(key, []).append(sheet)
        seen.qty += float(row.qty or 0)
        seen.so_date = seen.so_date or row.so_date
        seen.project = seen.project or row.project
        seen.location = seen.location or row.location
        seen.not_ordered = seen.not_ordered or row.not_ordered
        # Unioned rather than replaced: one line split across two purchase orders is written
        # `202606-S0024 & 202607-S0043`, and a later tab naming only one of them has not
        # cancelled the other.
        for po in row.po_numbers:
            if po not in seen.po_numbers:
                seen.po_numbers = seen.po_numbers + (po,)

    winners: list[_Instalment] = []
    absorbed: list[int] = []
    for key, sheets in order.items():
        best = max(sheets, key=lambda s: rank.get(s, -1))
        winner = per_sheet[(key, best)]
        for sheet in sheets:
            rows = rows_seen.get((key, sheet), [])
            if sheet == best:
                # The first row of the winning tab IS the instalment; anything after it in
                # the same tab added its quantity to it.
                absorbed.extend(rows[1:])
                continue
            absorbed.extend(rows)
            for po in per_sheet[(key, sheet)].po_numbers:
                if po not in winner.po_numbers:
                    winner.po_numbers = winner.po_numbers + (po,)
        winners.append(winner)

    return winners, absorbed


def _purchasing_status(inst: _Instalment) -> str:
    """What the sheet says about buying this instalment.

    A purchase order named on the row is the strongest statement there is, so it wins even
    when the cell also says `ORDER` - `202605-S0042 & ORDER` is a line partly placed, and the
    part that is placed is a fact.
    """
    if inst.po_numbers:
        return "ordered"
    if inst.not_ordered:
        return "needs_purchase"
    # On the sheet at all means CS has looked at it. Without a PO and without the ORDER
    # marker there is nothing more specific to say than "it is waiting to be bought".
    return "needs_purchase"


def _row_identity(row) -> dict:
    """What names a sheet row in the job detail. No ids - the operator reads SO numbers.

    The tab is part of the name. Row numbers restart on every sheet, so `row 42` is four
    different rows in a book of monthly tabs and an outcome carrying the number alone points
    at none of them.
    """
    return {
        "doc_no": row.so_number,
        "item_code": row.item_code,
        "delivery_date": row.delivery_date.isoformat() if row.delivery_date else "",
        "sheet": getattr(row, "sheet", "") or "",
    }


def _create_orders(db: Session, parsed, now: datetime,
                   outcome: Optional[ImportOutcome] = None, collapsed=None) -> dict:
    """Turn the sheet's rows into sales orders, under the ownership rule.

    The rule, in one place because it is the whole design:

    * no such order -> create it, header and lines, stamped with this feed.
    * an order THIS feed created -> refresh its lines, keyed by (order, item).
    * an order anybody else created -> leave every figure alone. The caller still writes the
      stock location and the purchase-order claim, which is all this sheet did before.

    "Last writer wins" across two feeds with different refresh rhythms is how a quantity
    silently reverts, so the owner is recorded rather than inferred.

    `outcome` records what happened to each sheet ROW. Optional so a direct caller keeps the
    old signature; a throwaway non-persisting recorder stands in when it is absent.
    `collapsed` is the caller's already-computed `(instalments, absorbed)` pair.
    """
    outcome = outcome or ImportOutcome(None, persist=False)
    instalments, absorbed = collapsed if collapsed is not None else _instalments(parsed)

    by_number: dict[str, list] = {}
    for row in instalments:
        by_number.setdefault(row.so_number, []).append(row)

    existing = _orders_by_number(db, set(by_number))
    products = _products_by_code(db, {r.item_code for r in instalments if r.item_code})
    warehouses = _warehouses_by_code(db, {r.location for r in instalments if r.location})
    customers = _customers_by_name(db, {r.project for r in instalments if r.project})

    orders_created = lines_created = lines_refreshed = lines_withdrawn = 0
    orders_owned_elsewhere = 0
    unmatched_items: set[str] = set()

    for number, rows in by_number.items():
        order = existing.get(number)
        if order is not None and (order.source_system or "") != SOURCE_SYSTEM:
            # Somebody else's order. The caller still annotates it; quantities and dates
            # stay theirs. ONE column is stamped all the same: the inquiry naming this
            # order is exactly what makes it project demand (S13b), and the fact does not
            # depend on who owns the figures. Without it the reverse ordering breaks - the
            # CS book lands first, the inquiry names the order later, and its demand stays
            # invisible because origin was only ever written at creation. Never cleared:
            # dropping off a later sheet is one person tidying a working file, not CS
            # withdrawing the demand.
            if order.demand_origin != SOURCE_SYSTEM:
                order.demand_origin = SOURCE_SYSTEM
            orders_owned_elsewhere += 1
            # Per ROW, so the job's counts are a count of source rows. The row is not a
            # failure - the sheet still writes its location and its purchase-order claim
            # afterwards - but no figure on the document was touched, which is the thing
            # somebody re-reading the job needs to be told.
            for row in rows:
                outcome.skip(row=row.source_row, code=oc.DOCUMENT_OWNED_ELSEWHERE,
                             identity=_row_identity(row), value=number)
            continue

        buildable = [r for r in rows if r.item_code and r.item_code in products]
        unmatched_items.update(r.item_code for r in rows if r.item_code not in products)
        for row in rows:
            if not row.item_code:
                outcome.skip(row=row.source_row, code=oc.MISSING_ITEM_CODE,
                             identity=_row_identity(row))
            elif row.item_code not in products:
                # Never created: a product invented from a working spreadsheet is a SKU the
                # plan then buys. Counted, named in the summary, and now pinned to its row.
                outcome.skip(row=row.source_row, code=oc.PRODUCT_NOT_FOUND,
                             identity=_row_identity(row), value=row.item_code)
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
                # Origin survives adoption; source_system does not. Project demand is keyed
                # on THIS stamp (S13b), so CS taking ownership of the order later must not
                # be able to erase where it came from.
                demand_origin=SOURCE_SYSTEM,
                source_ref=SOURCE,
            )
            db.add(order)
            db.flush()
            existing[number] = order
            orders_created += 1
            current: dict[tuple[str, Optional[date]], list[SalesOrderLine]] = {}
        else:
            # Keyed by the INSTALMENT, not the item. One sales-order line called off across
            # six dates is six rows here, and keying on the item alone made every tab that
            # mentioned the line insert another one.
            #
            # A LIST per key, not a single line, because the database already holds the
            # duplicates the old importer wrote (15,481 rows describing 8,272 instalments).
            # A dict keyed the same way silently keeps one and leaves the rest invisible to
            # both the refresh and the withdrawal below - so they would survive every future
            # upload, and the count would never come down.
            current = {}
            for pc, ln in (
                db.query(Product.product_code, SalesOrderLine)
                .join(SalesOrderLine, SalesOrderLine.product_id == Product.id)
                .filter(SalesOrderLine.sales_order_id == str(order.id))
                .order_by(SalesOrderLine.created_at)
                .all()
            ):
                current.setdefault((str(pc), ln.required_date), []).append(ln)

        for row in buildable:
            key = (row.item_code, row.delivery_date)
            held = current.get(key) or []
            line = held[0] if held else None
            # Anything past the first is a duplicate the old importer wrote for this same
            # instalment. The oldest survives and carries the sheet's current figures.
            for extra in held[1:]:
                if (extra.source_system or "") == SOURCE_SYSTEM:
                    db.delete(extra)
                    lines_withdrawn += 1
                    outcome.updated(code=oc.LINE_WITHDRAWN, identity=_row_identity(row),
                                    value=row.so_number)
            if held:
                current[key] = held[:1]
            qty = float(row.qty or 0)
            warehouse_id = warehouses.get(row.location) if row.location else None
            status = _purchasing_status(row)
            if line is None:
                line = SalesOrderLine(
                    sales_order_id=str(order.id),
                    product_id=products[row.item_code],
                    warehouse_id=warehouse_id,
                    qty_ordered=qty,
                    qty_delivered=0,
                    qty_required=qty,
                    purchasing_status=status,
                    line_status="open",
                    required_date=row.delivery_date,
                    source_system=SOURCE_SYSTEM,
                    source_ref=SOURCE,
                )
                db.add(line)
                # Kept, or a second row for the same instalment inside ONE upload inserts
                # again. That omission is the whole duplication bug.
                current[key] = [line]
                lines_created += 1
                outcome.success(row=row.source_row, code=oc.CREATED,
                                identity=_row_identity(row), value=row.so_number)
            else:
                # Its own line, so the file is the truth for it: a quantity corrected in the
                # sheet has to reach the plan, and the alternative is a second line.
                line.qty_ordered = qty
                line.qty_required = qty
                line.purchasing_status = status
                if warehouse_id:
                    line.warehouse_id = warehouse_id
                lines_refreshed += 1
                # `updated` whatever the values were: this feed rewrites the line it owns
                # unconditionally, so claiming "unchanged" would be a guess about a write
                # that definitely happened.
                outcome.updated(row=row.source_row, identity=_row_identity(row),
                                value=row.so_number, entity_type="order_line",
                                entity_id=line.id)

        # Gone: an instalment this feed wrote that the sheet has stopped stating. Scoped
        # twice over - only lines THIS feed owns, and only on documents in this file - so a
        # book covering one month cannot withdraw the demand of an order it never mentions,
        # and a document another feed owns is never touched (that rule is enforced above).
        stated = {(row.item_code, row.delivery_date) for row in buildable}
        for key, held in list(current.items()):
            if key in stated:
                continue
            for line in held:
                if (line.source_system or "") != SOURCE_SYSTEM:
                    continue
                db.delete(line)
                lines_withdrawn += 1
                # No source row: a withdrawal is reached by the sheet's SILENCE, so there is
                # no row in this upload to point at. Recorded anyway - it is the destructive
                # half, and the job detail is where somebody finds out what went away.
                outcome.updated(code=oc.LINE_WITHDRAWN,
                                identity={"doc_no": number, "item_code": key[0]},
                                value=number)

    db.flush()
    return {
        "orders_created": orders_created,
        "lines_created": lines_created,
        "lines_refreshed": lines_refreshed,
        "lines_withdrawn": lines_withdrawn,
        "orders_owned_elsewhere": orders_owned_elsewhere,
        "unmatched_item_codes": sorted(unmatched_items)[:200],
        "unmatched_items": len(unmatched_items),
        # Named on the upload screen. A book of 15,797 rows describing 8,272 instalments is
        # not an error, but a reader who is not told will read the smaller number as loss.
        "instalments": len(instalments),
        "rows_restating_an_instalment": len(absorbed),
    }


def apply(db: Session, file_data: bytes, actor: Optional[str] = None,
          outcome: Optional[ImportOutcome] = None,
          on_total_rows: Optional[Callable[[int], None]] = None) -> dict:
    """Create the demand the sheet carries, then write locations and claim the PO links.

    `outcome` records what happened to each sheet ROW for the job detail. Optional so a
    direct caller keeps the old signature; a throwaway non-persisting recorder stands in when
    it is absent, so there is one code path either way.
    """
    outcome = outcome or ImportOutcome(None, persist=False)
    parsed = read_order_inquiry(file_data)
    if on_total_rows is not None:
        # The sheet's own rows, published the moment it is read so the drawer has a
        # denominator. It GROWS below once the withdrawals are known.
        on_total_rows(len(parsed.rows))
    # Collapsed ONCE per apply and passed down. Three readers need the same pair - the
    # summary, the write, and the restating rows - and collapsing 15,797 rows three times is
    # three times the work for an answer that cannot differ.
    collapsed = _instalments(parsed)
    summary = _summarise(db, parsed, collapsed)
    summary["total_rows"] = len(parsed.rows)
    summary["locations_written"] = 0
    summary["claims_written"] = 0
    summary["orders_created"] = 0
    summary["lines_created"] = 0
    summary["lines_refreshed"] = 0
    summary["lines_withdrawn"] = 0
    summary["orders_owned_elsewhere"] = 0
    if not parsed.ok:
        return summary

    now = _now()
    # Create first: the annotate loop below reads sales-order lines, and the ones this call
    # just wrote are exactly the ones the sheet has a location for.
    created = _create_orders(db, parsed, now, outcome, collapsed)
    summary.update(created)

    # What this JOB accounts for, which is more than the sheet states. A withdrawal is reached
    # by the sheet's SILENCE, so it carries an outcome and no source row: with the row count
    # alone as the total, a book that withdraws one instalment finishes past 100%. Known only
    # now - a withdrawal is discovered while writing - so the denominator grows here.
    summary["total_rows"] = len(parsed.rows) + int(created.get("lines_withdrawn", 0))
    if on_total_rows is not None and created.get("lines_withdrawn"):
        on_total_rows(summary["total_rows"])

    instalments, absorbed = collapsed
    # The rows that state a delivery another tab already states. Nothing is skipped - their
    # quantity is inside the instalment - so they ride on `unchanged`, and every row of the
    # book is now accounted for exactly once: instalments plus these equals the row count.
    for row_number in absorbed:
        outcome.unchanged(row=row_number or None, code=oc.RESTATES_AN_INSTALMENT)
    known_lines = _so_lines(db, {r.so_number for r in instalments})
    warehouses = _warehouses_by_code(
        db, {r.location for r in instalments if r.location}
    )

    def _key(row) -> tuple[str, str, Optional[date]]:
        return (row.so_number, row.item_code, row.delivery_date)

    # Re-derived AFTER creating, because `_summarise` ran against the state before this
    # upload: it counted 15,787 rows as "sales order not found" and the very next step
    # created most of those orders. Reporting the earlier figure would have the result
    # contradict itself on the same screen.
    matched_now = sum(1 for r in instalments if _key(r) in known_lines)
    summary["lines_matched"] = matched_now
    summary["lines_unmatched"] = len(instalments) - matched_now
    summary["sales_orders_not_found"] = sorted({
        r.so_number for r in instalments if _key(r) not in known_lines
    })[:200]
    locations_written = 0
    claims_written = 0
    seen_claims: set[tuple[str, str, str]] = set()

    for row in instalments:
        line = known_lines.get(_key(row))
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
