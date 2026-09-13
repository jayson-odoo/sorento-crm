"""L3 - migrating the Order Inquiry sheet into the worklist.

**Project Sales module code.** Ownership moved here from `app/services/scm/` per ADR 0010:
the whole Order Inquiry loop - derive, export, human edit, import - belongs to Project Sales,
and SCM keeps the role it already had, reader of core `sales_orders`. Only the service layer
moved: the route path `/api/v1/scm/order-inquiry/*` and the permission `scm.reorder.run` are
deliberately unchanged so the FE upload dialog keeps working (the route file now holds a thin
shim onto this module).

**What this sheet is now** (`PLAN-scm-oi-sheet-migration.md`, owner ruling 13 Sep 2026):
a MIGRATION TOOL. Sales orders, purchase orders and shipping orders already arrive from
AutoCount in real time, so the book is not this file's to write any more. What AutoCount does
not hold is the operator's own Excel: which sales-order line is owed where, and which purchase
or shipping order it is waiting on. So this importer:

  * creates NO sales order and NO sales-order line, and writes no `warehouse_id` (D4);
  * RAISES one order inquiry row against the sales order line the sheet names, whatever that
    line's status - closed and fully delivered lines migrate too (D8);
  * PAIRS that row to the document AutoCount's own ingest already states for the line (D9),
    following a purchase order through to the shipping order it became (D10), and falls back
    to the document the sheet's remark cites only for the need AutoCount leaves;
  * opens NO claim of its own: the claim beside a link is written by the one link writer
    (`ProjectOrderInquiryService._write_link`), and nothing else here writes one.

Three honest limits, each counted and named rather than smoothed over.

**A row can only be raised against a line that exists.** A sales order the CRM does not hold
is named under `sales_orders_not_found` and nothing is invented for it; a row whose item,
location or quantity fits no line of that order is reported with the FIRST reason it failed.

**A line that already carries an order inquiry row is left exactly as it is** (D2). The sheet
is a migration, not a source of truth about rows somebody has since worked on, so a re-upload
writes nothing new.

**A cited document with no capacity is not forced.** The row is still raised, its citation
stays on it, and the number is named under `documents_not_linkable` - which is how the
operator sees where the sheet and the book disagree.

`SOURCE_SYSTEM` below stays the literal `'scm_order_inquiry'`. The string is baked into raw
SQL (`scm/demand.py`), into migration 346's backfill and into the `OrderLinkClaim` CHECK
constraint, and the 12 sales orders older uploads created still carry it, so renaming it would
be a data migration that buys no correctness.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product
from app.services import import_outcome_codes as oc
from app.services.import_outcome import ImportOutcome
from app.services.project_label_rules import apply_project_label, label_from_inquiry_cell
from app.services.project_order_inquiry_reader import OrderInquiryResult, read_order_inquiry
from app.services.scm import order_link_service, spo_supply
from app.services.scm import upload_validation as val
from app.services.scm.demand import PROJECT_CLASS
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

SOURCE = "order_inquiry"

#: Stamped on the sales orders and lines this feed CREATED, back when it created any. Kept
#: because those 12 orders still carry it and three readers still match on it.
SOURCE_SYSTEM = "scm_order_inquiry"

#: How many entries a named list carries onto the screen. The counts beside them are the
#: truth; the list is a sample of it.
_CAP = 200

_ZERO = Decimal("0")

#: The claim sources that state what the BOOK says (D9). `order_inquiry` is this feature's
#: own echo of a link it wrote, and `crm_supply` / `planner` are the CRM's own decisions -
#: none of the three is AutoCount's record of a pairing, so none of them pairs anything here.
_BOOK_CLAIM_SOURCES = (
    order_link_service.SOURCE_AUTOCOUNT,
    "po_history",
    order_link_service.SOURCE_PO_UPLOAD,
)

#: What `_write_link` stamps on the row's note for a pairing the book stated, so a link the
#: migration followed is tellable on the worklist from one the operator's remark asked for.
_AUTOCOUNT_TRIGGER = "autocount linkage"

#: Prefixed to every row this importer raises (AC-S1-28), so a migrated row is tellable from
#: a board-raised one without a new column.
_MIGRATION_STAMP = "Migrated from order inquiry sheet"

#: How an EARLIER version of this importer wrote a row's extra citations onto its note, and
#: how `ProjectOrderInquiryService._cited_documents` still reads them back off the rows that
#: carry one. Read-only from here: the migration resolves every citation itself and keeps the
#: first on `cited_document`, so nothing writes this prefix any more - but the rows that
#: already have it are on the live database and the walk must go on understanding them.
ALSO_CITED_PREFIX = "Also cited on the form:"

#: The two target families, spelled once. `_purchase_side` answers in the same two words.
_PO = "po_line_id"
_SPO = "spo_allocation_id"


def _now() -> datetime:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return _ZERO
    return Decimal(str(value))


# --------------------------------------------------------------------------- #
# the plan: what this sheet would do, computed once                            #
# --------------------------------------------------------------------------- #


@dataclass
class _Match:
    """One sheet row, matched (or not) to the core sales order line it names."""

    row: Any
    core_line: Optional[SalesOrderLine] = None
    #: The matched line's own warehouse code, for a sheet row that states no location.
    line_location: Optional[str] = None
    #: Why no line fits, as the FIRST filter that refused it.
    reason: Optional[str] = None
    #: Why the whole order was refused: `order_not_found` or `order_not_plannable`.
    code: Optional[str] = None
    #: The matched line's mirror already carries a non-cancelled row, so this one is skipped.
    already_raised: bool = False
    #: The documents the sheet's remark names, in the order the operator wrote them.
    cited: Tuple[str, ...] = ()

    @property
    def raisable(self) -> bool:
        return self.core_line is not None and not self.already_raised


@dataclass
class _Plan:
    """Every decision this upload makes, taken before anything is written.

    Computed once so `preview` and `apply` cannot disagree: the counts on the screen before
    Confirm are the counts Confirm produces.
    """

    parsed: OrderInquiryResult
    matches: List[_Match] = field(default_factory=list)
    orders: Dict[str, SalesOrder] = field(default_factory=dict)
    orders_not_found: List[str] = field(default_factory=list)
    orders_not_plannable: List[dict] = field(default_factory=list)


@dataclass
class _RowLinks:
    """What one raised row would be linked to, and what it would still be short."""

    takes: List[dict] = field(default_factory=list)
    need_left: Decimal = _ZERO
    from_book: bool = False


def _orders_by_number(db: Session, numbers: set) -> Dict[str, SalesOrder]:
    if not numbers:
        return {}
    rows = db.query(SalesOrder).filter(SalesOrder.so_number.in_(list(numbers))).all()
    return {str(o.so_number): o for o in rows}


def _lines_of(db: Session, order_ids: set) -> Dict[str, List[tuple]]:
    """EVERY line of each order, with its item code and warehouse code.

    Any status: the sheet is history, and D8 is explicit that a closed or fully delivered
    line is exactly what it names. The warehouse is outer-joined because a line with no
    location matches whatever the sheet states for it (D1).
    """
    if not order_ids:
        return {}
    rows = (
        db.query(SalesOrderLine, Product.product_code, Warehouse.warehouse_code)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(SalesOrderLine.sales_order_id.in_([str(i) for i in order_ids]))
        .all()
    )
    held: Dict[str, List[tuple]] = {}
    for line, code, location in rows:
        held.setdefault(str(line.sales_order_id), []).append(
            (line, str(code), (location or "").strip().upper())
        )
    return held


def _cited_from(po_numbers: Sequence[str]) -> Tuple[str, ...]:
    """The documents the row names, upper-cased, in the order the operator wrote them.

    `SPO-2026/08-0061 & 202606-S0082` cites two and both matter: the first is tried for the
    whole need and the second answers for whatever the first could not cover (AC-S1-16).
    """
    ordered: List[str] = []
    for number in po_numbers or ():
        text = str(number).strip().upper()
        if text and text not in ordered:
            ordered.append(text)
    return tuple(ordered)


def _rank_for(row) -> Callable[[tuple], tuple]:
    """The line this row means, when several fit (D1, AC-S1-8).

    The line whose required date IS the sheet's date; then an open line before a closed one;
    then the earliest required date (undated last); then the oldest line, so two runs of the
    same sheet land the same way.
    """
    wanted = row.delivery_date

    def key(candidate: tuple) -> tuple:
        line = candidate[0]
        return (
            0 if line.required_date == wanted else 1,
            0 if (line.line_status or "open") == "open" else 1,
            line.required_date is None,
            line.required_date or date.min,
            line.created_at or datetime.min,
        )

    return key


def _match_row(
    row, candidates: List[tuple], taken: Dict[str, Decimal]
) -> Tuple[Optional[tuple], Optional[str]]:
    """The line for one sheet row, or the FIRST filter that refused it.

    Item, then location, then quantity - reported in that order because that is the order a
    person checks them in, and "no line for this item" and "location differs" send them to
    two different places.

    The quantity test is against what the line ORDERED, less what EARLIER rows of this same
    file already took of it: the sheet may split one line across several rows (AC-S1-2), and
    the importer never splits one itself.
    """
    wanted_item = (row.item_code or "").strip()
    same_item = [c for c in candidates if c[1] == wanted_item]
    if not same_item:
        return None, oc.NO_LINE_FOR_ITEM

    location = (row.location or "").strip().upper()
    if location:
        # A line with no warehouse accepts any location (AC-S1-3): the book simply does not
        # state one, and the sheet is what carries it.
        same_place = [c for c in same_item if not c[2] or c[2] == location]
    else:
        same_place = same_item
    if not same_place:
        return None, oc.LOCATION_DIFFERS

    qty = _dec(row.qty)
    fits = [
        c for c in same_place
        if _dec(c[0].qty_ordered) - taken.get(str(c[0].id), _ZERO) >= qty
    ]
    if not fits:
        return None, oc.QTY_EXCEEDS_ORDERED

    found = sorted(fits, key=_rank_for(row))[0]
    taken[str(found[0].id)] = taken.get(str(found[0].id), _ZERO) + qty
    return found, None


def _already_raised(db: Session, core_lines: List[SalesOrderLine]) -> set:
    """The core lines whose MIRROR already carries a non-cancelled order inquiry row (D2).

    Read off the state BEFORE this upload, once, so two rows of the same file may both land
    on one line while a re-upload of that file raises nothing.
    """
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow, ProjectSalesOrderLine

    if not core_lines:
        return set()
    core_ids = [str(line.id) for line in core_lines]
    mirrors = (
        db.query(ProjectSalesOrderLine.id, ProjectSalesOrderLine.core_sales_order_line_id)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(core_ids))
        .all()
    )
    if not mirrors:
        return set()
    core_by_mirror = {str(mirror_id): str(core_id) for mirror_id, core_id in mirrors}
    held = (
        db.query(OrderInquiryRow.so_line_id)
        .filter(
            OrderInquiryRow.so_line_id.in_(list(core_by_mirror)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    return {core_by_mirror[str(mirror_id)] for (mirror_id,) in held if str(mirror_id) in core_by_mirror}


def _plan(db: Session, parsed: OrderInquiryResult) -> _Plan:
    """Match every row, decide raise / skip / report. Pure: writes nothing."""
    plan = _Plan(parsed=parsed, matches=[_Match(row=row) for row in parsed.rows])
    numbers = {row.so_number for row in parsed.rows if row.so_number}
    plan.orders = _orders_by_number(db, numbers)
    plan.orders_not_found = sorted(n for n in numbers if n not in plan.orders)
    plan.orders_not_plannable = [
        {"so_number": number, "code": "sales_order_not_project_class"}
        for number, order in sorted(plan.orders.items())
        if order.demand_class != PROJECT_CLASS
    ]
    refused = {entry["so_number"] for entry in plan.orders_not_plannable}

    lines = _lines_of(db, {str(order.id) for order in plan.orders.values()})
    #: How much of each line this FILE has already spoken for, in file order.
    taken: Dict[str, Decimal] = {}

    for match in plan.matches:
        row = match.row
        match.cited = _cited_from(row.po_numbers)
        order = plan.orders.get(row.so_number)
        if order is None:
            match.code = oc.ORDER_NOT_FOUND
            continue
        if row.so_number in refused:
            match.code = oc.ORDER_NOT_PLANNABLE
            continue
        found, match.reason = _match_row(row, lines.get(str(order.id)) or [], taken)
        if found is not None:
            match.core_line, match.line_location = found[0], found[2] or None

    skipped = _already_raised(
        db, [m.core_line for m in plan.matches if m.core_line is not None]
    )
    for match in plan.matches:
        if match.core_line is not None and str(match.core_line.id) in skipped:
            match.already_raised = True
    return plan


# --------------------------------------------------------------------------- #
# pairing: what the book states first, what the sheet cites second             #
# --------------------------------------------------------------------------- #


def _target_facts(db: Session, target_ids: set) -> Dict[str, dict]:
    """Everything a link needs about a purchase-order line or an SPO allocation.

    Capacity is `qty_ordered` / `allocated_quantity` - the line's own size, NEVER its
    outstanding (AC-S1-12): the sheet is history, and a closed, fully received line is
    exactly what the rows being migrated are waiting on. What OTHER links already claim is
    subtracted by the caller.
    """
    wanted = [str(i) for i in target_ids if i]
    if not wanted:
        return {}
    facts: Dict[str, dict] = {}
    for line, number, supplier in (
        db.query(PurchaseOrderLine, PurchaseOrder.po_number, Supplier.supplier_name)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(PurchaseOrderLine.id.in_(wanted))
        .all()
    ):
        facts[str(line.id)] = {
            "kind": _PO,
            "document": number,
            "supplier_name": supplier,
            "expected_date": line.expected_date,
            "capacity": _dec(line.qty_ordered),
            "product_id": str(line.product_id or ""),
            "po_line_id": str(line.id),
            "spo_allocation_id": None,
        }
    for allocation, supplier in (
        db.query(SPOAllocation, Supplier.supplier_name)
        .outerjoin(Supplier, Supplier.id == SPOAllocation.supplier_id)
        .filter(SPOAllocation.id.in_(wanted))
        .all()
    ):
        facts[str(allocation.id)] = {
            "kind": _SPO,
            "document": allocation.spo_number,
            "supplier_name": supplier,
            "expected_date": allocation.expected_date,
            "capacity": _dec(allocation.allocated_quantity),
            "product_id": str(allocation.product_id or ""),
            "po_line_id": None,
            "spo_allocation_id": str(allocation.id),
        }
    return facts


def _chain_allocations(db: Session, po_numbers: set, product_ids: set) -> Dict[tuple, List[str]]:
    """The SPO allocations a purchase order BECAME, per `(PO number, product)` (D10).

    The shipping order feed states the purchase order it came from
    (`spo_allocations.from_po_number`), which is the second of the two ways the
    SO -> PO -> SPO chain is known. Following it is what puts the link on the SPO, so the
    worklist shows the shipping order with its source PO beside it rather than a purchase
    order the goods have already left.
    """
    if not po_numbers or not product_ids:
        return {}
    rows = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.from_po_number.in_(list(po_numbers)),
            SPOAllocation.product_id.in_([str(p) for p in product_ids]),
            *spo_supply.visible_line_clauses(),
        )
        .order_by(
            SPOAllocation.spo_number.asc(),
            SPOAllocation.spo_line_number.asc(),
            SPOAllocation.id.asc(),
        )
        .all()
    )
    held: Dict[tuple, List[str]] = {}
    for allocation in rows:
        key = (str(allocation.from_po_number), str(allocation.product_id or ""))
        held.setdefault(key, []).append(str(allocation.id))
    return held


def _claimed_capacity(db: Session) -> Dict[str, Decimal]:
    """What every EXISTING link already claims, per target.

    Read through the one owner of that tally (`ProjectOrderInquiryService._linked_by_target`)
    rather than a second query, so this importer and the worklist cannot come to disagree
    about how much of a line is left. Taken once and decremented locally as this run hands
    quantity out, which is also what makes `preview` and `apply` produce the same numbers.
    """
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    by_po, by_spo = ProjectOrderInquiryService(db)._linked_by_target()
    used: Dict[str, Decimal] = {}
    used.update({str(key): _dec(value) for key, value in by_po.items()})
    used.update({str(key): _dec(value) for key, value in by_spo.items()})
    return used


def _claim_order(facts: Dict[str, dict]) -> Callable[[dict], tuple]:
    """SPO allocation before purchase order line, then the earliest claim (AC-S1-32).

    "SPO first then PO" is R5 of `PLAN-scm-oi-draft-links.md`, and for the same reason it
    was written there: a quantity already on a ship is owed against that ship before it is
    owed against the order that bought it.
    """

    def key(claim: dict) -> tuple:
        fact = facts.get(claim["target_id"]) or {}
        return (
            0 if fact.get("kind") == _SPO else 1,
            claim.get("claimed_at") or datetime.min,
            claim["claim_id"],
        )

    return key


def _pair(db: Session, plan: _Plan) -> Tuple[Dict[int, _RowLinks], List[str]]:
    """What each raisable row would be linked to, in the order the two sources rank.

    **Source 1, what AutoCount states** (D9, the owner: "we don't trust the remark column in
    the sheet, we can refer but the source of truth is the autocount linkage"). The ingest
    already writes that linkage as RESOLVED claims on the core sales-order line, so those are
    read first and their targets linked, SPO before PO, and a purchase order followed through
    to the allocations it became before the purchase-order line itself.

    **Source 2, what the sheet cites** - for the need source 1 leaves, in the order the
    operator wrote the documents. A document the book has already linked is not linked twice;
    one that resolves to nothing, or to a target with no room, is named on the result.

    Nothing is written here. `apply` writes exactly what this returns, and `preview` counts
    it, so the two can never answer differently.
    """
    wanted = [(i, m) for i, m in enumerate(plan.matches) if m.raisable]
    links: Dict[int, _RowLinks] = {}
    not_linkable: List[str] = []
    if not wanted:
        return links, not_linkable

    claims = [
        claim
        for claim in order_link_service._claim_rows(
            db, so_line_ids={str(m.core_line.id) for _, m in wanted}
        )
        if claim["source"] in _BOOK_CLAIM_SOURCES
    ]
    by_line: Dict[str, List[dict]] = {}
    for claim in claims:
        by_line.setdefault(str(claim["so_line_id"]), []).append(claim)

    cited_numbers = {number for _, m in wanted for number in m.cited}
    by_key, _by_number = (
        order_link_service._purchase_side(db, cited_numbers) if cited_numbers else ({}, {})
    )

    target_ids = {claim["target_id"] for claim in claims}
    target_ids |= {target for _side, target in by_key.values()}
    facts = _target_facts(db, target_ids)

    chain = _chain_allocations(
        db,
        {
            facts[claim["target_id"]]["document"]
            for claim in claims
            if facts.get(claim["target_id"], {}).get("kind") == _PO
        },
        {str(m.core_line.product_id or "") for _, m in wanted},
    )
    chained = {
        allocation_id for allocations in chain.values() for allocation_id in allocations
    }
    facts.update(
        {key: value for key, value in _target_facts(db, chained).items() if key not in facts}
    )

    used = _claimed_capacity(db)

    for index, match in wanted:
        held = _RowLinks(need_left=_dec(match.row.qty))
        seen: set = set()

        def take(target_id: str, *, from_book: bool) -> bool:
            fact = facts.get(str(target_id))
            if fact is None or str(target_id) in seen:
                return False
            free = fact["capacity"] - used.get(str(target_id), _ZERO)
            if free <= _ZERO:
                return False
            qty = min(held.need_left, free)
            if qty <= _ZERO:
                return False
            used[str(target_id)] = used.get(str(target_id), _ZERO) + qty
            held.need_left -= qty
            seen.add(str(target_id))
            held.takes.append({
                "document": fact["document"],
                "supplier_name": fact["supplier_name"],
                "expected_date": fact["expected_date"],
                "po_line_id": fact["po_line_id"],
                "spo_allocation_id": fact["spo_allocation_id"],
                "qty": qty,
                "from_book": from_book,
            })
            held.from_book = held.from_book or from_book
            return True

        line_claims = by_line.get(str(match.core_line.id)) or []
        for claim in sorted(line_claims, key=_claim_order(facts)):
            if held.need_left <= _ZERO:
                break
            fact = facts.get(claim["target_id"])
            if fact is None:
                continue
            if fact["kind"] == _SPO:
                take(claim["target_id"], from_book=True)
                continue
            # A purchase order the book paired: its shipping orders first (D10), the
            # purchase-order line itself only for what they cannot cover.
            for allocation_id in chain.get(
                (str(fact["document"]), str(match.core_line.product_id or "")), []
            ):
                if held.need_left <= _ZERO:
                    break
                take(allocation_id, from_book=True)
            if held.need_left > _ZERO:
                take(claim["target_id"], from_book=True)

        for number in match.cited:
            if held.need_left <= _ZERO:
                break
            side = by_key.get((number, (match.row.item_code or "").strip()))
            if side is None:
                not_linkable.append(number)
                continue
            target_id = str(side[1])
            if target_id in seen:
                # The book already put this row on that document. Not a failure, and not a
                # second link.
                continue
            if not take(target_id, from_book=False):
                not_linkable.append(number)

        if held.takes:
            links[index] = held
    return links, not_linkable


# --------------------------------------------------------------------------- #
# the result the operator reads                                                #
# --------------------------------------------------------------------------- #


def _identity(row) -> dict:
    """What names a sheet row in the job detail. No ids - the operator reads SO numbers.

    The tab is part of the name: row numbers restart on every sheet, so "row 42" alone names
    four different rows in a book of monthly tabs.
    """
    return {
        "doc_no": row.so_number,
        "item_code": row.item_code,
        "delivery_date": row.delivery_date.isoformat() if row.delivery_date else "",
        "sheet": getattr(row, "sheet", "") or "",
    }


def _result(
    plan: _Plan,
    links: Dict[int, _RowLinks],
    not_linkable: Sequence[str],
    *,
    rows_raised: int,
) -> dict:
    """The fifteen keys, and nothing else (AC-S1-22).

    The retired counters are GONE rather than zeroed: a screen that can print
    `lines_created` is a screen that can tell somebody this sheet wrote the book.
    """
    line_not_found = [
        {
            "so_number": match.row.so_number,
            "item_code": match.row.item_code,
            "qty": float(_dec(match.row.qty)),
            "reason": match.reason,
        }
        for match in plan.matches
        if match.reason
    ]
    documents: List[str] = []
    for number in not_linkable:
        if number not in documents:
            documents.append(number)
    return {
        "ok": plan.parsed.ok,
        "problems": list(plan.parsed.problems),
        "rows": len(plan.parsed.rows),
        "rows_raised": rows_raised,
        "rows_already_raised": sum(1 for m in plan.matches if m.already_raised),
        "rows_line_not_found": len(line_not_found),
        "line_not_found": line_not_found[:_CAP],
        "sales_orders_not_found": plan.orders_not_found[:_CAP],
        "orders_not_plannable": plan.orders_not_plannable[:_CAP],
        # Per ROW, not per link: a row that lands on two documents is one row the book
        # answered for, and counting the links would make the two numbers uncomparable.
        "links_written": len(links),
        "links_partial": sum(1 for held in links.values() if held.need_left > _ZERO),
        "links_from_autocount": sum(1 for held in links.values() if held.from_book),
        "documents_not_linkable": documents[:_CAP],
        "sheets_read": list(plan.parsed.sheets_read),
        "sheets_skipped": list(plan.parsed.sheets_skipped),
    }


def _empty(parsed: OrderInquiryResult) -> dict:
    """The same fifteen keys for a file that could not be read (AC-S1-25)."""
    return _result(_Plan(parsed=parsed), {}, [], rows_raised=0)


def preview(db: Session, file_data: bytes) -> dict:
    """What this sheet would raise and link. Writes nothing (AC-S1-24)."""
    parsed = read_order_inquiry(file_data)
    if not parsed.ok:
        return _empty(parsed)
    plan = _plan(db, parsed)
    links, not_linkable = _pair(db, plan)
    return _result(
        plan, links, not_linkable,
        rows_raised=sum(1 for match in plan.matches if match.raisable),
    )


def validate(db: Session, file_data: bytes) -> dict:
    """The Test verdict: `{valid, errors, warnings, summary}`. Writes nothing.

    Only an unreadable sheet is an ERROR. Everything else the migration cannot do - a sales
    order the CRM does not hold, a row that fits no line, a document that could not be
    linked - is a WARNING: the rest of the file is still worth migrating, and a panel that
    calls a 400-row book a failure over 3 rows is a panel nobody reads.
    """
    out = preview(db, file_data)
    warnings = [
        val.named(
            len(out["sales_orders_not_found"]), out["sales_orders_not_found"],
            one="sales order the CRM does not hold",
            many="sales orders the CRM does not hold",
        ),
        (f"{out['rows_line_not_found']:,} rows name no sales order line we hold, so they "
         f"will not be raised") if out["rows_line_not_found"] else None,
        (f"{out['rows_already_raised']:,} rows are on a line that already carries an order "
         f"inquiry, and are left alone") if out["rows_already_raised"] else None,
        val.named(
            len(out["documents_not_linkable"]), out["documents_not_linkable"],
            one="cited document we could not link",
            many="cited documents we could not link",
        ),
        (f"{len(out['sheets_skipped']):,} sheets had no header row and were skipped: "
         f"{', '.join(out['sheets_skipped'][:12])}") if out["sheets_skipped"] else None,
    ]
    return val.envelope(
        ok=out["ok"], problems=out["problems"], warnings=warnings,
        summary={
            "total_rows": out["rows"],
            "would_apply": out["rows_raised"],
            "skipped_rows": out["rows_already_raised"] + out["rows_line_not_found"],
            "error_count": 0 if out["ok"] else len(out["problems"]),
            "sheets_read": len(out["sheets_read"]),
        },
    )


# --------------------------------------------------------------------------- #
# the write                                                                    #
# --------------------------------------------------------------------------- #


def _link_actor(actor: Optional[str]) -> Optional[str]:
    """Whose name goes on a link this upload writes.

    The uploader, when a person queued the job - which is the normal case, and the honest
    answer. Failing that the configured act-as principal
    (`EXTERNAL_API_KEY_ACT_AS_USER_ID`), which is the convention this codebase already uses
    for an unattended write that still has to be attributable. `None` when there is neither,
    and the pairing is then SKIPPED rather than writing links nobody can be asked about:
    `order_inquiry_links.linked_by` is nullable, so an anonymous link is a row that passes
    every constraint and answers no question.
    """
    if actor:
        return str(actor)
    from app.config import settings

    configured = getattr(settings, "external_api_key_act_as_user_id", None)
    return str(configured) if configured else None


def _stamp_orders(plan: _Plan) -> None:
    """The two header stamps the sheet has always applied to an order it does NOT own.

    Rule 1 of `PLAN-so-project-label.md` (AC-S1-37): the project half of the inquiry's own
    cell, under `apply_project_label`'s existing precedence gate - a customer-only cell
    carries no label and leaves an existing one alone.

    And `demand_origin`: an inquiry naming a sales order is exactly what makes it project
    demand (S13b), and the fact does not depend on who owns the figures. Never cleared -
    dropping off a later sheet is one person tidying a working file, not CS withdrawing the
    demand.

    This is the only write this importer makes to `sales_orders`, and it is an UPDATE to a
    header the CRM already holds. Nothing is created (AC-S1-19).
    """
    labels: Dict[str, str] = {}
    for match in plan.matches:
        project = (getattr(match.row, "project", "") or "").strip()
        if project and match.row.so_number not in labels:
            labels[match.row.so_number] = project
    for number, order in plan.orders.items():
        if order.demand_origin != SOURCE_SYSTEM:
            order.demand_origin = SOURCE_SYSTEM
        cell = labels.get(number)
        label = label_from_inquiry_cell(cell) if cell else None
        if label:
            apply_project_label(order, label, "inquiry")


def _note_for(row, file_name: Optional[str]) -> str:
    """The migration stamp, with the operator's own remark kept after it (AC-S1-28)."""
    stamp = f"{_MIGRATION_STAMP} {file_name}".strip() if file_name else _MIGRATION_STAMP
    remark = (getattr(row, "remark", "") or "").strip()
    return f"{stamp}; {remark}" if remark else stamp


class _Raiser:
    """Adopts each sales order once, and raises rows against its mirror lines.

    A class rather than a closure because three things have to be remembered across the
    sheet's rows and none of them may be recomputed per row: the planning record, its
    inquiry header, and the mirror line for each core line.
    """

    def __init__(self, db: Session, actor: Optional[str], now: datetime):
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        self.db = db
        self.actor = actor
        self.now = now
        self.adoption = ProjectSOAdoptionService(db)
        self._records: Dict[str, Optional[dict]] = {}

    def record_for(self, order: SalesOrder) -> Optional[dict]:
        """The planning record, its header and its mirror map. Adopted once per order."""
        key = str(order.id)
        if key in self._records:
            return self._records[key]
        from app.services.error_handler import AppException

        try:
            adopted = self.adoption.adopt_for_migration(str(order.id), self.actor)
        except AppException as refusal:
            logger.info(
                "Order inquiry sheet: %s could not be adopted (%s)",
                order.so_number, refusal.code,
            )
            self._records[key] = None
            return None
        pso_id = str(adopted["project_sales_order_id"])
        self._records[key] = {
            "pso_id": pso_id,
            "inquiry": self._inquiry(order, pso_id),
            "mirrors": self._mirrors(pso_id),
        }
        return self._records[key]

    def _inquiry(self, order: SalesOrder, pso_id: str):
        """The order's open inquiry header, or a new one.

        Only a header THIS upload creates is stamped with the uploader. An inquiry the BOARD
        raised belongs to the CS who confirmed it, and re-stamping it would make the order
        inquiry page name whoever last sent a spreadsheet as the person who decided the
        order - which is the one question that column exists to answer.
        """
        from app.models.project_so import INQUIRY_RAISED, OrderInquiry

        inquiry = (
            self.db.query(OrderInquiry)
            .filter(
                OrderInquiry.project_sales_order_id == pso_id,
                OrderInquiry.amendment_id.is_(None),
            )
            .first()
        )
        if inquiry is not None:
            return inquiry
        inquiry = OrderInquiry(
            company_id=order.company_id,
            project_sales_order_id=pso_id,
            state=INQUIRY_RAISED,
            raised_by=self.actor,
            raised_at=self.now,
        )
        self.db.add(inquiry)
        self.db.flush()
        return inquiry

    def _mirrors(self, pso_id: str) -> Dict[str, str]:
        """Mirror line id per core line id.

        `order_inquiry_rows.so_line_id` addresses `projects.sales_order_lines`, which is the
        shim every other reader reaches the core line through.
        """
        from app.models.project_so import ProjectSalesOrderLine

        return {
            str(core_id): str(mirror_id)
            for mirror_id, core_id in self.db.query(
                ProjectSalesOrderLine.id, ProjectSalesOrderLine.core_sales_order_line_id
            ).filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            if core_id
        }

    def raise_row(self, match: _Match, order: SalesOrder, *, file_name: Optional[str]):
        """One order inquiry row, born acknowledged, against the sheet's own line."""
        from app.models.project_so import (
            ACK_ACKNOWLEDGED,
            INQUIRY_RAISED,
            IV_ORDER,
            IV_ORDER_BACK,
            OrderInquiryRow,
        )

        record = self.record_for(order)
        if record is None:
            return None
        mirror_id = record["mirrors"].get(str(match.core_line.id))
        if mirror_id is None:
            logger.warning(
                "Order inquiry sheet: no mirror line for core line %s on %s",
                match.core_line.id, order.so_number,
            )
            return None
        row = match.row
        location = (row.location or "").strip().upper() or None
        entry = OrderInquiryRow(
            company_id=order.company_id,
            order_inquiry_id=record["inquiry"].id,
            so_line_id=mirror_id,
            item_code=row.item_code,
            qty=_dec(row.qty),
            # The sheet's date, or the line's own when the operator wrote words where the
            # date goes. `ORDER BACK` is not a date and must not become one.
            delivery_date=row.delivery_date or (
                None if row.order_back else match.core_line.required_date
            ),
            stock_location=location or match.line_location,
            verb=IV_ORDER_BACK if row.order_back else IV_ORDER,
            cited_document=match.cited[0] if match.cited else None,
            note=_note_for(row, file_name),
            state=INQUIRY_RAISED,
            # Born acknowledged (G4, `PLAN-scm-reorder-oi-feedback-1sep.md` S1): this is a
            # migration of instructions purchasing has been working from for months, not a
            # fresh request waiting on somebody's confirm.
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=self.actor,
            acknowledged_at=self.now,
        )
        self.db.add(entry)
        self.db.flush()
        return entry


def apply(
    db: Session,
    file_data: bytes,
    actor: Optional[str] = None,
    outcome: Optional[ImportOutcome] = None,
    on_total_rows: Optional[Callable[[int], None]] = None,
    file_name: Optional[str] = None,
) -> dict:
    """Raise the sheet's rows against the book's lines, and pair each to its document.

    One transaction, owned by the caller (`_run_scm_upload_job`). `outcome` records what
    happened to each sheet ROW for the job detail; optional so a direct caller keeps the old
    signature, with a throwaway non-persisting recorder standing in when it is absent.
    `file_name` is stamped on every row this raises (AC-S1-28).
    """
    outcome = outcome or ImportOutcome(None, persist=False)
    parsed = read_order_inquiry(file_data)
    if on_total_rows is not None:
        on_total_rows(len(parsed.rows))
    if not parsed.ok:
        return _empty(parsed)

    plan = _plan(db, parsed)
    link_actor = _link_actor(actor)
    if link_actor:
        links, not_linkable = _pair(db, plan)
    else:
        # Every link records WHO made it, so an unattended upload with no actor raises the
        # rows and leaves the documents to the worklist's own Auto-link button, under a real
        # name. The citations are named rather than silently dropped.
        links, not_linkable = {}, [
            number for entry in plan.matches if entry.raisable for number in entry.cited
        ]

    now = _now()
    _stamp_orders(plan)
    raiser = _Raiser(db, actor, now)
    service = None
    linked: List[Any] = []
    raised = 0

    for index, match in enumerate(plan.matches):
        row = match.row
        identity = _identity(row)
        if match.code == oc.ORDER_NOT_FOUND:
            outcome.skip(row=row.source_row, code=oc.ORDER_NOT_FOUND,
                         identity=identity, value=row.so_number)
            continue
        if match.code == oc.ORDER_NOT_PLANNABLE:
            outcome.skip(row=row.source_row, code=oc.ORDER_NOT_PLANNABLE,
                         identity=identity, value=row.so_number)
            continue
        if match.reason:
            outcome.skip(row=row.source_row, code=match.reason,
                         identity=identity, value=row.so_number)
            continue
        if match.already_raised:
            outcome.skip(row=row.source_row, code=oc.ALREADY_RAISED,
                         identity=identity, value=row.so_number)
            continue

        entry = raiser.raise_row(match, plan.orders[row.so_number], file_name=file_name)
        if entry is None:
            outcome.skip(row=row.source_row, code=oc.ORDER_NOT_PLANNABLE,
                         identity=identity, value=row.so_number)
            continue
        raised += 1
        outcome.success(row=row.source_row, code=oc.CREATED, identity=identity,
                        value=row.so_number, entity_type="order_inquiry_row",
                        entity_id=entry.id)

        held = links.get(index)
        if not held:
            continue
        if service is None:
            from app.services.project_order_inquiry_service import ProjectOrderInquiryService

            service = ProjectOrderInquiryService(db)
        for take in held.takes:
            # `_write_link` is the ONE writer of a link, its audit claim and the row's note
            # stamp. Called directly rather than through `place_on_po_allocations`, whose
            # open-line gate is exactly what D8 removes: history is closed lines.
            service._write_link(
                entry,
                take,
                take["qty"],
                actor_user_id=link_actor,
                auto_trigger=_AUTOCOUNT_TRIGGER if take["from_book"] else None,
            )
        linked.append(entry)

    if service is not None and linked:
        # ONCE, for every row this upload linked. `refresh_link_state` re-derives each
        # inquiry's bundles before reading the links, so calling it per row would redo that
        # derivation for the whole inquiry on every row of a sheet that names it.
        service.refresh_link_state(linked)

    db.flush()
    return _result(plan, links, not_linkable, rows_raised=raised)
