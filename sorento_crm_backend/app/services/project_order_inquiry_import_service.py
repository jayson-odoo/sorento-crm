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
    following a purchase order through to the shipping order it became (D10). The sheet's
    remark pairs NOTHING and picks no line (section 8 of the pairing-repair plan, owner
    15 Sep 2026: "let's ignore the sheet remark at all"); it is kept on the row's note, so a
    person can still read what the sheet said;
  * opens NO claim of its own: the claim beside a link is written by the one link writer
    (`ProjectOrderInquiryService._write_link`), and nothing else here writes one.

**How that pairing is read** (`PLAN-scm-oi-sheet-pairing-repair.md`, owner rulings R1 to R3,
14 Sep 2026). The purchase side carries the exact sales order line it was raised for, in its
own column: `purchase_order_lines.from_so_line_ref` and the `spo_allocations` twin, both
joinable to `sales_order_lines.source_ref`. That column is read FIRST, because it is exact,
already persisted, and is what the owner's own query reads. Claims are the fallback for the
documents AutoCount stated only by NUMBER: a claim is one row per
`(so_number, po_number, item_code)` and never repoints, so it cannot say "line 3 to purchase
order A, line 4 to purchase order B" for two same-item lines, and on the 14 Sep prod copy the
August `po_history` extract already held the claim key for 28,397 pairings the column states
exactly, which is why `po_history` pairs nothing any more. The same column also decides WHICH
line of the order a row lands on when several fit, through five passes in order
(`PLAN-oi-sheet-line-pick-month-po.md`, owner rulings R1 to R7, 19 Sep 2026,
`_match_in_passes`): the line whose required date IS the sheet's date; failing that, a line
in the sheet's own month whose book document the sheet ALSO cites (R4, prod C-FH14: the
sheet's PO outranks the month when they disagree, or an April row citing one purchase order
steals the month's only line from a row that actually cites it); failing that, any line
among the book's own documents the sheet cites, whichever month it falls in (R2: the sheet's
PO may pick the LINE even though it still pairs nothing); failing that, any line left in the
sheet's own month with no PO to decide it; and only then the line the book bought for at
all, unchanged from before. Inside every one of the five, a line whose own `qty_ordered`
equals the row's quantity is tried before a bigger one (R6, prod CB2805A-DIY: two same-date
lines with nothing else to tell them apart otherwise left the smaller row taking the bigger
line on a bare created-at tie-break). A cancelled August-extract ghost line is never offered
by the first four passes at all and ranks last in the fifth, the fallback, where it is still
taken when it is the only line that fits (R7, 19 Sep 2026, prod comparison workbook: a ghost
carries its line's ORIGINAL date, so it was routinely the only exact-date candidate a row
had, and used to win pass 1 outright before a live line the row's own citation named was
ever offered in a later pass).

Three honest limits, each counted and named rather than smoothed over.

**A row can only be raised against a line that exists.** A sales order the CRM does not hold
is named under `sales_orders_not_found` and nothing is invented for it; a row whose item,
location or quantity fits no line of that order is reported with the FIRST reason it failed.

**A line that already carries an order inquiry row is left exactly as it is** (D2). The sheet
is a migration, not a source of truth about rows somebody has since worked on, so a re-upload
writes nothing new.

**A genuine typo inside one tab still raises twice** (R5, 19 Sep 2026: a restatement is only
ever across tabs, never within one). A row a person mistyped rather than meant to split is
indistinguishable here from a real second delivery, so it raises like one, and is only reported
(`qty_exceeds_ordered`) once it overflows the line it and its twin both want. Measured on the
owner's book, 18 Sep prod copy: lines holding more than one sheet row went from 183 to 285, and
`qty_exceeds_ordered` from 531 to 619.

`SOURCE_SYSTEM` below stays the literal `'scm_order_inquiry'`. The string is baked into raw
SQL (`scm/demand.py`), into migration 346's backfill and into the `OrderLinkClaim` CHECK
constraint, and the 12 sales orders older uploads created still carry it, so renaming it would
be a data migration that buys no correctness.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
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
from app.services.scm.demand import COVERED, PROJECT_CLASS, qty_of
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

#: The claim sources that still state what the BOOK says, once the line reference has been
#: read (D9 as repaired, `PLAN-scm-oi-sheet-pairing-repair.md` section 2.3). `order_inquiry`
#: is this feature's own echo of a link it wrote, and `crm_supply` / `planner` are the CRM's
#: own decisions - none of the three is AutoCount's record of a pairing, so none of them
#: pairs anything here.
#:
#: `po_history` left this list with owner ruling R1 (14 Sep 2026). Those 33,235 rows are ONE
#: August Excel extract, and since a claim is one row per `(so_number, po_number, item_code)`
#: and never repoints, they hold the key for 28,397 pairings AutoCount states exactly on the
#: purchase side. Trusted as the book, they moved rows onto documents the goods never came
#: from.
_BOOK_CLAIM_SOURCES = (
    order_link_service.SOURCE_AUTOCOUNT,
    order_link_service.SOURCE_PO_UPLOAD,
)

#: What `_write_link` stamps on the row's note for a pairing the book stated, so a link the
#: migration followed is tellable on the worklist from one the operator's remark asked for.
_AUTOCOUNT_TRIGGER = "autocount linkage"

#: Prefixed to every row this importer raises (AC-S1-28), so a migrated row is tellable from
#: a board-raised one without a new column.
_MIGRATION_STAMP = "Migrated from order inquiry sheet"

#: Why an upload with no actor is refused (AC-S1-42). Worded for the uploader, since it
#: travels to the job page as the reason the job failed.
NO_ACTOR_PROBLEM = (
    "this upload has nobody to attribute it to, so nothing was raised: sign in and upload "
    "again, or configure the act-as principal for an unattended run."
)

#: How an EARLIER version of this importer wrote a row's extra citations onto its note, and
#: how `ProjectOrderInquiryService._cited_documents` still reads them back off the rows that
#: carry one. Read-only from here: the migration resolves every citation itself and keeps the
#: first on `cited_document`, so nothing writes this prefix any more - but the rows that
#: already have it are on the live database and the walk must go on understanding them.
ALSO_CITED_PREFIX = "Also cited on the form:"

#: `order_inquiry_rows.stock_location` is `String(80)` and `warehouses.warehouse_code` is
#: shorter still, so a longer cell names no warehouse this system could hold. Refused as a
#: location that differs rather than carried into the insert, where it would abort the whole
#: job over one bad cell (security review N3, 14 Sep).
_MAX_LOCATION = 80

#: The two target families, spelled once: a purchase order line, or a shipping order's own
#: allocation. Every fact, every take and every link names one of the two.
_PO = "po_line_id"
_SPO = "spo_allocation_id"

#: A CANCELLED purchase order line is never a link target and never evidence that a sales
#: order line was bought for (section 8 of `PLAN-scm-oi-sheet-pairing-repair.md`). Stated
#: once and applied to both reads that touch purchase order lines, the same way
#: `po_last_cost_service._LIVE_LINE_CLAUSES` states it for costs. `line_status` is NOT NULL
#: with a default of `open` and no row on the prod copy carries a NULL, so the plain test is
#: the whole test. The SPO side already carries `spo_supply.visible_line_clauses()`.
_LIVE_PO_LINE = PurchaseOrderLine.line_status != "cancelled"


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
    #: An earlier row of this same upload says exactly this, on this tab or another (D7).
    duplicate: bool = False
    #: The id of the MIGRATED `OrderInquiryRow` this row's own delivery date would repair,
    #: decided once in `_plan` (`_resolve_delivery_date_repairs`, B1/S1, 19 Sep 2026) so
    #: `preview` and `apply` read the same answer. `None` when nothing on the line needs
    #: repairing, whether because it is not already-raised, it states no date, or every
    #: candidate is already on the sheet's date.
    repair_row_id: Optional[str] = None
    #: Which repair `repair_row_id` needs (round 5/6, 19 Sep 2026, prod feedback after
    #: #1004/#1011 deployed): `"A"` writes the row's own `delivery_date` (untouched since
    #: migration); `"B"` writes `previous_delivery_date` instead - a row a planning change
    #: already restated IN PLACE, whose Now (`qty`/`delivery_date`) is correct but still
    #: carries 7.4's mistake on its Was side; `"C"` writes BOTH `previous_qty` and
    #: `previous_delivery_date` - a row a board Confirm restated IN PLACE before either was
    #: ever recorded, adopting the sheet row as the Was the settle never wrote. `None` when
    #: `repair_row_id` is `None`.
    repair_shape: Optional[str] = None
    #: 2.1(a) (`PLAN-oi-rollback-recover-planning-rows.md`, R6): the id of the live
    #: `Replaces N used` sibling row this sheet row is raised AS - an exact quantity AND
    #: date match against its OWN `previous_qty` / `previous_delivery_date`, with no used
    #: row of its own yet. Set in `_resolve_recovery_matches`, which also flips
    #: `already_raised` back to `False` so this match is raised rather than skipped.
    used_sibling_id: Optional[str] = None
    #: R6: this match sits beside a `Replaces N used` line, but no fresh row's own
    #: previous quantity AND date matches it exactly - nothing is guessed, and `apply`
    #: reports it under its own code (AC-RB-3) instead of the ordinary `ALREADY_RAISED`.
    no_used_delivery_match: bool = False
    #: 2.1(b): the ACTIVE `so_supply_decisions` row covering this (unraised) line, when its
    #: snapshot differs from the sheet and its `buy_qty` is not zero (R4). `settle_buy_qty`
    #: / `settle_required_date` are the decision's own figures, read once in `_plan` so
    #: `raise_row`'s caller never re-parses the snapshot.
    settle_decision_id: Optional[str] = None
    settle_buy_qty: Optional[Decimal] = None
    settle_required_date: Optional[date] = None
    #: R8 (`PLAN-oi-rollback-recover-planning-rows.md`, AC-RB-27): this line's live ORDER /
    #: ORDER BACK rows all carry the ACTIVE decision, but the sheet row's own quantity plus
    #: theirs does not equal the decision's `buy_qty` - nothing is guessed, reported under
    #: its own code (`TOP_UP_SUM_MISMATCH`) rather than the ordinary `ALREADY_RAISED`.
    top_up_sum_mismatch: bool = False

    @property
    def raisable(self) -> bool:
        return (
            self.core_line is not None and not self.already_raised and not self.duplicate
        )


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
    #: The sales orders this upload will actually work on: not refused, and carrying at
    #: least one row it can raise. The header stamps reach these and nothing else
    #: (AC-S1-39), and the adoptions are counted over them (AC-S1-22).
    orders_in_play: List[str] = field(default_factory=list)
    #: Of those, the ones with no planning record yet - what `orders_adopted` will be.
    orders_to_adopt: int = 0
    #: `(source_ref, product_id)` for every candidate line the book BOUGHT for (section 7).
    #: The fallback pass of the line pick reads it, before any pairing happens.
    bought_refs: set = field(default_factory=set)
    #: The rows that set was derived from, kept so `_pair` groups them into the pairing's
    #: first source rather than reading the same two queries a second time.
    bought_rows: Optional[Tuple[List[Any], List[Any]]] = None
    #: `(source_ref, product_id)` -> the document NUMBERS the book bought it with
    #: (`_bought_documents`, PLAN-oi-sheet-line-pick-month-po.md section 2, "Book PO per
    #: line"), off the SAME rows `bought_rows` holds. The month and sheet-PO passes read it
    #: to tell whether a candidate line is one the sheet's own citation also names.
    bought_documents: Dict[tuple, set] = field(default_factory=dict)
    #: How many rows `matches` actually holds, once a `+` cell has been split into one row
    #: per member (`_members`, plan section 2). `None` for a plan `_plan` never ran on -
    #: `_empty`'s unreadable-file / no-actor shapes - where `_result` falls back to
    #: `len(plan.parsed.rows)`, the only count there is to report.
    rows_expanded: Optional[int] = None
    #: Mirror id per core line id, for every already-adopted line the named orders carry -
    #: the SAME map `_already_raised` builds internally (S3, 19 Sep 2026), stashed here so
    #: `_resolve_delivery_date_repairs` does not re-query it.
    mirror_by_core_line: Dict[str, str] = field(default_factory=dict)


@dataclass
class _RowLinks:
    """What one raised row would be linked to, and what it would still be short."""

    takes: List[dict] = field(default_factory=list)
    need_left: Decimal = _ZERO
    from_book: bool = False


@dataclass
class _Need:
    """One thing wanting a document, over one core sales-order line - `pair_needs`'
    own unit (S1, `PLAN-oi-follow-book-chain.md`).

    `key` is whatever the caller wants back: `_pair` uses the match's index into
    `plan.matches` (unchanged, AC-FB-12), and `ProjectOrderInquiryService.
    follow_book_for_rows` uses the row id directly, since a live row already
    exists and does not need one raised for it first.
    """

    key: Any
    need_qty: Decimal
    core_line: SalesOrderLine


def _orders_by_number(db: Session, numbers: set) -> Dict[str, SalesOrder]:
    """The sales orders the sheet names, one per number, the OLDEST first.

    Ordered and first-wins rather than a dict comprehension over an unordered read: two
    orders can carry the same number (AC-S1-43 - the company scope normally keeps them
    apart), and "whichever row the database returned last" is not an answer a second run
    would repeat. `preview` and `apply` each run this, and they must agree.
    """
    if not numbers:
        return {}
    rows = (
        db.query(SalesOrder)
        .filter(SalesOrder.so_number.in_(sorted(numbers)))
        .order_by(SalesOrder.so_number.asc(), SalesOrder.id.asc())
        .all()
    )
    held: Dict[str, SalesOrder] = {}
    for order in rows:
        held.setdefault(str(order.so_number), order)
    return held


def _lines_of(db: Session, order_ids: set) -> Dict[str, List[tuple]]:
    """EVERY line of each order, with its item code and warehouse code.

    Any status: the sheet is history, and D8 is explicit that a closed or fully delivered
    line is exactly what it names. The warehouse is outer-joined because a line with no
    location matches whatever the sheet states for it (D1).

    ORDERED, because `_rank_for` sorts these candidates and a sort is only as stable as what
    it is given: a whole AutoCount ingest shares one `created_at` (Postgres freezes `now()`
    per transaction), so without an explicit order the tie fell to whatever order the read
    happened to return and `preview` and `apply` could pick different lines for the same row.
    """
    if not order_ids:
        return {}
    rows = (
        db.query(SalesOrderLine, Product.product_code, Warehouse.warehouse_code)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(SalesOrderLine.sales_order_id.in_(sorted(str(i) for i in order_ids)))
        .order_by(
            SalesOrderLine.sales_order_id.asc(),
            SalesOrderLine.created_at.asc(),
            SalesOrderLine.id.asc(),
        )
        .all()
    )
    held: Dict[str, List[tuple]] = {}
    for line, code, location in rows:
        held.setdefault(str(line.sales_order_id), []).append(
            (line, str(code), (location or "").strip().upper())
        )
    return held


def _is_open_demand(line: SalesOrderLine) -> bool:
    """`is_open_demand()` against a line already fetched (AC-S1-29).

    The SQL predicate every demand reader shares, restated over the object rather than the
    column, because the answer is needed for a line this service is holding. Both columns
    are NOT NULL with defaults, so the two readings cannot diverge on a NULL.
    """
    return (
        line.line_status == "open"
        and line.purchasing_status != COVERED
        and qty_of(line) > 0
    )


