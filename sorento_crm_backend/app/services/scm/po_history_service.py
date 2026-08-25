"""L2 - writing purchase-order HISTORY from the AutoCount purchase exports.

The reader next door is pure; this is the write path. It serves BOTH shapes the client sends
(`purchase_history_reader` decides which arrived) and BOTH document families inside them:
`######-S####` purchase orders and `SPO-####/##-####` shipping orders, routed on the Doc No
PREFIX and never on AutoCount's own `Shipping Order` flag - nine rows of the captain's 2023
book disagree with their own flag, and a misfiled row is the one thing this channel must not
produce (ADR 337).

The two families land in DIFFERENT tables, and that is the whole point of the split: a
purchase order is written to `purchase_orders` / `purchase_order_lines`, a shipping order to
`spo_allocations`, one row per SPO line. `scm.on_order_v` reads `spo_allocations` and nothing
else, so a shipping order filed as a purchase order was supply the module could not see.
See `PLAN-scm-cs-planning-uat.md` section K and migration `420_spo_docs_in_allocations`,
which moved the 3,983 SPO documents already held across and reversed the S5 amendment that
had kept them here.

One rule governs everything else:

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
from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product
from app.models.scm import OrderLinkClaim
from app.services import import_outcome_codes as oc
from app.services.company_scope import get_company_scope, resolve_write_company_id
from app.services.import_alias_service import AliasResolver
from app.services.import_outcome import ImportOutcome
from app.services.scm import upload_validation as val
from app.services.scm.history_sources import PO_HISTORY_SOURCE, SPO_HISTORY_SOURCE
from app.services.scm.po_listing_reader import (
    FAMILY_SPO,
    LAYOUT_STRUCTURED,
    PoListingResult,
)
from app.services.scm.purchase_history_reader import (
    STRUCTURED_DOC_TYPE,
    read_purchase_history,
)
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

#: Written on every row this feed creates, so a later reader can tell imported history from
#: an order somebody raised in the system. Defined in `history_sources` because the OTHER
#: writer of these tables (`outstanding_import_service`, whose revive path lifts a closed line
#: back to open) has to recognise them, and it must not import this module's write path.
SOURCE_SYSTEM = PO_HISTORY_SOURCE

#: The same, for the SHIPPING-ORDER family (`SPO-2023/01-0001`), stamped on the
#: `spo_allocations` rows this feed writes. It is what lets a later reader tell an imported
#: shipping order from one this system raised, and it is what migration 420's downgrade
#: moves back. The three objections that once kept this family in `purchase_orders` are all
#: answered by that migration: `spo_allocations.warehouse_id` is nullable with the raw code
#: kept beside it, and the unique key is the LINE, so repeated item-on-one-SPO groups are
#: ordinary data rather than a collision.
SPO_SOURCE_SYSTEM = SPO_HISTORY_SOURCE

#: `source_ref` per file shape, so the two exports are distinguishable on the row.
BANDED_SOURCE_REF = "po_listing"
STRUCTURED_SOURCE_REF = "po_spo_listing"

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


#: Currency markers AutoCount appends to a creditor's NAME to name the account it is billed
#: in. A fixed list, not a shape: `(RMB)` is the same company as no suffix at all, while
#: `(CHINA)`, `(HK)` and `(M) SDN BHD` are different legal entities that bill separately, and
#: a rule like "a short parenthesised word" cannot tell those apart. Anything not on this list
#: stays part of the name, so the worst case is a creditor reported as unmatched rather than
#: a purchase attributed to the wrong company.
_CURRENCY_SUFFIXES = frozenset({
    "RMB", "CNY", "USD", "MYR", "SGD", "EUR", "HKD", "JPY", "GBP", "AUD", "THB", "IDR",
    "VND", "TWD",
})


def _creditor_key(name: str) -> str:
    """The comparison key for a creditor NAME.

    The structured extract writes the same creditor two ways - `XIAMEN TAIYANG TECHNOLOGY
    CO.,LTD` and `XIAMEN TAIYANG TECHNOLOGY CO.,LTD (RMB)` - because AutoCount appends the
    account's currency. Folding that away is what stops one supplier reading as two, and the
    currency list above is deliberately the ONLY thing folded.
    """
    text = " ".join((name or "").upper().split())
    if text.endswith(")") and "(" in text:
        head, _, tail = text.rpartition("(")
        if tail[:-1] in _CURRENCY_SUFFIXES:
            return head.strip()
    return text


def _suppliers_by_name(db: Session, names: set[str]) -> dict[str, Supplier]:
    """Creditors matched by NAME, for the export that carries no creditor code.

    Never creates. `suppliers.supplier_code` is unique and NOT NULL, so a supplier could only
    be created from this file by inventing its code - and an invented code is a supplier
    nobody can reconcile against AutoCount, on a master that already exists. The banded
    report DOES carry the code, which is why it may create; this one cannot, so an unmatched
    creditor is reported and its orders are written unlinked. The quantity and the date, which
    are what history is for, are true either way.

    An AMBIGUOUS name resolves to nothing. Two supplier rows can fold to one key (the same
    company held twice under two codes, one per currency account), and the query that finds
    them has no ORDER BY - so picking one would attribute a year of purchases to whichever row
    Postgres happened to return first, differently on the next run and silently either way.
    The name comes back unmatched instead, which is a line on the operator's list naming the
    creditor to merge.
    """
    if not names:
        return {}
    by_key: dict[str, list[Supplier]] = {}
    for supplier in db.query(Supplier).all():
        by_key.setdefault(_creditor_key(supplier.supplier_name), []).append(supplier)
    return {
        n: by_key[_creditor_key(n)][0]
        for n in names
        if len(by_key.get(_creditor_key(n), ())) == 1
    }


def _warehouses_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    """Stock locations by code, upper-cased on both sides.

    ORM rather than raw SQL on purpose: `warehouses` is company-scoped and the isolation
    filter runs on ORM execution only, so a raw lookup would resolve a code against every
    company's rows at once.

    Active rows only, and FIRST wins on a case collision (`brw` and `BRW` as two rows): last
    would make the answer depend on the order Postgres returned them in, which has no ORDER BY
    to fix it.
    """
    if not codes:
        return {}
    rows = (
        db.query(Warehouse.id, Warehouse.warehouse_code)
        .filter(func.upper(Warehouse.warehouse_code).in_([c.upper() for c in codes]),
                Warehouse.is_active.is_(True))
        .all()
    )
    out: dict[str, str] = {}
    for wid, code in rows:
        out.setdefault(str(code).upper(), str(wid))
    return out


def _allocations_for(
    db: Session, cache: dict[str, dict], spo_number: str
) -> dict[int, SPOAllocation]:
    """The SPO rows already held for ONE document, keyed by line number.

    The same shape as `existing_lines` on the purchase-order side, and for the same reason: a
    re-upload of a book somebody re-exported over a wider date range must refresh what it
    already holds instead of doubling every historical quantity.

    Per DOCUMENT, exactly as the purchase-order half reads its lines. A whole-file preload
    would send 13,550 document numbers in one `IN` list and hold every row they match in the
    session - some 74,000 ORM objects on a re-upload of the captain's own book - to answer a
    question that is only ever asked one document at a time. Cached, so a number that appears
    twice in one file is read once.
    """
    if spo_number not in cache:
        cache[spo_number] = {
            row.spo_line_number: row
            for row in db.query(SPOAllocation)
            .filter(SPOAllocation.spo_number == spo_number)
            .all()
        }
    return cache[spo_number]


def _write_shipping_order(
    db: Session,
    parsed_order,
    *,
    product_by_code: dict[str, str],
    warehouse_by_code: dict[str, str],
    supplier: Optional[Supplier],
    existing: dict[int, SPOAllocation],
    outcome: ImportOutcome,
    company_id: Optional[str],
    claimed: set,
    now: datetime,
) -> int:
    """One shipping order, as `spo_allocations` rows. Returns how many rows were created.

    Upserted on `(company, spo_number, spo_line_number)` - the line, not the
    (document, product, location) triple, because the book states the same product on one
    SPO 13,305 times over and every one of those is a real second container.

    Written CLOSED and fully received, which is this whole service's governing rule: history
    must never read as incoming supply. `scm.on_order_v` counts a row only while it is open
    AND still has quantity to come, so 3,517 shipping orders from 2020 are excluded by
    construction rather than by a filter somebody has to remember.
    """
    lines_created = 0
    held = existing
    for index, parsed_line in enumerate(parsed_order.lines, start=1):
        identity = {"doc_no": parsed_order.po_number,
                    "item_code": parsed_line.item_code,
                    "line_no": parsed_line.line_no}
        if not parsed_line.is_stock_item:
            outcome.skip(row=parsed_line.source_row, code=oc.CHARGE_LINE,
                         identity=identity, value=parsed_line.description or None)
            continue
        product_id = product_by_code.get(parsed_line.item_code)
        if product_id is None:
            outcome.skip(row=parsed_line.source_row, code=oc.PRODUCT_NOT_FOUND,
                         identity=identity, value=parsed_line.item_code)
            continue

        # The book's own line number where it states one, else this line's position in the
        # document. Position is only a fallback: the export that states none also states its
        # lines in a fixed order, so the same file re-uploaded lands on the same numbers.
        line_no = parsed_line.line_no or index
        code = parsed_line.location.upper() if parsed_line.location else None
        warehouse_id = warehouse_by_code.get(code) if code else None

        if parsed_line.so_number:
            # Claimed for every line the file states, whoever ends up owning the row below:
            # "this shipping order carries that sales order" is a fact about the DOCUMENT,
            # and the claim holds both numbers as text so it survives either way.
            _claim_so_link(db, parsed_order.po_number, parsed_line.so_number, now,
                           item_code=parsed_line.item_code, seen=claimed,
                           company_id=company_id)

        row = held.get(line_no)
        if row is not None and (row.source_system or "") not in (SOURCE_SYSTEM, SPO_SOURCE_SYSTEM):
            # Somebody else owns this line: the live outstanding book, or an SPO this system
            # raised from a draft shipment. Those rows carry the OPEN balance that is the
            # module's only incoming supply, and closing them because a history export also
            # mentions the document would delete that supply on a re-upload.
            outcome.skip(row=parsed_line.source_row, code=oc.DOCUMENT_OWNED_ELSEWHERE,
                         identity=identity, value=parsed_order.po_number)
            continue

        quantity = int(round(parsed_line.qty_ordered or 0))
        if row is None:
            row = SPOAllocation(
                spo_number=parsed_order.po_number,
                spo_line_number=line_no,
                product_id=product_id,
                warehouse_id=warehouse_id,
                # The code as the book spelled it, held or not. On 6,520 lines this is the
                # only record of where the goods were meant to go.
                location_code=code,
                allocated_quantity=quantity,
                quantity_received=quantity,
                receipt_status="fully_received",
                line_status="closed",
                source_system=SPO_SOURCE_SYSTEM,
                issue_date=parsed_order.order_date,
                expected_date=parsed_line.expected_date,
                supplier_id=str(supplier.id) if supplier else None,
                unit_cost=parsed_line.unit_price,
                currency=parsed_order.currency or None,
            )
            db.add(row)
            held[line_no] = row
            lines_created += 1
            outcome.success(row=parsed_line.source_row, code=oc.CREATED,
                            identity=identity, value=parsed_order.po_number)
            continue

        row.product_id = product_id
        row.allocated_quantity = quantity
        row.quantity_received = quantity
        row.receipt_status = "fully_received"
        row.line_status = "closed"
        row.unit_cost = parsed_line.unit_price
        row.currency = parsed_order.currency or row.currency
        row.issue_date = parsed_order.order_date or row.issue_date
        if code is not None:
            row.location_code = code
        if warehouse_id is not None:
            row.warehouse_id = warehouse_id
        if parsed_line.expected_date is not None:
            row.expected_date = parsed_line.expected_date
        if supplier is not None:
            row.supplier_id = str(supplier.id)
        # `updated`, not `unchanged`, whatever the values were: this feed's rule is that the
        # file is the record of what was ordered, so the write happened.
        outcome.updated(row=parsed_line.source_row, identity=identity,
                        value=parsed_order.po_number, entity_type="spo_allocation",
                        entity_id=row.id)
    return lines_created


def _parse(db: Session, file_data: bytes) -> PoListingResult:
    """Read the book, whichever of the two exports it is.

    One entry point for preview, validate and apply, so the Test verdict can never be a
    verdict about a different reading than the write performs.
    """
    resolver = AliasResolver.for_doc_type(db, STRUCTURED_DOC_TYPE)
    return read_purchase_history(file_data, resolver)


def _summarise(db: Session, parsed: PoListingResult) -> dict:
    """Counts both entry points report, computed once so they cannot disagree."""
    stock_codes = {
        l.item_code for o in parsed.orders for l in o.lines if l.is_stock_item
    }
    known = _products_by_code(db, stock_codes)
    unmatched = sorted(stock_codes - set(known))
    # Both tables, because the two families live in different ones. Asking only
    # `purchase_orders` would report every shipping order in the file as new, and the
    # "already held - they will be refreshed" warning is the operator's own check that they
    # are re-uploading the book they think they are.
    numbers = [o.po_number for o in parsed.orders]
    existing = ({
        n
        for (n,) in db.query(PurchaseOrder.po_number)
        .filter(PurchaseOrder.po_number.in_(numbers))
        .all()
    } | {
        n
        for (n,) in db.query(SPOAllocation.spo_number)
        .filter(SPOAllocation.spo_number.in_(numbers))
        .distinct()
        .all()
    }) if parsed.orders else set()

    # The creditor names and stock locations only the structured export states. Both are
    # reported rather than allowed to fail a line: a purchase we cannot attribute to a
    # supplier, or place in a warehouse, is still a purchase that happened on a date.
    creditor_names = {
        o.supplier_name for o in parsed.orders if o.supplier_name and not o.supplier_code
    }
    matched_creditors = set(_suppliers_by_name(db, creditor_names))
    location_codes = {l.location.upper() for o in parsed.orders for l in o.lines if l.location}
    known_locations = set(_warehouses_by_code(db, location_codes))

    return {
        "ok": parsed.ok,
        "problems": list(parsed.problems),
        "orders": len(parsed.orders),
        "orders_new": sum(1 for o in parsed.orders if o.po_number not in existing),
        "orders_existing": sum(1 for o in parsed.orders if o.po_number in existing),
        "lines": parsed.line_count,
        # The two document families, split by the Doc No prefix. Reported separately because
        # one file carries both and "13,641 purchase orders and 13,550 shipping orders" is
        # the number the operator checks their export against.
        "orders_po": sum(1 for o in parsed.orders if o.doc_family != FAMILY_SPO),
        "orders_spo": sum(1 for o in parsed.orders if o.doc_family == FAMILY_SPO),
        "lines_po": sum(len(o.lines) for o in parsed.orders if o.doc_family != FAMILY_SPO),
        "lines_spo": sum(len(o.lines) for o in parsed.orders if o.doc_family == FAMILY_SPO),
        # Columns this export carries that no alias resolves. Empty on the banded report,
        # which is read by band position rather than by header.
        "unmapped_headers": list(parsed.unmapped_headers),
        # Counts are the TRUTH, the lists are a capped sample of them - same split as
        # `unmatched_items` / `unmatched_item_codes` below. Heading a section with the length
        # of what it happens to be showing turns 400 unmatched creditors into "(200)", which
        # reads like a smaller, closed problem than it is.
        "unmatched_creditor_count": len(creditor_names - matched_creditors),
        "unmatched_creditors": sorted(creditor_names - matched_creditors)[:200],
        "unknown_location_count": len(location_codes - known_locations),
        "unknown_locations": sorted(location_codes - known_locations)[:200],
        # Every non-blank row the reader read, so the job's denominator and the operator's own
        # "how big is this file" are the same number. `lines` is the subset that is a purchase
        # line; the difference is the report's headers, notes and spacers.
        "total_rows": parsed.total_rows,
        "charge_lines": sum(
            1 for o in parsed.orders for l in o.lines if not l.is_stock_item
        ),
        "unmatched_items": len(unmatched),
        # Named, not just counted: a count tells somebody there is a problem, the codes tell
        # them which one, and the list is what they take to whoever owns the catalogue.
        "unmatched_item_codes": unmatched[:200],
        # BOTH ways a file can name a sales order: the banded report's order-level notes, and
        # the structured export's per-line `FromSODocList`. Summing only the first reported 0
        # claims for a file that goes on to write thousands of them.
        "so_claims": (
            sum(len(o.so_numbers) for o in parsed.orders)
            + sum(1 for o in parsed.orders for l in o.lines if l.so_number)
        ),
        "date_from": min(
            (o.order_date for o in parsed.orders if o.order_date), default=None
        ),
        "date_to": max((o.order_date for o in parsed.orders if o.order_date), default=None),
    }


def preview(db: Session, file_data: bytes) -> dict:
    """What this file would write. Writes nothing."""
    parsed = _parse(db, file_data)
    out = _summarise(db, parsed)
    out["date_from"] = out["date_from"].isoformat() if out["date_from"] else None
    out["date_to"] = out["date_to"].isoformat() if out["date_to"] else None
    return out


def validate(db: Session, file_data: bytes) -> dict:
    """The Test verdict: `{valid, errors, warnings, summary}`. Writes nothing.

    Only an unreadable file is an ERROR here. Everything else this book can carry - unknown
    items, charge lines, documents we already hold - is a warning, because the rest of the
    file is still worth loading and refusing 1,586 orders over two missing product codes
    would be the wrong call for the operator to be forced into.
    """
    out = preview(db, file_data)
    warnings = [
        val.named(
            out["unmatched_items"], out["unmatched_item_codes"],
            one="item code we do not hold, so its line is skipped",
            many="item codes we do not hold, so those lines are skipped",
        ),
        (f"{out['orders_existing']:,} of these orders are already held - they will be "
         f"refreshed, not duplicated") if out["orders_existing"] else None,
        (f"{out['charge_lines']:,} charge lines (handling, misc) carry cost but no product, "
         f"so they are counted on the order and not as stock") if out["charge_lines"] else None,
        val.named(
            out["unmatched_creditor_count"], out["unmatched_creditors"],
            one="creditor name we do not hold, so its orders are written unlinked",
            many="creditor names we do not hold, so their orders are written unlinked",
        ),
        val.named(
            out["unknown_location_count"], out["unknown_locations"],
            one="stock location we do not hold, so its lines carry no warehouse",
            many="stock locations we do not hold, so their lines carry no warehouse",
        ),
        val.named(
            len(out["unmapped_headers"]), out["unmapped_headers"],
            one="column we could not place, so nothing in it is read",
            many="columns we could not place, so nothing in them is read",
        ),
        (f"{out['orders_spo']:,} of these documents are shipping orders (SPO) and "
         f"{out['orders_po']:,} are purchase orders; the shipping orders are loaded as SPO "
         f"allocations, the purchase orders as purchase-order history")
        if out["orders_spo"] else None,
    ]
    return val.envelope(
        ok=out["ok"], problems=out["problems"], warnings=warnings,
        summary={
            "total_rows": out["lines"],
            "would_create": out["orders_new"],
            "would_update": out["orders_existing"],
            "error_count": 0 if out["ok"] else len(out["problems"]),
            "orders": out["orders"],
            "date_from": out["date_from"],
            "date_to": out["date_to"],
        },
    )


def apply(db: Session, file_data: bytes, actor: Optional[str] = None,
          outcome: Optional[ImportOutcome] = None,
          on_total_rows: Optional[Callable[[int], None]] = None) -> dict:
    """Write the history. Idempotent on the document number.

    Re-uploading is normal - somebody re-exports a wider date range and sends the whole book
    again. Without idempotency the second upload doubles every historical quantity, and
    because the lines are closed nothing downstream would show it until a supplier's cost
    history was read and found twice.

    `outcome` records what happened to each source LINE for the job detail. Optional so a
    direct caller keeps the old signature; a throwaway non-persisting recorder stands in when
    it is absent, so there is one code path either way.
    """
    outcome = outcome or ImportOutcome(None, persist=False)
    parsed = _parse(db, file_data)
    if on_total_rows is not None:
        # Every non-blank row the reader read, order headers and SO notes and spacers
        # included. They are not lines and nothing is written for them, but they ARE rows
        # somebody uploaded, so each carries its own `not_a_line` outcome below and the total
        # stays reachable. One definition of "total" across all five channels: source rows.
        on_total_rows(parsed.total_rows)
    summary = _summarise(db, parsed)
    if not parsed.ok:
        summary["orders_created"] = 0
        summary["lines_created"] = 0
        summary["date_from"] = None
        summary["date_to"] = None
        return summary

    # Rows that were never a line: the banded report's band labels, preamble, order headers,
    # `**SO:174830**` notes and numbered spacers, and the structured export's 924 captions
    # inside a document ("EXTRA LOADING : "). Their own code rather than a failure or a
    # silence - most of the first file was never a line, and a row with no outcome is a row
    # the job cannot account for.
    for row_number in parsed.layout_row_numbers:
        outcome.skip(row=row_number, code=oc.NOT_A_LINE)
    # Rows that stated something and still could not be a line: the grand-total row at the
    # foot of the structured export, which carries figures and no document number. The reader
    # already decided why, so the code is carried rather than re-derived here.
    for row_number, code in parsed.problem_row_codes.items():
        outcome.skip(row=row_number, code=code)

    stock_codes = {l.item_code for o in parsed.orders for l in o.lines if l.is_stock_item}
    product_by_code = _products_by_code(db, stock_codes)

    supplier_codes = {o.supplier_code for o in parsed.orders if o.supplier_code}
    supplier_by_code = _suppliers_by_code(db, supplier_codes)
    # The structured export names the creditor and never its code, so that half is matched by
    # name and never created (`_suppliers_by_name`).
    supplier_by_name = _suppliers_by_name(
        db, {o.supplier_name for o in parsed.orders if o.supplier_name and not o.supplier_code}
    )
    warehouse_by_code = _warehouses_by_code(
        db, {l.location.upper() for o in parsed.orders for l in o.lines if l.location}
    )
    source_ref = (STRUCTURED_SOURCE_REF if parsed.layout == LAYOUT_STRUCTURED
                  else BANDED_SOURCE_REF)

    existing_orders = {
        o.po_number: o
        for o in db.query(PurchaseOrder)
        .filter(PurchaseOrder.po_number.in_([o.po_number for o in parsed.orders]))
        .all()
    }
    #: SPO document number -> its rows by line number, filled one document at a time.
    existing_allocations: dict[str, dict] = {}

    orders_created = 0
    lines_created = 0
    now = _now()
    # Pairings this run has already claimed, keyed exactly as
    # `uq_scm_order_link_claim_identity` is. The database check below cannot stand alone:
    # `SessionLocal` runs `autoflush=False`, so a claim added for one line is still pending
    # when the next line's check reads, and the captain's own book states the same
    # (sales order, document, item) on two rows 2,253 times over - two containers of one
    # product on one purchase order. That is ordinary data, not a row problem, so the second
    # line writes its order line and adds no second claim. Without this the whole 27,192-row
    # job dies at flush on a `UniqueViolation`, having processed nothing.
    # (`order_inquiry_service` already carries the same guard, for the same reason.)
    claimed: set[tuple[Optional[str], str, str, str]] = set()
    # The company the claims below will be stamped with, resolved once. The unique index is
    # per company (migration 335) and so is the existence check, so both halves of the guard
    # have to agree about which company this run is writing into.
    claim_company_id = resolve_write_company_id(get_company_scope(db), ambiguous=None)

    for parsed_order in parsed.orders:
        supplier = (supplier_by_code.get(parsed_order.supplier_code)
                    if parsed_order.supplier_code
                    else supplier_by_name.get(parsed_order.supplier_name))
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

        # Which of the two writers this document belongs to, from its NUMBER. The routing is
        # a property of the document rather than of the file it arrived in, so a shipping
        # order in the banded report is filed the same way as one in the structured export.
        is_shipping_order = parsed_order.doc_family == FAMILY_SPO
        if is_shipping_order:
            held = _allocations_for(db, existing_allocations, parsed_order.po_number)
            document_is_new = not held
            lines_created += _write_shipping_order(
                db, parsed_order,
                product_by_code=product_by_code,
                warehouse_by_code=warehouse_by_code,
                supplier=supplier,
                existing=held,
                outcome=outcome,
                company_id=claim_company_id,
                claimed=claimed,
                now=now,
            )
            orders_created += 1 if document_is_new else 0
            _claim_so_links(db, parsed_order.po_number, parsed_order.so_numbers, now,
                            seen=claimed, company_id=claim_company_id)
            continue

        order = existing_orders.get(parsed_order.po_number)
        if order is None:
            order = PurchaseOrder(
                po_number=parsed_order.po_number,
                supplier_id=str(supplier.id) if supplier else None,
                issue_date=parsed_order.order_date,
                status=_ORDER_STATUS,
                currency=parsed_order.currency or None,
                source_system=SPO_SOURCE_SYSTEM if is_shipping_order else SOURCE_SYSTEM,
                source_ref=source_ref,
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
            identity = {"doc_no": parsed_order.po_number,
                        "item_code": parsed_line.item_code,
                        "line_no": parsed_line.line_no}
            if not parsed_line.is_stock_item:
                # Real money on the order, no product behind it. Carried by the reader so the
                # order total reconciles, and NOT written as a stock line: a quantity of 1
                # "HANDLING CHARGES" is not inventory, and the code would sit in the
                # unmatched list for ever.
                outcome.skip(row=parsed_line.source_row, code=oc.CHARGE_LINE,
                             identity=identity, value=parsed_line.description or None)
                continue
            product_id = product_by_code.get(parsed_line.item_code)
            if product_id is None:
                # Counted in the summary and named there. Never created.
                outcome.skip(row=parsed_line.source_row, code=oc.PRODUCT_NOT_FOUND,
                             identity=identity, value=parsed_line.item_code)
                continue

            # NULL where the export names no location (the banded report never does) and
            # where it names one we do not hold. Unlike an outstanding line, a history line
            # cannot be mis-placed by this - it is closed, so no coverage figure reads it -
            # which is why an unknown location costs the line its warehouse and never the
            # line itself. The codes that did not resolve are named on the summary.
            warehouse_id = (warehouse_by_code.get(parsed_line.location.upper())
                            if parsed_line.location else None)

            line = existing_lines.get(parsed_line.line_no)
            if line is None:
                line = PurchaseOrderLine(
                    purchase_order_id=str(order.id),
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    qty_ordered=parsed_line.qty_ordered,
                    # Fully received, so `on_order_v` cannot count it however the line
                    # status is later edited.
                    qty_received=parsed_line.qty_ordered,
                    # Absent on the structured export, which carries no purchase price at
                    # all: its `Standard Price` is the item's standard price rather than what
                    # this document paid, and the cost engines rank on what was paid.
                    unit_cost=parsed_line.unit_price,
                    currency=parsed_order.currency or None,
                    expected_date=parsed_line.expected_date,
                    line_status="closed",
                    source_system=SPO_SOURCE_SYSTEM if is_shipping_order else SOURCE_SYSTEM,
                    source_ref=str(parsed_line.line_no) if parsed_line.line_no else None,
                )
                db.add(line)
                lines_created += 1
                outcome.success(row=parsed_line.source_row, code=oc.CREATED,
                                identity=identity, value=parsed_order.po_number)
            else:
                line.qty_ordered = parsed_line.qty_ordered
                line.qty_received = parsed_line.qty_ordered
                line.unit_cost = parsed_line.unit_price
                line.line_status = "closed"
                if warehouse_id is not None:
                    line.warehouse_id = warehouse_id
                if parsed_line.expected_date is not None:
                    line.expected_date = parsed_line.expected_date
                # Written unconditionally on a re-upload: this feed's rule is that the file is
                # the record of what was ordered. So it is `updated`, not `unchanged` - the
                # write happened, whatever the values were.
                outcome.updated(row=parsed_line.source_row, identity=identity,
                                value=parsed_order.po_number, entity_type="order_line",
                                entity_id=line.id)

            if parsed_line.so_number:
                # The structured export states the pairing per LINE, so the claim can name
                # the item - which is the identity `order_link_service` resolves on. The
                # banded report's `**SO:174830**` notes are order-level and stay so below.
                _claim_so_link(db, parsed_order.po_number, parsed_line.so_number, now,
                               item_code=parsed_line.item_code, seen=claimed,
                               company_id=claim_company_id)

        _claim_so_links(db, parsed_order.po_number, parsed_order.so_numbers, now,
                        seen=claimed, company_id=claim_company_id)

    db.flush()
    summary["orders_created"] = orders_created
    summary["lines_created"] = lines_created
    summary["date_from"] = summary["date_from"].isoformat() if summary["date_from"] else None
    summary["date_to"] = summary["date_to"].isoformat() if summary["date_to"] else None
    return summary


def _claim_so_links(
    db: Session, po_number: str, so_numbers: tuple[str, ...], now: datetime, *,
    seen: set[tuple[Optional[str], str, str, str]],
    company_id: Optional[str],
) -> None:
    """Record the sales orders this purchase order's notes name.

    A CLAIM, not a link: the sales order may not have been uploaded yet, which is exactly the
    case the user described. No item code, because a note sits between lines and nothing in
    the file says which side it describes.

    Order-level claims repeat too - one document can carry the same `**SO:174830**` note more
    than once - so this half shares the run's `seen` set rather than trusting the numbers to
    be distinct.
    """
    for so_number in so_numbers:
        _claim_so_link(db, po_number, so_number, now, item_code=None, seen=seen,
                       company_id=company_id)


def _claim_so_link(db: Session, po_number: str, so_number: str, now: datetime, *,
                   item_code: Optional[str],
                   seen: set[tuple[Optional[str], str, str, str]],
                   company_id: Optional[str]) -> None:
    """One claim, get-or-create against BOTH the database and this run.

    `item_code` is what separates the two exports: the structured extract states the sales
    order per LINE (`FromSODocList`), so its claim names the item and resolves to that line;
    the banded report's note is order-level and its claim names none, so it resolves at
    document level.

    Two guards, because one file can state a pairing twice and one database can already hold
    it. `seen` is the run's memory, keyed as `uq_scm_order_link_claim_identity` is - the
    company, the two numbers, and the item code coalesced to `''` - and it is what the
    database check cannot supply: nothing is flushed until the end of `apply`, so a claim
    added moments ago is invisible to a SELECT. The SELECT is still needed for the re-upload
    case, where the pairing is committed and this run's set starts empty.

    The SELECT is pinned to the SAME company the row will be stamped with. The scope filter
    already narrows it for a single-company caller, but the system principal reads across
    every company and writes into the incumbent one, so without this an unrelated company's
    claim would suppress a claim this one is missing.
    """
    key = (company_id, so_number, po_number, item_code or "")
    if key in seen:
        return
    seen.add(key)
    query = db.query(OrderLinkClaim.id).filter(
        OrderLinkClaim.so_number == so_number,
        OrderLinkClaim.po_number == po_number,
        OrderLinkClaim.item_code.is_(None) if item_code is None
        else OrderLinkClaim.item_code == item_code,
    )
    if company_id is not None:
        query = query.filter(OrderLinkClaim.company_id == company_id)
    if query.first():
        return
    db.add(
        OrderLinkClaim(
            so_number=so_number,
            po_number=po_number,
            item_code=item_code,
            source="po_history",
            claimed_at=now,
        )
    )
