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
line of the order a row lands on when several fit - but only after the line whose required
date IS the sheet's date, and a cancelled August-extract ghost line ranks behind any real
line that fits.

Two honest limits, each counted and named rather than smoothed over.

**A row can only be raised against a line that exists.** A sales order the CRM does not hold
is named under `sales_orders_not_found` and nothing is invented for it; a row whose item,
location or quantity fits no line of that order is reported with the FIRST reason it failed.

**A line that already carries an order inquiry row is left exactly as it is** (D2). The sheet
is a migration, not a source of truth about rows somebody has since worked on, so a re-upload
writes nothing new.

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
    #: The third term of the line pick reads it, before any pairing happens.
    bought_refs: set = field(default_factory=set)
    #: The rows that set was derived from, kept so `_pair` groups them into the pairing's
    #: first source rather than reading the same two queries a second time.
    bought_rows: Optional[Tuple[List[Any], List[Any]]] = None
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
    blank - and `_plan` lends that citation to the row it restates rather than discarding it
    with the duplicate. An ORDER BACK row carries no delivery date at all, so the date still
    tells it apart from a dated row.
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
    """
    item_code = (row.item_code or "").strip()
    if "+" not in item_code or item_code in line_codes:
        return [row]
    return [
        replace(row, item_code=member)
        for member in (m.strip() for m in re.split(r"\s*\+\s*", item_code))
        if member
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

    A real line before a cancelled one, first of all - 10,499 cancelled August-extract ghosts
    are still in the book, and a ghost is never what a live sheet row means while a real line
    fits. A cancelled line is ranked last, never excluded: when it is the only line that fits
    it is still where the history is (D1 kept).

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
    already_raised: set,
    bought: set,
) -> Tuple[Optional[tuple], Optional[str]]:
    """The line for one sheet row, or the FIRST filter that refused it.

    Item, then location, then quantity - reported in that order because that is the order a
    person checks them in, and "no line for this item" and "location differs" send them to
    two different places.

    The quantity test is against what the line ORDERED, less what EARLIER rows of this same
    file already took of it: the sheet may split one line across several rows (AC-S1-2), and
    the importer never splits one itself.

    A row that lands on a line whose mirror ALREADY carries an inquiry takes nothing from
    that ledger (review finding 9, 14 Sep): it is skipped rather than raised, so charging
    its quantity to the line would push the NEXT row of the same file onto
    `qty_exceeds_ordered` for a quantity nobody used.
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

    found = sorted(fits, key=_rank_for(row, bought))[0]
    if str(found[0].id) not in already_raised:
        taken[str(found[0].id)] = taken.get(str(found[0].id), _ZERO) + qty
    return found, None