def _restates(row) -> tuple:
    """What makes two sheet rows the SAME instruction (D7, AC-S1-38 as amended by AC-R-11).

    The customer keeps one book with a month tab, a roll-up tab covering that month and a
    dated working snapshot, so the same delivery is written out two and three times by
    design. Sales order, item, quantity, delivery date and location is the whole key (owner
    ruling R3, 14 Sep 2026: "the remark doesn't really matter, differing remark is same also
    as long as other keys are the same"); anything that differs on those five - a quantity, a
    date, a location - is the sheet splitting the line, which AC-S1-2 says it may.

    The remark, the documents parsed out of it and the ORDER BACK flag are all OUT of the
    key. Which tab carries the purchase order number is an accident of how the book is kept,
    so a roll-up row that names one is the same instruction as the month row that left it
    blank - and `_plan` lends that citation onto the FIRST statement of the pair when that
    one carries none, before either row ever reaches the line pick. A first statement that
    already cites its own purchase order keeps it - lending never overwrites a citation, only
    fills the gap the blank tab left. An ORDER BACK row carries no delivery date at all, so
    the date still tells it apart from a dated row.

    R3's "the remark doesn't matter" was about ONE delivery written on a month tab, a
    roll-up tab and a dated snapshot - never about two IDENTICAL rows inside the SAME tab.
    Measured, 19 Sep 2026 (R5, prod CB1178A-SS-NEW / SO324265): the order holds two lines of
    qty 25 on the same delivery date (two unit types), and the sheet states that delivery
    TWICE inside one tab, then twice again on the roll-up. Reading `_restates`' key alone
    per row, as `_plan` used to, collapsed all four into ONE instruction and raised only one
    of the two lines; book-wide, 517 keys are stated more than once inside a single tab, 650
    deliveries are dropped as restatements, across 90 sales orders.

    A restatement is only ever ACROSS tabs. Inside one tab, the n-th row carrying a given key
    is its own instruction, distinct from every other row that shares the key on that SAME
    tab; on a LATER tab, the n-th row carrying that key restates the n-th instruction (first
    tab's first occurrence, second tab's first occurrence, and so on by position) rather than
    every occurrence on the later tab piling onto the first. The number of instructions a key
    holds is therefore the MAX count that key reaches on any single tab, not the count summed
    across every tab in the file. `_plan` keeps this by pairing `_restates`' key with the
    row's own `sheet` in a per-(sheet, key) counter, so two identical rows in one tab are two
    instructions and a later tab's own identical rows restate them positionally.
    """
    return (
        (row.so_number or "").strip(),
        (row.item_code or "").strip(),
        _dec(row.qty),
        row.delivery_date,
        (row.location or "").strip().upper(),
    )


def _members(row, line_codes: set) -> list:
    """One sheet row, or one row per product a `+` cell names (plan section 1).

    Measured on the customer's own monthly book, 15 Sep 2026 (PLAN section 0): 173 of
    16,060 sheet rows join several product codes with `+` in one ITEM CODE cell - a set the
    customer always sells together, written as one row though AutoCount holds it as
    SEPARATE lines, one per member, each at the cell's own quantity. Splitting is the only
    way those rows ever raise.

    A cell that IS a line's own product code is never split - four real codes on the book
    contain `+` themselves (`FUR-GA30T+A66C`, `FUR-GA905T+A908C`, `FUR-GA3131T+A58C`,
    `P69190C-ENG + D969-ENG`), so `line_codes` is checked BEFORE the `+` is ever looked at.
    An order this row's number does not name passes an empty `line_codes` here (no line can
    possibly hold the cell whole), so the cell still splits - the count in `line_not_found`
    is what the operator reads either way.

    Split on `+` only, whitespace either side optional. An empty member from a stray
    leading, trailing or doubled `+` is dropped silently - no `""` item_code ever reaches
    the match loop or the result.

    A cell naming the SAME code twice (`X + X`) is one statement, not two: de-duplicated,
    order kept (`dict.fromkeys`), or the two members would share `row.sheet` and every
    `_restates` term, and R5 (19 Sep 2026: a restatement is only ever across tabs) would read
    them as two separate instructions inside the one cell that stated only one.
    """
    item_code = (row.item_code or "").strip()
    if "+" not in item_code or item_code in line_codes:
        return [row]
    members = (m.strip() for m in re.split(r"\s*\+\s*", item_code))
    return [
        replace(row, item_code=member)
        for member in dict.fromkeys(m for m in members if m)
    ]


def _unambiguous_refs(db: Session, refs: set) -> set:
    """Of these `sales_order_lines.source_ref` values, the ones that name exactly ONE line.

    `source_ref` is not unique. The August extract wrote bare ordinals, so `'1'` sits on
    3,364 lines across 3,364 different sales orders, and 25,771 lines on the prod copy share
    a ref with another line. A ref that names 3,364 lines is not a statement about any of
    them: it must neither pair a document to a line (`_ref_targets`) nor tell the line pick
    that the book bought for one (`_bought_refs`), where it would mark thousands of unrelated
    lines, cancelled August ghosts among them, as the line a document names.

    One query. Company scope applies, which is the right unit: the pairing it guards is
    company-scoped too.
    """
    wanted = sorted({str(ref).strip() for ref in refs if str(ref or "").strip()})
    if not wanted:
        return set()
    return {
        str(ref)
        for (ref,) in db.query(SalesOrderLine.source_ref)
        .filter(SalesOrderLine.source_ref.in_(wanted))
        .group_by(SalesOrderLine.source_ref)
        .having(func.count(SalesOrderLine.id) == 1)
    }


def _rank_for(row, bought: set) -> Callable[[tuple], tuple]:
    """The line this row means, when several fit (D1, AC-S1-8, as section 8 leaves it).

    Read by two of the five passes the line pick now runs (`_match_in_passes`,
    `PLAN-oi-sheet-line-pick-month-po.md` section 2): pass 1, exact date, where every term
    below the first is moot because the candidates already share the row's own date; and
    pass 5, the fallback, over every line of the order once passes 1 to 4 have placed what
    they can - which is the only place the "date matches no line" and "book bought for it"
    stories below still happen. Passes 2, 3 and 4 read their OWN rank instead
    (`_rank_for_month`, `_rank_for_po`, just below `_match_row`): the month passes need the
    NEAREST date ahead of "earliest", since every candidate there already shares the row's
    month, and carry no citation term of their own any more (review round 2, 19 Sep 2026:
    pass 2's own narrow already guarantees every candidate it sees cites the row, and pass 4
    can never still tie on one either, since pass 3 already tried every candidate that
    could). The PO pass needs no date term at all, since `_narrow_sheet_po` already means
    every candidate it sees is one the row itself cites. There is no plain "same month, no
    citation to break the tie" pass left for this function to rank any more either: R4
    (19 Sep 2026, prod C-FH14, SO324265) split the old single month pass into pass 2 (month
    AND the sheet's own citation) and pass 4 (month alone, after the PO pass), precisely so
    a row's citation always outranks the month rather than losing a tie inside it.

    A real line before a cancelled one, first of all - 10,499 cancelled August-extract ghosts
    are still in the book, and a ghost is never what a live sheet row means while a real line
    fits. This term only ever has anything to rank in pass 5, the fallback (R7, 19 Sep 2026):
    `_run_pass` now drops a cancelled candidate before pass 1 ever reaches this function, so a
    ghost that happens to carry the row's own exact date no longer wins on that account -
    only the fallback, where every line of the order is still offered, can still hand a row a
    cancelled one, and only when it is the only line that fits (D1 kept).

    Then the line whose required date IS the sheet's date. The sheet states a delivery, and a
    line carrying that very date is the delivery it states - section 7 had put "the book
    bought for it" above this, and on SO388822 / C-FHSS12 that cascaded a whole sales order:
    the 31/03 row took the 14/04 line because somebody had bought for it, the 14/04 row found
    it occupied and slid to 28/04, every later row slid one delivery, and the last pair landed
    on the 1414 @ 01/01/2030 balance line. Whole sheet, 1,180 rows sat on a line whose date
    was not the sheet's while a same-item sibling carrying it stood free. An ORDER BACK row
    states NO date, and a row with no date has nothing to match: without the `wanted is not
    None` guard `None == None` would read as an exact match and hand the row to an undated
    line over the one the book bought for. The undated-last term below still applies.

    Then a line the book BOUGHT for (section 7, unchanged in meaning and one place lower):
    where NO line carries the sheet's date the term above ties, and "the line the row means is
    the one AutoCount bought for" is still the best answer left. SO395635 / SRTWC8317-RL's
    November row is that case - its date matches no line, and it lands on the bought one.

    Then the terms that were always here: an open line before a closed one, the earliest
    required date (undated last), and the oldest line, so two runs of the same sheet land the
    same way.

    The line's own id has the last word. Every term above it can tie - a whole AutoCount
    ingest shares one `created_at`, because Postgres freezes `now()` for the transaction that
    wrote it - and a tie left to the read order is a sheet that pairs differently on the
    preview and on the apply.
    """
    wanted = row.delivery_date

    def key(candidate: tuple) -> tuple:
        line = candidate[0]
        ref = (line.source_ref or "").strip()
        return (
            0 if (line.line_status or "open") != "cancelled" else 1,
            0 if (wanted is not None and line.required_date == wanted) else 1,
            0 if (ref and (ref, str(line.product_id or "")) in bought) else 1,
            0 if (line.line_status or "open") == "open" else 1,
            line.required_date is None,
            line.required_date or date.min,
            line.created_at or datetime.min,
            str(line.id),
        )

    return key


def _match_row(
    row,
    candidates: List[tuple],
    taken: Dict[str, Decimal],
    *,
    rank: Callable[[tuple], tuple],
) -> Tuple[Optional[tuple], Optional[str]]:
    """The line for one sheet row, against `candidates` exactly as given, or the FIRST filter
    that refused it. `candidates` and `rank` are the caller's to narrow: `_run_pass`, the only
    caller, hands over a NARROWED list and the pass's own rank for passes 1 to 4 of the
    five-pass line pick (PLAN section 2), and every line of the order, unnarrowed, with
    `_rank_for(row, plan.bought_refs)` built fresh, for pass 5, the fallback.

    Item, then location, then quantity - reported in that order because that is the order a
    person checks them in, and "no line for this item" and "location differs" send them to
    two different places.

    The quantity test is against what the line ORDERED, less what EARLIER rows of this same
    file already took of it: the sheet may split one line across several rows (AC-S1-2), and
    the importer never splits one itself.

    The ledger is charged for whatever line a row lands on, ALREADY RAISED or not - reversing
    review finding 9 (14 Sep) on purpose (PLAN section 2, "Ledger"). Finding 9 had this skip
    the charge on an already-raised line so the NEXT row of the same file would not read
    `qty_exceeds_ordered` for quantity nobody used, but the five-pass pick runs the identical
    ledger on a fresh upload and on every re-upload of the same file (a line raised by an
    EARLIER run is "already raised" on both), so a charge that only happens sometimes is a
    charge that lets the two runs place a later row on two different lines (AC-LP-11,
    AC-LP-13). Charging always keeps them in step; the only new `qty_exceeds_ordered` this can
    produce is a sheet that states more against a line than the order actually holds, which is
    a true report (AC-LP-12).
    """
    wanted_item = (row.item_code or "").strip()
    same_item = [c for c in candidates if c[1] == wanted_item]
    if not same_item:
        return None, oc.NO_LINE_FOR_ITEM

    location = (row.location or "").strip().upper()
    if len(location) > _MAX_LOCATION:
        return None, oc.LOCATION_DIFFERS
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

    found = sorted(fits, key=rank)[0]
    taken[str(found[0].id)] = taken.get(str(found[0].id), _ZERO) + qty
    return found, None


# --------------------------------------------------------------------------- #
# the five-pass line pick: exact date, month and PO, PO, month, fallback      #
# --------------------------------------------------------------------------- #


def _document_key(number: Any) -> str:
    """A document number, stripped and upper-cased, so the book's own numbers and whatever
    case the sheet's remark cell happened to be typed in still compare equal (PLAN section 2,
    "Book PO per line")."""
    return str(number or "").strip().upper()


def _bought_documents(
    db: Session, rows: Tuple[Sequence[Any], Sequence[Any]]
) -> Dict[tuple, set]:
    """`(source_ref, product_id)` -> the document NUMBERS the book bought it with, off the
    SAME rows `_bought_refs` already read (`plan.bought_rows` from `_bought_rows`):
    `SPOAllocation.spo_number` directly; a `PurchaseOrderLine` through the `po_number` of its
    own `purchase_order_id`, in one extra query over the purchase orders those lines actually
    named - never more ids than `_bought_rows` itself already saw.

    Wider than the line pick will ever ask of it, exactly like `_bought_refs`: a key nothing
    looks up costs nothing.
    """
    allocations, po_lines = rows
    held: Dict[tuple, set] = {}

    def _add(ref: Any, product_id: Any, number: Any) -> None:
        # Stripped so a `from_so_line_ref` with stray whitespace still keys the same as the
        # reader's own `(line.source_ref or "").strip()` (`_narrow_sheet_po`) - a mismatch
        # here would silently drop the candidate from the month-and-PO and PO passes rather
        # than raise.
        ref = str(ref or "").strip()
        if not ref or not number:
            return
        held.setdefault((ref, str(product_id or "")), set()).add(_document_key(number))

    for allocation in allocations:
        _add(allocation.from_so_line_ref, allocation.product_id, allocation.spo_number)

    po_ids = sorted({
        str(line.purchase_order_id) for line in po_lines if line.purchase_order_id
    })
    numbers_by_po: Dict[str, str] = {}
    if po_ids:
        numbers_by_po = {
            str(po_id): number
            for po_id, number in db.query(PurchaseOrder.id, PurchaseOrder.po_number)
            .filter(PurchaseOrder.id.in_(po_ids))
            .all()
        }
    for line in po_lines:
        _add(
            line.from_so_line_ref,
            line.product_id,
            numbers_by_po.get(str(line.purchase_order_id or "")),
        )
    return held


def _narrow_exact_date(row) -> Callable[[tuple], bool]:
    """Pass 1: keep only candidates whose `required_date` IS the row's own delivery date.
    `wanted is not None` keeps an ORDER BACK row, which states no date at all, out of this
    pass entirely (AC-LP-9) - every candidate answers `False` for it, so `_run_pass` finds no
    candidates and moves the row on without a reason."""
    wanted = row.delivery_date

    def keep(candidate: tuple) -> bool:
        return wanted is not None and candidate[0].required_date == wanted

    return keep


def _narrow_same_month(row) -> Callable[[tuple], bool]:
    """Keep candidates in the row's own year and month, whatever the day. Read alone by
    pass 4 (a row whose citation named no free line, or named nothing at all, still gets the
    month's own terms before the blanket fallback) and, composed with `_narrow_sheet_po`
    (`_narrow_month_and_po`), by pass 2. The same `wanted is not None` guard keeps an ORDER
    BACK row out of both (AC-LP-9)."""
    wanted = row.delivery_date

    def keep(candidate: tuple) -> bool:
        required = candidate[0].required_date
        return (
            wanted is not None
            and required is not None
            and (required.year, required.month) == (wanted.year, wanted.month)
        )

    return keep


def _narrow_sheet_po(row, documents: Dict[tuple, set]) -> Callable[[tuple], bool]:
    """Keep candidates whose OWN book document (`_bought_documents`) is one the row itself
    cites (R2, 19 Sep 2026: the sheet's PO may pick the line). Read alone by pass 3, and
    composed with `_narrow_same_month` (`_narrow_month_and_po`) by pass 2. A row that cites
    nothing keeps no candidate at all in either shape - which is exactly what sends it on to
    the next pass rather than reporting a reason here (AC-LP-6)."""
    cited = {_document_key(number) for number in row.po_numbers}

    def keep(candidate: tuple) -> bool:
        if not cited:
            return False
        line = candidate[0]
        ref = (line.source_ref or "").strip()
        if not ref:
            return False
        held = documents.get((ref, str(line.product_id or "")))
        return bool(held and held & cited)

    return keep


def _narrow_month_and_po(row, documents: Dict[tuple, set]) -> Callable[[tuple], bool]:
    """Pass 2's own narrow (R4, 19 Sep 2026, prod C-FH14, SO324265): a candidate must clear
    BOTH `_narrow_same_month` and `_narrow_sheet_po`, composed rather than duplicated, so a
    row only lands here when the month and its own citation agree. On C-FH14 the sheet's
    04-01 row cited PO B while the only line in its month books PO A: under the old single
    month pass that line still ranked first (nothing else in the month outranked it), which
    stole it from the row that actually cited A and cascaded every later row onto the wrong
    line. Splitting the narrow in two lets pass 3 (the citation alone) catch a row like this
    one BEFORE pass 4, the plain month test the single pass used to be, ever gets a chance to
    rank the wrong line back in for it."""
    same_month = _narrow_same_month(row)
    same_po = _narrow_sheet_po(row, documents)

    def keep(candidate: tuple) -> bool:
        return same_month(candidate) and same_po(candidate)

    return keep


