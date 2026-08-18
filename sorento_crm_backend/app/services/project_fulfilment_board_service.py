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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import ProjectSalesOrderLine
from app.services.error_handler import AppException
from app.services.project_supply_service import ProjectSupplyService, _open_of
from app.services.scm import priority
from app.services.scm.demand import is_open_demand
from app.services.scm.front_planning_engine import (
    BUY,
    RESERVE,
    TIMELY_SPO,
    attribute_sources,
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


def _project_label(order: SalesOrder) -> Optional[str]:
    note = (order.internal_note or "").strip()
    if not note:
        return None
    if note.startswith(_PROJECT_NOTE_PREFIX):
        return note[len(_PROJECT_NOTE_PREFIX):].strip() or None
    return note


class _Row:
    """One still-owed core sales-order line, which is all the board is ever built from."""

    __slots__ = (
        "line_id", "sales_order_id", "so_number", "customer_id", "customer_name",
        "project_label", "order_date", "line_no", "item_code", "product_id", "qty",
        "required_date", "warehouse_id", "location", "priority", "demand_class",
        "payment_terms_days", "bucket_key", "is_past", "rank_score", "rank_factors",
        "sources", "contested",
    )

    def __init__(self, **kw: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))
        self.rank_score = 0.0
        self.rank_factors = []
        self.sources = []
        self.contested = False
        self.is_past = False

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

    # ----------------------------------------------------------------- public

    def build(
        self,
        so_numbers: Sequence[str],
        *,
        granularity: str = "week",
        as_of: Optional[date] = None,
        day_window_start: Optional[date] = None,
        preview_policy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The board for one selection of sales orders.

        `as_of` is a parameter rather than the clock so which periods read as past is
        reproducible, and it is echoed back in the response for the same reason: a board that
        quietly disagreed with itself between two reads would be disagreeing about which of the
        planner's commitments are already late.
        """
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
        for row in rows:
            row.bucket_key = bucket_key_for(row.required_date, as_of, granularity)
            # Per LINE, against its own date, which is the number the "N of M lines are past
            # their required date" summary counts. A line dated yesterday is past even though
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

        # Board order: bucket by bucket, product by product, and inside a cell by rank. That
        # is the order the one pile is served in, so a line owed in 2025 is served before a
        # line owed in 2030 rather than losing to it by an accident of iteration. With the
        # buckets now plainly chronological this falls out of the axis itself, where before it
        # needed the aggregate past column pinned to the front.
        served: List[_Row] = []
        for bucket in buckets:
            for item in products:
                served.extend(cells_by_key.get((item, bucket["key"]), []))

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
            "orders": self._standings(rows),
        }

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
            self.db.query(SalesOrderLine, SalesOrder, Product, Warehouse)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .join(Product, Product.id == SalesOrderLine.product_id)
            .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
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
            {str(order.customer_id) for _l, order, _p, _w in records if order.customer_id}
        )
        terms = priority.payment_terms_by_customer(self.db, list(customers.keys()))
        line_numbers = self._line_numbers(records)

        rows: List[_Row] = []
        for line, order, product, warehouse in records:
            customer_id = str(order.customer_id) if order.customer_id else None
            row = _Row(
                line_id=str(line.id),
                sales_order_id=str(order.id),
                so_number=order.so_number,
                customer_id=customer_id,
                customer_name=customers.get(customer_id or ""),
                project_label=_project_label(order),
                order_date=order.order_date,
                line_no=line_numbers[str(line.id)],
                item_code=product.product_code,
                product_id=str(line.product_id),
                # The same open quantity the sheet promises (AC-B01), imported rather than
                # restated: what is still owed, in the line's own UOM.
                qty=_open_of(line),
                required_date=line.required_date,
                warehouse_id=str(line.warehouse_id) if line.warehouse_id else None,
                location=warehouse.warehouse_code if warehouse else None,
                priority=line.priority,
                demand_class=order.demand_class,
            )
            row.payment_terms_days = terms.get(customer_id or "")
            rows.append(row)
        return rows

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
        for line, order, product, _warehouse in records:
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

        mirrored = self._mirror_line_numbers([str(line.id) for line, *_rest in records])
        for entries in by_order.values():
            ids = [entry[3] for entry in entries]
            numbers = [mirrored.get(line_id) for line_id in ids]
            if all(n is not None for n in numbers) and len(set(numbers)) == len(numbers):
                for line_id, number in zip(ids, numbers):
                    derived[line_id] = int(number)
        return derived

    def _mirror_line_numbers(self, core_line_ids: Sequence[str]) -> Dict[str, int]:
        if not core_line_ids:
            return {}
        rows = (
            self.db.query(
                ProjectSalesOrderLine.core_sales_order_line_id,
                ProjectSalesOrderLine.line_no,
            )
            .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(list(core_line_ids)))
            .all()
        )
        seen: Dict[str, int] = {}
        for core_id, line_no in rows:
            if core_id is None or line_no is None:
                continue
            # A core line claimed by two planning records cannot name one number; leave it to
            # the derived ordinal rather than picking a winner.
            seen[str(core_id)] = -1 if str(core_id) in seen else int(line_no)
        return {k: v for k, v in seen.items() if v > 0}

    # -------------------------------------------------------------- sourcing

    def _allocate(self, served: Sequence[_Row]) -> None:
        """Serve each (product, location) pile down the board order, and say who lost.

        Deliberately NOT pro-rata. Splitting 100 free units across five lines needing 100 each
        produces five short deliveries instead of one complete one and four honest Buys, and
        short-shipping everybody is the worst outcome available.

        The division itself is `attribute_sources` - the same engine the per-order sheet runs,
        called once per pile with the lines pre-ordered by the ranking. Only the order differs.
        """
        plannable = [row for row in served if not row.unplannable]
        for row in served:
            if row.unplannable:
                row.sources = [
                    {
                        "kind": "unplannable",
                        "qty": qty_text(row.qty),
                        "location": None,
                        "reason": (
                            "No fulfilment location on the sales order line, so nothing can "
                            "be sourced for it."
                        ),
                        "spo_number": None,
                        "arrival_date": None,
                    }
                ]

        product_ids = {row.product_id for row in plannable if row.product_id}
        free = self.supply.free_stock_by_location(product_ids)
        spo = self.supply.incoming_by_location(
            product_ids, {row.warehouse_id for row in plannable if row.warehouse_id}
        )

        piles: Dict[Tuple[str, str], List[_Row]] = defaultdict(list)
        for row in plannable:
            piles[(row.product_id, row.warehouse_id)].append(row)

        for (product_id, warehouse_id), members in piles.items():
            location = members[0].location or warehouse_id
            attributed = attribute_sources(
                warehouse_code=location,
                opening_stock=free.get((product_id, warehouse_id), _ZERO),
                supply_events=[
                    {
                        "spo_number": ref.spo_number,
                        "spo_line_no": ref.spo_line_no,
                        "allocation_id": ref.allocation_id,
                        "arrival_date": ref.arrival_date,
                        "qty": ref.qty,
                    }
                    for ref in spo.get((product_id, warehouse_id), [])
                ],
                demand_lines=[
                    {
                        "so_number": row.so_number,
                        "line_no": row.line_no,
                        "line_id": row.line_id,
                        "open_qty": row.qty,
                        "required_date": row.required_date,
                    }
                    for row in members
                ],
                preserve_demand_order=True,
            )
            taken = _ZERO
            winner: Optional[_Row] = None
            for row in members:
                components = attributed.get((row.so_number, row.line_no), ())
                bought = sum(
                    (c.qty for c in components if c.kind == BUY), _ZERO
                )
                supplied = sum(
                    (c.qty for c in components if c.kind in (RESERVE, TIMELY_SPO)), _ZERO
                )
                # Contested means the supply this line would otherwise have had was actually
                # TAKEN by a row served before it - the whole point of showing the cell.
                # A location that never held any stock is NOT contested; it is a plain Buy.
                row.contested = bought > _ZERO and taken > _ZERO
                row.sources = [
                    self._source(component, row, winner)
                    for component in components
                ]
                if supplied > _ZERO:
                    taken += supplied
                    winner = row

    def _source(self, component, row: _Row, winner: Optional[_Row]) -> Dict[str, Any]:
        """One proposed source, with the sentence its rule wrote.

        The engine's reasons are fragments meant to follow "Reserve 10:", so they are stated
        as sentences here. A contested Buy says who took the stock instead of stating a bare
        residual, because "why did this order lose" is the question the planner opens the cell
        with (13.5).
        """
        reason = component.reason
        if component.kind == BUY and row.contested and winner is not None:
            if winner.bucket_key == row.bucket_key:
                reason = (
                    f"Free stock at {row.location} went to {winner.so_number}, which "
                    f"outranks this line {winner.rank_score:.2f} to {row.rank_score:.2f}."
                )
            else:
                reason = (
                    f"Free stock at {row.location} went to {winner.so_number}, which is "
                    "owed sooner."
                )
        elif component.kind == BUY:
            reason = (
                f"Nothing free at {row.location} by the required date, so the quantity is "
                "bought."
                if row.location
                else "Nothing free by the required date, so the quantity is bought."
            )
        else:
            reason = reason[:1].upper() + reason[1:] + "."
        return {
            "kind": component.kind,
            "qty": qty_text(component.qty),
            "location": component.source_location,
            "reason": reason,
            # The SPO number and its date are IN the engine's sentence ("SPO 202703-S0011
            # arrives on 2027-03-01"), which is what the cell shows. Parsing them back out of
            # it to fill two more fields would be a second source of the same fact.
            "spo_number": None,
            "arrival_date": None,
        }

    # ------------------------------------------------------------ the answer

    def _cell(self, item_code: str, bucket_key: str, members: Sequence[_Row]) -> Dict[str, Any]:
        totals: Dict[Optional[str], Decimal] = {}
        for row in members:
            totals[row.location] = totals.get(row.location, _ZERO) + row.qty
        return {
            "item_code": item_code,
            "bucket_key": bucket_key,
            # Summed across every contributing line INCLUDING the unplannable ones: the demand
            # is not hidden because the source record is incomplete (13.7).
            "total_qty": qty_text(sum((row.qty for row in members), _ZERO)),
            "locations": [
                {"location": location, "qty": qty_text(qty)}
                for location, qty in sorted(
                    totals.items(), key=lambda item: (-item[1], item[0] or "")
                )
            ],
            "contributions": [self._contribution(row) for row in members],
            "unplannable_count": sum(1 for row in members if row.unplannable),
            "contested_count": sum(1 for row in members if row.contested),
            # Lines whose OWN required date is already past. Counted here so the screen can say
            # "160 of 160 lines are past their required date" without walking every
            # contribution, which is the information the aggregate Overdue column used to carry
            # and the only part of it worth keeping.
            "past_count": sum(1 for row in members if row.is_past),
        }

    def _contribution(self, row: _Row) -> Dict[str, Any]:
        return {
            "key": row.key,
            "sales_order_id": row.sales_order_id,
            "so_number": row.so_number,
            "customer_name": row.customer_name,
            "project_label": row.project_label,
            "line_no": row.line_no,
            "item_code": row.item_code,
            "qty": qty_text(row.qty),
            "required_date": row.required_date,
            #: This line's own date is behind the as-of date. Per line, not per column.
            "is_past": row.is_past,
            "fulfilment_location": row.location,
            "unplannable": row.unplannable,
            "priority": row.priority,
            "rank_score": round(float(row.rank_score), 6),
            "rank_factors": [factor.as_dict() for factor in row.rank_factors],
            "sources": row.sources,
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