def _already_raised(
    db: Session, core_lines: Sequence[SalesOrderLine]
) -> Tuple[set, Dict[str, str]]:
    """The core lines whose MIRROR already carries a non-cancelled order inquiry row (D2),
    and the core-line-id -> mirror-id map that answer was read off (S3, 19 Sep 2026):
    `_resolve_delivery_date_repairs` needs the same map and must not re-query it.

    Read off the state BEFORE this upload, once, and for every line the named orders carry
    rather than only the matched ones, because the matcher consults it as it goes: the
    answer decides whether a matched line's quantity is charged to this file's ledger.

    Two rows of the same file may still both land on one line - nothing here changes as the
    file is read - while a re-upload of that file raises nothing new.
    """
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow, ProjectSalesOrderLine

    if not core_lines:
        return set(), {}
    core_ids = [str(line.id) for line in core_lines]
    mirrors = (
        db.query(ProjectSalesOrderLine.id, ProjectSalesOrderLine.core_sales_order_line_id)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(core_ids))
        .all()
    )
    if not mirrors:
        return set(), {}
    core_by_mirror = {str(mirror_id): str(core_id) for mirror_id, core_id in mirrors}
    mirror_by_core = {core_id: mirror_id for mirror_id, core_id in core_by_mirror.items()}
    held = (
        db.query(OrderInquiryRow.so_line_id)
        .filter(
            OrderInquiryRow.so_line_id.in_(list(core_by_mirror)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    raised = {
        core_by_mirror[str(mirror_id)] for (mirror_id,) in held if str(mirror_id) in core_by_mirror
    }
    return raised, mirror_by_core


def _resolve_line_repairs(
    dated_rows: Sequence[Tuple[int, Any]], migrated_rows: Sequence[Any]
) -> Dict[int, str]:
    """B1, 19 Sep 2026: which migrated row (if any) each dated sheet row of ONE already-
    raised line would repair. Pure and deterministic - no database access - so the same
    inputs always resolve the same way.

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
    return repairs


def _resolve_delivery_date_repairs(db: Session, plan: _Plan) -> None:
    """B1/S1/S3/S8/S10/S13, 19 Sep 2026: decide, ONCE and read-only, which already-raised
    sheet rows would repair which migrated row - so `preview` can forecast
    `rows_delivery_date_updated` and `apply` writes exactly what was forecast, never
    recomputing the decision.

    **B2, purchasing's own work is never touched.** Eligible migrated rows carry
    `previous_qty IS NULL AND previous_delivery_date IS NULL AND changed_at IS NULL` - no
    planning change has restated this row since the sheet raised it. A row a change HAS
    settled (5,793 of 11,810 migrated rows on the 15 Sep prod copy carry a link; SO314593's
    own rows are linked, received, some redirected to the pool) keeps the change's own
    date: this is a repair of the MIGRATION's mistake, not a second opinion about a decision
    purchasing has since made, and it writes no handshake stamp of its own (no `changed_at`,
    no ack flip) for the same reason - purchasing already works to the sheet's date.

    **S8, confined to 7.4's own artefacts.** Eligible only when the migrated row's
    `delivery_date` still equals its CORE LINE's `required_date` - that is exactly what 7.4
    wrote and nothing else does. A row that already carries a date the line does not (a
    sheet date raised under this fix, or one a person edited) is never rewritten by a later
    sheet: the sheet is a migration, not a second opinion. Compared in PYTHON against
    `required_date_by_mirror`, not one `OR`-of-per-line-equality clause in SQL (S13, 19 Sep
    2026 perf round): `delivery_date` is not indexed, so at prod scale (11,500 already-raised
    mirrors on a full book re-upload) that clause is an 1.1 MB statement forcing a Seq Scan
    (measured 753 ms) where `so_line_id.in_(mirror_ids)` alone still uses the index.

    Repairs are resolved per LINE (`_resolve_line_repairs`), never per row, and grouped by
    MIRROR so every already-raised line's migrated siblings are loaded in ONE query (S3),
    selecting only the columns the resolver (and the S8 comparison) read (S10) rather than
    hydrating full rows - 233 migrated rows shared a `(mirror, item, qty)` group on the 15
    Sep prod copy alone, and a book re-upload can touch all of `scm.order_inquiry_row`'s
    ~11.8k migrated rows.
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

    rows = (
        db.query(OrderInquiryRow)
        .with_entities(
            OrderInquiryRow.id,
            OrderInquiryRow.so_line_id,
            OrderInquiryRow.item_code,
            OrderInquiryRow.qty,
            OrderInquiryRow.delivery_date,
        )
        .filter(
            OrderInquiryRow.so_line_id.in_(mirror_ids),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.previous_qty.is_(None),
            OrderInquiryRow.previous_delivery_date.is_(None),
            OrderInquiryRow.changed_at.is_(None),
            OrderInquiryRow.note.like(f"{_MIGRATION_STAMP}%"),
        )
        .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
        .all()
    )
    migrated_by_mirror: Dict[str, List[Any]] = {}
    for candidate in rows:
        mirror_id = str(candidate.so_line_id)
        # S8, done here rather than in SQL (S13): a required_date of `None` matches
        # nothing - a migrated row's `delivery_date` is never `None` - so a line with no
        # required date of its own is correctly never a repair candidate.
        required = required_date_by_mirror.get(mirror_id)
        if required is None or candidate.delivery_date != required:
            continue
        migrated_by_mirror.setdefault(mirror_id, []).append(candidate)

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
        repairs = _resolve_line_repairs(dated_rows, migrated_by_mirror.get(mirror_id, []))
        for index, migrated_id in repairs.items():
            plan.matches[index].repair_row_id = migrated_id


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

    raised_already, plan.mirror_by_core_line = _already_raised(
        db, [held[0] for group in lines.values() for held in group]
    )
    #: Which candidate lines the book BOUGHT for, over every line of every order the sheet
    #: names rather than only the matched ones - the line pick asks the question before a row
    #: has a line, so the answer cannot wait for the match. `_pair` groups the same rows.
    plan.bought_rows = _bought_rows(
        db, [held[0] for group in lines.values() for held in group]
    )
    plan.bought_refs = _bought_refs(plan.bought_rows)
    #: How much of each line this FILE has already spoken for, in file order.
    taken: Dict[str, Decimal] = {}

    #: Every instruction this file has already stated, whichever tab stated it.
    stated: set = set()

    for match in plan.matches:
        row = match.row
        key = _restates(row)
        if key in stated:
            # Counted, never matched: a restatement must not take the line's quantity from
            # the row it restates, or the second tab would read `qty_exceeds_ordered`.
            match.duplicate = True
            continue
        stated.add(key)
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
        found, match.reason = _match_row(
            row, lines.get(str(order.id)) or [], taken, raised_already, plan.bought_refs,
        )
        if found is not None:
            match.core_line, match.line_location = found[0], found[2] or None
            match.already_raised = str(found[0].id) in raised_already

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


def _pair(db: Session, plan: _Plan) -> Tuple[Dict[int, _RowLinks], List[str]]:
    """What each raisable row would be linked to, in the order the two sources rank.

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

    ref_allocations, ref_po_lines = _ref_targets(plan.bought_rows or ([], []))

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
        {str(m.core_line.product_id or "") for _, m in wanted},
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

        product = str(match.core_line.product_id or "")

        def _through_po(po_line_id: str) -> None:
            """A purchase order line the book named: its shipping orders first (D10), the
            purchase order line itself only for what they cannot cover.

            The shipping orders THIS LINE became, where the feed says so, and only otherwise
            the ones the whole document became: one purchase order can carry five lines of
            the same item for five different sales order lines, and the quantity is owed
            against the container that holds this one.
            """
            fact = facts.get(str(po_line_id))
            if fact is None:
                return
            exact = chain_by_line.get(
                (str(fact["document"]), str(fact.get("source_ref") or ""), product)
            )
            for allocation_id in (exact or chain.get((str(fact["document"]), product), [])):
                if held.need_left <= _ZERO:
                    break
                take(allocation_id, from_book=True)
            if held.need_left > _ZERO:
                take(str(po_line_id), from_book=True)

        ref = (match.core_line.source_ref or "").strip()
        if ref:
            for allocation_id in ref_allocations.get((ref, product), []):
                if held.need_left <= _ZERO:
                    break
                take(allocation_id, from_book=True)
            for po_line_id in ref_po_lines.get((ref, product), []):
                if held.need_left <= _ZERO:
                    break
                _through_po(po_line_id)

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
            _through_po(claim["target_id"])

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
        (f"{out['rows_delivery_date_updated']:,} rows are on a line that already carries "
         f"an order inquiry; the migrated row's delivery date will be corrected to the "
         f"sheet's own") if out["rows_delivery_date_updated"] else None,
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
        outcome.success(row=row.source_row, code=oc.CREATED, identity=identity,
                        value=row.so_number, entity_type="order_inquiry_row",
                        entity_id=entry.id)
        if not _is_open_demand(match.core_line):
            history.append(entry)

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

    for mirror_id in repaired_mirrors:
        old_earliest, old_total_qty = before_repair.get(mirror_id, (None, None))
        _resync_sibling_was_now(db, mirror_id, old_earliest, old_total_qty)

    _close_history(history, actor, now)
    db.flush()
    return _result(plan, links, not_linkable, rows_raised=raised,
                   orders_adopted=raiser.adopted, orders_stamped=stamped)