def _rank_for_month(row) -> Callable[[tuple], tuple]:
    """Passes 2 and 4's own tie-break (AC-LP-4): live before cancelled, then the NEAREST
    date rather than the earliest - every candidate here already shares the row's month, so
    "earliest" would only ever prefer the first of the month - then the terms `_rank_for`
    always closes a tie on.

    The live-before-cancelled term never actually has a cancelled candidate to rank against
    any more (R7, 19 Sep 2026): both passes are narrowed (`narrow is not None`), so
    `_run_pass` has already dropped every cancelled line before either ever reaches this
    function. Kept rather than removed - a defensive term costs nothing and the passes'
    own narrow, not this rank, is what R7 actually leans on.

    NO citation term (review round 2, 19 Sep 2026 - dropped, 106 tests stayed green): pass
    2's own narrow (`_narrow_month_and_po`) already means every candidate it sees cites the
    row, so the term would only ever tie there; pass 4's candidates are a SUPERSET of pass
    2's, over the SAME ledger, which only ever GROWS between them, so any candidate that
    could still satisfy the row's citation was already offered to this row in pass 2 - a
    candidate reaching pass 4 that still ties on citation here can never exist."""
    wanted = row.delivery_date

    def key(candidate: tuple) -> tuple:
        line = candidate[0]
        required = line.required_date
        # Unreachable in practice: `_narrow_same_month` only ever lets a candidate through
        # once both dates are known, so the distance below always has two real dates to
        # compare. Kept defensive rather than assumed.
        distance = abs((required - wanted).days) if required and wanted else 10**6
        return (
            0 if (line.line_status or "open") != "cancelled" else 1,
            distance,
            0 if (line.line_status or "open") == "open" else 1,
            required is None,
            required or date.min,
            line.created_at or datetime.min,
            str(line.id),
        )

    return key


def _rank_for_po(candidate: tuple) -> tuple:
    """Pass 3's own tie-break (AC-LP-5): live before cancelled, open before closed, the
    earliest required date, the oldest line, the id - `_narrow_sheet_po` already decided
    WHICH candidates reached this pass, so nothing about the row itself is read here.

    Pass 3 is narrowed too, so the live-before-cancelled term here is likewise moot in
    practice (R7, 19 Sep 2026): `_run_pass` never hands this function a cancelled
    candidate. Kept for the same reason `_rank_for_month`'s does."""
    line = candidate[0]
    return (
        0 if (line.line_status or "open") != "cancelled" else 1,
        0 if (line.line_status or "open") == "open" else 1,
        line.required_date is None,
        line.required_date or date.min,
        line.created_at or datetime.min,
        str(line.id),
    )


def _run_pass(
    matches: List[_Match],
    plan: _Plan,
    lines: Dict[str, List[tuple]],
    taken: Dict[str, Decimal],
    raised_already: set,
    *,
    narrow: Optional[Callable[[Any], Callable[[tuple], bool]]],
    rank: Callable[[Any], Callable[[tuple], tuple]],
    order: Sequence[_Match],
) -> List[_Match]:
    """Attempt every match in `order`, against candidates `narrow` allows - every line of
    the row's own order, unnarrowed, when `narrow` is `None` (pass 5, the fallback). A match
    this places is mutated in place (`core_line`, `line_location`, `already_raised`); a
    REASON is kept only for the fallback's own final step, because a narrowed attempt that
    finds nothing has said nothing about the row - the fallback's own unnarrowed read is the
    first filter that actually refused it (PLAN section 2).

    TWO steps over the same `order`, in every pass including the fallback (R6, 19 Sep 2026,
    prod CB2805A-DIY / SO324265): first with candidates further narrowed to a line whose
    `qty_ordered` EQUALS the row's own quantity, then - for whatever is still unplaced - with
    the pass's ordinary candidates, unnarrowed by quantity, exactly as before. Today's single
    step carries no quantity term at all, so a sheet row for the SMALLER of two same-date
    lines could take the BIGGER one on nothing but a created-at tie-break, leaving the
    bigger row's own line too small or already spent - CB2805A-DIY's own 150-line and
    230-line, on the SAME date, landed exactly that way; book-wide, 490 rows across 97 sales
    orders land differently once the equal-quantity line is tried first. A row that splits a
    line (its own quantity smaller than every candidate, AC-S1-2) never matches the first
    step and is unaffected, landing in the second exactly as it does today.

    A CANCELLED line may only be taken by the fallback (R7, 19 Sep 2026, prod comparison
    workbook): dropped from `candidates` before either step of a narrowed pass (`narrow is
    not None`) ever runs, not merely ranked last inside them. The August-extract ghosts
    carry their line's ORIGINAL delivery date, so a ghost was routinely the only exact-date
    candidate a row had, and won pass 1 outright before a live line elsewhere in the order -
    one the row's own citation named - was ever offered in a later pass (measured,
    18 Sep prod copy, SO324265 / CB2807-DIY read off the owner's comparison workbook: rows
    sitting on a cancelled line fell 1,028 to 299; 817 rows moved line, 736 of them off a
    cancelled line onto a live one; the net landed-row count held at 9,307 and
    `qty_exceeds_ordered` at 572, but the SET underneath is not the same one - 30 rows that
    used to land lost their line and 30 others gained one, an accepted cost of running each
    row through one narrowed pass at a time rather than a global best assignment (PLAN
    section 5, "Trigger for more machinery")). The equal step still never offers a cancelled
    line either (review round 2, 19 Sep 2026, blocker 2), but that term now only ever bites
    in the fallback, since a narrowed pass has nothing cancelled left to filter by the time
    it gets there - a lone cancelled line still matches through the fallback's second step,
    exactly as it always has (D1 kept).

    An EMPTY candidate list skips only a NARROWED attempt (review round 2, blocker 1): the
    equal step is narrowed by definition, and a genuinely narrowed pass finding nothing has
    said nothing about the row either - but the fallback's own final, UNNARROWED step must
    still reach `_match_row` even against an empty list, or an order with no lines at all
    (44 such project-class orders on the 18 Sep prod copy; a line whose product is gone
    falls out of `_lines_of`'s own inner join the same way) leaves `match.reason` `None`
    forever, and `apply` unconditionally calls `raiser.raise_row`, which dereferences
    `match.core_line.id` on a match nothing ever set: an AttributeError that rolls back the
    whole upload, where the row should simply read `no_line_for_item`.

    Returns the matches from `matches` still unplaced, in `matches`' OWN order - `order` may
    attempt them in a different sequence (pass 3, AC-LP-5) without disturbing the file order
    the later passes, and the final reason, rely on.
    """

    def _attempt(
        attempt_order: Sequence[_Match], *, equal_qty_only: bool, may_set_reason: bool,
    ) -> set:
        placed_ids: set = set()
        for match in attempt_order:
            row = match.row
            candidates = lines.get(str(plan.orders[row.so_number].id)) or []
            if narrow is not None:
                # R7 (19 Sep 2026, prod comparison workbook): a cancelled line may only be
                # taken by the fallback (`narrow is None`). Dropped before the pass's own
                # narrow runs, so a cancelled line that happens to be the only exact-date
                # or same-month candidate never wins passes 1 to 4 on that account alone -
                # it is invisible to them, not merely ranked last inside them.
                candidates = [
                    c for c in candidates if (c[0].line_status or "open") != "cancelled"
                ]
                keep = narrow(row)
                candidates = [c for c in candidates if keep(c)]
            if equal_qty_only:
                # The `cancelled` term here now only ever bites in the fallback
                # (`narrow is None`): a narrowed pass has already dropped every cancelled
                # candidate above (R7), so this is a no-op there and kept only because
                # duplicating the branch on `narrow` to skip it would cost more than it
                # saves.
                wanted = _dec(row.qty)
                candidates = [
                    c for c in candidates
                    if _dec(c[0].qty_ordered) == wanted
                    and (c[0].line_status or "open") != "cancelled"
                ]
            if (narrow is not None or equal_qty_only) and not candidates:
                continue
            found, reason = _match_row(row, candidates, taken, rank=rank(row))
            if found is not None:
                match.core_line, match.line_location = found[0], found[2] or None
                match.already_raised = str(found[0].id) in raised_already
                placed_ids.add(id(match))
            elif may_set_reason:
                match.reason = reason
        return placed_ids

    placed = _attempt(order, equal_qty_only=True, may_set_reason=False)
    still_pending = [m for m in order if id(m) not in placed]
    placed |= _attempt(still_pending, equal_qty_only=False, may_set_reason=narrow is None)
    return [m for m in matches if id(m) not in placed]


def _match_in_passes(
    plan: _Plan,
    lines: Dict[str, List[tuple]],
    taken: Dict[str, Decimal],
    raised_already: set,
    pending: List[_Match],
) -> None:
    """The five passes (PLAN-oi-sheet-line-pick-month-po.md section 2, owner rulings R1 to
    R7, 19 Sep 2026): exact date; same month AND the sheet's own citation agreeing; the
    sheet's own citation alone; same month alone; then today's fallback rank - over the ONE
    `taken` ledger the caller built, so a row placed in an earlier pass takes no further
    part in a later one. Every one of the five runs its OWN candidate whose `qty_ordered`
    equals the row's quantity before it ever falls back to its ordinary rank (R6, prod
    CB2805A-DIY / SO324265: see `_run_pass`, which is the one seam all five passes share).
    The first four never offer a CANCELLED candidate at all (R7: see `_run_pass`) - only
    the fifth, the fallback, may still take one.

    R4 (prod C-FH14, SO324265): the sheet's own citation outranks the month when they
    disagree. Under the old single month pass, a row whose citation named a DIFFERENT
    purchase order than the only line in its month could still steal that line from a row
    whose citation actually named it, because nothing in that pass's own rank read the
    citation ahead of the month itself; splitting it into "month AND citation" (pass 2,
    ahead of the citation-alone pass) and "month alone" (pass 4, behind it) means a row only
    ever wins a month-mate's line on citation grounds when its OWN citation is the one that
    line's book document actually names.

    Passes 1, 2, 4 and 5 attempt `pending` in FILE order, exactly as before. Pass 3 (the
    citation alone) attempts its own leftovers by the row's OWN delivery date instead
    (AC-LP-5, the earliest row to the earliest free line), undated rows last, ties broken by
    file order - but it still RETURNS what is left in `pending`'s own order, so passes 4 and
    5 read FILE order too.
    """
    remaining = _run_pass(
        pending, plan, lines, taken, raised_already,
        narrow=_narrow_exact_date,
        rank=lambda row: _rank_for(row, plan.bought_refs),
        order=pending,
    )
    remaining = _run_pass(
        remaining, plan, lines, taken, raised_already,
        narrow=lambda row: _narrow_month_and_po(row, plan.bought_documents),
        rank=_rank_for_month,
        order=remaining,
    )
    po_order = [
        match
        for _, match in sorted(
            enumerate(remaining),
            key=lambda pair: (
                pair[1].row.delivery_date is None,
                pair[1].row.delivery_date or date.max,
                pair[0],
            ),
        )
    ]
    remaining = _run_pass(
        remaining, plan, lines, taken, raised_already,
        narrow=lambda row: _narrow_sheet_po(row, plan.bought_documents),
        rank=lambda row: _rank_for_po,
        order=po_order,
    )
    remaining = _run_pass(
        remaining, plan, lines, taken, raised_already,
        narrow=_narrow_same_month,
        rank=_rank_for_month,
        order=remaining,
    )
    _run_pass(
        remaining, plan, lines, taken, raised_already,
        narrow=None,
        rank=lambda row: _rank_for(row, plan.bought_refs),
        order=remaining,
    )


def _already_raised(
    db: Session, core_lines: Sequence[SalesOrderLine]
) -> Tuple[set, Dict[str, str], Dict[str, List[Any]]]:
    """The core lines whose MIRROR already carries a non-cancelled ORDER / ORDER BACK row
    (D2, R7 as of 20 Sep 2026), the core-line-id -> mirror-id map that answer was read off
    (S3, 19 Sep 2026): `_resolve_delivery_date_repairs` needs the same map and must not
    re-query it, and the mirror-id -> its own LIVE rows map (every verb, not only ORDER /
    ORDER BACK) `_resolve_recovery_matches` (2.1(a), R8) reads its used-row and top-up
    candidates off - the SAME query, extended to keep the full rows rather than only
    `so_line_id`, so the recovery rule costs no second pass over this table (plan section
    3.1: "one query for the whole plan, not one per row").

    R7, 20 Sep 2026: a NOTICE row (DELAY and the other non-buy verbs) never stands for the
    line's own row - only a live ORDER or ORDER BACK row counts as "already raised", the
    same two verbs `_settle_row_in_place` settles. `rows_by_mirror` still carries the
    notice row (2.1(b)'s settle path reads nothing off it, but `_resolve_recovery_matches`
    must never mistake its ABSENCE from `raised` for its absence from the mirror).

    Read off the state BEFORE this upload, once, and for every line the named orders carry
    rather than only the matched ones, because the matcher consults it as it goes: the
    answer decides whether a matched line's quantity is charged to this file's ledger.

    Two rows of the same file may still both land on one line - nothing here changes as the
    file is read - while a re-upload of that file raises nothing new.
    """
    from app.models.project_so import (
        INQUIRY_CANCELLED,
        IV_ORDER,
        IV_ORDER_BACK,
        OrderInquiryRow,
        ProjectSalesOrderLine,
    )

    if not core_lines:
        return set(), {}, {}
    core_ids = [str(line.id) for line in core_lines]
    mirrors = (
        db.query(ProjectSalesOrderLine.id, ProjectSalesOrderLine.core_sales_order_line_id)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(core_ids))
        .all()
    )
    if not mirrors:
        return set(), {}, {}
    core_by_mirror = {str(mirror_id): str(core_id) for mirror_id, core_id in mirrors}
    mirror_by_core = {core_id: mirror_id for mirror_id, core_id in core_by_mirror.items()}
    held = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id.in_(list(core_by_mirror)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    raised = {
        core_by_mirror[str(row.so_line_id)]
        for row in held
        if str(row.so_line_id) in core_by_mirror
        and row.verb in (IV_ORDER, IV_ORDER_BACK)
    }
    rows_by_mirror: Dict[str, List[Any]] = {}
    for row in held:
        rows_by_mirror.setdefault(str(row.so_line_id), []).append(row)
    return raised, mirror_by_core, rows_by_mirror


def _used_row_candidate(
    mirror_rows: Sequence[Any], row: Any, claimed: set
) -> Tuple[Optional[Any], bool]:
    """AC-RB-1/AC-RB-2 (R6): the LIVE `Replaces N used` sibling this sheet row is raised
    AS, or `(None, report)` when nothing exact fits.

    A candidate is a live row with no used pair of its own yet (`redirected_to_pool` is
    false, `previous_qty` / `previous_delivery_date` set, note starting `"Replaces "` - the
    exact shape `project_order_inquiry_service.py` ~1104-1185 writes for a replan that
    redirected a received line). The note prefix matters: 2.1(b)'s own settle also sets
    `previous_qty` / `previous_delivery_date` on a row that is NOT a used-row candidate at
    all (AC-RB-16), and without it a second upload would mistake a settled row for one and
    raise a spurious used row beside it. An EXACT quantity AND date match against its own
    previous figures wins it (never a quantity-only guess: AC-RB-2's own CB2807-DIY shape
    carries two candidates of the SAME quantity, told apart only by date) - unless a used
    row already sits at that exact quantity and date (AC-RB-4, a second upload of the same
    book: silently left alone, not reported) or another sheet row already claimed it
    earlier in this same pass.

    `report` is true only when this mirror carries a used-row candidate SHAPE at all but
    none of them fits this row exactly (AC-RB-3): a plain live row (AC-RB-15) reports
    nothing here, because it is not this rule's business at all.
    """
    sheet_qty = _dec(row.qty)
    fresh_rows = [
        r
        for r in mirror_rows
        if not r.redirected_to_pool
        and r.previous_qty is not None
        and r.previous_delivery_date is not None
        and (r.note or "").startswith("Replaces ")
    ]
    if not fresh_rows:
        return None, False
    for candidate in fresh_rows:
        if str(candidate.id) in claimed:
            continue
        if _dec(candidate.previous_qty) != sheet_qty:
            continue
        if candidate.previous_delivery_date != row.delivery_date:
            continue
        already_used = any(
            other.redirected_to_pool
            and _dec(other.qty) == sheet_qty
            and other.delivery_date == row.delivery_date
            for other in mirror_rows
        )
        if already_used:
            return None, False
        return candidate, False
    return None, True


def _top_up_status(
    mirror_rows: Sequence[Any], row: Any, decision: Any, snapshot: dict
) -> Optional[bool]:
    """R8 (AC-RB-26/27/28), the SRTWC8605-SC-RL shape: this mirror's live ORDER / ORDER
    BACK rows are a TOP-UP of the ACTIVE decision for the line.

    `True` when every live ORDER / ORDER BACK row carries THIS decision's own id and the
    sheet row's quantity plus theirs equals the decision's `buy_qty` (AC-RB-26: raise the
    sheet row plain). `False` when they all carry it but the sum does not match (AC-RB-27:
    raise nothing, report). `None` when the shape does not even apply - any live ORDER /
    ORDER BACK row that carries NO decision id, or one from a DIFFERENT (stale or
    superseded) revision (AC-RB-28): the ordinary `already_raised` skip stands, unreported.

    Only ever called once `_used_row_candidate` has already said this mirror carries no
    `Replaces N used` shape at all - a fresh row that DOES carry this decision's id (the
    writer sets one, `project_order_inquiry_service.py` ~1104-1185) is a 2.1(a) candidate
    first, never a top-up row, so R6's exact match always gets first refusal.
    """
    from app.models.project_so import IV_ORDER, IV_ORDER_BACK

    order_rows = [r for r in mirror_rows if r.verb in (IV_ORDER, IV_ORDER_BACK)]
    if not order_rows:
        return None
    if any(str(r.supply_decision_id) != str(decision.id) for r in order_rows):
        return None
    buy_qty = _dec(snapshot.get("buy_qty"))
    total = _dec(row.qty) + sum((_dec(r.qty) for r in order_rows), _ZERO)
    return total == buy_qty


def _active_decision_snapshots(
    db: Session, order_ids: set
) -> Dict[str, Tuple[Any, dict]]:
    """2.1(b): every mirror line's ACTIVE `so_supply_decisions` snapshot, for whichever of
    these CORE sales orders even carry one - one pass over the whole plan
    (`ProjectSupplyService.active_decision`'s own filter, restated here as a plan-wide read
    since the importer has no request-scoped service to call it on), never one query per
    row.
    """
    from app.models.project_so import DECISION_ACTIVE, ProjectSalesOrder, SOSupplyDecision

    if not order_ids:
        return {}
    psos = (
        db.query(ProjectSalesOrder.id)
        .filter(ProjectSalesOrder.so_id.in_(sorted(str(i) for i in order_ids)))
        .all()
    )
    if not psos:
        return {}
    pso_ids = [str(pso_id) for (pso_id,) in psos]
    decisions = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id.in_(pso_ids),
            SOSupplyDecision.state == DECISION_ACTIVE,
        )
        .all()
    )
    out: Dict[str, Tuple[Any, dict]] = {}
    for decision in decisions:
        for snapshot in decision.line_snapshots or []:
            mirror_id = snapshot.get("project_line_id")
            if mirror_id:
                out[str(mirror_id)] = (decision, snapshot)
    return out


