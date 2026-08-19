"""The multi-order planning board: dates across, products down, one pile per location.

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` section 13,
and the Phase 1 shapes in
`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts`.

The board is a LENS. It writes nothing, holds no decision object of its own, and creates no
status: `projects.so_supply_decisions` stays keyed per sales order, and a cell cuts across
orders, so a cell could never be the unit of persistence (13.4). Everything here is a read.

Four ideas carry the file.

**Nothing about supply is recomputed here.** Free stock is `ProjectSupplyService`'s own
figure through `free_stock_by_location`, and the division of one location's pile is
`attribute_sources`, the same pure engine the per-order sheet runs. What the board adds is
the ORDER the pile is served in, which is the one thing that genuinely differs (13.5).

**The ranking is the reorder engine's policy, not a second one.** `scm.priority_policy`
through `app.services.scm.priority.factors_for_demand_rows` - same row, same
`SUM(w*v) / SUM(w present)`, same rule that an absent factor is dropped from both sums and
never scored zero. The board states which policy produced what is on screen, and says so when
that policy separates nothing at all rather than showing a plausible-looking order it did not
earn.

**Every date keeps its own column.** There is no aggregate for the past: a line owed in July
2022 is shown in July 2022, marked as past, not merged into an "Overdue" pile with everything
else. The earlier build had that pile and on real data it swallowed 160 of 160 lines into one
column, which is precisely the schedule the planner opened the board to read.

**Allocation is per (product, LOCATION), never across.** Free stock at one warehouse cannot
cover a line that must be fulfilled from another; moving it is a transfer, which is M9's job
and a non-goal here (13.7). One cell therefore legitimately spans several locations, and the
source strip says which.

**The contest is shown, not hidden.** `_free_stock` nets CONFIRMED holds only, so two orders
composed separately can both be proposed the same stock and the second only finds out when
its confirmation is refused (13.5.1). Here they are in one cell: the higher-ranked row takes
the stock, and every row that lost is marked `contested` with a reason naming who took it.
The locking fix belongs to the confirmation path and is not attempted here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import (
    DECISION_ACTIVE,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException
from app.services.project_supply_service import (
    ProjectSupplyService,
    _dec,
    _leading_factor,
    _open_of,
)
from app.services.scm import priority
from app.services.scm.demand import demand_qty, is_open_demand, is_plan_demand_line
from app.services.scm.front_planning_engine import (
    BORROW,
    BUY,
    RESERVE,
    TIMELY_SPO,
    qty_text,
)

_ZERO = Decimal("0")

#: How many orders may be planned together (13.2). Not arbitrary: the whole book is 862
#: products across 349 dates, roughly 300,000 cells, which is not a screen. The bound is part
#: of the design rather than a guard bolted on, so it is stated when it bites.
BOARD_ORDER_CAP = 50

#: The one column that is not a bucket of time. An absent required date has no period to be
#: put in, and guessing one is the same class of silent wrong answer as guessing a warehouse,
#: so it gets its own column, pinned last.
#:
#: There is deliberately NO aggregate column for the past. An earlier build lumped every past
#: date into one "Overdue", and on real data that swallowed 160 of 160 lines into a single
#: column - which destroys exactly the schedule the planner opened the board to read. A date
#: in the past is still a date; what it needs is to be MARKED, not merged (see `is_past`).
NO_DATE_BUCKET = "no_date"

#: Day granularity renders a window, not a column per distinct date (13.3). A DISPLAY bound
#: only: nothing is filtered out of the plan by it, and demand outside it is reached by moving
#: the window.
DAY_WINDOW_COLUMNS = 30

GRANULARITIES = ("day", "week", "month")

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

#: What the Order Inquiry feed writes into `sales_orders.internal_note` when it cannot resolve
#: the project to a customer. Stripped for display, never shown with its own prefix.
_PROJECT_NOTE_PREFIX = "Order Inquiry project:"


def week_start(when: date) -> date:
    """The Monday of the ISO week containing `when`."""
    return when - timedelta(days=when.weekday())


def bucket_key_for(
    required_date: Optional[date], as_of: date, granularity: str
) -> str:
    """Which column a line belongs in: its own period, whether that period is past or future.

    Nothing is aggregated by age. The captain, on seeing the earlier build: "don't put overdue
    together, still split by the date, don't put under overdue". A line owed in July 2022 is
    owed in July 2022, and collapsing three years of them into one column destroys the schedule
    the board exists to show.

    `as_of` therefore takes NO part in the key, and is kept in the signature on purpose: the
    key is what the frontend rebuilds (`bucketKeyFor` in `_shared/lib/fulfilmentBoard.ts`), the
    two must stay the same function, and dropping the argument on one side only would be a
    silent divergence. Whether a period has already passed is reported separately, as a flag
    (`is_past`), because a bucket that is past today is not past-SHAPED - it is just old.

    Bucketing is a DISPLAY choice and nothing is ever stored bucketed: every contribution
    carries the line's own real `required_date`, and the allocation sorts on the ranking,
    never on the bucket.
    """
    if required_date is None:
        return NO_DATE_BUCKET
    if granularity == "month":
        return required_date.replace(day=1).isoformat()
    if granularity == "day":
        return required_date.isoformat()
    return week_start(required_date).isoformat()


def bucket_end(key: str, granularity: str) -> Optional[date]:
    """The last date the bucket covers, or None for the dateless column."""
    if key == NO_DATE_BUCKET:
        return None
    start = date.fromisoformat(key)
    if granularity == "day":
        return start
    if granularity == "week":
        return start + timedelta(days=6)
    following = (
        date(start.year + 1, 1, 1) if start.month == 12
        else date(start.year, start.month + 1, 1)
    )
    return following - timedelta(days=1)


def _bucket_label(key: str, granularity: str) -> str:
    if key == NO_DATE_BUCKET:
        return "No date"
    when = date.fromisoformat(key)
    month = _MONTHS[when.month - 1]
    if granularity == "month":
        return f"{month} {when.year}"
    if granularity == "day":
        return f"{when.day} {month} {when.year}"
    return f"w/c {when.day} {month} {when.year}"


#: Said by every rung the ladder reached after the line was already covered. One sentence, in
#: one place, so five rungs cannot phrase the same fact five ways.
_COVERED_BEFORE = "Fully covered before this rung."

#: What each ranking factor MEANS when it is the reason another line stands in front of you.
#: The planner's words, matching the frontend's `factorLabel` map subject for subject: the
#: policy's own keys (`need_by_date`) are exactly what the rank chips were told to stop showing.
_AHEAD_PHRASES = {
    "need_by_date": "an earlier delivery date",
    "document_age": "an older order date",
    "customer_credit": "shorter payment terms",
    "demand_class": "a higher-ranked demand type",
    "po_document_sequence": "an earlier purchase order sequence",
    #: Not policy factors at all: these three are the tie-break, in `_pile_book`'s own order
    #: (delivery date, then line number within an order, then sales-order number), and naming
    #: a factor here would claim a score difference the two lines do not have.
    "earlier_date": "the same rank and an earlier delivery date",
    "line_order": "an earlier line number in the same order",
    "tie_break": "the same rank and a lower sales order number",
}


def _ahead_phrase(by_factor: Optional[Dict[str, int]]) -> str:
    """Why the queue is ahead, in at most two reasons.

    The two commonest, biggest first. Naming all five would be a paragraph, and a paragraph is
    what the captain rejected ("the justification needs to be STRUCTURED").
    """
    ranked = sorted((by_factor or {}).items(), key=lambda item: (-item[1], item[0]))
    phrases = [_AHEAD_PHRASES.get(key, key.replace("_", " ")) for key, _n in ranked[:2]]
    if not phrases:
        return "a higher rank"
    return " or ".join(phrases)


def _date_words(when: Optional[date]) -> str:
    """A date as it is said out loud: `3 Sep 2026`. Never ISO inside a sentence."""
    if when is None:
        return "an unstated date"
    return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"


def _project_key(label: Optional[str]) -> Optional[str]:
    """A stable key a pivot may group a project by.

    The board can be read with SALES ORDER, CUSTOMER or PROJECT down the side instead of
    product, and a pivot must never merge two subjects that merely read alike. For a customer
    that is `customer_id`. For a project there is no id to use: an order adopted from the
    AutoCount book has no project registration by design (plan section 4), and the project
    string the sheet named is the only identity it has. So the key is that string, normalised -
    case-folded with its whitespace collapsed - which merges "PP CHIN HIN / KIN TONG" with
    "PP Chin Hin /  Kin Tong" and nothing else. Null when the order names no project.
    """
    if not label:
        return None
    return " ".join(label.split()).casefold() or None


def _project_label_from_note(note: Optional[str]) -> Optional[str]:
    text_value = (note or "").strip()
    if not text_value:
        return None
    if text_value.startswith(_PROJECT_NOTE_PREFIX):
        return text_value[len(_PROJECT_NOTE_PREFIX):].strip() or None
    return text_value


def _project_label(order: SalesOrder) -> Optional[str]:
    return _project_label_from_note(order.internal_note)


class _Row:
    """One still-owed core sales-order line, which is all the board is ever built from."""

    __slots__ = (
        "line_id", "sales_order_id", "so_number", "customer_id", "customer_name",
        "agent_code", "agent_label",
        "project_label", "order_date", "line_no", "item_code", "product_id", "qty",
        "required_date", "warehouse_id", "location", "priority", "demand_class",
        "payment_terms_days", "bucket_key", "is_past", "rank_score", "rank_factors",
        "sources", "trail", "contested", "qty_ordered", "qty_delivered", "proposed",
        "free_before",
        "raw_facts", "taken_before", "last_taker", "borrow_candidates",
        "project_sales_order_id", "project_line_id", "warehouse_ids", "project_key",
        "so_qty_ahead", "lines_ahead", "available_to_this_line",
        "decision", "item_flags",
    )

    def __init__(self, **kw: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))
        self.rank_score = 0.0
        self.rank_factors = []
        self.sources = []
        # The ladder as it was walked for this line, rung by rung. Empty for an unplannable
        # line: no ladder was walked for it.
        self.trail = []
        self.contested = False
        self.is_past = False
        # Filled by `_allocate`: what the engine proposes for this line, by kind, and what was
        # still unclaimed at its location when this line was reached.
        self.proposed = {}
        self.free_before = None
        self.raw_facts = {}
        # Who had already drawn this line's pile down when it was reached, and how much - the
        # evidence behind `contested` and behind the sentence a Buy carries.
        self.taken_before = None
        self.last_taker = None
        self.borrow_candidates = []
        # Warehouse CODE -> id, for the locations this line's Reserve may name. A confirm
        # component addresses a warehouse by id and the screen reads a code, so the pair has
        # to travel together (the same reason `SupplyComponent.source_warehouse_id` exists).
        self.warehouse_ids = {}
        # The queue in front of this line at its own pile, and what it left behind. None on a
        # covered line, which is not in that queue at all - see `covered`.
        self.so_qty_ahead: Optional[Decimal] = _ZERO
        self.lines_ahead: Optional[int] = 0
        self.available_to_this_line: Optional[Decimal] = _ZERO
        # What the order's ACTIVE revision froze for this line, when it covers it (13.4).
        self.decision: Optional[Dict[str, Any]] = None
        # The item facts the ladder judged this line on (dealer hot-selling and where,
        # discontinued, whether anybody classified it). None on a line the ladder never
        # walked - unplannable or covered - because `false` there would claim a judgement that
        # was never made.
        self.item_flags: Optional[Dict[str, Any]] = None

    @property
    def covered(self) -> bool:
        """An active decision already covers this line, so nothing is proposed for it.

        The board kept re-planning such a line - "Buy 43" beside a confirmed borrow of 10 and
        buy of 33 - because it stayed in the board's demand while the pile's own queue
        (`_pile_book`) rightly left it out: it asked the projection for a share it is
        deliberately not in, got nothing, and read that as "nothing is ahead of you".
        """
        return self.decision is not None

    @property
    def unplannable(self) -> bool:
        """No location on the sales-order line, so nothing can be sourced for it (AC-FP16)."""
        return not self.warehouse_id

    @property
    def key(self) -> str:
        """The stable draft key, and part of the contract: the frontend REBUILDS it.

        `standingsFor` in `_shared/lib/fulfilmentBoard.ts` recomputes
        `${sales_order_id}|${line_no}|${item_code}|${bucket_key}` to count what the planner
        has decided, so a different shape here silently zeroes that counter.
        """
        return f"{self.sales_order_id}|{self.line_no}|{self.item_code}|{self.bucket_key}"


class FulfilmentBoardService:
    """`GET /project-sales/fulfilment-planning/board`. A pure read."""

    def __init__(self, db: Session):
        self.db = db
        self.supply = ProjectSupplyService(db)
        # Per-request stock facts, filled by `_allocate` and read by `_cell`. Cached rather
        # than re-read because the cell states the same figures the allocation was computed
        # from - a second read could disagree with the proposal sitting next to it.
        self._free: Dict[Tuple[str, str], Decimal] = {}
        self._levels: Dict[Tuple[str, str], Tuple[Decimal, Decimal]] = {}
        self._incoming: Dict[Tuple[str, str], List[Any]] = {}
        # Core line id -> how the confirm endpoint names it (planning record, mirror line).
        self._addressing: Dict[str, Dict[str, Any]] = {}
        # (product, warehouse) -> (owed by the whole book, of which confirmed) and what
        # confirmed decisions hold there. Read once, printed beside the free figure.
        self._pressure: Dict[Tuple[str, str], Tuple[Decimal, Decimal]] = {}
        self._held: Dict[Tuple[str, str], Decimal] = {}
        # (product, POOL warehouse) -> AutoCount's `on hand / so_qty / spo_qty`, for the pool
        # rung of the trail. One batched read over every pool a served line may draw on.
        self._pool_piles: Dict[Tuple[str, str], Dict[str, Decimal]] = {}
        # PROJECT line ids `build()` was asked to preview as uncovered (`exclude_covered_line_ids`).
        self._exclude_covered_line_ids: set = set()

    # ----------------------------------------------------------------- public

    def build(
        self,
        so_numbers: Sequence[str],
        *,
        granularity: str = "week",
        as_of: Optional[date] = None,
        day_window_start: Optional[date] = None,
        preview_policy: Optional[str] = None,
        exclude_covered_line_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """The board for one selection of sales orders.

        `as_of` is a parameter rather than the clock so which periods read as past is
        reproducible, and it is echoed back in the response for the same reason: a board that
        quietly disagreed with itself between two reads would be disagreeing about which of the
        planner's commitments are already late.

        `exclude_covered_line_ids` (PROJECT line ids) previews the ladder for a line an ACTIVE
        decision currently covers, as if that one line's hold did not exist: its own reserve is
        un-netted and its demand stays in the queue - `ProjectSupplyService`'s own carve-out for
        the lines a `confirm` is about to replace (`_decided_elsewhere`). Used by the planning-
        change batch to show what the ladder would propose TODAY for a `replan` row, rather than
        the composition that is about to be released.
        """
        self._exclude_covered_line_ids = {
            str(i) for i in (exclude_covered_line_ids or [])
        }
        if granularity not in GRANULARITIES:
            raise AppException(
                status_code=422,
                message=(
                    "Granularity must be day, week or month, "
                    f"not '{granularity}'."
                ),
                code="board_granularity_unknown",
            )
        numbers = [str(n).strip() for n in so_numbers if str(n).strip()]
        if len(numbers) > BOARD_ORDER_CAP:
            raise AppException(
                status_code=422,
                message=(
                    f"A board plans at most {BOARD_ORDER_CAP} sales orders at once, and "
                    f"{len(numbers)} were selected. Narrow the selection and try again."
                ),
                code="board_selection_too_large",
            )
        as_of = as_of or date.today()
        policy_name, weights, class_weights, is_preview = self._policy(preview_policy)

        rows = self._demand_rows(numbers)
        if self._exclude_covered_line_ids:
            for row in rows:
                if row.project_line_id and row.project_line_id in self._exclude_covered_line_ids:
                    # Previewed as uncovered (see `build`'s docstring): the ladder is walked for
                    # it below like any other row, against facts that un-net its own hold.
                    row.decision = None
        for row in rows:
            row.bucket_key = bucket_key_for(row.required_date, as_of, granularity)
            # Per LINE, against its own date, which is the number the "N of M lines are past
            # their delivery date" summary counts. A line dated yesterday is past even though
            # the week it sits in has not ended, so the bucket flag alone would undercount it.
            row.is_past = row.required_date is not None and row.required_date < as_of

        cells_by_key: Dict[Tuple[str, str], List[_Row]] = defaultdict(list)
        for row in rows:
            cells_by_key[(row.item_code, row.bucket_key)].append(row)

        factors_by_key: Dict[str, Any] = {}
        for members in cells_by_key.values():
            factors = priority.factors_for_demand_rows(
                self.db,
                [
                    {
                        "row_key": member.key,
                        "required_date": member.required_date,
                        "order_date": member.order_date,
                        "payment_terms_days": member.payment_terms_days,
                        "demand_class": member.demand_class,
                    }
                    for member in members
                ],
                weights=weights,
                class_weights=class_weights,
            )
            scores = priority.scores_for(factors)
            for member in members:
                member.rank_factors = factors[member.key]
                member.raw_facts = priority.raw_facts_for_demand_row(
                    {
                        "required_date": member.required_date,
                        "order_date": member.order_date,
                        "payment_terms_days": member.payment_terms_days,
                        "demand_class": member.demand_class,
                    }
                )
                member.rank_score = scores[member.key]
                factors_by_key[member.key] = factors[member.key]
            # Highest rank first, ties broken on sales-order number then line number so the
            # order is TOTAL: a non-total rule gives a different answer on each refresh and
            # "why did this order lose today" becomes unanswerable.
            members.sort(key=lambda m: (-m.rank_score, m.so_number, m.line_no))

        buckets = self._buckets(
            {row.bucket_key for row in rows}, granularity, day_window_start, as_of
        )
        products = sorted({row.item_code for row in rows})

        # Serve order: bucket by bucket in date order, product by product, and inside a cell by
        # rank. That is the order the one pile is served in, so a line owed in 2025 is served
        # before a line owed in 2030 rather than losing to it by an accident of iteration. With
        # the buckets now plainly chronological this falls out of the axis itself, where before
        # it needed the aggregate past column pinned to the front.
        #
        # Built from EVERY bucket the selection has, never from the ones on screen. The day
        # window is a display bound, and a display bound that changed what a line was proposed
        # would make the same line read Reserve on one view and Buy on another.
        served: List[_Row] = []
        for bucket_key in self._serve_order({row.bucket_key for row in rows}):
            for item in products:
                served.extend(cells_by_key.get((item, bucket_key), []))

        self._allocate(served)

        cells: List[Dict[str, Any]] = []
        for bucket in buckets:
            for item in products:
                members = cells_by_key.get((item, bucket["key"]))
                if not members:
                    # No cell at all, and the grid renders that as blank. A blank cell is NOT
                    # a zero: it means no selected order owes this product by this date.
                    continue
                cells.append(self._cell(item, bucket["key"], members))

        return {
            "granularity": granularity,
            "as_of": as_of,
            "policy": {
                "name": policy_name,
                "factors": {k: float(v or 0.0) for k, v in (weights or {}).items()},
                "demand_class_weights": {
                    k: float(v or 0.0) for k, v in (class_weights or {}).items()
                },
                "is_preview": is_preview,
                # Stated rather than left for the reader to work out: under the live seeded
                # rule every board row scores 0.0, and a planner who cannot see that is
                # looking at a flat ranking believing it is a considered one (13.5).
                "discriminates_nothing": priority.discriminates_nothing(factors_by_key),
            },
            "dateBuckets": buckets,
            "productRows": [{"item_code": item, "description": None} for item in products],
            "cells": cells,
            # EVERY contributing line, never windowed: a cell only exists for a bucket that
            # made it into `buckets`, and at day granularity that is the 30-day window
            # (`DAY_WINDOW_COLUMNS`), not the whole selection. `_allocate` already ran over
            # every bucket (`served`, above), so a line outside the window carries a real
            # proposal here even though no cell on screen shows it - Approve all, the strip and
            # the List view read this list, never `cells`, for exactly that reason.
            "contributions": [self._contribution(row) for row in rows],
            "orders": self._standings(rows),
            # SELECTION-scoped totals, counted over every contributing line before any window
            # is applied - never over the cells on screen.
            #
            # The screen cannot compute these for itself. Summed off the visible cells, "143 of
            # 153 lines are already past their delivery date" is right at week and month and
            # DISAPPEARS at day, because the 30-day window opens on work still to come and so
            # holds no past cell at all. The planner switching to the closest view would
            # silently lose the most important number on the board.
            "line_count": len(rows),
            "past_line_count": sum(1 for row in rows if row.is_past),
            "unplannable_line_count": sum(1 for row in rows if row.unplannable),
            "contested_line_count": sum(1 for row in rows if row.contested),
        }

    # ----------------------------------------------------- the stock drill-down

    def stock_detail(self, product_id: str, warehouse_id: str) -> Dict[str, Any]:
        """One product at one location: the four totals, and the documents behind them.

        AutoCount's Stock Status with Detail, which is the screen the captain checks stock on:
        On Hand, SO Qty, PO Qty, Available - and under it, every document contributing to those
        totals. "so when a SO is created, it already flows to the outstanding quantity same
        goes for PO created, so it cannot be all quantity are free because we got so many
        outstanding SO, right?"

        The list ADDS UP to the total by construction: both are summed from the same rows, so a
        drill-down can never justify a number the strip did not print. The predicate is the
        shared one - `SalesOrder.status = 'open'` plus `is_open_demand()` - so this screen,
        `/scm/sales-orders` and the netting engine cannot disagree about what is outstanding.
        Deliberately every demand class, because a dealer order occupies the stock as
        completely as a project one does.

        Bounded by nature: one product at one location. The widest on the live book is 289
        sales-order lines (B2155-NL-BLUE at BRW-BB), so this is a page, not a report.
        """
        product = (
            self.db.query(Product).filter(Product.id == product_id).first()
            if product_id
            else None
        )
        warehouse = (
            self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
            if warehouse_id
            else None
        )
        if product is None or warehouse is None:
            raise AppException(
                status_code=404,
                message="That product or location does not exist.",
                code="stock_detail_not_found",
            )

        owed = demand_qty()
        rows = (
            self.db.query(
                SalesOrderLine.id.label("line_id"),
                SalesOrder.id.label("sales_order_id"),
                SalesOrder.so_number,
                SalesOrder.order_date,
                SalesOrder.internal_note,
                SalesOrder.demand_class,
                Customer.customer_name,
                Customer.id.label("customer_id"),
                SalesOrderLine.required_date,
                owed.label("owed"),
                case((~is_plan_demand_line(), True), else_=False).label("covered"),
                # Who sold it. A purchase row (the SPO list below) has no agent - it is not a
                # sales document - so the column is S/O-only by construction, never a guess.
                SalesAgent.sales_agent.label("agent_code"),
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
            .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
            .filter(
                SalesOrderLine.product_id == product_id,
                SalesOrderLine.warehouse_id == warehouse_id,
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .order_by(SalesOrderLine.required_date, SalesOrder.so_number)
            .all()
        )

        # The rank each document holds in THIS pile's queue - the same `pile_book` the trail
        # serves stock down and the queue screen reads out, never a second ranking. The captain,
        # reading the drill-down sorted by delivery date: "is this sorted by the rank also? ...
        # we should have a rank column and be able to sort by that (default sort by that)". A
        # covered line is absent from the book (its claim is already a hold, PLAN 13.5), so it
        # carries no rank and lists after the queue in date order.
        book = self.supply.pile_book(str(product.id), str(warehouse.id))
        ranked = {
            row["line_id"]: (
                position,
                round(float(row.get("rank_score") or 0.0), 6),
                [
                    {**factor.as_dict(), "raw": raw.get(factor.key)}
                    for factor in (row.get("factors") or [])
                ],
                # The mirror line's number, when the order is adopted; a core line has none of
                # its own (`PileQueueLine.line_no`).
                row.get("line_no"),
            )
            for position, row in enumerate(book, start=1)
            for raw in (priority.raw_facts_for_demand_row(row),)
        }
        policy_name = self._policy(None)[0]

        def _so_row(row) -> Dict[str, Any]:
            position, score, factors, line_no = ranked.get(
                str(row.line_id), (None, None, [], None)
            )
            return {
                "line_id": str(row.line_id),
                "line_no": line_no,
                "sales_order_id": str(row.sales_order_id),
                "so_number": row.so_number,
                "customer_name": row.customer_name,
                "customer_id": str(row.customer_id) if row.customer_id else None,
                "agent_code": row.agent_code,
                "project_label": _project_label_from_note(row.internal_note),
                "demand_class": row.demand_class,
                #: AutoCount prints the document's own date and the date it is wanted.
                "doc_date": row.order_date,
                "delivery_date": row.required_date,
                "so_qty": qty_text(_dec(row.owed)),
                #: A confirmed decision already covers this line, so its demand is committed
                #: rather than merely outstanding.
                "is_covered": bool(row.covered),
                "rank_position": position,
                "rank_score": score,
                "rank_factors": factors,
            }

        sales_orders = sorted(
            (_so_row(row) for row in rows),
            # Queue order first (the default sort the captain asked for), then the unranked
            # covered lines in the date order the query already gave them (a stable sort keeps
            # it).
            key=lambda so: (so["rank_position"] is None, so["rank_position"] or 0),
        )
        incoming_rows = self.supply.incoming_by_location([product_id], [warehouse_id]).get(
            (str(product_id), str(warehouse_id)), []
        )
        incoming = [
            {
                "spo_number": ref.spo_number,
                "supplier_name": ref.supplier_name,
                "expected_date": ref.arrival_date,
                "spo_qty": qty_text(ref.qty),
            }
            for ref in sorted(
                incoming_rows,
                key=lambda ref: (ref.arrival_date is None, ref.arrival_date, ref.spo_number),
            )
        ]

        levels = self.supply.stock_levels_by_location([product_id])
        on_hand, reserved = levels.get((str(product_id), str(warehouse_id)), (_ZERO, _ZERO))
        so_qty = sum((_dec(row.owed) for row in rows), _ZERO)
        spo_qty = sum((ref.qty for ref in incoming_rows), _ZERO)
        free = self.supply.free_stock_by_location([product_id]).get(
            (str(product_id), str(warehouse_id)), _ZERO
        )
        held = self.supply.held_stock_by_location([product_id]).get(
            (str(product_id), str(warehouse_id)), _ZERO
        )
        return {
            "product_id": str(product.id),
            "item_code": product.product_code,
            "description": product.product_name,
            "warehouse_id": str(warehouse.id),
            "location": warehouse.warehouse_code,
            "qty_on_hand": qty_text(on_hand),
            "so_qty": qty_text(so_qty),
            "spo_qty": qty_text(spo_qty),
            # Signed, never clamped: this is where "oversold by 632" is said out loud.
            "available_qty": qty_text(on_hand - so_qty + spo_qty),
            # The engine's own figures, so the other reconciliation still closes.
            "qty_reserved": qty_text(reserved),
            "qty_held_by_decisions": qty_text(held),
            "qty_free": qty_text(free),
            "sales_orders": sales_orders,
            "incoming": incoming,
            #: The policy the ranks above came from, named beside them as the queue names it.
            "policy_name": policy_name,
        }

    def pile_queue(
        self,
        product_id: str,
        warehouse_id: str,
        line_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The WHOLE queue at one pile, in the order the stock is actually served in.

        The captain, having been given the top three beside the rung: "I need to know what is
        ahead of me to have the visibility, and why they are ahead of me, meaning I need to know
        their rank also."

        So this is `_pile_book` read out - the SAME list `_attribution` counts `so_qty_ahead`
        from, never a second ranking of the same pile - with each line's rank, the factors and
        the facts behind it, the running total of what is claimed by the time the queue reaches
        it, and (against the line that asked) which factor put it in front.

        A line a confirmed decision covers is absent for the reason `_pile_book` states: its
        claim is already expressed as a hold that came out of the opening stock, and listing it
        again would count the same units twice. `is_covered_excluded` says so per row and is
        false on every row that IS here, so the field means something the day the exclusion is
        made visible rather than being a placeholder.
        """
        product = (
            self.db.query(Product).filter(Product.id == product_id).first()
            if product_id
            else None
        )
        warehouse = (
            self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
            if warehouse_id
            else None
        )
        if product is None or warehouse is None:
            raise AppException(
                status_code=404,
                message="That product or location does not exist.",
                code="pile_queue_not_found",
            )

        book = self.supply.pile_book(str(product.id), str(warehouse.id))
        asked = next(
            (row for row in book if line_id and row["line_id"] == str(line_id)), None
        )
        names = self._customer_names(
            {row["customer_id"] for row in book if row.get("customer_id")}
        )

        asked_position = (
            next(
                (
                    position
                    for position, row in enumerate(book, start=1)
                    if row["line_id"] == asked["line_id"]
                ),
                None,
            )
            if asked is not None
            else None
        )

        lines: List[Dict[str, Any]] = []
        running = _ZERO
        for position, row in enumerate(book, start=1):
            running += _dec(row["open_qty"])
            raw = priority.raw_facts_for_demand_row(row)
            lines.append(
                {
                    "position": position,
                    "line_id": row["line_id"],
                    "sales_order_id": row.get("sales_order_id"),
                    "so_number": row["so_number"],
                    "line_no": row.get("line_no"),
                    "customer_name": names.get(row.get("customer_id") or ""),
                    "qty": qty_text(_dec(row["open_qty"])),
                    "required_date": row["required_date"],
                    "order_date": row.get("order_date"),
                    "payment_terms_days": row.get("payment_terms_days"),
                    "demand_class": row.get("demand_class"),
                    "rank_score": round(float(row.get("rank_score") or 0.0), 6),
                    "rank_factors": [
                        {**factor.as_dict(), "raw": raw.get(factor.key)}
                        for factor in (row.get("factors") or [])
                    ],
                    # Why this line is in front of the one that asked. Null for the asked line
                    # itself, which outranks nobody; null for every row BEHIND it, which is
                    # not in front of anything and must not claim a reason for being; and
                    # null when nobody asked.
                    "leading_factor": (
                        None
                        if asked_position is None or position >= asked_position
                        else _leading_factor(asked, row)
                    ),
                    #: What the queue has claimed by the time it has served this row, this row
                    #: included. Read down the column and the point the pile runs out is
                    #: visible without arithmetic.
                    "cumulative_ahead_qty": qty_text(running),
                    "is_this_line": asked is not None and row["line_id"] == asked["line_id"],
                    "is_covered_excluded": False,
                }
            )

        return {
            "product_id": str(product.id),
            "item_code": product.product_code,
            "description": product.product_name,
            "warehouse_id": str(warehouse.id),
            "location": warehouse.warehouse_code,
            #: What the pile held before the queue drew on it: the same opening figure the
            #: trail's own rung prints.
            "qty_free_opening": qty_text(
                self.supply.free_stock_by_location([str(product.id)]).get(
                    (str(product.id), str(warehouse.id)), _ZERO
                )
            ),
            "this_line_position": (
                next(
                    (line["position"] for line in lines if line["is_this_line"]),
                    None,
                )
            ),
            "policy_name": self._policy(None)[0],
            "lines": lines,
        }

    def _customer_names(self, customer_ids: Iterable[str]) -> Dict[str, str]:
        """Ids to names in one query. The queue prints a customer, never an id."""
        ids = [cid for cid in customer_ids if cid]
        if not ids:
            return {}
        rows = (
            self.db.query(Customer.id, Customer.customer_name)
            .filter(Customer.id.in_(ids))
            .all()
        )
        return {str(row.id): row.customer_name for row in rows}

    # ---------------------------------------------------------------- policy

    def _policy(
        self, preview_policy: Optional[str]
    ) -> Tuple[str, dict, dict, bool]:
        """Which policy ranks this board, and whether it is the live one.

        A preview is a what-if, never a second active policy: the partial unique index allows
        exactly one active row, and two policies for two moments is the defect
        `app/services/scm/priority.py` exists to prevent. So a preview READS a named row (or
        the module's own board preview when no row carries that name) and persists nothing.

        `1` / `true` means the module's own board preview, and that translation lives HERE
        rather than in the route: the parameter's meaning has one owner, or the tested service
        and the shipped endpoint come to disagree about what "preview" was asked for.
        """
        if (preview_policy or "").strip().lower() in {"1", "true"}:
            preview_policy = priority.BOARD_PREVIEW_NAME
        if not preview_policy:
            active = priority.active_policy(self.db)
            weights, class_weights = priority.policy_weights(active)
            name = active.name if active else "No policy configured (document sequence)"
            return name, weights, class_weights, False

        named = priority.policy_by_name(self.db, preview_policy)
        if named is not None:
            weights, class_weights = priority.policy_weights(named)
            # Named ROW, so whether it is a preview is a fact about the row rather than about
            # the request: asking for the policy that happens to be live is not a what-if, and
            # labelling it "Preview, not live" would be a lie on screen.
            return named.name, weights, class_weights, not bool(named.is_active)
        if preview_policy == priority.BOARD_PREVIEW_NAME:
            return (
                priority.BOARD_PREVIEW_NAME,
                dict(priority.BOARD_PREVIEW_WEIGHTS),
                dict(priority.BOARD_PREVIEW_CLASS_WEIGHTS),
                True,
            )
        raise AppException(
            status_code=404,
            message=f"No priority policy named '{preview_policy}'.",
            code="priority_policy_not_found",
        )

    # ------------------------------------------------------------ the demand

    def _demand_rows(self, so_numbers: Sequence[str]) -> List[_Row]:
        """Every still-owed line of the selected project-class sales orders.

        "Outstanding" is `is_open_demand()` plus the header predicate, unchanged and shared
        with the netting engine (PLAN section 3), so the sales-order book screen, the worklist
        and this board cannot disagree about which orders are still owed. Company scoping is
        the session's, injected into every SELECT touching a scoped model - so an order of
        another company is simply not there.
        """
        if not so_numbers:
            return []
        records = (
            self.db.query(SalesOrderLine, SalesOrder, Product, Warehouse, SalesAgent)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .join(Product, Product.id == SalesOrderLine.product_id)
            .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
            # Who sold it. One join, on the same read that already pulls the whole board's
            # demand - the captain asked for the agent "everywhere", and a per-row lookup
            # would be one query per line rather than one for the board.
            .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
            .filter(
                SalesOrder.so_number.in_(list(so_numbers)),
                SalesOrder.status == "open",
                SalesOrder.demand_class == "project",
                is_open_demand(),
            )
            .all()
        )
        if not records:
            return []

        # The ids are already inside the caller's company scope (they came off scoped rows),
        # which is what makes the unscoped raw read of the terms column safe.
        customers = self._customers(
            {str(order.customer_id) for _l, order, _p, _w, _a in records if order.customer_id}
        )
        terms = priority.payment_terms_by_customer(self.db, list(customers.keys()))
        # How the confirm endpoint names these lines, when their order has been adopted.
        # Resolved before the line numbers, which prefer the mirror's own numbering.
        self._addressing = self._mirror_addressing([str(line.id) for line, *_r in records])
        line_numbers = self._line_numbers(records)
        # What an active revision already froze, per CORE line. One read for the whole board.
        frozen = self._frozen_decisions()

        rows: List[_Row] = []
        for line, order, product, warehouse, agent in records:
            customer_id = str(order.customer_id) if order.customer_id else None
            row = _Row(
                line_id=str(line.id),
                sales_order_id=str(order.id),
                so_number=order.so_number,
                customer_id=customer_id,
                customer_name=customers.get(customer_id or ""),
                agent_code=agent.sales_agent if agent else None,
                agent_label=agent.person_label if agent else None,
                project_label=_project_label(order),
                order_date=order.order_date,
                line_no=line_numbers[str(line.id)],
                item_code=product.product_code,
                product_id=str(line.product_id),
                # The same open quantity the sheet promises (AC-B01), imported rather than
                # restated: what is still owed, in the line's own UOM.
                qty=_open_of(line),
                qty_ordered=_dec(line.qty_ordered),
                qty_delivered=_dec(line.qty_delivered),
                required_date=line.required_date,
                warehouse_id=str(line.warehouse_id) if line.warehouse_id else None,
                location=warehouse.warehouse_code if warehouse else None,
                priority=line.priority,
                demand_class=order.demand_class,
            )
            addressing = self._addressing.get(str(line.id), {})
            # Null when nobody has adopted this sales order: there is no record to confirm
            # against, and that IS the state of a not-started row. An invented id or an
            # absent key would both make the screen guess.
            row.project_sales_order_id = addressing.get("project_sales_order_id")
            row.project_line_id = addressing.get("project_line_id")
            row.project_key = _project_key(row.project_label)
            row.payment_terms_days = terms.get(customer_id or "")
            # Covered or not, and by what. A line an active decision covers is not planned
            # again: it states the composition that was frozen for it (13.4).
            row.decision = frozen.get(str(line.id))
            rows.append(row)
        return rows

    def _frozen_decisions(self) -> Dict[str, Dict[str, Any]]:
        """What each ACTIVE revision froze, keyed by the CORE line it covers.

        The core line id is the key because that is what a snapshot names a covered line by,
        and it is the same key `_decided_elsewhere` reads to keep such a line out of the pile's
        queue - so the two halves of "this line is decided" cannot come apart.

        One query for the whole board, and the parse is `ProjectSupplyService`'s own
        (`frozen_lines_of`): a second reading of `line_snapshots` here would be a second
        opinion about what a decision covered.
        """
        pso_ids = {
            entry["project_sales_order_id"]
            for entry in self._addressing.values()
            if entry.get("project_sales_order_id")
        }
        if not pso_ids:
            return {}
        decisions = (
            self.db.query(SOSupplyDecision)
            .filter(
                SOSupplyDecision.project_sales_order_id.in_(list(pso_ids)),
                SOSupplyDecision.state == DECISION_ACTIVE,
            )
            .all()
        )
        out: Dict[str, Dict[str, Any]] = {}
        for decision in decisions:
            frozen = self.supply.frozen_lines_of(decision)
            for snapshot in decision.line_snapshots or []:
                core_line_id = (snapshot or {}).get("core_line_id")
                line_id = str((snapshot or {}).get("project_line_id") or "")
                if not core_line_id or line_id not in frozen:
                    continue
                out[str(core_line_id)] = self._line_decision(decision, frozen[line_id])
        return out

    def _line_decision(
        self, decision: SOSupplyDecision, frozen: Dict[str, Any]
    ) -> Dict[str, Any]:
        """One covered line's frozen composition, in the words the confirmation takes back.

        The WHOLE composition rather than a summary of it: the Amend editor is seeded from
        it (there is no proposal to seed from on a covered line), and an amendment posts the
        composition back in these words. The board does NOT re-post an untouched covered
        line - the server carries every covered line the body does not name into the next
        revision itself (`ProjectSupplyService.confirm`, 13.4).
        """
        components = list(frozen.get("components") or [])

        def total(kind: str) -> Decimal:
            return sum(
                (_dec(c.get("qty")) for c in components if c.get("kind") == kind), _ZERO
            )

        return {
            "revision_no": decision.revision_no,
            "confirmed_at": decision.confirmed_at,
            "timely_spo_qty": qty_text(total(TIMELY_SPO)),
            "reserve": [
                {
                    "warehouse_id": c.get("source_warehouse_id"),
                    "location": c.get("source_location"),
                    "qty": qty_text(_dec(c.get("qty"))),
                }
                for c in components
                if c.get("kind") == RESERVE
            ],
            "borrow": [
                {
                    "source": c.get("source") or "other_location",
                    "warehouse_id": c.get("source_warehouse_id"),
                    "location": c.get("source_location"),
                    "donor_project_id": c.get("donor_project_id"),
                    "qty": qty_text(_dec(c.get("qty"))),
                    # The PERSON's reason, with the rule's sentence as the fallback: the
                    # confirmation refuses a Borrow carrying none, so re-posting this
                    # composition needs whichever of the two was actually given.
                    "reason": (c.get("cs_reason") or c.get("reason") or ""),
                }
                for c in components
                if c.get("kind") == BORROW
            ],
            "buy_qty": qty_text(total(BUY)),
            "buy_reason": frozen.get("buy_reason"),
            "amend_reason": frozen.get("amend_reason"),
        }

    def _demand_pressure(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Tuple[Decimal, Decimal]]:
        """`(owed by the whole book, of which already covered by a confirmed decision)`.

        The captain, reading a cell that said 478 free beside 482 owed: "why is everything
        free, are you sure there is no SO occupying this?" They were right to doubt it - 47,009
        was owed at that location across 289 open lines, and `_free_stock` nets only
        `stock.quantity_reserved` and holds belonging to CONFIRMED decisions, of which the book
        has two. So "free" is very nearly raw on-hand, and printing it alone invites exactly
        that wrong conclusion.

        This changes NO allocation. It states the pressure beside the pile.

        The predicate is the shared one, not a private restatement: `is_open_demand()` plus
        `SalesOrder.status = 'open'`, which is what the worklist, the netting engine and
        `scm.committed_v` all mean by outstanding - so the two screens cannot disagree about
        what is owed. Deliberately NOT narrowed to `demand_class = 'project'`: that filter says
        which orders this screen may PLAN, and the question here is what occupies the stock,
        which a dealer order does just as well as a project one.

        The quantity is `demand_qty()` - `coalesce(qty_required, qty_ordered) - delivered`,
        floored - the same figure the netting engine sums, so a planner comparing this against
        the reorder plan sees one number. It can differ from a board row's own
        `qty_outstanding`, which is what is owed the CUSTOMER (AC-B01) rather than what
        purchasing was asked to cover; they differ only where CS has stated a `qty_required`.

        "Covered" is per LINE, through `is_plan_demand_line()`, so a partially confirmed order
        contributes only its confirmed lines - the same rule `committed_v` applies since
        migration 384, rather than a second opinion about what a decision covers.
        """
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        owed = demand_qty()
        rows = (
            self.db.query(
                SalesOrderLine.product_id,
                SalesOrderLine.warehouse_id,
                func.coalesce(func.sum(owed), 0).label("owed"),
                func.coalesce(
                    func.sum(case((~is_plan_demand_line(), owed), else_=0)), 0
                ).label("confirmed"),
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(
                SalesOrderLine.product_id.in_(pids),
                SalesOrderLine.warehouse_id.in_(wids),
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .group_by(SalesOrderLine.product_id, SalesOrderLine.warehouse_id)
            .all()
        )
        return {
            (str(row.product_id), str(row.warehouse_id)): (
                _dec(row.owed),
                _dec(row.confirmed),
            )
            for row in rows
        }

    def _customers(self, customer_ids: Iterable[str]) -> Dict[str, str]:
        ids = [cid for cid in customer_ids if cid]
        if not ids:
            return {}
        return {
            str(row.id): row.customer_name
            for row in self.db.query(Customer).filter(Customer.id.in_(ids)).all()
        }

    def _line_numbers(self, records: Sequence[tuple]) -> Dict[str, int]:
        """A line number per core line, because the core table has none.

        Derived per sales order by (required date nulls last, item code, line id), which is
        the same deterministic rule adoption uses to number the mirror - so the board and the
        sheet call the same line by the same number. Where a mirror line ALREADY exists and
        numbers every contributing line of that order distinctly, its numbers win: the mirror
        is what the sheet shows, and Re-sync can renumber a later line.
        """
        by_order: Dict[str, List[tuple]] = defaultdict(list)
        for line, order, product, _warehouse, _agent in records:
            by_order[str(order.id)].append(
                (
                    line.required_date is None,
                    line.required_date or date.min,
                    product.product_code or "",
                    str(line.id),
                )
            )
        derived: Dict[str, int] = {}
        for entries in by_order.values():
            for index, entry in enumerate(sorted(entries), start=1):
                derived[entry[3]] = index

        mirrored = {
            core_id: entry["line_no"]
            for core_id, entry in self._addressing.items()
            if entry.get("line_no")
        }
        for entries in by_order.values():
            ids = [entry[3] for entry in entries]
            numbers = [mirrored.get(line_id) for line_id in ids]
            if all(n is not None for n in numbers) and len(set(numbers)) == len(numbers):
                for line_id, number in zip(ids, numbers):
                    derived[line_id] = int(number)
        return derived

    def _mirror_addressing(
        self, core_line_ids: Sequence[str]
    ) -> Dict[str, Dict[str, Any]]:
        """How the confirm endpoint names each core line, when anybody has adopted its order.

        `POST /sales-orders/{pso_id}/confirm` addresses a planning RECORD and its own mirror
        LINES (`ProjectSupplyService.confirm` builds `by_id` from `lines_of(order.id)`), so a
        board that returned only core ids could not reach it and the frontend would have to
        map between two id spaces to get there.

        Scoped to the record that HOLDS the core order (`projects.sales_orders.so_id`), which
        a partial unique index makes at most one. An authored Project SO that happens to
        mirror the same core line is a different subject and must not be confirmed by
        accident, so it is not offered here.
        """
        if not core_line_ids:
            return {}
        rows = (
            self.db.query(
                ProjectSalesOrderLine.core_sales_order_line_id,
                ProjectSalesOrderLine.id,
                ProjectSalesOrderLine.line_no,
                ProjectSalesOrder.id,
                ProjectSalesOrder.so_id,
            )
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
            )
            .filter(
                ProjectSalesOrderLine.core_sales_order_line_id.in_(list(core_line_ids)),
                ProjectSalesOrder.so_id.isnot(None),
            )
            .all()
        )
        out: Dict[str, Dict[str, Any]] = {}
        for core_id, line_id, line_no, pso_id, so_id in rows:
            if core_id is None:
                continue
            out[str(core_id)] = {
                "project_sales_order_id": str(pso_id),
                "project_line_id": str(line_id),
                "line_no": int(line_no) if line_no is not None else None,
                "sales_order_id": str(so_id),
            }
        return out

    # -------------------------------------------------------------- sourcing

    def _allocate(self, served: Sequence[_Row]) -> None:
        """Compose every contributing line through the SHEET'S OWN ladder, in board order.

        Two questions, and they belong to different owners.

        **Which sources may cover this line, in what order** is `ProjectSupplyService.
        compose_line`: own location, then the shared pool under PLAN 3.3's hot-selling rules,
        then timely incoming, then Buy. That is the sheet's code, called here rather than
        approximated - an earlier build ran a reduced three-source version, and it proposed a
        Buy for a line the sheet would have covered from the pool, so purchasing acting on the
        board and purchasing acting on the sheet disagreed about the same line.

        **Who gets a scarce pile** is the board's: contributions are served in the
        fulfilment-priority ranking (13.5), which is what the per-order sheet structurally
        cannot show. So each pile - the own-location free stock, its dated incoming, and the
        shared pool - is drawn down in board order, and the ladder is then run per line against
        what is left.

        Deliberately NOT pro-rata. Splitting 100 free units across five lines needing 100 each
        produces five short deliveries instead of one complete one and four honest Buys.

        Borrow is not proposed, here or on the sheet: it needs a donor and a reason from a
        person (AC-B09). What the board does is SAY it is available, so a Buy is never printed
        as if the stock existed nowhere.

        A line an ACTIVE decision covers is left out of all of it. It is not competing for the
        pile - the pile's own queue leaves it out, because its claim is already a hold - so
        running the ladder for it produced a fresh proposal for a line that had been decided,
        beside share figures that defaulted to zero because it is not in the queue they are
        counted from. It states what was frozen instead.
        """
        # Covered rows still count towards the STOCK reads: a cell whose only line is decided
        # still has a location, and dropping it here would blank that location's position.
        plannable = [row for row in served if not row.unplannable]
        proposable = [row for row in plannable if not row.covered]
        for row in served:
            if row.covered:
                self._apply_frozen(row)
            elif row.unplannable:
                row.sources = [
                    {
                        "kind": "unplannable",
                        "qty": qty_text(row.qty),
                        "location": None,
                        "warehouse_id": None,
                        "reason": (
                            "No fulfilment location on the sales order line, so nothing can "
                            "be sourced for it."
                        ),
                        "spo_number": None,
                        "arrival_date": None,
                    }
                ]

        product_ids = {row.product_id for row in plannable if row.product_id}
        warehouse_ids = {row.warehouse_id for row in plannable if row.warehouse_id}
        # Every stock fact the board states comes from these reads and no other, so the
        # availability printed beside a proposal is the availability the proposal was computed
        # from.
        free = self._free = self.supply.free_stock_by_location(product_ids)
        self._levels = self.supply.stock_levels_by_location(product_ids)
        self._held = self.supply.held_stock_by_location(product_ids)
        self._pressure = self._demand_pressure(product_ids, warehouse_ids)
        self._incoming = self.supply.incoming_by_location(product_ids, warehouse_ids)
        # Facts for every plannable row, covered ones included: a covered line is not run
        # through the ladder (its share fields come back empty, and `_apply_frozen` reads
        # none of them), but its DONORS are still read below, from the same fact - Amend on a
        # decided line offers a Borrow exactly as it does on an undecided one.
        facts = self.supply.demand_facts(
            [
                {
                    "key": row.key,
                    # The core line id, which is what the book-wide projection is keyed by.
                    "line_id": row.line_id,
                    "product_id": row.product_id,
                    "warehouse_id": row.warehouse_id,
                    "open_qty": row.qty,
                    "required_date": row.required_date,
                    "order_date": row.order_date,
                    "payment_terms_days": row.payment_terms_days,
                    "demand_class": row.demand_class,
                    "so_number": row.so_number,
                    "line_no": row.line_no,
                    "item_code": row.item_code,
                }
                for row in plannable
            ],
            exclude_line_ids=list(self._exclude_covered_line_ids) or None,
        )

        # The pool piles behind rung 2, in AutoCount's own triple, read once for every pool a
        # served line may draw on. `Pool BRW | Had 0` beside `Available 1` in Inventory is two
        # true numbers, and the trail has to show the pile the queue was netted from.
        pool_pairs = {
            (fact.product_id, str(fact.pool.id))
            for fact in facts.values()
            if fact.product_id and fact.pool is not None
        }
        self._pool_piles = (
            self.supply.pile_triples(
                {product_id for product_id, _pool in pool_pairs},
                {pool_id for _product, pool_id in pool_pairs},
            )
            if pool_pairs
            else {}
        )

        piles: Dict[Tuple[str, str], List[_Row]] = defaultdict(list)
        for row in proposable:
            piles[(row.product_id, row.warehouse_id)].append(row)

        # Pass one: bookkeeping only. How much of its own pile each line may have was already
        # decided by `demand_facts`, from the SAME book-wide projection the confirmation judges
        # against - a line reserves what is left after the demand the active policy ranks ahead
        # of it, and nothing more. What is recorded here is who drew the pile down before this
        # row was reached, which is what the contest sentence and `qty_free_remaining` say.
        for (product_id, warehouse_id), members in piles.items():
            free_left = free.get((product_id, warehouse_id), _ZERO)
            taken = _ZERO
            taker: Optional[_Row] = None
            for row in members:
                fact = facts[row.key]
                own_share = fact.own_free
                timely_share = fact.timely_qty
                # Stock is not per date, so the same free figure is true of every column of
                # this product; what differs is how much an earlier date has already taken.
                row.free_before = free_left
                row.taken_before = taken
                row.last_taker = taker
                free_left = max(free_left - own_share, _ZERO)
                if own_share + timely_share > _ZERO:
                    taken += own_share + timely_share
                    taker = row

        # Pass two: run the ladder per line, in board order, against the running pool balance.
        pool_left: Dict[str, Decimal] = {}
        borrow_cache: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
        for row in proposable:
            fact = facts[row.key]
            pool_key = fact.pool_key
            if pool_key and pool_key not in pool_left:
                pool_left[pool_key] = fact.pool_free
            # A Reserve component names its location by CODE and the confirmation addresses a
            # warehouse by ID, so the pair is captured here where both are in hand.
            row.so_qty_ahead = fact.so_qty_ahead
            row.lines_ahead = fact.lines_ahead
            row.available_to_this_line = fact.available_to_this_line
            row.warehouse_ids = {
                code: warehouse_id
                for code, warehouse_id in (
                    (fact.own_code, str(fact.warehouse.id) if fact.warehouse else None),
                    (fact.pool_code, str(fact.pool.id) if fact.pool else None),
                )
                if code and warehouse_id
            }
            # What the shared pool still held when THIS line was reached, captured before the
            # draw: the trail states what each source held, and reading it back afterwards
            # would state what was left instead.
            pool_open = pool_left.get(pool_key, _ZERO) if pool_key else None
            components = self.supply.compose_line(fact, pool_free_left=pool_open)
            if pool_key and fact.pool_code:
                drawn = sum(
                    (
                        c.qty
                        for c in components
                        if c.kind == RESERVE and c.source_location == fact.pool_code
                    ),
                    _ZERO,
                )
                pool_left[pool_key] = max(pool_left.get(pool_key, _ZERO) - drawn, _ZERO)

            reserved = sum((c.qty for c in components if c.kind == RESERVE), _ZERO)
            incoming = sum((c.qty for c in components if c.kind == TIMELY_SPO), _ZERO)
            bought = sum((c.qty for c in components if c.kind == BUY), _ZERO)
            row.proposed = {RESERVE: reserved, TIMELY_SPO: incoming, BUY: bought}
            # Contested means this line is buying while its location DOES hold free stock -
            # somebody got there first, whether that somebody is on this board or is one of the
            # earlier-dated orders in the book that the share above already accounts for. A
            # location that never held any stock is NOT contested; it is a plain Buy.
            row.contested = bought > _ZERO and self._free.get(
                (row.product_id, row.warehouse_id), _ZERO
            ) > _ZERO

            # Donors on EVERY plannable row, not only a row the engine is buying for. The
            # captain's flow is "borrow instead of taking the reserved stock", and a line met
            # from its own Reserve had no donors on it, so Amend said nobody held any and
            # offered no Borrow. A need of 0 ranks the donors by availability alone.
            row.borrow_candidates = self._donors_for(borrow_cache, row, fact, bought)

            row.sources = [self._source(component, row) for component in components]
            # Said, not implied: the ladder consulted these and never printed them, and the
            # captain read the trail as if it had consulted nothing.
            row.item_flags = {
                "dealer_hot_selling": bool(fact.is_dealer_hot_selling),
                "dealer_hot_selling_where": list(fact.dealer_hot_selling_where or []),
                "project_hot_selling": bool(fact.is_project_hot_selling),
                "project_hot_selling_where": list(fact.project_hot_selling_where or []),
                "dealer_classified": bool(fact.dealer_classified),
                "project_classified": bool(fact.project_classified),
                "discontinued": bool(fact.is_discontinued),
                "retail_classification_available": not fact.classification_unavailable,
            }
            row.trail = self._trail(row, fact, components, pool_open)

        # A covered line is amendable too, so its donors are read - ranked against what its
        # frozen composition is still buying - and nothing else about it is touched: no
        # ladder, no contest, no share of a queue it is not in.
        for row in plannable:
            if not row.covered:
                continue
            fact = facts[row.key]
            row.borrow_candidates = self._donors_for(
                borrow_cache, row, fact, row.proposed.get(BUY, _ZERO)
            )
            # Amend on a covered line reads the same flags a proposal states: a discontinued
            # product needs a Buy reason whether or not the line was decided before.
            row.item_flags = {
                "dealer_hot_selling": bool(fact.is_dealer_hot_selling),
                "dealer_hot_selling_where": list(fact.dealer_hot_selling_where or []),
                "project_hot_selling": bool(fact.is_project_hot_selling),
                "project_hot_selling_where": list(fact.project_hot_selling_where or []),
                "dealer_classified": bool(fact.dealer_classified),
                "project_classified": bool(fact.project_classified),
                "discontinued": bool(fact.is_discontinued),
                "retail_classification_available": not fact.classification_unavailable,
            }

    def _donors_for(
        self,
        borrow_cache: Dict[Tuple[Any, ...], List[Dict[str, Any]]],
        row: _Row,
        fact: Any,
        need: Decimal,
    ) -> List[Dict[str, Any]]:
        """Where else this line could be met from, read once per distinct question.

        Cached per (product, location, the quantity being covered): the donors depend on the
        fact's reserve reach rather than on the line, and recomputing them per row walks the
        whole free-stock cache once per row - but the RANKING is against this line's residual
        (13.11), so two rows covering different quantities are two different questions.
        Hot-selling no longer changes the donor set (own location is always Reserve-eligible,
        never a Borrow source), so it is not part of the key.
        """
        cache_key = (fact.product_id, row.warehouse_id, need)
        if cache_key not in borrow_cache:
            borrow_cache[cache_key] = self.supply.borrow_candidates_for(fact, need=need)
        return borrow_cache[cache_key]

    def _apply_frozen(self, row: _Row) -> None:
        """A covered line states what was decided for it, and nothing else (13.4).

        The sources are the FROZEN composition, including a Borrow - the engine proposes none,
        but a person did, and printing it as anything else would describe a decision nobody
        took. There is no trail because no ladder was walked, no contest because a decided line
        is not competing, and no share of the queue because it is not in the queue: `null`
        there, never `0`, which would be a claim about a contest it left. Its donors are the
        one thing still read for it, by `_allocate`, because it can still be amended.
        """
        decision = row.decision or {}
        reserve = sum((_dec(c["qty"]) for c in decision.get("reserve") or []), _ZERO)
        incoming = _dec(decision.get("timely_spo_qty"))
        bought = _dec(decision.get("buy_qty"))
        row.proposed = {RESERVE: reserve, TIMELY_SPO: incoming, BUY: bought}
        row.sources = [
            *(
                {
                    "kind": RESERVE,
                    "qty": component["qty"],
                    "location": component.get("location"),
                    "warehouse_id": component.get("warehouse_id"),
                    "reason": self._frozen_reason(row, f"Reserved at {component.get('location')}"),
                    "spo_number": None,
                    "arrival_date": None,
                }
                for component in decision.get("reserve") or []
            ),
            *(
                [
                    {
                        "kind": TIMELY_SPO,
                        "qty": qty_text(incoming),
                        "location": row.location,
                        "warehouse_id": row.warehouse_id,
                        "reason": self._frozen_reason(row, "Incoming supply, as confirmed"),
                        "spo_number": None,
                        "arrival_date": None,
                    }
                ]
                if incoming > _ZERO
                else []
            ),
            *(
                {
                    "kind": BORROW,
                    "qty": component["qty"],
                    "location": component.get("location"),
                    "warehouse_id": component.get("warehouse_id"),
                    "reason": self._frozen_reason(
                        row,
                        f"Borrowed from {component.get('location') or 'another location'}",
                        component.get("reason"),
                    ),
                    "spo_number": None,
                    "arrival_date": None,
                }
                for component in decision.get("borrow") or []
            ),
            *(
                [
                    {
                        "kind": BUY,
                        "qty": qty_text(bought),
                        "location": None,
                        "warehouse_id": None,
                        "reason": self._frozen_reason(row, "Bought, as confirmed"),
                        "spo_number": None,
                        "arrival_date": None,
                    }
                ]
                if bought > _ZERO
                else []
            ),
        ]
        row.trail = []
        row.item_flags = None
        row.contested = False
        # Donors are NOT cleared: `_allocate` reads them for a covered line too, because a
        # decided line is still amendable and Amend has to be able to offer a Borrow on it.
        row.so_qty_ahead = None
        row.lines_ahead = None
        row.available_to_this_line = None

    @staticmethod
    def _frozen_reason(row: _Row, what: str, said: Optional[str] = None) -> str:
        """The sentence a frozen component carries: what was done, in which revision.

        Never the engine's own reason for a proposal it did not make - this quantity was
        decided by a person, and the reason they gave (a Borrow's, always) is what follows it.
        """
        revision = (row.decision or {}).get("revision_no")
        sentence = f"{what} in revision {revision}." if revision else f"{what}."
        stated = (said or "").strip()
        return f"{sentence} {stated}" if stated else sentence

    def _trail(
        self,
        row: _Row,
        fact: Any,
        components: Sequence[Any],
        pool_open: Optional[Decimal],
    ) -> List[Dict[str, Any]]:
        """The ladder for one line, rung by rung, in the order it was walked.

        The captain: "can you justify how you arrive at the buy, like what's the process you
        have gone through: checking the available quantity first, deciding whether to reserve
        it or not, then checking the SPO quantity, then checking whether can borrow".

        EVERY rung is emitted, including the ones that gave nothing, because "the pool was
        checked and had none" is the answer to that question and an omitted step reads as a step
        that was never taken. A rung skipped by a RULE - the pool is this line's own location
        and was already checked above, a location has no shared pool at all - says so under its
        own outcome rather than looking like a source that happened to be empty.

        A READ, never a second allocator: every quantity here is either one the engine already
        produced (`components`) or one the facts already state, so the trail cannot disagree
        with the proposal it explains.
        """
        steps: List[Dict[str, Any]] = []
        remaining = _dec(row.qty)
        own_code = fact.own_code
        pool_code = fact.pool_code

        def took(kind: str, location: Optional[str]) -> Decimal:
            return sum(
                (
                    component.qty
                    for component in components
                    if component.kind == kind and component.source_location == location
                ),
                _ZERO,
            )

        def add(
            kind: str,
            *,
            location: Optional[str] = None,
            warehouse_id: Optional[str] = None,
            opening: Optional[Decimal] = None,
            offered: Decimal = _ZERO,
            taken: Decimal = _ZERO,
            ahead_qty: Optional[Decimal] = None,
            ahead_lines: Optional[int] = None,
            ahead: Optional[Sequence[Dict[str, Any]]] = None,
            ahead_more: int = 0,
            ahead_by_factor: Optional[Dict[str, int]] = None,
            note: Optional[str] = None,
            why: Optional[Callable[[str], str]] = None,
            eligible: bool = True,
            offer_only: bool = False,
            pool: Optional[Dict[str, Any]] = None,
        ) -> None:
            nonlocal remaining
            wanted = remaining
            remaining = max(remaining - taken, _ZERO)
            if not eligible:
                outcome = "not_eligible"
            elif taken > _ZERO:
                outcome = "took"
            elif wanted <= _ZERO:
                outcome = "none_needed"
            elif offer_only and offered > _ZERO:
                outcome = "offered"
            else:
                outcome = "nothing_left"
            steps.append(
                {
                    "step": len(steps) + 1,
                    "kind": kind,
                    "location": location,
                    "warehouse_id": warehouse_id,
                    "opening": None if opening is None else qty_text(opening),
                    "ahead_qty": None if ahead_qty is None else qty_text(ahead_qty),
                    "ahead_lines": ahead_lines,
                    # Who is in that queue, for the one rung that HAS a queue. The numbers said
                    # 142 lines wanted 18730 and the captain asked "why do the orders stand
                    # ahead of me? why?" - which is a question about names and reasons, not
                    # about a total.
                    "ahead": list(ahead or []),
                    "ahead_more": ahead_more,
                    "ahead_by_factor": dict(ahead_by_factor or {}),
                    "offered": qty_text(offered),
                    "taken": qty_text(taken),
                    "remaining_after": qty_text(remaining),
                    "outcome": outcome,
                    # ONE sentence saying why the rung ended this way, chosen by the outcome the
                    # arithmetic above just produced. Plain words: the row of numbers beside it
                    # is what needed explaining, so restating it would explain nothing.
                    "why": _COVERED_BEFORE if why is None else why(outcome),
                    "note": note,
                    # The pool pile behind rung 2, in AutoCount's triple. Null on every other
                    # rung, and on a pool rung that has no pile to describe.
                    "pool": pool,
                }
            )

        # 1. The line's own location. ALWAYS Reserve-eligible, hot-selling or not (captain,
        #    19 August 2026: "reserve can always reserve regardless of dealer hot selling or
        #    not"). What the demand ranked ahead of it there had left is the only thing that
        #    still limits it.
        own_opening = self._free.get((row.product_id, row.warehouse_id), _ZERO)
        own_offered = fact.available_to_this_line
        own_taken = took(RESERVE, own_code)
        add(
            "reserve_own",
            location=own_code,
            warehouse_id=row.warehouse_ids.get(own_code),
            opening=own_opening,
            ahead_qty=fact.so_qty_ahead,
            ahead_lines=fact.lines_ahead,
            ahead=fact.ahead_lines_named,
            ahead_more=fact.ahead_more,
            ahead_by_factor=fact.ahead_by_factor,
            offered=own_offered,
            taken=own_taken,
            why=lambda outcome: self._own_why(
                fact, outcome, own_code, own_opening, own_offered, own_taken
            ),
        )

        # 2. The shared pool - what hot-selling gates now, by demand class (PLAN 3.3a). Own
        #    location's Reserve above already covers this location fully when the pool IS this
        #    location, so that case is never walked twice.
        if not pool_code:
            add(
                "reserve_pool",
                eligible=False,
                note="no shared pool",
                why=lambda _outcome: "No shared pool for this product.",
            )
        elif pool_code == own_code:
            add(
                "reserve_pool",
                location=pool_code,
                warehouse_id=row.warehouse_ids.get(pool_code),
                eligible=False,
                note="pool is this location",
                why=lambda _outcome: "The pool is this location, already checked above.",
            )
        else:
            balance = max(_dec(pool_open), _ZERO)
            pile = self._pool_pile(row, fact, balance)
            available = _dec(pile.get("available"))
            if fact.is_dealer_hot_selling:
                pool_offered = _ZERO
            elif fact.is_project_hot_selling:
                pool_offered = max(min(balance, available), _ZERO)
            else:
                pool_offered = balance
            pool_taken = took(RESERVE, pool_code)
            add(
                "reserve_pool",
                location=pool_code,
                warehouse_id=row.warehouse_ids.get(pool_code),
                opening=balance,
                offered=pool_offered,
                taken=pool_taken,
                eligible=not fact.is_dealer_hot_selling,
                note=(
                    "dealer hot-selling: pool not offered"
                    if fact.is_dealer_hot_selling
                    else "project hot-selling: capped by pool availability"
                    if fact.is_project_hot_selling
                    else None
                ),
                why=lambda outcome: self._pool_why(
                    fact, outcome, pile, balance, pool_offered, pool_taken
                ),
                pool=pile,
            )

        # 3. Supply already on its way that lands on or before the required date.
        incoming_taken = took(TIMELY_SPO, own_code)
        add(
            "incoming",
            location=own_code,
            warehouse_id=row.warehouse_ids.get(own_code),
            opening=fact.timely_qty,
            offered=fact.timely_qty,
            taken=incoming_taken,
            note=self._incoming_note(fact),
            why=lambda outcome: self._incoming_why(fact, outcome, incoming_taken),
        )

        # 4. Borrow: offered, never proposed. It needs a donor and a reason from a person
        #    (AC-B09), so the trail shows what was found and that nothing was taken.
        donors = sum(
            (_dec(candidate["free_qty"]) for candidate in row.borrow_candidates), _ZERO
        )
        add(
            "borrow",
            opening=donors if row.borrow_candidates else _ZERO,
            offered=donors,
            note=self._donor_note(row),
            why=lambda outcome: self._borrow_why(outcome),
            offer_only=True,
        )

        # 5. Whatever is still uncovered.
        residual = row.proposed.get(BUY, _ZERO)
        add(
            "buy",
            offered=residual,
            taken=residual,
            why=lambda outcome: self._buy_why(fact, outcome),
        )
        return steps

    def _pool_pile(
        self,
        row: _Row,
        fact: Any,
        balance: Decimal,
    ) -> Dict[str, Any]:
        """The pool's pile as rung 2 saw it, in AutoCount's vocabulary and this line's.

        The captain, on `Pool BRW | Had 0` beside `Available 1` in Inventory: "why it shows
        0?" Because `Had` is what the pool's OWN book ranked ahead of this line left, and
        Available is the pile's whole position - two true numbers, so both are printed with
        the subtraction between them. `available` is SIGNED and never clamped, as on a
        donor row.

        `cap` is always null (19 August 2026): the old reorder-level cap on a hot-selling
        line's pool draw is gone - dealer hot-selling offers the pool nothing at all, and
        project hot-selling caps it against `available` instead. Kept for wire
        compatibility, never a number that would read as a limit nobody set.
        """
        pool_id = str(fact.pool.id)
        key = (fact.product_id, pool_id)
        triple = self._pool_piles.get(
            key, {"on_hand": _ZERO, "so_qty": _ZERO, "spo_qty": _ZERO}
        )
        on_hand, reserved = self._levels.get(key, (triple["on_hand"], _ZERO))
        return {
            "location": fact.pool_code,
            "warehouse_id": pool_id,
            "on_hand": qty_text(on_hand),
            "so_qty": qty_text(triple["so_qty"]),
            "spo_qty": qty_text(triple["spo_qty"]),
            "available": qty_text(on_hand - triple["so_qty"] + triple["spo_qty"]),
            "reserved": qty_text(reserved),
            "free": qty_text(self._free.get(key, _ZERO)),
            "claimed_ahead_qty": qty_text(fact.pool_claimed_qty),
            "claimed_ahead_lines": int(fact.pool_claimed_lines or 0),
            "left": qty_text(balance),
            "reorder_level": qty_text(max(_dec(fact.pool_reorder_level), _ZERO)),
            "cap": None,
        }

    @staticmethod
    def _hot_prefix(fact: Any, *, dealer: bool) -> str:
        """"Dealer hot-selling at BRW" or the project equivalent - the evidence sentence the
        pool rung leads with (PLAN 3.3a).

        The captain: "don't give me jargon like abc classification, just tell me hot selling
        or cold selling, at project or retail" (19 August 2026) - so this names the class and
        the location, never the letter or the word behind it. The number itself (which rank,
        out of how many, what share) is a press away on the trail's Proof button
        (`GET .../fulfilment-planning/classification`).
        """
        if dealer:
            where = ", ".join(fact.dealer_hot_selling_where or [])
            return f"Dealer hot-selling at {where}" if where else "Dealer hot-selling"
        where = ", ".join(fact.project_hot_selling_where or [])
        return f"Project hot-selling at {where}" if where else "Project hot-selling"

    @staticmethod
    def _cold_prefix(fact: Any) -> str:
        """"Cold at retail and project" or the one class that carries evidence - the plain
        word for "classified, but never ranked A", read off `dealer_classified` /
        `project_classified` rather than off `classification_unavailable`, which only
        answers "any evidence at all", not which class it was."""
        classes = []
        if fact.dealer_classified:
            classes.append("retail")
        if fact.project_classified:
            classes.append("project")
        return f"Cold at {' and '.join(classes)}"

    # ------------------------------------------------------------------ why, per rung

    def _own_why(
        self,
        fact: Any,
        outcome: str,
        location: Optional[str],
        opening: Decimal,
        offered: Decimal,
        taken: Decimal,
    ) -> str:
        """Why the line's own location ended where it did, in one sentence.

        The captain's own rung read `478 | 18730 across 142 lines | 0 | 0 | 21 | Nothing left`,
        and his question was "what does this mean? why do the orders stand ahead of me? why?".
        So the sentence names the queue, what it wants, and WHY those lines rank first - in the
        planner's words, never in the policy's factor keys.

        No hot-selling clause here (19 August 2026): own-location Reserve is always eligible,
        so this rung reads exactly as it does for an ordinary item - hot-selling is the POOL
        rung's business now (`_pool_why`).
        """
        where = f" at {location}" if location else ""
        if outcome == "none_needed":
            return _COVERED_BEFORE
        if outcome == "took":
            if fact.lines_ahead:
                return (
                    f"{qty_text(offered)} left after the {fact.lines_ahead} lines "
                    f"ahead; this line takes {qty_text(taken)}."
                )
            return f"First in the queue here; this line takes {qty_text(taken)}."
        if fact.lines_ahead:
            return (
                f"{qty_text(opening)} on hand, but {fact.lines_ahead} lines with "
                f"{_ahead_phrase(fact.ahead_by_factor)} rank ahead and want "
                f"{qty_text(fact.so_qty_ahead)} - none is left for this line."
            )
        return f"No free stock{where}."

    def _pool_why(
        self,
        fact: Any,
        outcome: str,
        pile: Dict[str, Any],
        balance: Decimal,
        offered: Decimal,
        taken: Decimal,
    ) -> str:
        """Why the pool rung ended where it did, with the pool's own numbers in the sentence.

        The captain, on `Pool BRW | Had 0` beside `Available 1` in Inventory: "why it shows
        0?" - and on `Pool BRW | 4 | took 4`: "is it taken because for location BRW there is
        no outstanding quantity?" The answer is the pool's on hand, its availability, and what
        its own orders ranked ahead of this line claim, said together.

        Amended 19 August 2026 (PLAN 3.3a): hot-selling is what gates the pool now, by demand
        class - dealer wins when both flags are set, and each has its own sentence. A
        classified-but-not-hot item ("Cold at retail" / "Cold at project" / both) is offered
        the pool as it would be for any ordinary item, said in those words; an unclassified
        item (no delivered demand of either class, ever) is offered the same way and says so
        too - "Not classified" is a different answer from "cold" and must not print as it.

        Amended again the same day: the captain, reading the trail, asked for the plain word
        instead of the classification jargon - "don't give me jargon like abc classification,
        just tell me hot selling or cold selling, at project or retail". Every sentence below
        now names hot/cold/not-classified and never the letter or the word "ABC"; the ranked
        number behind each verdict is the trail's Proof button
        (`GET .../fulfilment-planning/classification`), not this sentence.
        """
        code = fact.pool_code
        if outcome == "none_needed":
            return _COVERED_BEFORE
        if fact.is_dealer_hot_selling:
            return (
                f"{self._hot_prefix(fact, dealer=True)}: {code} is kept for retail, so the "
                "pool is not offered."
            )
        available = _dec(pile.get("available"))
        if fact.is_project_hot_selling:
            prefix = self._hot_prefix(fact, dealer=False)
            if available > _ZERO:
                base = (
                    f"{prefix}: {code} may be drawn while its availability stays positive - "
                    f"{qty_text(available)} available, {qty_text(offered)} offered."
                )
            else:
                base = (
                    f"{prefix}: {code}'s availability is {qty_text(available)}, so nothing "
                    "is offered."
                )
            return f"{base} This line takes {qty_text(taken)}." if outcome == "took" else base
        if fact.classification_unavailable:
            base = (
                "Not classified (no retail or project deliveries of this item in the last "
                f"12 months), so {code} is offered as for a cold item."
            )
            return f"{base} This line takes {qty_text(taken)}." if outcome == "took" else base
        prefix = self._cold_prefix(fact)
        on_hand = _dec(pile.get("on_hand"))
        # The "Available" the captain was holding the rung against is the Inventory screen's
        # (on hand less reserved), so that is the figure the sentence quotes; AutoCount's
        # signed position (on hand - SO + SPO) is beside it in the sub-table.
        on_hand_available = on_hand - _dec(pile.get("reserved"))
        claimed = _dec(pile.get("claimed_ahead_qty"))
        left = (
            f"{prefix}, so {code} is offered: {qty_text(balance)} left after its own queue "
            "ahead of this line"
        )
        if outcome == "took":
            return f"{left}; this line takes {qty_text(taken)}."
        if claimed > _ZERO:
            return (
                f"{prefix}, so {code} is offered. {code} holds {qty_text(on_hand)} on hand "
                f"(Available {qty_text(on_hand_available)} in stock), but {code}'s own orders "
                f"ranked ahead of this line claim {qty_text(claimed)}, so {qty_text(balance)} "
                "is left."
            )
        if on_hand > _ZERO:
            return (
                f"{prefix}, so {code} is offered. {code} holds {qty_text(on_hand)} on hand "
                f"(Available {qty_text(on_hand_available)} in stock), but none is left for "
                "this line."
            )
        return f"{prefix}, so {code} is offered, but there is no stock at {code}."

    @staticmethod
    def _buy_why(fact: Any, outcome: str) -> str:
        """Why the remainder is bought - and, for a discontinued item, that the buy will need
        a reason. `is_discontinued` only ever forced a REASON on the buy; saying so here is
        cheaper than a refusal at confirm being the first anybody hears of it."""
        if outcome != "took":
            return _COVERED_BEFORE
        sentence = "Nothing left to take, so the remainder is bought."
        if fact.is_discontinued:
            return f"{sentence} Discontinued: the buy needs a reason."
        return sentence

    def _incoming_why(self, fact: Any, outcome: str, taken: Decimal) -> str:
        if outcome == "none_needed":
            return _COVERED_BEFORE
        refs = list(fact.timely_refs or [])
        if refs:
            first = refs[0]
            when = _date_words(first.arrival_date) if first.arrival_date else "an unstated date"
            more = f" (+{len(refs) - 1} more)" if len(refs) > 1 else ""
            arriving = f"{first.spo_number} arrives {when}, in time{more}"
            if outcome == "took":
                return f"{arriving}; this line takes {qty_text(taken)}."
            return f"{arriving}."
        if fact.required_date:
            return f"No supplier PO arrives by {_date_words(fact.required_date)}."
        return "No supplier PO is on its way to this location."

    @staticmethod
    def _borrow_why(outcome: str) -> str:
        """The answer to "why is the donor offered but I did not take" (the captain, verbatim)."""
        if outcome == "none_needed":
            return _COVERED_BEFORE
        if outcome == "offered":
            return (
                "Borrowing is never automatic: a person names the donor and the reason. "
                "Use Amend to borrow."
            )
        return "No other location holds this product free."

    @staticmethod
    def _donor_note(row: _Row) -> Optional[str]:
        """Which donors, and how much each holds. Named beats counted: "6 donors" is not a place
        anybody can go and ask."""
        candidates = row.borrow_candidates
        if not candidates:
            return None
        shown = " · ".join(
            f"{candidate['warehouse_code']} {qty_text(_dec(candidate['free_qty']))}"
            for candidate in candidates[:3]
        )
        more = len(candidates) - 3
        return f"{shown} (+{more} more)" if more > 0 else shown

    @staticmethod
    def _incoming_note(fact: Any) -> Optional[str]:
        """Which document the incoming cover is, said once and shortly.

        Named is the useful form - "ZZT-SPO-0001 arrives 2026-08-25" is something a planner can
        look up, and an unnamed quantity is not - and the rest of the documents are already on
        the location strip, so this states the first and how many follow it.
        """
        refs = list(fact.timely_refs or [])
        if not refs:
            return None
        first = refs[0]
        when = first.arrival_date.isoformat() if first.arrival_date else "an unstated date"
        note = f"{first.spo_number} arrives {when}"
        return note if len(refs) == 1 else f"{note} +{len(refs) - 1} more"

    def _buy_reason(self, row: _Row) -> str:
        """Why this quantity is being bought, said in a way a person can check.

        Three cases the earlier build got wrong, all visible in one card the captain read:

        * the row that took the stock belonged to the SAME sales order, and the sentence read
          "went to SO396563, which outranks this line" on a contribution FROM SO396563 - an
          order cannot outrank itself, and what actually happened is that its own earlier line
          took it;
        * the two scores were EQUAL and the sentence still said "outranks ... 0.00 to 0.00".
          A tie is not a ranking; what decided it was the tiebreaker, so the tiebreaker is what
          the sentence names;
        * nothing was said about Borrow, so a Buy read as "this stock exists nowhere" when it
          existed one location away.
        """
        taker = row.last_taker if row.contested else None
        where = f" at {row.location}" if row.location else ""
        if taker is None:
            reason = (
                f"Nothing free{where} by the delivery date, so the quantity is bought."
            )
        elif taker.sales_order_id == row.sales_order_id:
            reason = (
                f"An earlier line of this sales order (line {taker.line_no}) took the free "
                f"stock{where}, so the residual is bought."
            )
        elif taker.rank_score > row.rank_score:
            reason = (
                f"Free stock{where} went to {taker.so_number}, which outranks this line "
                f"{taker.rank_score:.2f} to {row.rank_score:.2f}."
            )
        else:
            reason = (
                f"Free stock{where} went to {taker.so_number}, which ties this line on rank "
                f"({row.rank_score:.2f}) and was served first by the tiebreaker: sales order "
                "number, then line number."
            )
        if row.borrow_candidates:
            where_from = ", ".join(
                candidate["warehouse_code"] for candidate in row.borrow_candidates[:3]
            )
            reason += (
                f" Borrowing is possible from {where_from}, which is a decision for a person "
                "and carries a reason."
            )
        return reason

    def _source(self, component, row: _Row) -> Dict[str, Any]:
        """One proposed source, with the sentence its rule wrote.

        The engine's reasons are fragments meant to follow "Reserve 10:", so they are stated
        as sentences here. A Buy says why it is a Buy, because "why did this order lose" is the
        question the planner opens the cell with (13.5).
        """
        reason = component.reason
        if component.kind == BUY:
            reason = self._buy_reason(row)
        else:
            reason = reason[:1].upper() + reason[1:] + "."
        return {
            "kind": component.kind,
            "qty": qty_text(component.qty),
            "location": component.source_location,
            #: Addressing only, never rendered: a Reserve component of the confirmation names
            #: its warehouse by id while the screen names it by code. Null for a Buy, which is
            #: not held anywhere, and for the unplannable row, which has no location at all.
            "warehouse_id": row.warehouse_ids.get(component.source_location),
            "reason": reason,
            # The SPO number and its date are IN the engine's sentence ("SPO 202703-S0011
            # arrives on 2027-03-01"), which is what the cell shows. Parsing them back out of
            # it to fill two more fields would be a second source of the same fact.
            "spo_number": None,
            "arrival_date": None,
        }

    # ------------------------------------------------------------ the answer

    def _cell(self, item_code: str, bucket_key: str, members: Sequence[_Row]) -> Dict[str, Any]:
        by_location: Dict[Optional[str], List[_Row]] = defaultdict(list)
        for row in members:
            by_location[row.location].append(row)
        locations = sorted(
            (self._location(location, rows) for location, rows in by_location.items()),
            key=lambda entry: (-Decimal(entry["qty_demand"]), entry["location"] or ""),
        )
        return {
            "item_code": item_code,
            "bucket_key": bucket_key,
            # Summed across every contributing line INCLUDING the unplannable ones: the demand
            # is not hidden because the source record is incomplete (13.7).
            "total_qty": qty_text(sum((row.qty for row in members), _ZERO)),
            "locations": locations,
            "contributions": [self._contribution(row) for row in members],
            "unplannable_count": sum(1 for row in members if row.unplannable),
            "contested_count": sum(1 for row in members if row.contested),
            #: How many DISTINCT sales orders contribute here, and whether the ranking actually
            #: told any two of these rows apart. "The active policy separates none of these
            #: rows" is true of a cell holding one line, and of a cell holding several lines of
            #: one order - and in both cases it reads as a policy failure when nothing failed.
            #: These two say which case it is, so the screen can word it honestly.
            "distinct_order_count": len({row.sales_order_id for row in members}),
            "rank_separates": len({round(float(row.rank_score), 6) for row in members}) > 1,
            # Lines whose OWN delivery date is already past. Counted here so the screen can say
            # "160 of 160 lines are past their delivery date" without walking every
            # contribution, which is the information the aggregate Overdue column used to carry
            # and the only part of it worth keeping.
            "past_count": sum(1 for row in members if row.is_past),
        }

    def _location(self, location: Optional[str], rows: Sequence[_Row]) -> Dict[str, Any]:
        """One (product, location) line of the cell: what is owed there, and what is there.

        The strip used to read "BRW-BB 22" and the 22 was the DEMAND, which is the one reading
        nobody guessed - the captain asked "how do i see the available quantity for each stock,
        is it BRW-BB - 22?". So every number is named, and the stock facts sit beside the
        demand rather than being implied by a sentence.

        A row whose sales order states no location answers `null` for every stock fact, never
        zero: there is no location whose stock could be counted, and a zero would read as
        "that location is empty".
        """
        first = rows[0]
        key = (first.product_id, first.warehouse_id)
        # What was still unclaimed when this cell was reached, off the first row that was
        # actually served: a covered row never draws the pile down, so reading it off the first
        # row full stop would answer "not stated" for a cell whose first line is decided.
        free_remaining = next(
            (row.free_before for row in rows if row.free_before is not None), None
        )
        on_hand, reserved = self._levels.get(key, (None, None))
        incoming = self._incoming.get(key, [])
        stated = location is not None and first.warehouse_id is not None
        owed, _covered = self._pressure.get(key, (None, None))
        incoming_qty = sum((ref.qty for ref in incoming), _ZERO) if stated else None
        # AutoCount's own arithmetic: on hand, less what the book has sold, plus what is on the
        # water. It may be NEGATIVE and is never clamped - "oversold here by 632" is the signal
        # a planner needs, and a floor of zero would report it as "nothing left", which is a
        # different and less useful fact.
        available = (
            (on_hand or _ZERO) - (owed or _ZERO) + (incoming_qty or _ZERO)
            if stated and on_hand is not None
            else None
        )
        return {
            "location": location,
            #: Addressing only: the stock drill-down is opened by id, never by resolving a
            #: warehouse code or an item code back into one.
            "product_id": first.product_id if stated else None,
            "warehouse_id": first.warehouse_id if stated else None,
            #: The demand, kept under its old name because the frontend's source strip reads
            #: it. `qty_demand` is the same number said unambiguously.
            "qty": qty_text(sum((row.qty for row in rows), _ZERO)),
            "qty_demand": qty_text(sum((row.qty for row in rows), _ZERO)),
            "qty_on_hand": qty_text(on_hand) if stated and on_hand is not None else None,
            "qty_reserved": qty_text(reserved) if stated and reserved is not None else None,
            #: What this engine may actually use: on hand, less reserved, less what confirmed
            #: decisions already hold. The figure the proposal was computed from.
            "qty_free": (
                qty_text(self._free.get(key, _ZERO)) if stated else None
            ),
            #: Of that, what was still unclaimed when THIS cell's lines were served. Earlier
            #: dates draw first, so a December cell can face a smaller pile than the product's
            #: free figure suggests.
            "qty_free_remaining": (
                qty_text(free_remaining) if stated and free_remaining is not None
                else None
            ),
            #: What confirmed decisions are holding here. On hand, less reserved, less this, IS
            #: `qty_free`, so the arithmetic on screen closes rather than looking like a
            #: rounding error.
            "qty_held_by_decisions": (
                qty_text(self._held.get(key, _ZERO)) if stated else None
            ),
            #: What the WHOLE BOOK still owes at this location - every open line of every open
            #: sales order, not merely the ones on this board. The number that stops "478 free"
            #: being read as "478 available to me" when 47,009 is owed.
            "qty_owed_all_orders": (
                qty_text(self._pressure.get(key, (_ZERO, _ZERO))[0]) if stated else None
            ),
            #: Of that, the part already covered by a confirmed decision, so committed pressure
            #: can be told from uncommitted pressure.
            "qty_owed_confirmed": (
                qty_text(self._pressure.get(key, (_ZERO, _ZERO))[1]) if stated else None
            ),
            #: Still to arrive at this location: allocated on a supply PO, not yet received.
            "qty_incoming": qty_text(incoming_qty) if stated else None,
            # ---- AutoCount's Stock Status vocabulary, which is what the planner reads ----
            #: "SO Qty": everything the book still owes here. The same number as
            #: `qty_owed_all_orders`, under the word the captain uses.
            "so_qty": qty_text(owed) if stated and owed is not None else None,
            #: "PO Qty" in AutoCount is the supplier order; in Sorento that is the SPO.
            "spo_qty": qty_text(incoming_qty) if stated else None,
            #: "Available Qty": on hand - SO + SPO. Signed.
            "available_qty": qty_text(available) if available is not None else None,
            "incoming": [
                {
                    "spo_number": ref.spo_number,
                    "arrival_date": ref.arrival_date,
                    "qty": qty_text(ref.qty),
                }
                for ref in sorted(
                    incoming, key=lambda ref: (ref.arrival_date is None, ref.arrival_date)
                )
            ] if stated else [],
            "qty_proposed_reserve": self._proposed_text(rows, RESERVE),
            "qty_proposed_incoming": self._proposed_text(rows, TIMELY_SPO),
            "qty_proposed_buy": self._proposed_text(rows, BUY),
        }

    @staticmethod
    def _proposed_text(rows: Sequence[_Row], kind: str) -> str:
        return qty_text(sum((row.proposed.get(kind, _ZERO) for row in rows), _ZERO))

    def _contribution(self, row: _Row) -> Dict[str, Any]:
        return {
            "key": row.key,
            "sales_order_id": row.sales_order_id,
            #: The CORE sales-order line, which is what the pile queue is addressed by
            #: (`GET .../fulfilment-planning/queue?line_id=`). Addressing only, never rendered.
            #: Distinct from `project_line_id`, which is the MIRROR and is null until somebody
            #: adopts the order - a line with no mirror still stands in a queue.
            "line_id": row.line_id,
            #: The product, for the same drill-down and by the same rule: two products on the
            #: live book share the item code `B2155-NL-BLUE`, so a pile looked up by code would
            #: be the wrong pile. Addressing only, never rendered.
            "product_id": row.product_id,
            #: The MIRROR line id, which is what `confirm` names a line by
            #: (`lines[].project_line_id`). Null until somebody adopts this sales order, and
            #: null is the honest answer: there is no planning record to confirm against.
            "project_line_id": row.project_line_id,
            "so_number": row.so_number,
            "customer_name": row.customer_name,
            #: Addressing only, and the key a pivot BY CUSTOMER groups on: two different
            #: customers can carry the same name, and grouping by the label would merge them.
            "customer_id": row.customer_id,
            #: Who sold it (`sales_orders.sales_agent_id` -> `sales_agents`). The code is what
            #: the column shows; the label names who the code belongs to, in the code's title.
            "agent_code": row.agent_code,
            "agent_label": row.agent_label,
            "project_label": row.project_label,
            #: The key a pivot BY PROJECT groups on (see `_project_key`).
            "project_key": row.project_key,
            "line_no": row.line_no,
            "item_code": row.item_code,
            #: The owed quantity, kept under its old name because the frontend reads it.
            #: `qty_outstanding` is the same number said unambiguously.
            "qty": qty_text(row.qty),
            #: What the customer ordered on this line, what has gone out, and what is still
            #: owed. Three names rather than one `qty`, because they differ the moment a
            #: delivery is part-made and the board plans against the LAST of them.
            "qty_ordered": qty_text(row.qty_ordered or _ZERO),
            "qty_delivered": qty_text(row.qty_delivered or _ZERO),
            "qty_outstanding": qty_text(row.qty),
            #: What the engine proposes to meet it with. The three add up to the outstanding
            #: quantity, which is the balance invariant the per-order sheet also keeps.
            "qty_proposed_reserve": qty_text(row.proposed.get(RESERVE, _ZERO)),
            "qty_proposed_incoming": qty_text(row.proposed.get(TIMELY_SPO, _ZERO)),
            "qty_proposed_buy": qty_text(row.proposed.get(BUY, _ZERO)),
            #: What could be borrowed instead of bought, and from where. Never PROPOSED - a
            #: Borrow needs a donor and a reason from a person (AC-B09) - but never hidden
            #: either, or a Buy reads as "this stock exists nowhere".
            #: The arithmetic behind the Reserve, in the strip's own vocabulary, so the planner
            #: can check it against the drill-down: "1015 on hand, 1015 owed to 12 lines ranked
            #: ahead, 0 left for this line, so it is bought".
            #: Null on a covered line, which is not in the queue these count (see `covered`).
            "so_qty_ahead": (
                None if row.so_qty_ahead is None else qty_text(row.so_qty_ahead)
            ),
            "lines_ahead": row.lines_ahead,
            "available_to_this_line": (
                None
                if row.available_to_this_line is None
                else qty_text(row.available_to_this_line)
            ),
            "qty_borrow_available": qty_text(
                sum(
                    (_dec(candidate["free_qty"]) for candidate in row.borrow_candidates),
                    _ZERO,
                )
            ),
            # The sheet's own candidate, passed through whole. It was being narrowed to the
            # four fields a READER needs, and the board now composes a Borrow: the confirm
            # body names the donor by `warehouse_id` and `donor_project_id`, neither of which
            # a warehouse code can be resolved into on the client without guessing at an id.
            "borrow_candidates": [
                {
                    "source": candidate["source"],
                    "warehouse_code": candidate["warehouse_code"],
                    "warehouse_id": candidate.get("warehouse_id"),
                    "donor_project_ref": candidate.get("donor_project_ref"),
                    "donor_project_id": candidate.get("donor_project_id"),
                    "free_qty": candidate["free_qty"],
                    # AutoCount's triple for the DONOR's pile, and the ranking that put this
                    # row where it is (PLAN 13.11). "Before I decide to borrow, I need to
                    # know I am not hurting them" is not answerable from a free figure.
                    "qty_on_hand": candidate.get("qty_on_hand"),
                    "so_qty": candidate.get("so_qty"),
                    "spo_qty": candidate.get("spo_qty"),
                    "available_qty": candidate.get("available_qty"),
                    "qty_free": candidate.get("qty_free"),
                    "qty_committed": candidate.get("qty_committed"),
                    "need_qty": candidate.get("need_qty"),
                    "available_after_need": candidate.get("available_after_need"),
                    "recommended": bool(candidate.get("recommended")),
                    "donor_impact": candidate.get("donor_impact"),
                }
                for candidate in row.borrow_candidates
            ],
            "required_date": row.required_date,
            #: This line's own date is behind the as-of date. Per line, not per column.
            "is_past": row.is_past,
            "fulfilment_location": row.location,
            #: The same warehouse by id, addressing only. An amendment on a line the engine
            #: proposed nothing for has no Reserve source to read one off, and inventing one
            #: from the location code would be guessing at an id.
            "fulfilment_warehouse_id": row.warehouse_id,
            "unplannable": row.unplannable,
            "priority": row.priority,
            "rank_score": round(float(row.rank_score), 6),
            # The normalised score with the ABSOLUTE fact beside it. On its own a 0.00 next to
            # a 1.00 explains nothing, and under a policy that weights nothing a demand row
            # carries every score is 0.00 - so the screen shows the fact (this line's required
            # date, this order's document date, this customer's terms) and keeps the normalised
            # value secondary.
            "rank_factors": [
                {**factor.as_dict(), "raw": row.raw_facts.get(factor.key)}
                for factor in row.rank_factors
            ],
            #: An active decision already covers this line, and what it froze. A covered line
            #: is not proposed for again: everything above states what was DECIDED.
            "covered": row.covered,
            "decision": row.decision,
            "sources": row.sources,
            # The ladder, rung by rung, in the order it was walked - including the rungs that
            # gave nothing, because "the pool was checked and had none" is the answer to "how
            # did you arrive at the Buy" and an omitted step reads as a step never taken.
            "trail": row.trail,
            # The item facts the ladder judged this line on. Null, never `false`, on a line
            # it did not walk: an unplannable or covered line was judged against nothing.
            "item_flags": row.item_flags,
            "contested": row.contested,
        }

    def _buckets(
        self,
        keys: Iterable[str],
        granularity: str,
        day_window_start: Optional[date],
        as_of: date,
    ) -> List[Dict[str, Any]]:
        """Chronological, earliest first, with No date pinned last (13.3).

        No aggregate column: a past period is a column like any other, carrying `is_past` so
        the screen can tint it and count what is late. A bucket is past when its WHOLE period
        ended before the as-of date - the period we are inside is not past, because some of its
        dates are still to come and tinting it would tell the planner this week is already
        lost.

        Only DATED buckets somebody owes are emitted, so a selection with a three-year gap in
        it produces no columns for those years. That keeps the axis proportional to the work
        rather than to the calendar; the day granularity's 30-column window is the one place a
        run of empty columns IS rendered, because there a gap between two days is the
        information and a calendar that hides its empty days is not a calendar.

        Demand outside the day window is not lost from the plan - it is reached by moving the
        window - but it is not SHOWN, and so is not served from the pile either. A day view can
        therefore offer stock the week view has already promised to a line outside the window,
        which is why the window is a display control rather than a planning horizon.
        """
        present = set(keys)
        dated = sorted(k for k in present if k != NO_DATE_BUCKET)
        if granularity == "day":
            start = day_window_start or self._default_day_window(dated, as_of)
            dated = (
                [(start + timedelta(days=offset)).isoformat()
                 for offset in range(DAY_WINDOW_COLUMNS)]
                if start
                else []
            )
        buckets: List[Dict[str, Any]] = []
        for key in dated:
            end = bucket_end(key, granularity)
            buckets.append(
                {
                    "key": key,
                    "kind": "dated",
                    "label": _bucket_label(key, granularity),
                    "start": date.fromisoformat(key),
                    "is_past": end is not None and end < as_of,
                }
            )
        if NO_DATE_BUCKET in present:
            buckets.append(
                {
                    "key": NO_DATE_BUCKET,
                    "kind": "no_date",
                    "label": "No date",
                    "start": None,
                    # An absent date has not passed. It is simply absent, which is a different
                    # thing and must not be tinted as lateness.
                    "is_past": False,
                }
            )
        return buckets

    @staticmethod
    def _serve_order(keys: Iterable[str]) -> List[str]:
        """Every bucket the selection has, in the order the piles are served.

        Chronological, with the dateless column last: a line nobody has dated cannot claim
        stock ahead of one with a date on it. Deliberately independent of `_buckets`, which
        answers a different question - what is on SCREEN - and at day granularity answers it
        with a 30-column window. Allocating over the window instead would leave every line
        outside it with no proposal at all and would make the board's contest counts describe
        the columns rather than the selection.
        """
        present = set(keys)
        ordered = sorted(key for key in present if key != NO_DATE_BUCKET)
        if NO_DATE_BUCKET in present:
            ordered.append(NO_DATE_BUCKET)
        return ordered

    @staticmethod
    def _default_day_window(dated: Sequence[str], as_of: date) -> Optional[date]:
        """Where the 30-day window opens when the planner has not moved it.

        On the earliest day still to come, and only on the earliest day owed at all when
        everything is already past. Without the second half a selection of old orders would
        open on an empty month; without the first, one whose oldest line is from 2024 would
        open the calendar three years ago - which is what happened the moment the aggregate
        past column was removed and "the earliest dated bucket" stopped meaning "the earliest
        future one".
        """
        if not dated:
            return None
        future = [key for key in dated if date.fromisoformat(key) >= as_of]
        return date.fromisoformat(future[0] if future else dated[0])

    def _standings(self, rows: Sequence[_Row]) -> List[Dict[str, Any]]:
        """Per order: how much of it is on this board, and how much of it can never be decided.

        `decided_count` is 0 from the server, always: the verdicts live in the board's client
        draft (13.4), and the screen recomputes this from the draft it holds. It is carried
        so the shape is the one the frontend already reads, not because the server knows.
        """
        by_order: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            standing = by_order.setdefault(
                row.sales_order_id,
                {
                    "sales_order_id": row.sales_order_id,
                    #: The planning record this order's confirmation posts to
                    #: (`POST /sales-orders/{pso_id}/confirm`). NULL when nobody has adopted
                    #: the sales order yet - the screen then says so instead of guessing.
                    "project_sales_order_id": row.project_sales_order_id,
                    "so_number": row.so_number,
                    "customer_name": row.customer_name,
                    "line_count": 0,
                    "decided_count": 0,
                    "unplannable_count": 0,
                },
            )
            standing["line_count"] += 1
            if row.unplannable:
                standing["unplannable_count"] += 1
        return sorted(by_order.values(), key=lambda s: s["so_number"] or "")