def _snapshot_date(value: Optional[str]) -> Optional[date]:
    """`line_snapshots` freezes a date as its own ISO string (S3.1)."""
    return date.fromisoformat(value) if value else None


def _resolve_recovery_matches(
    db: Session, plan: _Plan, rows_by_mirror: Dict[str, List[Any]]
) -> None:
    """2.1(a), 2.1(b) and R8 (`PLAN-oi-rollback-recover-planning-rows.md`): decide, for
    every matched row, whether it is recovering a planning trait rather than being skipped
    (already raised) or raised plain - read here, before `_pair` and
    `_matched_lines_by_order` decide what this run links and adopts, since both key off
    `match.raisable` / `match.already_raised`.
    """
    order_ids = {str(order.id) for order in plan.orders.values()}
    decision_snapshots = _active_decision_snapshots(db, order_ids)
    claimed: set = set()
    for match in plan.matches:
        if match.core_line is None or match.duplicate or match.code or match.reason:
            continue
        mirror_id = plan.mirror_by_core_line.get(str(match.core_line.id))
        if mirror_id is None:
            continue
        if match.already_raised:
            candidate, report = _used_row_candidate(
                rows_by_mirror.get(mirror_id, []), match.row, claimed
            )
            if candidate is not None:
                match.already_raised = False
                match.used_sibling_id = str(candidate.id)
                claimed.add(str(candidate.id))
            elif report:
                match.no_used_delivery_match = True
            else:
                # R8: no `Replaces N used` shape at all on this mirror - try the top-up
                # shape before leaving the ordinary `already_raised` skip to stand.
                decision, snapshot = decision_snapshots.get(mirror_id, (None, None))
                if decision is not None:
                    status = _top_up_status(
                        rows_by_mirror.get(mirror_id, []), match.row, decision, snapshot
                    )
                    if status is True:
                        match.already_raised = False
                    elif status is False:
                        match.top_up_sum_mismatch = True
                    # `status is None`: AC-RB-28, the plain `already_raised` skip stands.
            continue
        decision, snapshot = decision_snapshots.get(mirror_id, (None, None))
        if decision is None:
            continue
        buy_qty = _dec(snapshot.get("buy_qty"))
        if buy_qty <= _ZERO:
            # R4: all from stock for this line - the sheet row is raised plain, not settled.
            continue
        required_date = _snapshot_date(snapshot.get("required_date"))
        if buy_qty == _dec(match.row.qty) and required_date == match.row.delivery_date:
            # AC-RB-12: the decision agrees with the sheet - nothing to restate.
            continue
        match.settle_decision_id = decision.id
        match.settle_buy_qty = buy_qty
        match.settle_required_date = required_date


def _resolve_line_repairs(
    dated_rows: Sequence[Tuple[int, Any]], migrated_rows: Sequence[Any]
) -> Tuple[Dict[int, str], set]:
    """B1, 19 Sep 2026: which migrated row (if any) each dated sheet row of ONE already-
    raised line would repair, and which rows pass 1 settled as an exact no-op (N10, round 4
    review: returned rather than re-derived by `_resolve_shape_b_repairs`). Pure and
    deterministic - no database access - so the same inputs always resolve the same way.

    A migrated row's own item code and quantity is not a unique key: a sheet that splits
    one line's quantity across several dated rows (100 @ 2026-09-01 + 100 @ 2026-10-01, one
    line) leaves several migrated rows sharing both (116 `(mirror, item, qty)` groups /
    233 migrated rows on the 15 Sep prod copy alone). Resolving row-by-row with no ordering
    let an unchanged re-upload overwrite September's row with October's date and flip the
    pair back on every further run, converging on nothing.

    Two passes fix that, both reading `migrated_rows` in the SAME fixed order
    (`created_at`, `id` - the caller's job) and `dated_rows` in file order:

    * **Pass 1** lets a sheet row claim, as a no-op, a migrated row that ALREADY carries its
      exact item, quantity AND date - settling every row a re-upload of an unchanged sheet
      would otherwise fight over before pass 2 ever runs.
    * **Pass 2** lets each sheet row pass 1 left unsettled claim the first STILL-unclaimed
      migrated row with the same item and quantity (whatever its date) and repair it.

    A migrated row is claimed at most once per run, by at most one sheet row, so two
    same-qty rows can never both point at the row pass 1 or 2 already gave to the other.
    """
    unclaimed = list(migrated_rows)
    settled: set = set()

    for index, row in dated_rows:
        qty = _dec(row.qty)
        for candidate in unclaimed:
            if (
                candidate.item_code == row.item_code
                and _dec(candidate.qty) == qty
                and candidate.delivery_date == row.delivery_date
            ):
                unclaimed.remove(candidate)
                settled.add(index)
                break

    repairs: Dict[int, str] = {}
    for index, row in dated_rows:
        if index in settled:
            continue
        qty = _dec(row.qty)
        for candidate in unclaimed:
            if candidate.item_code == row.item_code and _dec(candidate.qty) == qty:
                unclaimed.remove(candidate)
                repairs[index] = str(candidate.id)
                break
    return repairs, settled


def _resolve_shape_b_repairs(
    dated_rows: Sequence[Tuple[int, Any]],
    shape_a_exact_matched: set,
    shape_a_repairs: Dict[int, str],
    settled_rows: Sequence[Any],
) -> Dict[int, str]:
    """Shape B, round 5 (19 Sep 2026, prod feedback after #1004 deployed): a migrated row a
    planning change already restated IN PLACE keeps its Now (`qty`/`delivery_date` - what
    purchasing works to) correct, but can still carry 7.4's mistake on its WAS side
    (`previous_qty`/`previous_delivery_date` - the line's own `required_date`, exactly as
    shape A's own fingerprint, just read off the other pair of columns). SO314593's own
    SRTWCX8605-S-RL-PJ / CB2806A-DIY / SRTWB245 rows: qty 280, `delivery_date` 2026-06-01
    (correct, the book's date), `previous_qty` 182, `previous_delivery_date` 2027-03-01 (the
    mistake) - the sheet says 182 @ 1.6.2026, which describes the row's WAS state, not a
    fresh instruction.

    Pure and deterministic, over `previous_qty` instead of `qty` - but only for sheet rows
    shape A left with nothing to do: "exact match first, shape A, then shape B" (round 5
    review), so a row shape A already claimed - whether repaired or settled as an exact
    no-op match (`shape_a_exact_matched`, `_resolve_line_repairs`'s own second return value,
    N10 round 4 review) - is never also handed to shape B.

    Its OWN pass 1 (S14, round 4 review): a settled candidate whose `previous_delivery_date`
    already equals the sheet's date needs no repair - claimed as a no-op, same as shape A's,
    so it is not ALSO reported `DELIVERY_DATE_UPDATED` and counted on every further run while
    nothing actually changes.
    """
    shape_a_claimed = shape_a_exact_matched | set(shape_a_repairs)
    unclaimed = list(settled_rows)
    settled_b: set = set()

    for index, row in dated_rows:
        if index in shape_a_claimed:
            continue
        qty = _dec(row.qty)
        for candidate in unclaimed:
            if (
                candidate.item_code == row.item_code
                and _dec(candidate.previous_qty) == qty
                and candidate.previous_delivery_date == row.delivery_date
            ):
                unclaimed.remove(candidate)
                settled_b.add(index)
                break

    repairs: Dict[int, str] = {}
    for index, row in dated_rows:
        if index in shape_a_claimed or index in settled_b:
            continue
        qty = _dec(row.qty)
        for candidate in unclaimed:
            if candidate.item_code == row.item_code and _dec(candidate.previous_qty) == qty:
                unclaimed.remove(candidate)
                repairs[index] = str(candidate.id)
                break
    return repairs


def _resolve_shape_c_repairs(
    dated_rows: Sequence[Tuple[int, Any]],
    already_claimed: set,
    live_candidates: Sequence[Any],
    cancelled_siblings: Sequence[Any],
) -> Dict[int, str]:
    """Shape C, round 7 (19 Sep 2026, owner go) - revised after a prod `SELECT` showed the
    round 6 premise (stamp + `changed_at` + no Was, on ONE row) never actually occurs.

    The real shape, SO314593's CB2806A-DIY / SRTWB245: a reconfirm CANCELLED a migrated
    row that had ALREADY been settled in place once (qty 220, `previous_qty` 182,
    `previous_delivery_date` 2027-03-01 - its OWN Was, from that earlier settle) and its
    note overwritten to `"Superseded by revision N"` (`_settle_row_in_place`'s cancel path
    replaces the note outright - the migration stamp is GONE, so a cancelled sibling can
    never be found by it), then RAISED A FRESH LIVE ROW in its place (qty 220,
    `delivery_date` the line's own `required_date`, no Was at all, no stamp - board-raised,
    not migrated). The sheet's 182 @ 1.6.2026 is the Was the live row never got, because it
    REPLACES a migrated row rather than being one.

    A sheet row is paired to a LIVE row through a CANCELLED, migrated SIBLING on the SAME
    mirror whose OWN quantity - its `qty` (never settled before being superseded) OR its
    `previous_qty` (settled once, then superseded) - equals the sheet row's own quantity:
    that identity is what says "this sheet row is about the SAME instruction that migrated
    row was." Only a sibling `import_job_rows` itself records as a row this feature CREATED
    (`entity_type="order_inquiry_row"`, `outcome="created"`, `entity_id` = the row's own id -
    the same durable record `outcome.success(...)` writes for every row it raises) ever
    counts as a migrated sibling (S1, round 7 review round 2): the cancel path overwrites the
    note, so a plain cancelled BOARD row can otherwise coincidentally share a quantity with a
    sheet row and be mistaken for one.

    The live row adopted is the unclaimed live candidate whose OWN `qty` equals the
    sibling's own `qty` (S2, round 7 review round 2) - prod's own shape (sibling `qty` 220,
    live `qty` 220) - falling back to the first unclaimed candidate sharing the sibling's
    item code only when no quantity match exists. NEVER by file position (round 7 review):
    two live rows and two cancelled siblings of the same item are paired by which sibling's
    own quantity the sheet row's own quantity matches, not by which pair happens to line up
    positionally.

    Claim-once on BOTH pools - "one live row per cancelled migrated sibling" - so a second
    live row cannot ride on a sibling a first live row already used, and a second sibling
    carrying the same quantity is what a second live row needs. Only for sheet rows shapes
    A and B leave unclaimed (`already_claimed` is their combined claim set) - "exact match,
    shape A, shape B, shape C" is the full priority order.

    No pass-1 no-op: `previous_qty IS NULL` can never already equal the sheet's own
    (non-`NULL`) quantity, so idempotency comes from the eligibility precondition itself -
    once this writes `previous_qty`/`previous_delivery_date`, the row no longer carries
    `previous_qty IS NULL` and drops out of the candidate pool on the next run entirely.
    """
    unclaimed_live = list(live_candidates)
    unclaimed_siblings = list(cancelled_siblings)
    repairs: Dict[int, str] = {}
    for index, row in dated_rows:
        if index in already_claimed:
            continue
        qty = _dec(row.qty)
        sibling = next(
            (
                candidate for candidate in unclaimed_siblings
                if candidate.item_code == row.item_code
                and (
                    _dec(candidate.qty) == qty
                    or (
                        candidate.previous_qty is not None
                        and _dec(candidate.previous_qty) == qty
                    )
                )
            ),
            None,
        )
        if sibling is None:
            continue
        # S2, round 7 review round 2: paired by the sibling's OWN qty first (prod's own
        # shape - sibling `qty` 220, live `qty` 220), never by list/creation position - a
        # bare item-code match alone is a coin flip whenever more than one live candidate
        # shares the item. Falls back to item-only only when nothing carries that quantity.
        sibling_qty = _dec(sibling.qty)
        live = next(
            (
                c for c in unclaimed_live
                if c.item_code == row.item_code and _dec(c.qty) == sibling_qty
            ),
            None,
        )
        if live is None:
            live = next(
                (c for c in unclaimed_live if c.item_code == row.item_code), None
            )
        if live is None:
            continue
        unclaimed_siblings.remove(sibling)
        unclaimed_live.remove(live)
        repairs[index] = str(live.id)
    return repairs


def _resolve_delivery_date_repairs(db: Session, plan: _Plan) -> None:
    """B1/S1/S3/S8/S10/S13, 19 Sep 2026: decide, ONCE and read-only, which already-raised
    sheet rows would repair which migrated row - so `preview` can forecast
    `rows_delivery_date_updated` and `apply` writes exactly what was forecast, never
    recomputing the decision.

    **B2, purchasing's own work is never touched by shape A.** Shape A's eligible migrated
    rows carry `previous_qty IS NULL AND previous_delivery_date IS NULL AND changed_at
    IS NULL` - no planning change has restated this row since the sheet raised it. A row a
    change HAS settled in place keeps its own Now (`qty`/`delivery_date`); shape B (below)
    still corrects the mistake it can carry on its WAS side.

    **S8, confined to 7.4's own artefacts.** Shape A is eligible only when the migrated
    row's `delivery_date` still equals its CORE LINE's `required_date` - that is exactly
    what 7.4 wrote and nothing else does. A row that already carries a date the line does
    not (a sheet date raised under this fix, or one a person edited) is never rewritten by a
    later sheet: the sheet is a migration, not a second opinion. Compared in PYTHON against
    `required_date_by_mirror`, not a SQL clause (S13, 19 Sep 2026 perf round): `delivery_date`
    is not indexed, so at prod scale (11,500 already-raised mirrors on a full book
    re-upload) an `OR`-of-per-line-equality clause is an 1.1 MB statement forcing a Seq Scan
    (measured 753 ms) where `so_line_id.in_(mirror_ids)` alone still uses the index.

    **Shape B, round 5 (19 Sep 2026, prod feedback after #1004 deployed).** A migrated row a
    planning change already restated IN PLACE (`_settle_row_in_place`) keeps its Now
    correct but can still carry 7.4's mistake on its WAS side - `previous_qty` /
    `previous_delivery_date` are the migration's own figures, never touched by the settle
    except to be overwritten by it, so they carry the SAME fingerprint shape A looks for on
    the other pair of columns: `previous_delivery_date == required_date`, and the sheet's
    quantity is compared against `previous_qty`, not the row's current `qty`. Written by
    `_resolve_shape_b_repairs`; see `apply()` for what actually moves (only
    `previous_delivery_date` and the note's own "Was ... on" fragment - the row's Now,
    `changed_at` and `ack_state` are all untouched).

    **Shape C, round 7 (19 Sep 2026, owner go)** - revised after a prod `SELECT` showed
    round 6's premise (one row: stamp + `changed_at` + no Was) never actually occurs. The
    real shape, SO314593's CB2806A-DIY / SRTWB245: a reconfirm CANCELLED a migrated row
    that had already been settled once (so it carries ITS OWN Was, from that settle, and
    its note is overwritten to `"Superseded by revision N"` - the stamp is gone, so this
    row can never be found by it) and RAISED A FRESH LIVE ROW in its place (no Was at all,
    no stamp, `delivery_date` the line's own `required_date`). The sheet row is the Was the
    live row never got, because it replaces a migrated row rather than being one.
    `_resolve_shape_c_repairs` pairs a sheet row to the live row through a CANCELLED
    sibling on the same mirror whose OWN `qty` or `previous_qty` equals the sheet's
    quantity - never by file position. Written `apply()`-side onto the LIVE row only; the
    cancelled sibling is read, never touched.

    Repairs are resolved per LINE, never per row, all three shapes together in
    `_resolve_line_repairs` (A) then `_resolve_shape_b_repairs` (B) then
    `_resolve_shape_c_repairs` (C, only for sheet rows A and B leave unclaimed), and
    grouped by MIRROR so every already-raised line's rows this needs - live AND cancelled -
    are loaded in ONE query (S3), selecting only the columns either resolver (or the
    S8-style comparison) reads (S10) rather than hydrating full rows.
    """
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

    # Every already-raised line's mirror id and its own required_date (S8), keyed by
    # mirror since that is what the migrated rows themselves are addressed by.
    required_date_by_mirror: Dict[str, Optional[date]] = {}
    for match in plan.matches:
        if not match.already_raised or match.core_line is None:
            continue
        core_id = str(match.core_line.id)
        mirror_id = plan.mirror_by_core_line.get(core_id)
        if mirror_id is None:
            continue
        required_date_by_mirror.setdefault(mirror_id, match.core_line.required_date)

    mirror_ids = list(required_date_by_mirror)
    if not mirror_ids:
        return

    # ONE query for every row a repair on these mirrors could need - LIVE candidates for
    # shapes A/B/C, and CANCELLED ones for shape C's sibling lookup (round 7, S3): the
    # state filter that used to exclude cancelled rows entirely is gone, since shape C's
    # own sibling is always one, and its note can never be trusted (the cancel path
    # overwrites it to "Superseded by revision N").
    rows = (
        db.query(OrderInquiryRow)
        .with_entities(
            OrderInquiryRow.id,
            OrderInquiryRow.so_line_id,
            OrderInquiryRow.item_code,
            OrderInquiryRow.qty,
            OrderInquiryRow.delivery_date,
            OrderInquiryRow.previous_qty,
            OrderInquiryRow.previous_delivery_date,
            OrderInquiryRow.changed_at,
            OrderInquiryRow.note,
            OrderInquiryRow.state,
        )
        .filter(OrderInquiryRow.so_line_id.in_(mirror_ids))
        .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
        .all()
    )
    shape_a_by_mirror: Dict[str, List[Any]] = {}
    shape_b_by_mirror: Dict[str, List[Any]] = {}
    shape_c_live_by_mirror: Dict[str, List[Any]] = {}
    cancelled_candidates: List[Any] = []
    for candidate in rows:
        mirror_id = str(candidate.so_line_id)
        if candidate.state == INQUIRY_CANCELLED:
            # Shape C's sibling pool: identified by QUANTITY alone at resolution time,
            # never by note (round 7) - collected here unconditionally; narrowed to
            # genuinely MIGRATED rows below (S1, round 7 review round 2).
            cancelled_candidates.append(candidate)
            continue
        # S8, done here rather than in SQL (S13): a required_date of `None` matches
        # nothing - a migrated row's `delivery_date` is never `None` - so a line with no
        # required date of its own is correctly never a repair candidate, any shape.
        required = required_date_by_mirror.get(mirror_id)
        if required is None:
            continue
        stamped = (candidate.note or "").startswith(_MIGRATION_STAMP)
        if candidate.previous_qty is None:
            if candidate.delivery_date != required:
                continue
            # Shape A (B2, unchanged since #1004): stamped, and ALL THREE markers NULL
            # (`previous_qty` already is, here) - no planning change has restated this
            # row at all, on either pair of columns. Checked in PYTHON, not SQL, for the
            # same un-indexed-column reason S13 moved `delivery_date` out.
            if (
                stamped
                and candidate.previous_delivery_date is None
                and candidate.changed_at is None
            ):
                shape_a_by_mirror.setdefault(mirror_id, []).append(candidate)
            else:
                # Shape C's live-row pool: everything else with no Was - ANY origin, no
                # stamp required, and mutually EXCLUSIVE with shape A's own pool (a row
                # genuinely eligible for shape A must never also be independently
                # available to shape C, or the two resolvers could both claim it - the
                # prod live row itself carries `changed_at` set from the reconfirm that
                # raised it, which is exactly why this cannot require `changed_at IS
                # NULL` the way shape A does).
                shape_c_live_by_mirror.setdefault(mirror_id, []).append(candidate)
        elif stamped and candidate.previous_delivery_date == required:
            shape_b_by_mirror.setdefault(mirror_id, []).append(candidate)

    # S1, round 7 review round 2: a cancelled row's own note can never be trusted once
    # superseded (the cancel path overwrites it to "Superseded by revision N"), so a plain
    # cancelled BOARD row can otherwise coincidentally share a quantity with a sheet row
    # and be mistaken for a migrated sibling. `import_job_rows` is the durable record of
    # every row THIS FEATURE ever created (`outcome.success(..., entity_type=
    # "order_inquiry_row", entity_id=entry.id)`, `oc.OUTCOME_CREATED`) - a cancelled row
    # only qualifies as a sibling when its OWN id is recorded there. One extra query over
    # the cancelled candidate ids on this same round trip, never per-row; skipped
    # entirely when there is nothing to narrow.
    cancelled_by_mirror: Dict[str, List[Any]] = {}
    if cancelled_candidates:
        from app.models.job import ImportJobRow

        candidate_ids = [str(c.id) for c in cancelled_candidates]
        migrated_ids = {
            entity_id
            for (entity_id,) in db.query(ImportJobRow.entity_id)
            .filter(
                ImportJobRow.entity_type == "order_inquiry_row",
                ImportJobRow.outcome == oc.OUTCOME_CREATED,
                ImportJobRow.entity_id.in_(candidate_ids),
            )
            .all()
        }
        for candidate in cancelled_candidates:
            if str(candidate.id) not in migrated_ids:
                continue
            cancelled_by_mirror.setdefault(str(candidate.so_line_id), []).append(candidate)

    dated_rows_by_mirror: Dict[str, List[Tuple[int, Any]]] = {}
    for index, match in enumerate(plan.matches):
        if not match.already_raised or match.core_line is None:
            continue
        # S2, 19 Sep 2026: an undated row (ORDER BACK, or a blank cell) states nothing
        # about a migrated row's date, so it never claims one and never writes NULL over
        # one either - it is simply left out of the resolution entirely.
        if match.row.delivery_date is None:
            continue
        mirror_id = plan.mirror_by_core_line.get(str(match.core_line.id))
        if mirror_id is None:
            continue
        dated_rows_by_mirror.setdefault(mirror_id, []).append((index, match.row))

    for mirror_id, dated_rows in dated_rows_by_mirror.items():
        shape_a_candidates = shape_a_by_mirror.get(mirror_id, [])
        repairs_a, exact_matched_a = _resolve_line_repairs(dated_rows, shape_a_candidates)
        for index, migrated_id in repairs_a.items():
            plan.matches[index].repair_row_id = migrated_id
            plan.matches[index].repair_shape = "A"

        repairs_b = _resolve_shape_b_repairs(
            dated_rows, exact_matched_a, repairs_a, shape_b_by_mirror.get(mirror_id, [])
        )
        for index, migrated_id in repairs_b.items():
            plan.matches[index].repair_row_id = migrated_id
            plan.matches[index].repair_shape = "B"

        claimed_ab = exact_matched_a | set(repairs_a) | set(repairs_b)
        repairs_c = _resolve_shape_c_repairs(
            dated_rows,
            claimed_ab,
            shape_c_live_by_mirror.get(mirror_id, []),
            cancelled_by_mirror.get(mirror_id, []),
        )
        for index, migrated_id in repairs_c.items():
            plan.matches[index].repair_row_id = migrated_id
            plan.matches[index].repair_shape = "C"


def _redirected_earliest_and_qty(
    db: Session, mirror_id: str
) -> Tuple[Optional[date], Optional[Decimal]]:
    """The EARLIEST date and total quantity over the mirror's currently `redirected_to_pool`
    MIGRATED rows - the exact pairing `ProjectOrderInquiryService`'s own writer
    (~1093-1098, AC-OH-40..42) stamps onto a fresh row's `previous_delivery_date` /
    `previous_qty`. `(None, None)` when the mirror carries none.
    """
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

    redirected = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == mirror_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.redirected_to_pool.is_(True),
            OrderInquiryRow.note.like(f"{_MIGRATION_STAMP}%"),
        )
        .all()
    )
    dated = [r.delivery_date for r in redirected if r.delivery_date is not None]
    if not dated:
        return None, None
    return min(dated), sum((_dec(r.qty) for r in redirected), _ZERO)


def _resync_sibling_was_now(
    db: Session, mirror_id: str, old_earliest: Optional[date], old_total_qty: Optional[Decimal]
) -> None:
    """B3/S5, 19 Sep 2026: bring a sibling row's Was/Now back into agreement, once a repair
    has moved the mirror's redirected rows' EARLIEST date - and touch NOTHING else.

    `old_earliest` / `old_total_qty` are the mirror's `redirected_to_pool` earliest date
    and total quantity CAPTURED BEFORE this run wrote any repair to this mirror (the
    caller's job): a sibling is touched only when its OWN `previous_delivery_date` /
    `previous_qty` are EXACTLY that pairing, so a row whose Was/Now came from something
    else entirely - its own planning change, a different redirect - is never touched, byte
    for byte (review finding B3, 19 Sep 2026: an unrelated placed sibling carrying
    "AutoCount moved PO-1 to SO-9 on 2026-05-01; Was 25 on 2026-05-01" was rewritten by an
    unrelated repair on the same mirror because the old code matched on the mirror alone).

    The note is corrected by replacing the ANCHORED fragment `f"Was {qty} on {old}"` with
    `f"Was {qty} on {new}"` - never a bare date substring, which also matched (and
    falsified) an "AutoCount moved PO-1 to SO-9 on <date>" provenance line
    `orderInquiryAck.ts` reads by prefix.
    """
    if old_earliest is None:
        return
    new_earliest, _ = _redirected_earliest_and_qty(db, mirror_id)
    if new_earliest is None or new_earliest == old_earliest:
        return

    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
    # Private on purpose (N7, 19 Sep 2026): the note prose must match the writer's own
    # formatting byte for byte ("182", never "182.0000"), so its own `_qty_str` is reused
    # rather than a second copy that could drift from it.
    from app.services.project_order_inquiry_service import _qty_str

    siblings = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == mirror_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.previous_delivery_date == old_earliest,
        )
        .all()
    )
    for sibling in siblings:
        if sibling.previous_qty is None or _dec(sibling.previous_qty) != old_total_qty:
            continue
        qty_str = _qty_str(_dec(sibling.previous_qty))
        old_fragment = f"Was {qty_str} on {old_earliest.isoformat()}"
        new_fragment = f"Was {qty_str} on {new_earliest.isoformat()}"
        if sibling.note and old_fragment in sibling.note:
            sibling.note = sibling.note.replace(old_fragment, new_fragment, 1)
        sibling.previous_delivery_date = new_earliest


def _plan(db: Session, parsed: OrderInquiryResult) -> _Plan:
    """Match every row, decide raise / skip / report. Pure: writes nothing."""
    plan = _Plan(parsed=parsed)
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

    #: One row per `+` member (`_members`), before anything else reads `plan.matches` - the
    #: match loop, the ledger and the result all work on the EXPANDED rows, never on
    #: `parsed.rows` (plan section 2). The reader's own list is not mutated.
    expanded: List[Any] = []
    for row in parsed.rows:
        order = plan.orders.get(row.so_number)
        line_codes = {c[1] for c in lines.get(str(order.id), [])} if order else set()
        expanded.extend(_members(row, line_codes))
    plan.matches = [_Match(row=row) for row in expanded]
    plan.rows_expanded = len(expanded)

    raised_already, plan.mirror_by_core_line, rows_by_mirror = _already_raised(
        db, [held[0] for group in lines.values() for held in group]
    )
    #: Which candidate lines the book BOUGHT for, over every line of every order the sheet
    #: names rather than only the matched ones - the line pick asks the question before a row
    #: has a line, so the answer cannot wait for the match. `_pair` groups the same rows.
    plan.bought_rows = _bought_rows(
        db, [held[0] for group in lines.values() for held in group]
    )
    plan.bought_refs = _bought_refs(plan.bought_rows)
    #: The same rows, this time by the document NUMBER the book bought each line with
    #: (`_bought_documents`) - what the same-month and sheet-PO passes read to tell a
    #: candidate line the sheet's own citation also names (PLAN section 2, "Book PO per
    #: line").
    plan.bought_documents = _bought_documents(db, plan.bought_rows)
    #: How much of each line this FILE has already spoken for, in file order - shared by all
    #: five passes of the line pick below, so a row placed by an earlier pass is unavailable
    #: to a later one, and a re-upload charges exactly what the first upload charged
    #: (`_match_row`, "Ledger", reversing review finding 9 of 14 Sep on purpose).
    taken: Dict[str, Decimal] = {}

    #: The instructions stated for each `_restates` key so far, in the order they were
    #: first stated (D7). A restatement is only ever ACROSS tabs (R5, 19 Sep 2026,
    #: `_restates`): the n-th row carrying a key on ONE tab is its OWN instruction, distinct
    #: from the key's other rows on that same tab, so a key can hold several entries here
    #: before any tab restates even the first of them.
    stated: Dict[tuple, List[_Match]] = {}
    #: How many rows carrying each `(sheet, key)` pair have been seen so far - the position
    #: `stated[key]` is read at. Keyed on the SHEET as well as the key, because the count
    #: resets to zero on every new tab: a tab's own first row is always position 0, whether
    #: or not an earlier tab already stated the key twice.
    seen: Dict[tuple, int] = {}

    #: Rows that cleared the file-level checks below and are left for the five passes to
    #: place (`_match_in_passes`).
    pending: List[_Match] = []

    for match in plan.matches:
        row = match.row
        key = _restates(row)
        instructions = stated.setdefault(key, [])
        position = seen.get((row.sheet, key), 0)
        seen[(row.sheet, key)] = position + 1
        if position < len(instructions):
            # This tab has already stated this key `position` times before this row, and an
            # EARLIER tab stated it at least `position + 1` times - so this row restates the
            # instruction an earlier tab put at that same position, not merely "the first
            # one ever seen" (D7, R5). Counted, never matched: a restatement must not take
            # the line's quantity from the row it restates, or the second tab would read
            # `qty_exceeds_ordered`.
            first = instructions[position]
            match.duplicate = True
            if row.po_numbers and not first.row.po_numbers:
                first.row = replace(first.row, po_numbers=row.po_numbers)
            continue
        # `position == len(instructions)`: no earlier tab reached this many rows of this key,
        # so this row is a NEW instruction - whether or not this same tab already stated the
        # key at an earlier position (R5: two identical rows on one tab are two instructions).
        instructions.append(match)
        if _dec(row.qty) <= _ZERO:
            # Never matched and never charged to the ledger (security review N2, 14 Sep):
            # a negative cell would otherwise hand capacity BACK to the line and let a later
            # row take more of it than the order holds.
            match.code = oc.INVALID_QUANTITY
            continue
        order = plan.orders.get(row.so_number)
        if order is None:
            match.code = oc.ORDER_NOT_FOUND
            continue
        if row.so_number in refused:
            match.code = oc.ORDER_NOT_PLANNABLE
            continue
        pending.append(match)

    _match_in_passes(plan, lines, taken, raised_already, pending)
    _resolve_recovery_matches(db, plan, rows_by_mirror)

    plan.orders_in_play = sorted({
        match.row.so_number for match in plan.matches if match.raisable
    })
    plan.orders_to_adopt = _unadopted(
        db, [plan.orders[number] for number in plan.orders_in_play]
    )
    _resolve_delivery_date_repairs(db, plan)
    return plan


def _unadopted(db: Session, orders: Sequence[SalesOrder]) -> int:
    """How many of these sales orders have no planning record yet (AC-S1-22).

    Counted rather than inferred from the write, so `preview` can report the same number
    without adopting anything: a screen that says nothing about adoption lets an operator
    press Confirm on 400 new planning records without knowing it (security review SF2).
    """
    if not orders:
        return 0
    from app.models.project_so import ProjectSalesOrder

    held = {
        str(so_id)
        for (so_id,) in db.query(ProjectSalesOrder.so_id).filter(
            ProjectSalesOrder.so_id.in_([str(order.id) for order in orders])
        )
    }
    return sum(1 for order in orders if str(order.id) not in held)


# --------------------------------------------------------------------------- #
# pairing: what the book states first, what the sheet cites second             #
# --------------------------------------------------------------------------- #


def _target_facts(db: Session, target_ids: set) -> Dict[str, dict]:
    """Everything a link needs about a purchase-order line or an SPO allocation.

    Capacity is `qty_ordered` / `allocated_quantity` - the line's own size, NEVER its
    outstanding (AC-S1-12): the sheet is history, and a closed, fully received line is
    exactly what the rows being migrated are waiting on. What OTHER links already claim is
    subtracted by the caller.

    A purchase order line's capacity has a second half, `_less_own_shipments` below: the
    units of it that are already on a ship belong to that shipment, not to the line as well
    (7.2). It is applied here rather than at the query because the shipments are only known
    once `_chain_allocations` has run, and that read needs the document numbers this
    function is what reads.

    A CANCELLED purchase order line answers with no fact at all (section 8, owner: the case
    is "straightforward"). This is the one place every source's PO-line facts pass through,
    so a source that names one - the line reference, a claim - finds nothing and moves on to
    the next thing it knows. On the 14 Sep prod copy 305 rows and 19,373 units were sitting
    on a line the purchase order had cancelled.
    """
    wanted = sorted(str(i) for i in target_ids if i)
    if not wanted:
        return {}
    facts: Dict[str, dict] = {}
    for line, number, supplier in (
        db.query(PurchaseOrderLine, PurchaseOrder.po_number, Supplier.supplier_name)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(PurchaseOrderLine.id.in_(wanted), _LIVE_PO_LINE)
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
            # This line's OWN document key, which the shipping order quotes back as
            # `spo_allocations.from_po_line_ref` - how `_chain_allocations` walks the chain
            # line to line rather than document to document.
            "source_ref": (line.source_ref or "").strip(),
        }
    for allocation, supplier in (
        db.query(SPOAllocation, Supplier.supplier_name)
        .outerjoin(Supplier, Supplier.id == SPOAllocation.supplier_id)
        .filter(
            SPOAllocation.id.in_(wanted),
            # The same visibility test `_purchase_side` and `_chain_allocations` apply
            # (review finding 1, 14 Sep): a line AutoCount stopped naming, and that never
            # received anything, is not a document a link may land on - and an old claim can
            # still point at one.
            *spo_supply.visible_line_clauses(),
        )
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
            "source_ref": (allocation.source_ref or "").strip(),
        }
    return facts


def _bought_rows(
    db: Session, lines: Sequence[SalesOrderLine]
) -> Tuple[List[SPOAllocation], List[PurchaseOrderLine]]:
    """Every purchase document row that NAMES one of these sales order lines.

    The purchase side carries the exact line it was raised for in its own column -
    `purchase_order_lines.from_so_line_ref` and the `spo_allocations` twin, both joinable to
    `sales_order_lines.source_ref`. That is the owner's own query, and it is the source of
    truth this importer reads FIRST (R1, `PLAN-scm-oi-sheet-pairing-repair.md` section 2.3).

    Read ONCE by `_plan`, over every candidate line of every order the sheet names, because
    the answer is needed twice: the line pick asks "did the book buy for this line at all"
    (section 7) before a row is matched, and `_ref_targets` groups the very same rows into
    the pairing's first source afterwards. Two reads, not four.

    A ref that names MORE THAN ONE sales order line is dropped before either query runs
    (`_unambiguous_refs`, security review 14 Sep): a purchase document carrying the August
    ordinal `'1'` in `from_so_line_ref` would otherwise answer for all 3,364 lines that
    ordinal sits on.

    Order is explicit on both sides - shipping order then line number, purchase order line by
    age - so two runs of the same sheet hand the quantity out the same way.
    """
    refs = {(line.source_ref or "").strip() for line in lines}
    refs.discard("")
    products = {str(line.product_id or "") for line in lines}
    products.discard("")
    if not refs or not products:
        return [], []
    refs = _unambiguous_refs(db, refs)
    if not refs:
        return [], []
    wanted, items = sorted(refs), sorted(products)

    allocations = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.from_so_line_ref.in_(wanted),
            SPOAllocation.product_id.in_(items),
            # The same visibility test every other reader here applies: a line AutoCount
            # stopped naming, that never received anything, is not a document a link may
            # land on, nor evidence that this line was bought for.
            *spo_supply.visible_line_clauses(),
        )
        .order_by(
            SPOAllocation.spo_number.asc(),
            SPOAllocation.spo_line_number.asc(),
            SPOAllocation.id.asc(),
        )
        .all()
    )
    po_lines = (
        db.query(PurchaseOrderLine)
        .filter(
            PurchaseOrderLine.from_so_line_ref.in_(wanted),
            PurchaseOrderLine.product_id.in_(items),
            # A cancelled line is neither a target nor evidence: it must not link, and it
            # must not tell the line pick that the book bought for the line it names, or a
            # row would be pulled onto a line by a purchase somebody withdrew.
            _LIVE_PO_LINE,
        )
        .order_by(PurchaseOrderLine.created_at.asc(), PurchaseOrderLine.id.asc())
        .all()
    )
    return allocations, po_lines


def _bought_refs(rows: Tuple[Sequence[Any], Sequence[Any]]) -> set:
    """`(ref, product)` for every line the book BOUGHT for (section 7, R2 finished).

    The product is part of the key, exactly as it is in `_ref_targets`: a stale ref on a
    document for another item says nothing about this line.
    """
    allocations, po_lines = rows
    return {
        (str(row.from_so_line_ref), str(row.product_id or ""))
        for row in list(allocations) + list(po_lines)
        if row.from_so_line_ref
    }


def _ref_targets(
    rows: Tuple[Sequence[Any], Sequence[Any]],
) -> Tuple[Dict[tuple, List[str]], Dict[tuple, List[str]]]:
    """What AutoCount itself states is for each sales order line, per `(ref, product)`.

    The rows `_plan` already read (`_bought_rows`), grouped. Required rather than optional:
    the plan always reads them, there is no other caller, and an optional fallback here would
    be a second read nobody asks for (reviewer, 15 Sep).

    The product is part of the key as well as the ref: a ref names one line of one order, but
    a wrong or stale ref on a document for another item must not pull that document in. The
    map may be WIDER than the rows being paired (the plan reads over every candidate line of
    the file, not only the matched ones); a key nothing looks up costs nothing.
    """
    allocations, po_lines = rows

    by_allocation: Dict[tuple, List[str]] = {}
    for allocation in allocations:
        by_allocation.setdefault(
            (str(allocation.from_so_line_ref), str(allocation.product_id or "")), []
        ).append(str(allocation.id))

    by_po_line: Dict[tuple, List[str]] = {}
    for line in po_lines:
        by_po_line.setdefault(
            (str(line.from_so_line_ref), str(line.product_id or "")), []
        ).append(str(line.id))
    return by_allocation, by_po_line


def _chain_allocations(
    db: Session, po_numbers: set, product_ids: set
) -> Tuple[Dict[tuple, List[str]], Dict[tuple, List[str]]]:
    """The SPO allocations a purchase order BECAME: per `(PO number, PO LINE ref, product)`
    and, for whatever cannot be read that way, per `(PO number, product)` (D10).

    The shipping order feed states the purchase order it came from
    (`spo_allocations.from_po_number`), which is the second of the two ways the
    SO -> PO -> SPO chain is known. Following it is what puts the link on the SPO, so the
    worklist shows the shipping order with its source PO beside it rather than a purchase
    order the goods have already left.

    It also states the exact purchase order LINE, in `from_po_line_ref`, quoting that line's
    own `source_ref` - and the document number alone is too coarse to stand in for it. On the
    3am 14 Sep prod copy, SPO-2026/01-0140 carries FIVE CB2154-DIY allocations from purchase
    order 202511-S0097 (300, 87, 1, 10 and 2), each raised for a different sales order line,
    so a walk by number lands the owner's 87 on the 300 belonging to somebody else. Every one
    of the 64,034 allocations that names a source purchase order names its line too, and
    64,026 of those refs resolve to a purchase order line we hold, so the finer key is
    available wherever the coarser one is (`PLAN-scm-oi-sheet-pairing-repair.md` 2.3).

    The document number stays in the finer key alongside the line ref, because
    `purchase_order_lines.source_ref` is NOT unique either: the August extract wrote bare
    ordinals, and `'1'`, `'2'` and `'3'` each sit on 190 to 240 purchase order lines. Keyed on
    the ref alone, an ordinal would chain one document's line to another document's
    containers.
    """
    if not po_numbers or not product_ids:
        return {}, {}
    rows = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.from_po_number.in_(sorted(str(n) for n in po_numbers)),
            SPOAllocation.product_id.in_(sorted(str(p) for p in product_ids)),
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
    by_line: Dict[tuple, List[str]] = {}
    for allocation in rows:
        product = str(allocation.product_id or "")
        held.setdefault((str(allocation.from_po_number), product), []).append(
            str(allocation.id)
        )
        ref = (allocation.from_po_line_ref or "").strip()
        if ref:
            by_line.setdefault(
                (str(allocation.from_po_number), ref, product), []
            ).append(str(allocation.id))
    return held, by_line


def _less_own_shipments(
    facts: Dict[str, dict], chain_by_line: Dict[tuple, List[str]]
) -> None:
    """A purchase order line answers only for what has NOT sailed yet (7.2, owner 14 Sep).

    A purchase order line and the shipping order it became are ONE supply. D10 links the
    shipment first and the line "for the remainder", but the remainder was measured against
    the line's whole `qty_ordered`, so the same units were owed twice: on the 3am prod copy
    555 rows carried a link to a PO line AND to that line's own allocation, 23,187 units
    counted twice (SO368872 / SRTWC286-SH is the owner's own case, 62 on PO 202510-S0078 and
    62 on SPO-2026/04-0043, which IS that line shipped).

    So the line's capacity drops by what its own allocations carry: ONLY the allocations
    that quote this line's `source_ref` in `from_po_line_ref`, never the document's own
    (reviewer B1, 15 Sep). Deducting the document's took a SIBLING line's shipment off this
    line and left a row with no link at all when that sibling's allocation was already
    occupied. On the 3am prod copy the fallback could not help anyway: 0 allocations carry a
    `from_po_number` without a `from_po_line_ref`, and 0 purchase order lines have a blank
    `source_ref`, so an allocation that really came from this line always names it.

    `_through_po` still walks the document's allocations when the feed named no line, which
    is D10 as it has always been (AC-R-2, AC-R-9). The two are not in conflict: an allocation
    that does not name this line is not evidence that this line's units have sailed, so it
    must not reduce the line, while taking it first is still the right walk when it is all
    the feed states. Floored at zero, and read off the facts already built for those
    allocations, so nothing is queried again.

    The owner still sees both documents: "we definitely cannot double count, but by this
    linking it helps us to know the PO and SPO corresponding to this order inquiry". The
    worklist's PO column names the source purchase order of a shipment it links (7.2, FE).
    """
    for fact in facts.values():
        if fact["kind"] != _PO:
            continue
        document, product = str(fact["document"]), fact["product_id"]
        shipped_ids = chain_by_line.get(
            (document, str(fact.get("source_ref") or ""), product)
        ) or []
        shipped = sum(
            (facts[str(i)]["capacity"] for i in shipped_ids if str(i) in facts), _ZERO
        )
        if shipped > _ZERO:
            fact["capacity"] = max(fact["capacity"] - shipped, _ZERO)


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


def pair_needs(
    db: Session,
    needs: Sequence[_Need],
    bought_rows: Optional[Tuple[List[Any], List[Any]]],
    *,
    book_targets_out: Optional[Dict[str, List[Tuple[str, dict]]]] = None,
) -> Tuple[Dict[Any, _RowLinks], List[str]]:
    """What each need would be linked to, in the order the two sources rank.

    Extracted from `_pair` (S1, `PLAN-oi-follow-book-chain.md`) with no behaviour
    change for the importer (AC-FB-12): `_pair` builds its own `needs` from
    `plan.matches` and calls this. The seam exists so a LIVE order inquiry row
    (`ProjectOrderInquiryService.follow_book_for_rows`) can run through the exact
    same rule a migrated row does, keyed by its own row id rather than a match's
    index into a sheet that does not exist for it.

    **Source 1, the line reference AutoCount itself wrote** (D9 as repaired, R1: "we don't
    trust the remark column in the sheet ... the source of truth is the autocount linkage").
    The purchase side names the exact sales order line in its own column, so that column is
    read FIRST: allocations that name the line, then, for a purchase order line that names
    it, the shipping orders that purchase order became (D10) and the purchase order line
    itself only for what they cannot cover. Measured on the 3am 14 Sep prod copy, 32,674
    purchase order lines name a held sales order line and only 4,277 carry a claim saying so.

    **Source 2, claims the ingest resolved** - for the need the reference leaves. Where
    AutoCount stated only a document NUMBER there is no reference to read, and the claim is
    all there is, so this source stays; it is merely no longer first, and `po_history` no
    longer counts as the book (`_BOOK_CLAIM_SOURCES`). SPO before PO, a purchase order
    followed through to the allocations it became before the purchase-order line itself.

    **There is no third source.** What the sheet's remark cites used to answer for the need
    the book left; it does not any more (section 8, owner 15 Sep 2026: "let's ignore the
    sheet remark at all"). 223 of the 5,833 links on the 14 Sep prod copy came from it, and
    the documents it named were read by number alone, which took units off lines the purchase
    order had cancelled. `documents_not_linkable` therefore comes back empty from every run,
    and stays on the result only so the contract keeps its keys.

    Nothing is written here. `apply` writes exactly what this returns, and `preview` counts
    it, so the two can never answer differently. `follow_book_for_rows` is the third caller
    that keeps that same promise: nothing is written until it decides to write it.

    `book_targets_out` (review round item 4, security B1 / reviewer blocker 3): when given a
    dict, this fills it with `{core_line_id: [(target_id, fact), ...]}` for SOURCE-1 (the
    ref, direct or through the PO -> SPO chain) ONLY - never a claim - in the exact rank this
    walk reads them, `fact` already netted (`_target_facts` + `_less_own_shipments`), whether
    or not `take()` could actually place anything on it. This is the one list of "what the
    book names for this line" `follow_book_for_rows`'s own displacement reads (`_book_targets_
    map` and its own re-derived, un-netted capacity query are retired in favour of it -
    PRINCIPLES "one copy"): a second walk of the same primitives could only ever answer the
    same question differently by accident.
    """
    links: Dict[Any, _RowLinks] = {}
    not_linkable: List[str] = []
    if not needs:
        return links, not_linkable

    claims = [
        claim
        for claim in order_link_service._claim_rows(
            db, so_line_ids={str(n.core_line.id) for n in needs}
        )
        if claim["source"] in _BOOK_CLAIM_SOURCES
    ]
    by_line: Dict[str, List[dict]] = {}
    for claim in claims:
        by_line.setdefault(str(claim["so_line_id"]), []).append(claim)

    ref_allocations, ref_po_lines = _ref_targets(bought_rows or ([], []))

    target_ids = {claim["target_id"] for claim in claims}
    target_ids |= {i for ids in ref_allocations.values() for i in ids}
    target_ids |= {i for ids in ref_po_lines.values() for i in ids}
    facts = _target_facts(db, target_ids)

    chain, chain_by_line = _chain_allocations(
        db,
        # Every purchase order this run may land on, whichever source named it: the
        # reference reaches the shipping order through exactly the same D10 walk a claim
        # does, so both sets of PO numbers are gathered before the one query.
        {
            facts[claim["target_id"]]["document"]
            for claim in claims
            if facts.get(claim["target_id"], {}).get("kind") == _PO
        }
        | {
            facts[line_id]["document"]
            for ids in ref_po_lines.values()
            for line_id in ids
            if line_id in facts
        },
        {str(n.core_line.product_id or "") for n in needs},
    )
    chained = {
        allocation_id for allocations in chain.values() for allocation_id in allocations
    }
    facts.update(
        {key: value for key, value in _target_facts(db, chained).items() if key not in facts}
    )
    # Now that the shipments are known, a purchase order line answers only for the units
    # that have not sailed (7.2). Before this, D10's "the line takes the remainder" measured
    # the remainder against the line's whole size and counted the same goods twice.
    _less_own_shipments(facts, chain_by_line)

    used = _claimed_capacity(db)

    for need in needs:
        held = _RowLinks(need_left=_dec(need.need_qty))
        seen: set = set()
        book_targets: List[Tuple[str, dict]] = []

        def _record_book_target(target_id: str) -> None:
            fact = facts.get(str(target_id))
            if fact is not None:
                book_targets.append((str(target_id), fact))

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

        product = str(need.core_line.product_id or "")

        def _through_po(po_line_id: str, *, record: bool = False) -> None:
            """A purchase order line the book named: its shipping orders first (D10), the
            purchase order line itself only for what they cannot cover.

            The shipping orders THIS LINE became, where the feed says so, and only otherwise
            the ones the whole document became: one purchase order can carry five lines of
            the same item for five different sales order lines, and the quantity is owed
            against the container that holds this one.

            `record` is `book_targets_out`'s own ask (source-1 only): true only when THIS
            call came from the ref walk below, never from a claim - `_through_po` is the
            same primitive either way, `record` is the only difference.
            """
            fact = facts.get(str(po_line_id))
            if fact is None:
                return
            exact = chain_by_line.get(
                (str(fact["document"]), str(fact.get("source_ref") or ""), product)
            )
            for allocation_id in (exact or chain.get((str(fact["document"]), product), [])):
                if record:
                    _record_book_target(allocation_id)
                if held.need_left <= _ZERO:
                    break
                take(allocation_id, from_book=True)
            if record:
                _record_book_target(po_line_id)
            if held.need_left > _ZERO:
                take(str(po_line_id), from_book=True)

        ref = (need.core_line.source_ref or "").strip()
        if ref:
            for allocation_id in ref_allocations.get((ref, product), []):
                _record_book_target(allocation_id)
                if held.need_left <= _ZERO:
                    break
                take(allocation_id, from_book=True)
            for po_line_id in ref_po_lines.get((ref, product), []):
                if held.need_left <= _ZERO:
                    break
                _through_po(po_line_id, record=True)

        line_claims = by_line.get(str(need.core_line.id)) or []
        for claim in sorted(line_claims, key=_claim_order(facts)):
            if held.need_left <= _ZERO:
                break
            fact = facts.get(claim["target_id"])
            if fact is None:
                continue
            if fact["kind"] == _SPO:
                take(claim["target_id"], from_book=True)
                continue
            _through_po(claim["target_id"])

        if book_targets_out is not None:
            book_targets_out[str(need.core_line.id)] = book_targets
        if held.takes:
            links[need.key] = held
    return links, not_linkable


def _pair(db: Session, plan: _Plan) -> Tuple[Dict[int, _RowLinks], List[str]]:
    """`plan.matches`, turned into `pair_needs`' own units and paired.

    The importer's own caller, unchanged behaviour (AC-FB-12): every raisable match
    becomes one `_Need`, keyed by its index into `plan.matches` exactly as before.
    """
    needs = [
        _Need(key=i, need_qty=_dec(m.row.qty), core_line=m.core_line)
        for i, m in enumerate(plan.matches)
        if m.raisable
    ]
    return pair_needs(db, needs, plan.bought_rows)


# --------------------------------------------------------------------------- #
# the result the operator reads                                                #
# --------------------------------------------------------------------------- #


def _identity(row) -> dict:
    """What names a sheet row in the job detail. No ids - the operator reads SO numbers.

    The tab is part of the name: row numbers restart on every sheet, so "row 42" alone names
    four different rows in a book of monthly tabs. `qty` joined 20 Sep 2026
    (`NO_USED_DELIVERY_MATCH`, AC-RB-3): a date/quantity mismatch is exactly what that
    report exists to tell purchasing about, and every other outcome simply ignores the key.
    """
    from app.services.project_order_inquiry_service import _qty_str

    return {
        "doc_no": row.so_number,
        "item_code": row.item_code,
        "delivery_date": row.delivery_date.isoformat() if row.delivery_date else "",
        "sheet": getattr(row, "sheet", "") or "",
        "qty": _qty_str(_dec(row.qty)),
    }


def _result(
    plan: _Plan,
    links: Dict[int, _RowLinks],
    not_linkable: Sequence[str],
    *,
    rows_raised: int,
    orders_adopted: int = 0,
    orders_stamped: int = 0,
) -> dict:
    """The eighteen keys, and nothing else (AC-S1-22).

    The retired counters are GONE rather than zeroed: a screen that can print
    `lines_created` is a screen that can tell somebody this sheet wrote the book.

    `rows_delivery_date_updated` joined them 18 Sep 2026: how many of the
    `rows_already_raised` rows this run repairs to the sheet's own date, rather than only
    leaving alone. Read off `plan.matches` rather than passed in (S1, 19 Sep 2026): the
    decision was already made, read-only, in `_resolve_delivery_date_repairs`, so `preview`
    forecasts the exact number `apply` writes rather than a caller-supplied count the two
    could drift apart on.
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
        # What this upload does to the BOOK's neighbours, said before Confirm rather than
        # discovered afterwards (security review SF2): how many planning records it opens,
        # and how many sales-order headers it stamps.
        "orders_adopted": orders_adopted,
        "orders_stamped": orders_stamped,
        "rows": plan.rows_expanded if plan.rows_expanded is not None else len(plan.parsed.rows),
        "rows_raised": rows_raised,
        "rows_already_raised": sum(1 for m in plan.matches if m.already_raised),
        "rows_delivery_date_updated": sum(1 for m in plan.matches if m.repair_row_id),
        "rows_line_not_found": len(line_not_found),
        "line_not_found": line_not_found[:_CAP],
        "sales_orders_not_found": plan.orders_not_found[:_CAP],
        "orders_not_plannable": plan.orders_not_plannable[:_CAP],
        # Per ROW, not per link: a row that lands on two documents is one row the book
        # answered for, and counting the links would make the two numbers uncomparable.
        "links_written": len(links),
        "links_partial": sum(1 for held in links.values() if held.need_left > _ZERO),
        "links_from_autocount": sum(1 for held in links.values() if held.from_book),
        # Always EMPTY since the remark stopped pairing anything (section 8): every link
        # this importer writes now comes from the book, so `links_from_autocount` equals
        # `links_written`. The key stays because the result's shape is a contract the job
        # page and the upload dialog both read (AC-R-45).
        "documents_not_linkable": documents[:_CAP],
        "sheets_read": list(plan.parsed.sheets_read),
        "sheets_skipped": list(plan.parsed.sheets_skipped),
    }


def _empty(parsed: OrderInquiryResult) -> dict:
    """The same eighteen keys for a file that could not be read (AC-S1-25)."""
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
        orders_adopted=plan.orders_to_adopt,
        orders_stamped=len(plan.orders_in_play),
    )


def validate(db: Session, file_data: bytes) -> dict:
    """The Test verdict: `{valid, errors, warnings, summary}`. Writes nothing.

    Only an unreadable sheet is an ERROR. Everything else the migration cannot do - a sales
    order the CRM does not hold, a row that fits no line, a document that could not be
    linked - is a WARNING: the rest of the file is still worth migrating, and a panel that
    calls a 400-row book a failure over 3 rows is a panel nobody reads.
    """
    out = preview(db, file_data)
    # Left alone excludes what will be repaired (S1, 19 Sep 2026): a row counted in both
    # lines would read as "left alone" AND "corrected", which is not what either means.
    left_alone = out["rows_already_raised"] - out["rows_delivery_date_updated"]
    warnings = [
        val.named(
            len(out["sales_orders_not_found"]), out["sales_orders_not_found"],
            one="sales order the CRM does not hold",
            many="sales orders the CRM does not hold",
        ),
        (f"{out['rows_line_not_found']:,} rows name no sales order line we hold, so they "
         f"will not be raised") if out["rows_line_not_found"] else None,
        (f"{left_alone:,} rows are on a line that already carries an order inquiry, and "
         f"are left alone") if left_alone else None,
        # "date" rather than "delivery date" since round 5: a migrated row a planning
        # change already restated is corrected on its Was date instead (shape B).
        (f"{out['rows_delivery_date_updated']:,} rows are on a line that already carries "
         f"an order inquiry; the migrated row's date will be corrected to the sheet's "
         f"own") if out["rows_delivery_date_updated"] else None,
        # Never fires since the remark stopped pairing anything (section 8):
        # `documents_not_linkable` comes back empty from every run, and `val.named(0, ...)`
        # is None. Kept beside the key it reads, which stays on the result because the
        # result's shape is a contract (AC-R-45).
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


def _stamp_orders(plan: _Plan) -> int:
    """The two header stamps, on the orders this upload actually works on (AC-S1-39).

    Rule 1 of `PLAN-so-project-label.md` (AC-S1-37): the project half of the inquiry's own
    cell, under `apply_project_label`'s existing precedence gate - a customer-only cell
    carries no label and leaves an existing one alone.

    And `demand_origin`: an inquiry naming a sales order is exactly what makes it project
    demand (S13b), and the fact does not depend on who owns the figures. Never cleared -
    dropping off a later sheet is one person tidying a working file, not CS withdrawing the
    demand.

    **Only an order that is not refused and has a raisable row** (security review SF1,
    14 Sep). Stamping every number the sheet merely MENTIONS let a file of 400 retail or
    mistyped sales orders relabel 400 headers it could do nothing else with, which is a
    write nobody asked for and no other part of the result would have reported.

    This is the only write this importer makes to `sales_orders`, and it is an UPDATE to a
    header the CRM already holds. Nothing is created (AC-S1-19).
    """
    labels: Dict[str, str] = {}
    for match in plan.matches:
        project = (getattr(match.row, "project", "") or "").strip()
        if project and match.row.so_number not in labels:
            labels[match.row.so_number] = project
    stamped = 0
    for number in plan.orders_in_play:
        order = plan.orders[number]
        if order.demand_origin != SOURCE_SYSTEM:
            order.demand_origin = SOURCE_SYSTEM
        cell = labels.get(number)
        label = label_from_inquiry_cell(cell) if cell else None
        if label:
            apply_project_label(order, label, "inquiry")
        stamped += 1
    return stamped


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

    def __init__(
        self,
        db: Session,
        actor: Optional[str],
        now: datetime,
        lines_by_order: Dict[str, List[str]],
    ):
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        self.db = db
        self.actor = actor
        self.now = now
        #: The core lines THIS upload matched, per sales order. What the adoption mirrors
        #: beyond the still-owed ones, and nothing more (review finding 4).
        self.lines_by_order = lines_by_order
        self.adoption = ProjectSOAdoptionService(db)
        self._records: Dict[str, Optional[dict]] = {}
        #: Planning records this upload created, for the result (AC-S1-22).
        self.adopted = 0

    def record_for(self, order: SalesOrder) -> Optional[dict]:
        """The planning record, its header and its mirror map. Adopted once per order."""
        key = str(order.id)
        if key in self._records:
            return self._records[key]
        from app.services.error_handler import AppException

        try:
            adopted = self.adoption.adopt_for_migration(
                str(order.id), self.actor, core_line_ids=self.lines_by_order.get(key, []),
            )
        except AppException as refusal:
            logger.info(
                "Order inquiry sheet: %s could not be adopted (%s)",
                order.so_number, refusal.code,
            )
            self._records[key] = None
            return None
        if not adopted.get("already_adopted"):
            self.adopted += 1
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
            # The SHEET's own date, and the sales order line's only when the sheet states
            # none (18 Sep 2026, reversing 7.4: "we should have followed the sheet's date").
            # SO314593's open AutoCount lines are 220 @ 01/03/2027 while the sheet said
            # 182 @ 1.9.2026, and 7.4 wrote the LINE's date onto every migrated row, so the
            # worklist read 01/03/2027 for a delivery purchasing was working to on
            # 1.9.2026, and the Was/Now (i) printed the same wrong date twice. An ORDER
            # BACK row still takes the line's date - the words in the date cell are never a
            # date, and `verb` is what says the quantity is owed against something already
            # ordered. The sheet's date still decides which line a row matches and whether
            # two rows restate one instruction; that reading is unchanged.
            delivery_date=row.delivery_date or match.core_line.required_date,
            stock_location=location or match.line_location,
            verb=IV_ORDER_BACK if row.order_back else IV_ORDER,
            # Never a citation any more (section 8): the remark neither picks the line nor
            # links, so there is nothing this row could honestly say it cites. The operator's
            # own words are on the note, which is where a person reads what the sheet said.
            cited_document=None,
            note=_note_for(row, file_name),
            state=INQUIRY_RAISED,
            # Born acknowledged (G4, `PLAN-scm-reorder-oi-feedback-1sep.md` S1): this is a
            # migration of instructions purchasing has been working from for months, not a
            # fresh request waiting on somebody's confirm.
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=self.actor,
            acknowledged_at=self.now,
            # 2.1(a): raised AS the used row rather than skipped, when `match` is a
            # recovered `Replaces N used` pairing (`_resolve_recovery_matches`).
            redirected_to_pool=bool(match.used_sibling_id),
        )
        self.db.add(entry)
        self.db.flush()
        return entry


def _matched_lines_by_order(plan: _Plan) -> Dict[str, List[str]]:
    """The core lines this upload will raise a row against, per sales order id."""
    held: Dict[str, List[str]] = {}
    for match in plan.matches:
        if not match.raisable:
            continue
        order = plan.orders.get(match.row.so_number)
        if order is None:
            continue
        ids = held.setdefault(str(order.id), [])
        if str(match.core_line.id) not in ids:
            ids.append(str(match.core_line.id))
    return held


def _close_history(rows: Sequence[Any], actor: Optional[str], now: datetime) -> None:
    """A row against a line that is no longer owed is HISTORY, so it is actioned (AC-S1-29).

    `scm.committed_v`'s project leg counts every `raised` / `partly_linked` inquiry row that
    carries no supply decision, and it does NOT look at the line's status (migration 424
    removed that condition on purpose). So a migrated row against a delivered line would be
    counted as live project demand and the plan would buy the goods again.

    `actioned` is the truthful state rather than a trick to dodge the view: purchasing dealt
    with this instruction, and the goods went out. It is set AFTER `refresh_link_state` so
    `po_ref` / `spo_ref` / `po_line_id` are derived from the links first - that function
    leaves an actioned row's state alone, which is exactly why the order matters - and the
    links stay visible on the worklist through `links_for_rows`.

    A row on a still-open line keeps whatever its links make it.
    """
    from app.models.project_so import INQUIRY_ACTIONED

    for row in rows:
        row.state = INQUIRY_ACTIONED
        # The uploader, when a person queued this. Never blanked: `_write_link` may already
        # have written the act-as principal on an unattended run, and NULL says less.
        row.actioned_by = actor or row.actioned_by
        row.actioned_at = now


def _apply_settle_recovery(entry: Any, match: _Match, now: datetime) -> None:
    """2.1(b) (AC-RB-11): the row's Now becomes the ACTIVE decision's own buy quantity and
    date, its Was the sheet's own - the same fields `project_order_inquiry_service.
    _settle_row_in_place` writes when a planning change restates a line in place, and the
    same Was fragment format, so a recovered row reads exactly as if a confirm had just
    restated it.
    """
    from app.models.project_so import ACK_CHANGED
    from app.services.project_order_inquiry_service import _qty_str

    previous_qty = entry.qty
    previous_date = entry.delivery_date
    entry.qty = match.settle_buy_qty
    if match.settle_required_date is not None:
        entry.delivery_date = match.settle_required_date
    entry.previous_qty = previous_qty
    entry.previous_delivery_date = previous_date
    entry.supply_decision_id = match.settle_decision_id
    entry.changed_at = now
    entry.ack_state = ACK_CHANGED
    fragment = (
        f"Was {_qty_str(previous_qty)} on {previous_date.isoformat()}"
        if previous_date
        else f"Was {_qty_str(previous_qty)}, no previous delivery date"
    )
    entry.note = f"{entry.note}; {fragment}" if entry.note else fragment


def _document_facts_for_link(db: Session, link: Any) -> Dict[str, Any]:
    """Supplier and expected date for the document `link` already names, for the note stamp
    `_write_link` writes when 2.2 moves it - looked up directly rather than through
    `_target_facts`, which filters to LIVE remaining capacity and would refuse the very
    closed or fully-received line a received link sits on.
    """
    row = None
    if link.po_line_id:
        row = (
            db.query(Supplier.supplier_name, PurchaseOrderLine.expected_date)
            .select_from(PurchaseOrderLine)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .filter(PurchaseOrderLine.id == link.po_line_id)
            .first()
        )
    elif link.spo_allocation_id:
        row = (
            db.query(Supplier.supplier_name, SPOAllocation.expected_date)
            .select_from(SPOAllocation)
            .outerjoin(Supplier, Supplier.id == SPOAllocation.supplier_id)
            .filter(SPOAllocation.id == link.spo_allocation_id)
            .first()
        )
    return {
        "document": link.document,
        "supplier_name": row[0] if row else None,
        "expected_date": row[1] if row else None,
        "po_line_id": link.po_line_id,
        "spo_allocation_id": link.spo_allocation_id,
    }


def _move_received_links(
    db: Session, service: Any, used_row: Any, sibling_id: str, link_actor: str
) -> Optional[Any]:
    """2.2 (AC-RB-6/7/8/9/10, rulings R1/R2): a used row raised by 2.1(a) takes over its
    `Replaces N used` sibling's RECEIVED links, up to its OWN quantity - through
    `_write_link`, the one link writer, so the claim at that identity is REUSED rather than
    duplicated (both rows share the same order inquiry header, mirror and item code, so
    `claim_placed_on_po` resolves onto the claim the sibling's own link already wrote). An
    OPEN link never moves (AC-RB-8): `_received_documents_for` is the SAME received test
    `_redirect_row_if_received` already applies.

    A link bigger than the used row's own quantity is REDUCED, not deleted, so the
    sibling keeps what the used row does not need (AC-RB-7).

    Returns the sibling row when anything actually moved, so the caller can resync its own
    derived fields too - `None` when there was nothing received to move.
    """
    from app.models.project_so import OrderInquiryRow

    sibling = db.get(OrderInquiryRow, sibling_id)
    if sibling is None:
        return None
    links = service._links_of(sibling.id)
    if not links:
        return None
    received = service._received_documents_for(links)
    received_links = [link for link in links if str(link.id) in received]
    if not received_links:
        return None
    remaining = _dec(used_row.qty)
    moved = False
    for link in received_links:
        if remaining <= _ZERO:
            break
        take = min(remaining, _dec(link.qty))
        if take <= _ZERO:
            continue
        candidate = _document_facts_for_link(db, link)
        service._write_link(used_row, candidate, take, actor_user_id=link_actor)
        if take >= _dec(link.qty):
            service._remove_links(sibling, [link])
        else:
            link.qty = _dec(link.qty) - take
        remaining -= take
        moved = True
    return sibling if moved else None


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
    if not parsed.ok:
        if on_total_rows is not None:
            on_total_rows(len(parsed.rows))
        return _empty(parsed)

    link_actor = _link_actor(actor)
    if not link_actor:
        # Every row this raises is born ACKNOWLEDGED and every link records who made it, so
        # an upload with nobody to attribute it to would write a page of decisions no one
        # can be asked about (security review N1, 14 Sep). The route always has an actor;
        # this guards a direct caller. Refused whole rather than half-written.
        if on_total_rows is not None:
            on_total_rows(len(parsed.rows))
        refused = _empty(parsed)
        refused["ok"] = False
        refused["problems"] = list(parsed.problems) + [NO_ACTOR_PROBLEM]
        return refused

    plan = _plan(db, parsed)
    # After `_plan`, not before (AC-M-10): a `+` cell splits into one row per member, and
    # `ImportOutcome` records one outcome per member row, so the job page's total must be
    # the EXPANDED count - never `len(parsed.rows)`, the sheet's own row count.
    if on_total_rows is not None:
        on_total_rows(plan.rows_expanded)
    links, not_linkable = _pair(db, plan)

    now = _now()
    stamped = _stamp_orders(plan)
    raiser = _Raiser(db, actor, now, _matched_lines_by_order(plan))
    service = None
    linked: List[Any] = []
    history: List[Any] = []
    raised = 0
    #: Mirrors touched by a repair this run, resynced once each (S5) after the loop -
    #: never inline, since a line's second dated row can still repair a sibling migrated
    #: row on the SAME mirror later in this same loop.
    repaired_mirrors: set = set()
    #: Mirror id -> (earliest date, total qty) over its `redirected_to_pool` migrated rows,
    #: captured BEFORE the first repair this run writes to that mirror (B3, 19 Sep 2026):
    #: `_resync_sibling_was_now` must compare a sibling's Was/Now against what the mirror
    #: looked like before this run touched it, never against its own already-mutated state.
    before_repair: Dict[str, Tuple[Optional[date], Optional[Decimal]]] = {}

    # N8, 19 Sep 2026: one query for every row this run will repair, not one `db.get` per
    # row inside the loop below.
    from app.models.project_so import OrderInquiryRow

    repair_ids = [m.repair_row_id for m in plan.matches if m.repair_row_id]
    repaired_rows = {
        str(r.id): r
        for r in db.query(OrderInquiryRow).filter(OrderInquiryRow.id.in_(repair_ids)).all()
    } if repair_ids else {}

    for index, match in enumerate(plan.matches):
        row = match.row
        identity = _identity(row)
        if match.duplicate:
            # Nothing is skipped: this row's quantity IS the instruction that was raised,
            # written out twice by a book that restates itself across tabs (D7). Reported as
            # a skip it would read as loss.
            outcome.unchanged(row=row.source_row, code=oc.RESTATES_AN_INSTALMENT,
                              identity=identity, value=row.so_number)
            continue
        if match.code:
            # `order_not_found`, `order_not_plannable` or `invalid_quantity` - whichever
            # refusal the plan reached first.
            outcome.skip(row=row.source_row, code=match.code,
                         identity=identity, value=row.so_number)
            continue
        if match.reason:
            outcome.skip(row=row.source_row, code=match.reason,
                         identity=identity, value=row.so_number)
            continue
        if match.already_raised:
            # The line is not raised again (D2), but a re-upload of a corrected sheet is
            # how a MIGRATED row's stale date gets fixed (18 Sep 2026 reversal of 7.4).
            # `_resolve_delivery_date_repairs` already decided WHICH row, read-only, in
            # `_plan` (S1) - this only writes it, so `preview`'s forecast and what `apply`
            # actually does cannot drift apart.
            if match.repair_row_id is not None:
                migrated = repaired_rows[match.repair_row_id]
                if match.repair_shape == "B":
                    # Shape B, round 5 (19 Sep 2026, prod feedback): the row's Now
                    # (`qty`/`delivery_date`) is a planning change's own settle and is
                    # never touched here - only its WAS side, which still carries 7.4's
                    # mistake. No sibling resync (that reads `redirected_to_pool` rows'
                    # own `delivery_date`, which this never moves) and no handshake stamp
                    # (`changed_at`/`ack_state` untouched) - this is the same data repair
                    # shape A is, just on the other pair of columns.
                    from app.services.project_order_inquiry_service import _qty_str

                    old_was = migrated.previous_delivery_date
                    migrated.previous_delivery_date = row.delivery_date
                    qty_str = _qty_str(_dec(migrated.previous_qty))
                    old_fragment = f"Was {qty_str} on {old_was.isoformat()}"
                    new_fragment = f"Was {qty_str} on {row.delivery_date.isoformat()}"
                    if migrated.note and old_fragment in migrated.note:
                        migrated.note = migrated.note.replace(old_fragment, new_fragment, 1)
                    outcome.updated(row=row.source_row, code=oc.DELIVERY_DATE_UPDATED,
                                     identity=identity, value=row.so_number,
                                     entity_type="order_inquiry_row", entity_id=migrated.id,
                                     message="Was date corrected to the sheet's own")
                    continue
                if match.repair_shape == "C":
                    # Shape C, round 7 (19 Sep 2026, owner go): the LIVE row that
                    # replaced a migrated row a reconfirm cancelled -
                    # `_resolve_shape_c_repairs` already found the cancelled sibling
                    # that identifies this sheet row; only the LIVE row is written here,
                    # the cancelled sibling is read-only. Now (`qty`/`delivery_date`),
                    # `state` and `ack_state` are all untouched; no sibling resync
                    # (there is no `redirected_to_pool` row behind this shape).
                    from app.services.project_order_inquiry_service import _qty_str

                    qty_str = _qty_str(_dec(row.qty))
                    fragment = f"Was {qty_str} on {row.delivery_date.isoformat()}"
                    migrated.previous_qty = _dec(row.qty)
                    migrated.previous_delivery_date = row.delivery_date
                    # Anchored (round 7 review, tightened round 7 review round 2 -
                    # BLOCKER): a plain `find("Was ")` + `existing_note[:was_at]` prefix
                    # rebuild drops EVERYTHING after the old fragment, which loses real
                    # prose a live row can carry beside it (a probe's own linkage note,
                    # "; Linked to ... ; auto: autocount linkage"). Matched by REGEX and
                    # spliced IN PLACE instead, so the tail survives byte for byte;
                    # appended only when the row carries no fragment to anchor onto at
                    # all.
                    existing_note = migrated.note or ""
                    anchor = re.search(r"Was \S+ on \d{4}-\d{2}-\d{2}", existing_note)
                    if anchor is None:
                        migrated.note = (
                            f"{existing_note}; {fragment}" if existing_note else fragment
                        )
                    else:
                        migrated.note = (
                            existing_note[: anchor.start()]
                            + fragment
                            + existing_note[anchor.end():]
                        )
                    outcome.updated(
                        row=row.source_row, code=oc.DELIVERY_DATE_UPDATED,
                        identity=identity, value=row.so_number,
                        entity_type="order_inquiry_row", entity_id=migrated.id,
                        message="Was adopted from the sheet (migrated row superseded)",
                    )
                    continue
                mirror_id = str(migrated.so_line_id)
                if mirror_id not in repaired_mirrors:
                    # The FIRST repair on this mirror this run - snapshot before anything
                    # on it is mutated (B3).
                    before_repair[mirror_id] = _redirected_earliest_and_qty(db, mirror_id)
                migrated.delivery_date = row.delivery_date
                repaired_mirrors.add(mirror_id)
                outcome.updated(row=row.source_row, code=oc.DELIVERY_DATE_UPDATED,
                                 identity=identity, value=row.so_number,
                                 entity_type="order_inquiry_row", entity_id=migrated.id)
            elif match.no_used_delivery_match:
                # AC-RB-3 (R6): this line carries a `Replaces N used` row, but neither its
                # quantity nor its date matches the fresh row's own previous figures - never
                # guessed at, and named under its own code rather than the ordinary
                # ALREADY_RAISED so purchasing and CS know which delivery to look at by hand.
                outcome.skip(row=row.source_row, code=oc.NO_USED_DELIVERY_MATCH,
                             identity=identity, value=row.so_number)
            elif match.top_up_sum_mismatch:
                # AC-RB-27 (R8): the line's live ORDER rows all carry the active decision,
                # but the sheet row's quantity plus theirs does not equal its `buy_qty` -
                # never guessed at, named under its own code for the same reason as above.
                outcome.skip(row=row.source_row, code=oc.TOP_UP_SUM_MISMATCH,
                             identity=identity, value=row.so_number)
            else:
                outcome.skip(row=row.source_row, code=oc.ALREADY_RAISED,
                             identity=identity, value=row.so_number)
            continue

        entry = raiser.raise_row(match, plan.orders[row.so_number], file_name=file_name)
        if entry is None:
            # The plan said this order was plannable and the adoption service disagreed, so
            # there is no row for its links to hang off either. Dropped from the tally rather
            # than counted, or the result would report a link nothing carries.
            links.pop(index, None)
            outcome.skip(row=row.source_row, code=oc.ORDER_NOT_PLANNABLE,
                         identity=identity, value=row.so_number)
            continue
        raised += 1
        if match.settle_decision_id:
            # 2.1(b) (AC-RB-11): the row's Now/Was is the decision's, not the sheet's own -
            # written AFTER the raise, over the ordinary fields `raise_row` just set.
            _apply_settle_recovery(entry, match, now)
        outcome.success(row=row.source_row, code=oc.CREATED, identity=identity,
                        value=row.so_number, entity_type="order_inquiry_row",
                        entity_id=entry.id)
        if not _is_open_demand(match.core_line):
            history.append(entry)

        held = links.get(index)
        if held or match.used_sibling_id:
            if service is None:
                from app.services.project_order_inquiry_service import ProjectOrderInquiryService

                service = ProjectOrderInquiryService(db)
            entry_touched = False
            if held:
                for take in held.takes:
                    # `_write_link` is the ONE writer of a link, its audit claim and the
                    # row's note stamp. Called directly rather than through
                    # `place_on_po_allocations`, whose open-line gate is exactly what D8
                    # removes: history is closed lines.
                    service._write_link(
                        entry,
                        take,
                        take["qty"],
                        actor_user_id=link_actor,
                        auto_trigger=_AUTOCOUNT_TRIGGER if take["from_book"] else None,
                    )
                entry_touched = True
            if match.used_sibling_id:
                # 2.2 (AC-RB-6/7/8/9/10): the used row takes over its sibling's RECEIVED
                # links, up to its own quantity - separate from the book pairing above,
                # which this line's own citation may or may not also have found.
                sibling = _move_received_links(
                    db, service, entry, match.used_sibling_id, link_actor,
                )
                if sibling is not None:
                    entry_touched = True
                    linked.append(sibling)
            if entry_touched:
                linked.append(entry)

    if service is not None and linked:
        # ONCE, for every row this upload linked. `refresh_link_state` re-derives each
        # inquiry's bundles before reading the links, so calling it per row would redo that
        # derivation for the whole inquiry on every row of a sheet that names it.
        service.refresh_link_state(linked)

    for mirror_id in repaired_mirrors:
        old_earliest, old_total_qty = before_repair.get(mirror_id, (None, None))
        _resync_sibling_was_now(db, mirror_id, old_earliest, old_total_qty)

    _close_history(history, actor, now)
    db.flush()
    return _result(plan, links, not_linkable, rows_raised=raised,
                   orders_adopted=raiser.adopted, orders_stamped=stamped)
