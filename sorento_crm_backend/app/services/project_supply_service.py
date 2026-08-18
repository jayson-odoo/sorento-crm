"""Order promising: the supply composition sheet, and the one atomic confirmation.

Contract: `PLAN-scm-front-planning.md` sections 3.1 to 3.5 and 4,
`documentation/plans/scm/STAGE1C-scm-front-planning-promising.md` section 5, UAC groups B
and C.

The arithmetic is NOT here. It is the pure engine next door
(`app.services.scm.front_planning_engine`), so the rules can be tested without a database
and so the sheet and the commit cannot drift into two different opinions about the same
line. This file is everything around it: which facts are read, how the one location pile is
shared, what is rechecked at commit, and what is written.

Four ideas run through the whole file.

**Confirmation is one decision per SO, covering the lines the planner chose** (3.1, as
amended by PLAN-fulfilment-planning-from-autocount-so.md 13.4). It was atomic over every
line of the order; it is now atomic over every line of THIS confirmation:

> "we shouldn't block the confirm when the decision for the order are incomplete yet, we
>  might want to flow a few product to reorder planning first"   (captain)

One stale, unbalanced or unmapped line among the chosen ones still rolls back the whole
transaction, and the refusal still names every failing line by line number and item code.
No UUID ever appears in a message. What changed is that a line the planner did not choose
is EXPLICITLY UNDECIDED (`decided: false`, no snapshot, no allocation, no inquiry row) -
never implicitly zero and never implicitly covered - so its full open quantity keeps
counting as demand for reorder planning. That is the whole reason the captain wanted this,
and the per-line half of `scm.committed_v` (`app/services/scm/demand.py`) is what makes it
true rather than merely intended. There is still no per-line workflow STATE: a line is
covered by the order's one active revision or it is not.

**Every fact is re-read at commit** (AC-C03). The sheet may have been open for an hour, and
the stock behind it moves. The payload is a proposal, not an instruction: open quantity, the
line's share of timely SPO, Reserve eligibility, the BRW cap, donor availability and product
lifecycle are all recomputed from authoritative rows before anything is written.

**Confirmed cover is not free** (AC-B13). Free stock is on hand, minus reserved, minus what
active decisions (and legacy confirmed allocations, which belong to no decision) already
hold. The order being composed is excluded from that subtraction, or its own previous
revision would compete with the one replacing it.

**One pile, one order of consumption** (3.5). Several lines can want the same product at the
same location, and which of them gets the stock and which gets the incoming is decided by
`attribute_sources`, once, for every outstanding line at that product and location - not by
whichever line the database happened to return first.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import InboundShipment, SPOAllocation, Supplier
from app.models.product import Product
from app.models.project_so import (
    ALLOC_SOURCE_BRW,
    ALLOC_SOURCE_ORDER,
    ALLOC_SOURCE_OTHER_LOCATION,
    ALLOC_SOURCE_OTHER_PROJECT,
    ALLOC_SOURCE_OWN,
    CLAIM_ACCEPTED,
    DECISION_ACTIVE,
    DECISION_CHALLENGED,
    DECISION_SUPERSEDED,
    LIVE_SO_STATUSES,
    AllocationClaim,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.models.projects import Project
from app.models.scm import ItemClassification, ReorderLevel
from app.models.user import User
from app.services.error_handler import AppException
from app.services.scm import priority
from app.services.scm.demand import demand_qty, is_open_demand
from app.services.scm.front_planning_engine import (
    BUY,
    RESERVE,
    TIMELY_SPO,
    Component,
    attribute_sources,
    propose_line,
    qty_text,
    reserve_capacity,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")

#: The statuses a Project SO may be confirmed in. A draft has not left the building and a
#: blocked one has findings in the way.
#:
#: `adopted` is IN, which is `PLAN-fulfilment-planning-from-autocount-so.md` section 4's own
#: verdict on this site ("Confirming it is the point"): an order adopted from the AutoCount
#: book is a real customer commitment that nobody in this module authored, and planning it
#: is the entire journey. It is `LIVE_SO_STATUSES` exactly - the same three the worklist and
#: the reconciliation service already treat as live - so the tuple is imported rather than
#: restated, or the two would drift the next time a status is added.
CONFIRMABLE_STATUSES = LIVE_SO_STATUSES

#: The warehouse segment the hot-selling test is about (PLAN 3.3). Stored on the warehouse
#: row, never parsed out of a code.
DEALER_SEGMENT = "dealer"


def _dec(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


#: How many of the queue in front of a line are NAMED beside it. The captain's question is "why
#: do the orders stand ahead of me", and 142 rows is not an answer to it: three named lines plus
#: a count of the rest BY WHAT PUT THEM THERE is. The whole queue is a click away (`pile_queue`).
_AHEAD_NAMED = 3


def _leading_factor(mine: Dict[str, Any], theirs: Dict[str, Any]) -> str:
    """Which factor put `theirs` in front of `mine`, in one word.

    The largest WEIGHTED difference, `weight * (their value - my value)` over the factors both
    lines carry a value for, because that is literally the term that made their score the bigger
    one. Absent on either side is skipped rather than read as zero, the same rule `rank_score`
    itself applies.

    Equal scores mean the POLICY separated nothing and the queue was decided by the tie-break
    instead. Saying "required date" there would be a lie about a date the two lines share, so it
    is named for what it was: an earlier line of the same order, or a lower sales-order number.
    """
    same_order = (theirs.get("so_number") or "") == (mine.get("so_number") or "")
    tie = "line_order" if same_order else "tie_break"
    if round(float(theirs.get("rank_score") or 0.0), 9) == round(
        float(mine.get("rank_score") or 0.0), 9
    ):
        return tie
    ours = {
        factor.key: factor
        for factor in (mine.get("factors") or [])
        if factor.present and factor.value is not None
    }
    best_key: Optional[str] = None
    best_diff = 0.0
    for factor in theirs.get("factors") or []:
        if not factor.present or factor.value is None or factor.weight <= 0:
            continue
        counterpart = ours.get(factor.key)
        if counterpart is None:
            continue
        diff = float(factor.weight) * (float(factor.value) - float(counterpart.value))
        if diff > best_diff:
            best_key, best_diff = factor.key, diff
    return best_key or tie


def _queue_entry(line: Dict[str, Any], mine: Dict[str, Any]) -> Dict[str, Any]:
    """One line of the queue as a screen reads it, against the line that is asking."""
    return {
        "so_number": line.get("so_number") or "",
        "line_no": line.get("line_no"),
        "qty": qty_text(line["open_qty"]),
        "required_date": line.get("required_date"),
        "rank_score": round(float(line.get("rank_score") or 0.0), 6),
        "leading_factor": _leading_factor(mine, line),
        "same_order": (line.get("so_number") or "") == (mine.get("so_number") or ""),
    }


def _ahead_detail(mine: Dict[str, Any], queued: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Who is in front of this line at its pile, and what put each of them there.

    Three named, in queue order, plus how many more there are and a count of the WHOLE queue by
    leading factor - so "142 lines are ahead" becomes "139 of them by required date, 2 by
    document age, and one is an earlier line of your own order".
    """
    by_factor: Dict[str, int] = {}
    named: List[Dict[str, Any]] = []
    for other in queued:
        entry = _queue_entry(other, mine)
        key = entry["leading_factor"]
        by_factor[key] = by_factor.get(key, 0) + 1
        if len(named) < _AHEAD_NAMED:
            named.append(entry)
    return {
        "lines": named,
        "more": max(len(queued) - len(named), 0),
        "by_factor": by_factor,
    }


def _open_of(core: Optional[SalesOrderLine]) -> Decimal:
    """AC-B01: the core line's CURRENT open fulfilment quantity, floored at zero.

    Not the original customer quantity, and not a figure a downstream reader has already
    netted: what is still owed, in the line's own UOM.
    """
    if core is None:
        return _ZERO
    return max(_dec(core.qty_ordered) - _dec(core.qty_delivered), _ZERO)


class SupplyLinesRefused(AppException):
    """A refusal that names its lines (AC-C02).

    The envelope stays the shared one - `message` is what `extractApiError` reads - and
    `failing_lines` travels beside it, because a sentence cannot tell the sheet WHICH row
    to mark and a list of rows cannot be read out as a sentence.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        failing_lines: Sequence[Dict[str, Any]],
        code: str = "supply_lines_failed",
    ):
        super().__init__(status_code=status_code, message=message, code=code)
        self.detail["failing_lines"] = list(failing_lines)


@dataclass
class _SpoRow:
    spo_number: str
    spo_line_no: Optional[int]
    allocation_id: str
    arrival_date: Optional[date]
    qty: Decimal
    #: Who it is coming from. Display only, and defaulted so every existing construction of
    #: this row keeps working; the sheet does not read it, the stock drill-down does.
    supplier_name: Optional[str] = None


@dataclass
class _LineFacts:
    """Everything one line is judged against, read live (AC-C03).

    `line` and `core` are optional because the same bundle now serves TWO callers: the sheet,
    which judges a mirror line, and the multi-order board, which judges a bare core demand row
    and has no mirror to point at. Everything the source ladder reads is below them.
    """

    line: Optional[ProjectSalesOrderLine] = None
    core: Optional[SalesOrderLine] = None
    item_code: Optional[str] = None
    product_id: Optional[str] = None
    open_qty: Decimal = _ZERO
    required_date: Optional[date] = None
    warehouse: Optional[Warehouse] = None
    pool: Optional[Warehouse] = None
    #: This line's share of the fulfilment location's free stock, from the shared
    #: projection - NOT the whole pile, or two lines would each be offered all of it.
    own_free: Decimal = _ZERO
    #: What the demand ranked AHEAD of this line at its own pile still wants, and how many
    #: lines that is. The arithmetic behind `own_free`, carried so a screen can print it:
    #: "1015 on hand, 1015 owed to 12 earlier lines, 0 left for this line".
    so_qty_ahead: Decimal = _ZERO
    lines_ahead: int = 0
    #: What was left AT THIS LINE'S OWN LOCATION when it was reached - `on hand - reserved -
    #: held - so_qty_ahead`. Distinct from `own_free`, which is what the line actually TOOK of
    #: it (capped at what it needs), and from a Reserve total, which may also draw on the pool.
    available_to_this_line: Decimal = _ZERO
    #: WHO is in that queue: the first `_AHEAD_NAMED` of it in rank order, how many more there
    #: are, and a count of the whole queue by the factor that put each line there. The captain,
    #: on a rung reading "18730 across 142 lines": "why do the orders stand ahead of me? why?"
    ahead_lines_named: List[Dict[str, Any]] = field(default_factory=list)
    ahead_more: int = 0
    ahead_by_factor: Dict[str, int] = field(default_factory=dict)
    pool_free: Decimal = _ZERO
    #: What the POOL'S OWN book, ranked ahead of this line, still claims there, and how many
    #: lines that is - the subtraction behind `pool_free`, carried so a screen can print it:
    #: "BRW holds 1 on hand, but its own orders ahead of this line claim 1, so 0 is left".
    pool_claimed_qty: Decimal = _ZERO
    pool_claimed_lines: int = 0
    pool_reorder_level: Decimal = _ZERO
    is_hot_selling: bool = False
    #: The dealer locations holding this item as ABC A, by code - the evidence behind
    #: `is_hot_selling`, so the verdict can be checked rather than trusted.
    hot_selling_where: List[str] = field(default_factory=list)
    classification_unavailable: bool = False
    is_discontinued: bool = False
    timely_qty: Decimal = _ZERO
    timely_refs: List[_SpoRow] = field(default_factory=list)
    advisory_refs: List[_SpoRow] = field(default_factory=list)

    @property
    def own_code(self) -> Optional[str]:
        return self.warehouse.warehouse_code if self.warehouse else None

    @property
    def pool_code(self) -> Optional[str]:
        return self.pool.warehouse_code if self.pool else None

    @property
    def pool_key(self) -> str:
        """Ledger key for pool draws: one bucket per PRODUCT per pool warehouse.

        `pool_free` is this product's free stock at the pool, so the running balance
        must be scoped the same way. Keyed by warehouse alone, a second product on the
        same SO would read the first product's remaining headroom as its own.
        """
        return f"{self.product_id}:{self.pool.id}" if self.pool else ""

    @property
    def pool_cap(self) -> Decimal:
        return max(self.pool_free - self.pool_reorder_level, _ZERO)


class _BorrowLedger:
    """What is still borrowable as one confirmation's lines are checked in turn.

    Two lines of the same Project SO can both name the same donor location, and each of
    them is checked against live figures - so without a running ledger both would pass and
    the same units would be promised twice inside one transaction. Seeded lazily from the
    live readers so nothing is queried for a location nobody borrows from.
    """

    def __init__(self) -> None:
        self._free: Dict[Tuple[str, str], Decimal] = {}
        self._held: Dict[Tuple[str, str, str], Decimal] = {}

    def free(self, product_id: Optional[str], warehouse_id: str, read) -> Decimal:
        key = (product_id or "", warehouse_id)
        if key not in self._free:
            self._free[key] = read(product_id, warehouse_id)
        return self._free[key]

    def take_free(self, product_id: Optional[str], warehouse_id: str, qty: Decimal) -> None:
        key = (product_id or "", warehouse_id)
        self._free[key] = max(self._free.get(key, _ZERO) - qty, _ZERO)

    def held(
        self, product_id: Optional[str], warehouse_id: str, donor_id: str, read
    ) -> Decimal:
        key = (product_id or "", warehouse_id, donor_id)
        if key not in self._held:
            self._held[key] = read(product_id, warehouse_id, donor_id)
        return self._held[key]

    def take_held(
        self, product_id: Optional[str], warehouse_id: str, donor_id: str, qty: Decimal
    ) -> None:
        key = (product_id or "", warehouse_id, donor_id)
        self._held[key] = max(self._held.get(key, _ZERO) - qty, _ZERO)


class ProjectSupplyService:
    """The supply sheet (`proposal_for`) and the atomic commit (`confirm`)."""

    def __init__(self, db: Session):
        self.db = db
        # Facts about THIS request, filled by `_facts_for` and read by the helpers below.
        # Per-request rather than per-call because one proposal asks the same "what is
        # free at that location" question once per line and once per borrow candidate.
        self._free_cache: Dict[Tuple[str, str], Decimal] = {}
        self._holds_cache: Dict[Tuple[str, str, str], Decimal] = {}
        # AutoCount's Stock Status triple per pile, for the locations this request touches.
        # Lazily filled, and only when somebody asks for borrow donors: a board that offers
        # no Borrow must not pay for three more reads. `None` means "not asked yet".
        self._pile_cache: Optional[Dict[Tuple[str, str], Dict[str, Decimal]]] = None

    # ------------------------------------------------------------------ lookups

    def get_order(self, pso_id: str) -> ProjectSalesOrder:
        order = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == pso_id)
            .first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )
        return order

    def lines_of(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def active_decision(self, pso_id: str) -> Optional[SOSupplyDecision]:
        return (
            self.db.query(SOSupplyDecision)
            .filter(
                SOSupplyDecision.project_sales_order_id == pso_id,
                SOSupplyDecision.state == DECISION_ACTIVE,
            )
            .first()
        )

    def latest_decision(self, pso_id: str) -> Optional[SOSupplyDecision]:
        return (
            self.db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == pso_id)
            .order_by(SOSupplyDecision.revision_no.desc())
            .first()
        )

    # -------------------------------------------------------------- the sheet

    def proposal_for(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        """The Supply composition section for one Project SO (J04).

        Reads live facts, challenges an active revision that no longer matches them, and
        proposes a composition per line with the reason beside every quantity.
        """
        lines = self.lines_of(str(order.id))
        self.challenge_if_drifted(order, lines=lines)
        decision = self.active_decision(str(order.id))
        facts = self._facts_for(order, lines)

        frozen = self._frozen_by_line(decision)
        pool_left: Dict[str, Decimal] = {}
        payload_lines: List[Dict[str, Any]] = []
        for line in lines:
            fact = facts[str(line.id)]
            pool_key = fact.pool_key
            if pool_key and pool_key not in pool_left:
                pool_left[pool_key] = fact.pool_free
            components = self.compose_line(
                fact, pool_free_left=pool_left.get(pool_key, _ZERO)
            )
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

            payload_lines.append(
                self._serialize_line(fact, components, frozen.get(str(line.id)))
            )

        header = self._header_fields(order)
        return {
            "lines_total": len(payload_lines),
            # How much of the order carries a verdict (13.4). The pill stays a whole-order
            # value (AC-A03) and this is the sentence beside it, so "Confirmed" on an order
            # with four of twelve lines decided is not read as a finished order.
            "lines_decided": sum(1 for line in payload_lines if line["decided"]),
            "project_sales_order_id": str(order.id),
            "provisional_ref": order.provisional_ref,
            "autocount_doc_no": order.autocount_doc_no,
            # None, never "None": an adopted order has no project (section 4), and a
            # stringified null is a value the screen renders and links to.
            "project_id": str(order.project_id) if order.project_id else None,
            "project_code": header.get("project_code"),
            "project_name": header.get("project_name"),
            "status": order.status,
            "review_state": self._review_state(order),
            "decision": self._serialize_decision(decision or self.latest_decision(str(order.id))),
            "lines": payload_lines,
        }

    def compose_line(
        self, fact: _LineFacts, *, pool_free_left: Optional[Decimal] = None
    ) -> Tuple[Component, ...]:
        """The source ladder for ONE line: own location, then the shared pool, then timely
        incoming, then Buy - with PLAN 3.3's hot-selling rules deciding what Reserve may touch.

        Public because it has two callers and must never have two implementations. The sheet
        composes one order's lines; the multi-order board composes every contributing line of a
        selection. A board that walked a reduced ladder proposed a Buy for a line the sheet
        would have covered from the pool, so purchasing acting on the board and purchasing
        acting on the sheet disagreed about the same line - which is the whole reason this is a
        method rather than a loop body.

        Borrow is not proposed here, on either surface: it needs a donor and a reason from a
        person (AC-B09). `borrow_candidates_for` is what offers it.

        `pool_free_left` is the caller's running pool balance, because the pool is shared: the
        sheet draws it down across one order's lines, the board across the whole selection.
        Defaults to the whole pool free, which is what a single line on its own may draw.
        """
        free_stock: Dict[str, Decimal] = {}
        if fact.own_code:
            free_stock[fact.own_code] = fact.own_free
        if fact.pool_code:
            free_stock[fact.pool_code] = (
                fact.pool_free if pool_free_left is None else pool_free_left
            )
        return propose_line(
            open_qty=fact.open_qty,
            line_no=fact.line.line_no if fact.line is not None else None,
            required_date=fact.required_date,
            fulfilment_location=fact.own_code,
            is_dealer_hot_selling=fact.is_hot_selling,
            free_stock=free_stock,
            pool_location=fact.pool_code,
            reorder_levels=(
                {fact.pool_code: fact.pool_reorder_level} if fact.pool_code else {}
            ),
            timely_spo_qty=fact.timely_qty,
            timely_spo_refs=[
                {
                    "spo_number": ref.spo_number,
                    "spo_line_no": ref.spo_line_no,
                    "arrival_date": ref.arrival_date,
                    "qty": ref.qty,
                }
                for ref in fact.timely_refs
            ],
            is_discontinued=fact.is_discontinued,
        )

    def borrow_candidates_for(
        self, fact: _LineFacts, *, need: Optional[Decimal] = None
    ) -> List[Dict[str, Any]]:
        """Where else this line could be met from, with what it costs the holder (AC-B09).

        Public for the board, which otherwise prints a bare Buy for a line whose stock exists
        one location away. Requires `demand_facts` or `_facts_for` to have run, because it
        reads the same free / holds caches the proposal was computed from.

        `need` is the line's RESIDUAL at the borrow rung - what the ladder was going to buy -
        and it is what the ranking is computed against (13.11). The caller states it because
        the caller is the one that just walked the ladder; omitted, the donors are ranked on
        availability alone.
        """
        return self._borrow_candidates(fact, need=need or _ZERO)

    def attribution_by_core_line(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Dict[str, Dict[str, Decimal]]]:
        """Each CORE line's share of its product-location pile, keyed by core line id.

        The section 3.5 projection, made public because the confirmation judges a Reserve
        against it and therefore anything that PROPOSES a Reserve has to be judged against the
        same figure. The board used to share the pile among the orders in its own selection,
        which on a crowded location offered a line stock the book had already promised
        elsewhere: `confirm` then refused it, and the planner was told their own location was
        not their own location.

        Requires `demand_facts` (or `_facts_for`) to have run: it reads the free-stock cache
        that the proposal was computed from, so the share and the availability behind it cannot
        come from two different reads.
        """
        warehouses = self._warehouses(warehouse_ids)
        return self._attribution(
            product_ids, warehouse_ids, warehouses, self._spo_rows(product_ids, warehouse_ids)
        )

    def demand_facts(
        self, rows: Sequence[Dict[str, Any]]
    ) -> Dict[str, _LineFacts]:
        """`_LineFacts` for arbitrary CORE demand rows, keyed by the caller's own `key`.

        The board's way in to the same facts the sheet judges a line against: the fulfilment
        warehouse and its pool, the pool's free stock and reorder level, the dealer hot-selling
        verdict, product lifecycle, and the location's undelivered incoming. Each row states
        `key`, `product_id`, `warehouse_id`, `open_qty`, `required_date` and `item_code`.

        `own_free` and `timely_qty` are filled here too, from the SAME book-wide projection the
        confirmation judges against (`_attribution`): a line may reserve what is left of its
        pile after the demand the active policy ranks ahead of it, and nothing more. They used
        to be left for the caller, from when the board ran a contest of its own among the
        selected orders - which is exactly how it came to propose Reserves the confirmation
        refused.
        """
        product_ids = {str(r["product_id"]) for r in rows if r.get("product_id")}
        warehouse_ids = {str(r["warehouse_id"]) for r in rows if r.get("warehouse_id")}
        warehouses = self._warehouses(warehouse_ids)
        pool_ids = {
            str(w.pool_warehouse_id) for w in warehouses.values() if w.pool_warehouse_id
        }
        warehouses.update(self._warehouses(pool_ids - set(warehouses)))

        self._free_cache = self._free_stock(product_ids, exclude_order_id=None)
        self._holds_cache = self._holds_by_project(product_ids, exclude_order_id=None)
        self._pile_cache = None
        hot, unavailable, hot_where = self._classification(product_ids)
        levels = self._reorder_levels(product_ids, pool_ids)
        discontinued = self._discontinued(product_ids)
        spo = self._spo_rows(product_ids, warehouse_ids)

        attribution = self._attribution(
            product_ids,
            warehouse_ids,
            warehouses,
            self._spo_rows(product_ids, warehouse_ids),
            # Only these lines are asking, so only these lines' queues are described. Every
            # other line of the pile still counts toward them - it is named, not counted, that
            # is being narrowed here.
            detail_for={
                str(row.get("line_id") or row["key"]) for row in rows if row.get("key")
            },
        )
        # What the shared pool's own book claims ahead of each line that would draw on it.
        pool_ahead = self.pool_claims(
            product_ids,
            {
                str(w.pool_warehouse_id)
                for w in warehouses.values()
                if w.pool_warehouse_id
            },
            [
                {
                    "key": str(row["key"]),
                    "product_id": str(row["product_id"]),
                    "pool_id": str(
                        warehouses[str(row["warehouse_id"])].pool_warehouse_id
                    ),
                    "required_date": row.get("required_date"),
                    "order_date": row.get("order_date"),
                    "payment_terms_days": row.get("payment_terms_days"),
                    "demand_class": row.get("demand_class"),
                    "so_number": row.get("so_number"),
                    "line_no": row.get("line_no"),
                }
                for row in rows
                if row.get("product_id")
                and row.get("warehouse_id")
                and str(row["warehouse_id"]) in warehouses
                and warehouses[str(row["warehouse_id"])].pool_warehouse_id
            ],
        )

        facts: Dict[str, _LineFacts] = {}
        for row in rows:
            product_id = str(row["product_id"]) if row.get("product_id") else None
            warehouse = (
                warehouses.get(str(row["warehouse_id"])) if row.get("warehouse_id") else None
            )
            pool = (
                warehouses.get(str(warehouse.pool_warehouse_id))
                if warehouse and warehouse.pool_warehouse_id
                else None
            )
            required_date = row.get("required_date")
            key = (product_id or "", str(warehouse.id) if warehouse else "")
            timely_refs = [
                ref
                for ref in spo.get(key, [])
                if required_date is None
                or (ref.arrival_date is not None and ref.arrival_date <= required_date)
            ]
            # The projection is keyed by CORE LINE id; the caller's own `key` may be anything
            # (the board's is a cell address). It states `line_id` when the two differ.
            shares = attribution.get(key, {}).get(
                str(row.get("line_id") or row["key"]), {}
            )
            claim = pool_ahead.get(str(row["key"]), {})
            claimed = _dec(claim.get("qty"))
            facts[str(row["key"])] = _LineFacts(
                item_code=row.get("item_code"),
                product_id=product_id,
                open_qty=_dec(row.get("open_qty")),
                required_date=required_date,
                warehouse=warehouse,
                pool=pool,
                own_free=_dec(shares.get(RESERVE)),
                timely_qty=_dec(shares.get(TIMELY_SPO)),
                so_qty_ahead=_dec(shares.get("so_qty_ahead")),
                lines_ahead=int(shares.get("lines_ahead") or 0),
                available_to_this_line=_dec(shares.get("available_to_this_line")),
                ahead_lines_named=list((shares.get("ahead_detail") or {}).get("lines") or []),
                ahead_more=int((shares.get("ahead_detail") or {}).get("more") or 0),
                ahead_by_factor=dict(
                    (shares.get("ahead_detail") or {}).get("by_factor") or {}
                ),
                # The pool nets its own book the same way the own location does: what is left
                # after the lines the policy ranks ahead of this one there.
                pool_free=(
                    max(self._free_at(product_id, str(pool.id)) - claimed, _ZERO)
                    if pool
                    else _ZERO
                ),
                pool_claimed_qty=claimed if pool else _ZERO,
                pool_claimed_lines=int(claim.get("lines") or 0) if pool else 0,
                pool_reorder_level=levels.get(
                    (product_id or "", str(pool.id) if pool else ""), _ZERO
                ),
                is_hot_selling=(product_id or "") in hot,
                hot_selling_where=list(hot_where.get(product_id or "", [])),
                classification_unavailable=(product_id or "") in unavailable,
                is_discontinued=(product_id or "") in discontinued,
                timely_refs=timely_refs,
                advisory_refs=[ref for ref in spo.get(key, []) if ref not in timely_refs],
            )
        return facts

    def _serialize_line(
        self,
        fact: _LineFacts,
        components: Sequence[Component],
        frozen: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        line = fact.line
        return {
            "project_line_id": str(line.id),
            "line_no": line.line_no,
            "item_code": fact.item_code,
            "description": line.description,
            "uom": line.uom,
            "open_qty": qty_text(fact.open_qty),
            "required_date": fact.required_date,
            "fulfilment_location": fact.own_code,
            "is_dealer_hot_selling": fact.is_hot_selling,
            "classification_unavailable": fact.classification_unavailable,
            "is_discontinued": fact.is_discontinued,
            "pool_location": fact.pool_code,
            "pool_cap": qty_text(fact.pool_cap) if fact.pool_code else None,
            "pool_reorder_level": (
                qty_text(fact.pool_reorder_level) if fact.pool_code else None
            ),
            "components": [
                self._serialize_component(component, fact) for component in components
            ],
            "timely_spo": [self._serialize_spo(ref) for ref in fact.timely_refs],
            "advisory_spo": [self._serialize_spo(ref) for ref in fact.advisory_refs],
            # Ranked against what this line still has to cover - the Buy the ladder just
            # proposed - because that is the quantity a donor would be asked for (13.11).
            "borrow_candidates": self._borrow_candidates(
                fact,
                need=sum(
                    (component.qty for component in components if component.kind == BUY),
                    _ZERO,
                ),
            ),
            "frozen": frozen,
            # Covered by the order's active revision, or explicitly not (13.4). Never
            # inferred from `frozen` being absent by whoever reads this next: an undecided
            # line and a line decided to nothing would look identical if it were.
            "decided": frozen is not None,
        }

    def _serialize_component(
        self, component: Component, fact: _LineFacts
    ) -> Dict[str, Any]:
        warehouse_id = None
        if component.source_location:
            if fact.own_code == component.source_location and fact.warehouse:
                warehouse_id = str(fact.warehouse.id)
            elif fact.pool_code == component.source_location and fact.pool:
                warehouse_id = str(fact.pool.id)
        return {
            "kind": component.kind,
            "qty": qty_text(component.qty),
            "reason": component.reason,
            "source_location": component.source_location,
            "source_warehouse_id": warehouse_id,
        }

    def _serialize_spo(self, ref: _SpoRow) -> Dict[str, Any]:
        return {
            "spo_number": ref.spo_number,
            "arrival_date": ref.arrival_date,
            "qty": qty_text(ref.qty),
        }

    def frozen_lines_of(
        self, decision: Optional[SOSupplyDecision]
    ) -> Dict[str, Dict[str, Any]]:
        """`_frozen_by_line` for a caller outside this service (the planning board).

        Public because the board reads back the same snapshots the sheet does, and a second
        parse of `line_snapshots` on that side would be a second opinion about what a decision
        covered.
        """
        return self._frozen_by_line(decision)

    def _frozen_by_line(
        self, decision: Optional[SOSupplyDecision]
    ) -> Dict[str, Dict[str, Any]]:
        """What the active revision froze, so a confirmed line states what it was balanced
        against rather than the quantity that is live now."""
        if decision is None:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for snapshot in decision.line_snapshots or []:
            line_id = str(snapshot.get("project_line_id") or "")
            if not line_id:
                continue
            out[line_id] = {
                "open_qty": str(snapshot.get("open_qty") or "0"),
                "components": list(snapshot.get("components") or []),
                # Read back beside the components it explains. A snapshot written before the
                # field existed simply has none, which is the same answer as "nobody amended
                # this line" and reads identically on screen.
                "amend_reason": snapshot.get("amend_reason"),
            }
        return out

    def _serialize_decision(
        self, decision: Optional[SOSupplyDecision]
    ) -> Optional[Dict[str, Any]]:
        if decision is None:
            return None
        name = None
        if decision.confirmed_by:
            user = (
                self.db.query(User.name).filter(User.id == decision.confirmed_by).first()
            )
            name = user[0] if user else None
        return {
            "revision_no": decision.revision_no,
            "state": decision.state,
            "confirmed_by_name": name,
            "confirmed_at": decision.confirmed_at,
            "challenged_reason": (
                decision.superseded_reason
                if decision.state == DECISION_CHALLENGED
                else None
            ),
        }

    def _review_state(self, order: ProjectSalesOrder) -> Optional[str]:
        from app.services.project_so_reconciliation_service import (
            ProjectSOReconciliationService,
        )

        states = ProjectSOReconciliationService(self.db).review_states_for([str(order.id)])
        return (states.get(str(order.id)) or {}).get("review_state")

    def _header_fields(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        row = (
            self.db.query(Project.project_code, Project.title)
            .filter(Project.id == order.project_id)
            .first()
        )
        return {
            "project_code": row[0] if row else None,
            "project_name": row[1] if row else None,
        }

    # ------------------------------------------------------- supersede / challenge

    def supersede_for_material_change(
        self, order: ProjectSalesOrder, reason: str
    ) -> bool:
        """AC-C06: a material change retires the active revision, with no replacement.

        The whole SO goes back to Needs CS review. Nothing about the components is
        deleted: the superseded revision and its allocations stay for audit, and any Buy
        already placed stays in purchasing's ledger.
        """
        decision = self.active_decision(str(order.id))
        if decision is None:
            return False
        decision.state = DECISION_SUPERSEDED
        decision.superseded_at = datetime.utcnow()
        decision.superseded_reason = reason
        self.db.flush()
        return True

    def challenge_if_drifted(
        self,
        order: ProjectSalesOrder,
        *,
        lines: Optional[Sequence[ProjectSalesOrderLine]] = None,
    ) -> Optional[str]:
        """Compare the active revision's snapshots against live facts (PLAN 5.3).

        A revision is a statement about quantities, links and dates that were true when CS
        pressed Confirm. When one of them moves the revision is no longer a promise anybody
        can keep, so it is flipped to `challenged` and the SO reads Needs CS review again -
        rather than staying Confirmed against facts that have gone.
        """
        decision = self.active_decision(str(order.id))
        if decision is None:
            return None
        rows = list(lines if lines is not None else self.lines_of(str(order.id)))
        by_id = {str(line.id): line for line in rows}
        core_ids = [
            str(line.core_sales_order_line_id)
            for line in rows
            if line.core_sales_order_line_id
        ]
        cores = {
            str(core.id): core
            for core in (
                self.db.query(SalesOrderLine)
                .filter(SalesOrderLine.id.in_(core_ids))
                .all()
                if core_ids
                else []
            )
        }

        reason = None
        snapshots = decision.line_snapshots or []
        for snapshot in snapshots:
            line = by_id.get(str(snapshot.get("project_line_id") or ""))
            if line is None:
                reason = "A line the confirmed revision covered is no longer on this sales order."
                break
            frozen_core = snapshot.get("core_line_id")
            live_core = (
                str(line.core_sales_order_line_id)
                if line.core_sales_order_line_id
                else None
            )
            if frozen_core is not None and str(frozen_core) != (live_core or ""):
                reason = (
                    f"Line {line.line_no} now points at a different AutoCount line than "
                    "the confirmed revision did."
                )
                break
            core = cores.get(live_core or "")
            frozen_open = snapshot.get("open_qty")
            if frozen_open is not None and _dec(frozen_open) != _open_of(core):
                reason = (
                    f"Line {line.line_no} is now open for "
                    f"{qty_text(_open_of(core))}, and the confirmed revision was balanced "
                    f"against {qty_text(_dec(frozen_open))}."
                )
                break
            frozen_date = snapshot.get("required_date")
            live_date = core.required_date if core is not None else None
            if frozen_date is not None and str(frozen_date) != (
                live_date.isoformat() if live_date else ""
            ):
                reason = f"Line {line.line_no}'s required date has changed."
                break
        # A revision covering FEWER lines than the order has is not drift: since 13.4 a
        # confirmation covers the subset the planner chose, and the remainder is
        # deliberately undecided. Counting the two sets and challenging on a mismatch
        # would flip every partial decision to `challenged` the instant it was written.
        # A line the revision DID cover and that has since gone is caught above, by name.
        if reason is None:
            return None

        decision.state = DECISION_CHALLENGED
        decision.superseded_at = datetime.utcnow()
        decision.superseded_reason = reason
        self.db.flush()
        return reason

    # ---------------------------------------------------------------- the commit

    def confirm(
        self,
        order: ProjectSalesOrder,
        payload: Any,
        *,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        """One transaction, every CHOSEN line, or nothing (PLAN 3.1, AC-C01 as amended
        by PLAN-fulfilment-planning-from-autocount-so.md 13.4).

        The payload names the lines being confirmed. They commit together or not at all;
        the lines it does not name stay undecided and keep flowing to reorder planning.
        A payload naming NO line is refused, because superseding the revision that is
        holding stock and putting nothing in its place is not a decision anybody made.

        The caller owns the commit. Everything here runs inside it, including the Order
        Inquiry refresh, so purchasing can never be told to buy something that was not
        also promised.
        """
        locked = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == order.id)
            .with_for_update()
            .first()
        )
        order = locked or order
        if order.status not in CONFIRMABLE_STATUSES:
            raise AppException(
                status_code=409,
                message=(
                    "This sales order is not published yet, so there is nothing to promise "
                    "supply against."
                ),
                code="supply_order_not_published",
            )

        lines = self.lines_of(str(order.id))
        by_id = {str(line.id): line for line in lines}
        payload_lines = list(getattr(payload, "lines", []) or [])
        if not payload_lines:
            raise AppException(
                status_code=422,
                message=(
                    "Nothing was chosen to confirm. Pick at least one line, or leave the "
                    "sales order as it is."
                ),
                code="supply_nothing_to_confirm",
            )
        self._lock_stock(payload_lines, lines)

        facts = self._facts_for(order, lines)
        item_codes = {
            str(line.id): facts[str(line.id)].item_code for line in lines
        }

        stale: List[Dict[str, Any]] = []
        invalid: List[Dict[str, Any]] = []
        seen: set = set()
        checked: List[Tuple[ProjectSalesOrderLine, Any, _LineFacts]] = []
        # What is still available as the payload is walked, so two lines of the SAME
        # confirmation cannot each be sold the whole pile. The per-line facts say what was
        # free when the sheet was read; these say what is left after the lines before it.
        pool_left: Dict[str, Decimal] = {}
        borrow_left: _BorrowLedger = _BorrowLedger()

        for entry in payload_lines:
            line = by_id.get(str(entry.project_line_id))
            if line is None:
                invalid.append(
                    {
                        "line_no": None,
                        "item_code": None,
                        "reason": "That line is not on this sales order any more.",
                    }
                )
                continue
            if str(line.id) in seen:
                invalid.append(
                    {
                        "line_no": line.line_no,
                        "item_code": item_codes.get(str(line.id)),
                        "reason": "This line appears twice in the composition.",
                    }
                )
                continue
            seen.add(str(line.id))
            fact = facts[str(line.id)]
            checked.append((line, entry, fact))
            self._check_line(entry, fact, pool_left, borrow_left, stale, invalid)

        # A line the payload does not name is NOT a failure any more (13.4). It is
        # undecided, deliberately, and its demand goes on flowing to reorder planning
        # untouched. What is still refused is a confirmation of nothing at all, below.

        if invalid or stale:
            failing = invalid + stale
            raise SupplyLinesRefused(
                status_code=422 if invalid else 409,
                message=(
                    f"{len(failing)} line{'' if len(failing) == 1 else 's'} cannot be "
                    "confirmed. Nothing was written."
                ),
                failing_lines=failing,
            )

        return self._write_decision(order, checked, actor_user_id=actor_user_id)

    def _lock_stock(
        self,
        payload_lines: Sequence[Any],
        lines: Sequence[ProjectSalesOrderLine],
    ) -> None:
        """Lock every stock row the payload touches, in a deterministic order.

        Deterministic because two confirmations touching the same two locations in
        opposite orders deadlock, and a deadlock reads to CS as the button doing nothing.
        """
        # Both spellings of the product: `_facts_for` prefers the CORE line's product when
        # the two disagree (a remap), and locking only the Project line's would leave the
        # rechecked free-stock read unprotected on exactly the remapped line.
        product_ids = {str(line.product_id) for line in lines if line.product_id}
        core_ids = [
            str(line.core_sales_order_line_id)
            for line in lines
            if line.core_sales_order_line_id
        ]
        if core_ids:
            for (core_product_id,) in (
                self.db.query(SalesOrderLine.product_id)
                .filter(SalesOrderLine.id.in_(core_ids))
                .all()
            ):
                if core_product_id:
                    product_ids.add(str(core_product_id))
        warehouse_ids: set = set()
        for entry in payload_lines:
            for source in list(entry.reserve or []) + list(entry.borrow or []):
                if getattr(source, "warehouse_id", None):
                    warehouse_ids.add(str(source.warehouse_id))
        if not product_ids or not warehouse_ids:
            return
        (
            self.db.query(Stock)
            .filter(
                Stock.product_id.in_(list(product_ids)),
                Stock.warehouse_id.in_(list(warehouse_ids)),
            )
            .order_by(Stock.product_id.asc(), Stock.warehouse_id.asc())
            .with_for_update()
            .all()
        )

    def _check_line(
        self,
        entry: Any,
        fact: _LineFacts,
        pool_left: Dict[str, Decimal],
        borrow_left: "_BorrowLedger",
        stale: List[Dict[str, Any]],
        invalid: List[Dict[str, Any]],
    ) -> None:
        """Recheck one line against authoritative facts (PLAN 3.1 steps 3 to 5)."""
        line = fact.line
        subject = {"line_no": line.line_no, "item_code": fact.item_code}

        def refuse(bucket: List[Dict[str, Any]], reason: str) -> None:
            bucket.append({**subject, "reason": reason})

        if fact.core is None:
            refuse(
                invalid,
                "This line has no reconciled AutoCount line, so there is no open "
                "quantity to promise against.",
            )
            return

        timely = _dec(entry.timely_spo_qty)
        reserve_items = [_dec(item.qty) for item in entry.reserve or []]
        borrow_items = [_dec(item.qty) for item in entry.borrow or []]
        reserve_total = sum(reserve_items, _ZERO)
        borrow_total = sum(borrow_items, _ZERO)
        buy = _dec(entry.buy_qty)
        # Every ITEM, not just the per-kind totals: a negative row beside a positive one
        # sums clean, then inflates the capacity ledger when it is subtracted, and the
        # snapshot-vs-allocation split drops it - the over-Reserve would commit.
        if min([timely, buy, *reserve_items, *borrow_items], default=_ZERO) < _ZERO:
            refuse(invalid, "A component quantity is negative.")
            return

        if timely > fact.timely_qty:
            refuse(
                stale,
                f"Timely SPO cover is now {qty_text(fact.timely_qty)}, not "
                f"{qty_text(timely)}.",
            )

        capacity = {
            location: qty
            for location, qty, _reason in reserve_capacity(
                is_dealer_hot_selling=fact.is_hot_selling,
                fulfilment_location=fact.own_code,
                pool_location=fact.pool_code,
                free_stock=self._free_for(fact, pool_left),
                reorder_levels=(
                    {fact.pool_code: fact.pool_reorder_level} if fact.pool_code else {}
                ),
            )
        }
        allowed = " or ".join([code for code in (fact.own_code, fact.pool_code) if code])
        for item in entry.reserve or []:
            warehouse = self._warehouse_of(fact, str(item.warehouse_id))
            qty = _dec(item.qty)
            if warehouse is None:
                # A location that is neither this line's own nor its pool. Name what was
                # asked for and what is allowed, by CODE - the old message named neither, so
                # a planner reading it could not tell whether the location, the quantity or
                # the whole line was the problem.
                posted = self._warehouse_row(str(item.warehouse_id))
                posted_code = posted.warehouse_code if posted else "another location"
                refuse(
                    invalid,
                    f"Reserve was asked for from {posted_code}, and this line can only "
                    f"reserve from {allowed or 'no location, because it states none'}. "
                    "Buy the quantity instead, or borrow it from that location on the "
                    "order's own sheet, which records who it came from and why.",
                )
                continue
            if warehouse not in capacity:
                # The location IS this line's own or its pool; it simply has nothing left for
                # this line. `reserve_capacity` omits a location contributing zero, so this
                # used to fall through to the message above and report a location error for a
                # quantity problem - which is what the planner saw as "Reserve may only come
                # from this line's own location" printed about their own location.
                refuse(
                    stale,
                    f"{warehouse} has nothing free for this line now, so none of the "
                    f"{qty_text(qty)} asked for can be reserved from it. Buy that quantity "
                    "instead, or borrow it on the order's own sheet.",
                )
                continue
            if qty > capacity[warehouse]:
                refuse(
                    stale,
                    f"{warehouse} now has {qty_text(capacity[warehouse])} free for this "
                    f"line, and {qty_text(qty)} was asked for.",
                )
                continue
            capacity[warehouse] -= qty
            if fact.pool_code and warehouse == fact.pool_code and fact.pool:
                pool_left[fact.pool_key] = max(
                    pool_left.get(fact.pool_key, fact.pool_free) - qty, _ZERO
                )

        for item in entry.borrow or []:
            self._check_borrow(item, fact, borrow_left, refuse, stale, invalid)

        if fact.is_discontinued and buy > _ZERO and not (entry.buy_reason or "").strip():
            refuse(
                invalid,
                "This product is discontinued. Say why it is still being bought before "
                "confirming.",
            )

        total = timely + reserve_total + borrow_total + buy
        if total != fact.open_qty:
            refuse(
                invalid,
                f"The components add up to {qty_text(total)} and the line is open for "
                f"{qty_text(fact.open_qty)}.",
            )

    def _free_for(
        self, fact: _LineFacts, pool_left: Dict[str, Decimal]
    ) -> Dict[str, Decimal]:
        free: Dict[str, Decimal] = {}
        if fact.own_code:
            free[fact.own_code] = fact.own_free
        if fact.pool_code and fact.pool:
            free[fact.pool_code] = pool_left.get(fact.pool_key, fact.pool_free)
        return free

    def _warehouse_of(self, fact: _LineFacts, warehouse_id: str) -> Optional[str]:
        if fact.warehouse and str(fact.warehouse.id) == warehouse_id:
            return fact.own_code
        if fact.pool and str(fact.pool.id) == warehouse_id:
            return fact.pool_code
        return None

    def _reserve_location_ids(self, fact: _LineFacts) -> set:
        """The warehouses Reserve MAY draw this line from (PLAN 3.3), by id.

        Structural, not "wherever there happens to be stock": for a dealer hot-selling
        product it is the shared pool and nothing else, so the line's OWN dealer location
        is outside Reserve and is therefore a legitimate BORROW source - which is exactly
        what 3.3 means by "Borrow may still deliberately use a non-Reserve source,
        including dealer stock". For every other product it is the fulfilment location and
        the pool.
        """
        if fact.is_hot_selling:
            return {str(fact.pool.id)} if fact.pool else set()
        ids = set()
        if fact.warehouse:
            ids.add(str(fact.warehouse.id))
        if fact.pool:
            ids.add(str(fact.pool.id))
        return ids

    def _check_borrow(
        self,
        item: Any,
        fact: _LineFacts,
        borrow_left: "_BorrowLedger",
        refuse,
        stale: List[Dict[str, Any]],
        invalid: List[Dict[str, Any]],
    ) -> None:
        qty = _dec(item.qty)
        if not (item.reason or "").strip():
            refuse(
                invalid,
                "Borrowing takes a reason. Say why this line is taking somebody else's "
                "stock.",
            )
            return
        warehouse = self._warehouse_row(str(item.warehouse_id))
        if warehouse is None:
            refuse(invalid, "That location no longer exists.")
            return
        if item.source == ALLOC_SOURCE_OTHER_LOCATION:
            if str(item.warehouse_id) in self._reserve_location_ids(fact):
                refuse(
                    invalid,
                    f"{warehouse.warehouse_code} is inside this line's Reserve pool. "
                    "Reserve it rather than borrowing it.",
                )
                return
            available = borrow_left.free(
                fact.product_id, str(warehouse.id), self._free_at
            )
            if qty > available:
                refuse(
                    stale,
                    f"{warehouse.warehouse_code} has {qty_text(available)} free, and "
                    f"{qty_text(qty)} was asked for.",
                )
                return
            borrow_left.take_free(fact.product_id, str(warehouse.id), qty)
            return

        if not item.donor_project_id:
            refuse(invalid, "Name the project this stock is being borrowed from.")
            return
        if self._project_id_of(fact.line) is None:
            # An order adopted from the AutoCount book has no project (section 4), and a
            # cross-project Borrow is a claim from one project to another: there is no
            # side to record. Refused by name here rather than exploding on
            # `AllocationClaim.from_project_id`, which is NOT NULL. The sheet does not
            # offer this Borrow on an adopted order either (`_borrow_candidates`); free
            # stock at another location is still available as an ordinary Borrow.
            refuse(
                invalid,
                "This sales order is planned straight from the AutoCount book and belongs "
                "to no project, so it cannot borrow another project's stock. Borrow the "
                "free stock at that location instead.",
            )
            return
        donor = (
            self.db.query(Project).filter(Project.id == item.donor_project_id).first()
        )
        if donor is None:
            refuse(invalid, "The project holding that stock no longer exists.")
            return
        # The donor's own hold first, then whatever is free at that location: both are
        # stock that exists, and neither may be handed to two lines of one confirmation.
        held = borrow_left.held(
            fact.product_id, str(warehouse.id), str(donor.id), self._held_at
        )
        free = borrow_left.free(fact.product_id, str(warehouse.id), self._free_at)
        if qty > held + free:
            refuse(
                stale,
                f"{donor.project_code} has {qty_text(held + free)} at "
                f"{warehouse.warehouse_code}, and {qty_text(qty)} was asked for.",
            )
            return
        from_hold = min(qty, held)
        borrow_left.take_held(fact.product_id, str(warehouse.id), str(donor.id), from_hold)
        borrow_left.take_free(fact.product_id, str(warehouse.id), qty - from_hold)

    # ------------------------------------------------------------------- writing

    def _write_decision(
        self,
        order: ProjectSalesOrder,
        checked: Sequence[Tuple[ProjectSalesOrderLine, Any, _LineFacts]],
        *,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        previous = self.active_decision(str(order.id))
        if previous is not None:
            previous.state = DECISION_SUPERSEDED
            previous.superseded_at = datetime.utcnow()
            previous.superseded_reason = "Reconfirmed by CS."
            # Flushed on its own: the partial unique index allows one active revision, so
            # the new row cannot be inserted while the old one still says it is active.
            self.db.flush()

        latest = self.latest_decision(str(order.id))
        revision_no = (latest.revision_no if latest else 0) + 1
        now = datetime.utcnow()
        snapshots = [
            self._snapshot(line, entry, fact) for line, entry, fact in checked
        ]

        decision = SOSupplyDecision(
            company_id=order.company_id,
            project_sales_order_id=order.id,
            revision_no=revision_no,
            state=DECISION_ACTIVE,
            source_revision=(
                f"{order.status} @ "
                f"{order.updated_at.isoformat() if order.updated_at else ''}"
            )[:120],
            line_snapshots=snapshots,
            confirmed_by=actor_user_id,
            confirmed_at=now,
            supersedes_id=previous.id if previous else None,
        )
        self.db.add(decision)
        try:
            self.db.flush()
        except IntegrityError as exc:
            # The DB-level singleton did its job: somebody else confirmed this order
            # between our read and our write, so this attempt loses whole (AC-C05).
            self.db.rollback()
            raise AppException(
                status_code=409,
                message=(
                    "Somebody else confirmed this sales order while this composition was "
                    "open. Reload it and check the composition before confirming again."
                ),
                code="supply_decision_conflict",
            ) from exc

        buy_lines: List[Dict[str, Any]] = []
        for line, entry, fact in checked:
            self._write_allocations(decision, line, entry, fact, actor_user_id=actor_user_id)
            self._restamp_stock_location(line, entry, fact)
            buy_lines.append(
                {
                    "line": line,
                    "line_no": line.line_no,
                    "item_code": fact.item_code,
                    "buy_qty": _dec(entry.buy_qty),
                    "required_date": fact.required_date or line.delivery_date,
                    "stock_location": line.stock_location,
                }
            )
        self.db.flush()

        from app.services.project_order_inquiry_service import (
            ProjectOrderInquiryService,
        )

        handoff = ProjectOrderInquiryService(self.db).refresh_for_decision(
            order,
            decision,
            buy_lines,
            actor_user_id=actor_user_id,
            borrow_shortfalls=self._borrow_shortfalls(order, checked),
        )
        decided = len(checked)
        return {
            "revision_no": decision.revision_no,
            "confirmed_at": decision.confirmed_at,
            "review_state": "confirmed",
            "inquiry_rows_created": handoff["created"],
            "exceptions": handoff["exceptions"],
            # Information, not a gate (13.4): the planner is told what is still open on
            # this order rather than being stopped from committing what is not.
            "lines_decided": decided,
            "lines_undecided": max(len(self.lines_of(str(order.id))) - decided, 0),
        }

    def _borrow_shortfalls(
        self,
        order: ProjectSalesOrder,
        checked: Sequence[Tuple[ProjectSalesOrderLine, Any, _LineFacts]],
    ) -> List[Dict[str, Any]]:
        """The holes this confirmation's borrows opened at the donors (PLAN 13.11).

        The captain: "when borrowed, does it / should it trigger an order back via order
        inquiries? Because I sort of need to return, right - or we should order back only if
        the available quantity of the borrowed location is negative?" **Only if negative.**
        A donor whose availability survives the borrow is not short of anything, and raising
        a buy for it would order stock nobody needs; a donor pushed below zero has a hole
        somebody must cover, and purchasing is told about the HOLE, not about the whole
        quantity that was taken.

        Aggregated per donor pile, because two lines of one order taking from the same
        location open one hole between them and not two.

        A Reserve drawn from the line's SHARED POOL is a donor by the same rule (13.11, the
        second rule). The captain, on a rung reading `Pool BRW | 4 | took 4`: "when we take
        from BRW, first we need to see its available quantity also, if available quantity is
        negative and if we want to take, we must have an order back just like mentioned."
        The pool's own book ranked BEHIND this line still wants that stock, and it shows in
        the pool's availability rather than in the queue ahead - so a pool take that leaves
        the pool's `on hand - SO + SPO` below zero opens a hole there, and purchasing is told
        about the hole at the POOL's location. A Reserve at the line's OWN location is never
        one: that location's demand IS this line, already inside its `SO qty`, and taking the
        reserve out again would count the same quantity twice.
        """
        piles: Dict[Tuple[str, str], Dict[str, Any]] = {}

        def pile_for(
            line: ProjectSalesOrderLine, fact: _LineFacts, warehouse_id: str
        ) -> Dict[str, Any]:
            return piles.setdefault(
                (fact.product_id or "", warehouse_id),
                {
                    "borrowed": _ZERO,
                    "reserved": _ZERO,
                    "item_code": fact.item_code,
                    "lines": [],
                    "line": line,
                    "required_date": fact.required_date or line.delivery_date,
                },
            )

        for line, entry, fact in checked:
            if not fact.product_id:
                continue
            for item in entry.borrow or []:
                qty = _dec(item.qty)
                if qty <= _ZERO or not item.warehouse_id:
                    continue
                pile = pile_for(line, fact, str(item.warehouse_id))
                pile["borrowed"] += qty
                pile["lines"].append(line.line_no)
            pool_id = str(fact.pool.id) if fact.pool else None
            own_id = str(fact.warehouse.id) if fact.warehouse else None
            if not pool_id or pool_id == own_id:
                continue
            for item in entry.reserve or []:
                qty = _dec(item.qty)
                if qty <= _ZERO or str(item.warehouse_id) != pool_id:
                    continue
                pile = pile_for(line, fact, pool_id)
                pile["reserved"] += qty
                pile["lines"].append(line.line_no)
        if not piles:
            return []

        availability = self.donor_availability(piles.keys())
        out: List[Dict[str, Any]] = []
        reference = order.autocount_doc_no or order.provisional_ref or ""
        for key, pile in piles.items():
            taken = pile["borrowed"] + pile["reserved"]
            after = availability.get(key, _ZERO) - taken
            if after >= _ZERO:
                continue
            warehouse = self._warehouse_row(key[1])
            code = warehouse.warehouse_code if warehouse else ""
            lines = ", ".join(f"line {no}" for no in sorted(set(pile["lines"])))
            parts: List[str] = []
            if pile["borrowed"] > _ZERO:
                parts.append(f"borrowed {qty_text(pile['borrowed'])}")
            if pile["reserved"] > _ZERO:
                parts.append(f"reserved {qty_text(pile['reserved'])} at {code}")
            what = " and ".join(parts)
            what = what[:1].upper() + what[1:]
            out.append(
                {
                    "line": pile["line"],
                    "item_code": pile["item_code"],
                    # The hole, not the take: taking 20 from a location with 10 to spare
                    # leaves 10 to be bought, and the other 10 was theirs to give.
                    "qty": min(taken, -after),
                    "required_date": pile["required_date"],
                    "stock_location": code,
                    "note": (
                        f"{what} for {reference} {lines}; "
                        f"{code} goes short by {qty_text(-after)}"
                    ),
                }
            )
        return out

    def _snapshot(
        self, line: ProjectSalesOrderLine, entry: Any, fact: _LineFacts
    ) -> Dict[str, Any]:
        """Freeze the line as it was decided, in the words it was decided in (AC-G01)."""
        components: List[Dict[str, Any]] = []
        for item in entry.reserve or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            location = self._warehouse_of(fact, str(item.warehouse_id))
            components.append(
                {
                    "kind": RESERVE,
                    "qty": qty_text(qty),
                    "source_location": location,
                    "source_warehouse_id": str(item.warehouse_id),
                    "reason": self._reserve_reason(fact, location),
                }
            )
        if _dec(entry.timely_spo_qty) > _ZERO:
            components.append(
                {
                    "kind": TIMELY_SPO,
                    "qty": qty_text(_dec(entry.timely_spo_qty)),
                    "source_location": fact.own_code,
                    "source_warehouse_id": (
                        str(fact.warehouse.id) if fact.warehouse else None
                    ),
                    "reason": self._timely_reason(fact),
                }
            )
        for item in entry.borrow or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            warehouse = self._warehouse_row(str(item.warehouse_id))
            donor = (
                self.db.query(Project).filter(Project.id == item.donor_project_id).first()
                if item.donor_project_id
                else None
            )
            components.append(
                {
                    "kind": "borrow",
                    "qty": qty_text(qty),
                    "source": item.source,
                    "source_location": warehouse.warehouse_code if warehouse else None,
                    "source_warehouse_id": str(item.warehouse_id),
                    "donor_project_ref": donor.project_code if donor else None,
                    "donor_project_id": str(donor.id) if donor else None,
                    "reason": self._borrow_reason(item, warehouse, donor),
                    "cs_reason": (item.reason or "").strip(),
                }
            )
        if _dec(entry.buy_qty) > _ZERO:
            components.append(
                {
                    "kind": BUY,
                    "qty": qty_text(_dec(entry.buy_qty)),
                    "reason": "remaining uncovered need",
                    "cs_reason": (entry.buy_reason or "").strip() or None,
                }
            )

        return {
            "line_no": line.line_no,
            "project_line_id": str(line.id),
            "core_line_id": str(line.core_sales_order_line_id)
            if line.core_sales_order_line_id
            else None,
            "product_id": fact.product_id,
            "item_code": fact.item_code,
            "location": fact.own_code,
            "required_date": (
                fact.required_date.isoformat() if fact.required_date else None
            ),
            "open_qty": qty_text(fact.open_qty),
            "timely_spo_qty": qty_text(_dec(entry.timely_spo_qty)),
            "timely_spo_refs": [
                {
                    "spo_number": ref.spo_number,
                    "arrival_date": (
                        ref.arrival_date.isoformat() if ref.arrival_date else None
                    ),
                    "qty": qty_text(ref.qty),
                }
                for ref in fact.timely_refs
            ],
            "reserve_qty": qty_text(
                sum((_dec(item.qty) for item in entry.reserve or []), _ZERO)
            ),
            "borrow_qty": qty_text(
                sum((_dec(item.qty) for item in entry.borrow or []), _ZERO)
            ),
            "buy_qty": qty_text(_dec(entry.buy_qty)),
            "components": components,
            "suggestion_basis": {
                "is_dealer_hot_selling": fact.is_hot_selling,
                "classification_unavailable": fact.classification_unavailable,
                "pool_location": fact.pool_code,
                "pool_cap": qty_text(fact.pool_cap) if fact.pool_code else None,
                "pool_reorder_level": (
                    qty_text(fact.pool_reorder_level) if fact.pool_code else None
                ),
            },
            "lifecycle_warning": (
                "This product is discontinued." if fact.is_discontinued else None
            ),
            "buy_reason": (entry.buy_reason or "").strip() or None,
            # Why the composition above is not the one the engine proposed. Frozen with the
            # line rather than discarded at the call: every other component carries the
            # sentence of the RULE that produced it, and on an amended line those sentences
            # explain a decision nobody took.
            "amend_reason": (getattr(entry, "amend_reason", None) or "").strip() or None,
        }

    def _reserve_reason(self, fact: _LineFacts, location: Optional[str]) -> str:
        for candidate, _qty, reason in reserve_capacity(
            is_dealer_hot_selling=fact.is_hot_selling,
            fulfilment_location=fact.own_code,
            pool_location=fact.pool_code,
            free_stock=self._free_for(fact, {}),
            reorder_levels=(
                {fact.pool_code: fact.pool_reorder_level} if fact.pool_code else {}
            ),
        ):
            if candidate == location:
                return reason
        return f"free stock at {location} covers the need by the required date"

    def _timely_reason(self, fact: _LineFacts) -> str:
        if not fact.timely_refs:
            return "incoming supply arrives by the required date"
        first = fact.timely_refs[0]
        when = first.arrival_date.isoformat() if first.arrival_date else "an unstated date"
        return f"SPO {first.spo_number} arrives on {when}, by the required date"

    def _borrow_reason(
        self, item: Any, warehouse: Optional[Warehouse], donor: Optional[Project]
    ) -> str:
        where = warehouse.warehouse_code if warehouse else "another location"
        if item.source == ALLOC_SOURCE_OTHER_PROJECT and donor is not None:
            return f"borrowed from {donor.project_code} at {where}"
        return f"borrowed from free stock at {where}"

    def _write_allocations(
        self,
        decision: SOSupplyDecision,
        line: ProjectSalesOrderLine,
        entry: Any,
        fact: _LineFacts,
        *,
        actor_user_id: str,
    ) -> None:
        """The components of THIS revision, grouped by `decision_id`.

        The previous revision's rows are left exactly where they are: they are the record
        of what was promised then, and the audit trail is the only thing that can answer
        "what did we tell the customer in March".
        """
        now = datetime.utcnow()
        for item in entry.reserve or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            location = self._warehouse_of(fact, str(item.warehouse_id))
            source = (
                ALLOC_SOURCE_BRW
                if fact.pool_code and location == fact.pool_code
                else ALLOC_SOURCE_OWN
            )
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=source,
                    warehouse_id=str(item.warehouse_id),
                    qty=qty,
                    decision_id=decision.id,
                    confirmed_by=actor_user_id,
                    confirmed_at=now,
                )
            )

        for item in entry.borrow or []:
            qty = _dec(item.qty)
            if qty <= _ZERO:
                continue
            claim_id = None
            donor_project_id = None
            if item.source == ALLOC_SOURCE_OTHER_PROJECT and item.donor_project_id:
                donor_project_id = str(item.donor_project_id)
                claim = AllocationClaim(
                    company_id=line.company_id,
                    from_project_id=self._project_id_of(line),
                    to_project_id=donor_project_id,
                    so_line_id=line.id,
                    product_id=fact.product_id,
                    warehouse_id=str(item.warehouse_id),
                    qty=qty,
                    # Straight to the terminal state (AC-B10): the confirming CS actor IS
                    # the approval, so there is no requested step for a donor to answer.
                    state=CLAIM_ACCEPTED,
                    reason=(item.reason or "").strip(),
                    requested_by=actor_user_id,
                    decided_by=actor_user_id,
                    decided_at=now,
                )
                self.db.add(claim)
                self.db.flush()
                claim_id = claim.id
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=item.source,
                    warehouse_id=str(item.warehouse_id),
                    source_project_id=donor_project_id,
                    qty=qty,
                    claim_id=claim_id,
                    decision_id=decision.id,
                    reason=(item.reason or "").strip(),
                    donor_impact_snapshot=self._donor_impact(item, fact, qty),
                    confirmed_by=actor_user_id,
                    confirmed_at=now,
                )
            )

        buy = _dec(entry.buy_qty)
        if buy > _ZERO:
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=ALLOC_SOURCE_ORDER,
                    warehouse_id=None,
                    qty=buy,
                    decision_id=decision.id,
                    reason=(entry.buy_reason or "").strip() or None,
                    confirmed_by=actor_user_id,
                    confirmed_at=now,
                )
            )

    def _project_id_of(self, line: ProjectSalesOrderLine) -> Optional[str]:
        """The project the line's order belongs to, or None for an adopted order.

        None rather than `str(None)`: this feeds `AllocationClaim.from_project_id`, which
        is a NOT NULL uuid column, so a stringified null would have reached Postgres as the
        text "None" and failed the write of an otherwise valid confirmation. The confirm
        recheck refuses a cross-project Borrow before it gets here (`_check_borrow`).
        """
        order = (
            self.db.query(ProjectSalesOrder.project_id)
            .filter(ProjectSalesOrder.id == line.project_sales_order_id)
            .first()
        )
        return str(order[0]) if order and order[0] else None

    def _donor_impact(self, item: Any, fact: _LineFacts, qty: Decimal) -> Dict[str, Any]:
        free = self._free_at(fact.product_id, str(item.warehouse_id))
        held = (
            self._held_at(fact.product_id, str(item.warehouse_id), str(item.donor_project_id))
            if item.donor_project_id
            else _ZERO
        )
        return {
            "free_before": qty_text(free + held),
            "free_after_full_borrow": qty_text(max(free + held - qty, _ZERO)),
            "committed_qty": qty_text(held),
        }

    def _restamp_stock_location(
        self, line: ProjectSalesOrderLine, entry: Any, fact: _LineFacts
    ) -> None:
        """AC-H5, from this revision's components: what the inquiry row quotes."""
        codes: List[str] = []
        for item in list(entry.reserve or []) + list(entry.borrow or []):
            if _dec(item.qty) <= _ZERO:
                continue
            warehouse = self._warehouse_row(str(item.warehouse_id))
            code = warehouse.warehouse_code if warehouse else None
            if code and code not in codes:
                codes.append(code)
        # A pure-Buy line names no source warehouse, but it is exactly the line that
        # becomes an inquiry row, and purchasing reads the location off that row: fall
        # back to the fulfilment location rather than handing over a blank.
        if not codes and fact.own_code:
            codes.append(fact.own_code)
        line.stock_location = " + ".join(codes) if codes else None

    # ------------------------------------------------------------------- facts

    def _facts_for(
        self, order: ProjectSalesOrder, lines: Sequence[ProjectSalesOrderLine]
    ) -> Dict[str, _LineFacts]:
        """Read every fact the sheet and the commit judge a line against.

        Refuses the whole order when a line has no reconciled core line: without it there
        is no current open quantity, and promising supply against the ORIGINAL customer
        quantity is exactly the double-count this contract exists to stop (PLAN 3.1 step 2).
        """
        unmapped = [line for line in lines if not line.core_sales_order_line_id]
        core_ids = [
            str(line.core_sales_order_line_id)
            for line in lines
            if line.core_sales_order_line_id
        ]
        cores = {
            str(row.id): row
            for row in (
                self.db.query(SalesOrderLine)
                .filter(SalesOrderLine.id.in_(core_ids))
                .all()
                if core_ids
                else []
            )
        }
        product_ids = {
            str(core.product_id)
            for core in cores.values()
            if core.product_id
        } | {str(line.product_id) for line in lines if line.product_id}
        codes = self._product_codes(product_ids)

        if unmapped:
            raise SupplyLinesRefused(
                status_code=422,
                message=(
                    f"{len(unmapped)} line{'' if len(unmapped) == 1 else 's'} "
                    "still has no AutoCount line. Reconcile the sales order first."
                ),
                failing_lines=[
                    {
                        "line_no": line.line_no,
                        "item_code": codes.get(str(line.product_id or "")),
                        "reason": "No reconciled AutoCount line.",
                    }
                    for line in unmapped
                ],
                code="supply_lines_unreconciled",
            )

        warehouse_ids = {
            str(core.warehouse_id) for core in cores.values() if core.warehouse_id
        }
        warehouses = self._warehouses(warehouse_ids)
        pool_ids = {
            str(w.pool_warehouse_id) for w in warehouses.values() if w.pool_warehouse_id
        }
        warehouses.update(self._warehouses(pool_ids - set(warehouses)))

        self._free_cache = self._free_stock(product_ids, exclude_order_id=str(order.id))
        self._holds_cache = self._holds_by_project(
            product_ids, exclude_order_id=str(order.id)
        )
        self._pile_cache = None
        pool_ahead = self.pool_claims(
            product_ids,
            pool_ids,
            exclude_order_id=str(order.id),
            members=[
                {
                    "key": str(line.id),
                    "product_id": str(
                        (cores.get(str(line.core_sales_order_line_id or "")) or line).product_id
                    ),
                    "pool_id": str(
                        warehouses[
                            str(cores[str(line.core_sales_order_line_id)].warehouse_id)
                        ].pool_warehouse_id
                    ),
                    "required_date": (
                        cores[str(line.core_sales_order_line_id)].required_date
                        or line.delivery_date
                    ),
                    "order_date": None,
                    "payment_terms_days": None,
                    "demand_class": None,
                    "so_number": order.provisional_ref,
                    "line_no": line.line_no,
                }
                for line in lines
                if line.core_sales_order_line_id
                and str(line.core_sales_order_line_id) in cores
                and cores[str(line.core_sales_order_line_id)].warehouse_id
                and str(cores[str(line.core_sales_order_line_id)].warehouse_id) in warehouses
                and warehouses[
                    str(cores[str(line.core_sales_order_line_id)].warehouse_id)
                ].pool_warehouse_id
            ],
        )
        hot, unavailable, hot_where = self._classification(product_ids)
        levels = self._reorder_levels(product_ids, pool_ids)
        discontinued = self._discontinued(product_ids)
        spo = self._spo_rows(product_ids, warehouse_ids)
        attribution = self._attribution(
            product_ids, warehouse_ids, warehouses, spo, exclude_order_id=str(order.id)
        )

        facts: Dict[str, _LineFacts] = {}
        for line in lines:
            core = cores.get(str(line.core_sales_order_line_id or ""))
            product_id = str(core.product_id) if core and core.product_id else (
                str(line.product_id) if line.product_id else None
            )
            warehouse = (
                warehouses.get(str(core.warehouse_id))
                if core and core.warehouse_id
                else None
            )
            pool = (
                warehouses.get(str(warehouse.pool_warehouse_id))
                if warehouse and warehouse.pool_warehouse_id
                else None
            )
            key = (product_id or "", str(warehouse.id) if warehouse else "")
            shares = attribution.get(key, {}).get(str(core.id) if core else "", {})
            ahead = _dec(shares.get("so_qty_ahead"))
            required_date = (core.required_date if core else None) or line.delivery_date
            timely_refs = [
                row
                for row in spo.get(key, [])
                if required_date is None
                or (row.arrival_date is not None and row.arrival_date <= required_date)
            ]
            claim = pool_ahead.get(str(line.id), {})
            claimed = _dec(claim.get("qty"))
            facts[str(line.id)] = _LineFacts(
                line=line,
                core=core,
                item_code=codes.get(product_id or ""),
                product_id=product_id,
                open_qty=_open_of(core),
                required_date=required_date,
                warehouse=warehouse,
                pool=pool,
                own_free=shares.get(RESERVE, _ZERO),
                so_qty_ahead=ahead,
                lines_ahead=int(shares.get("lines_ahead") or 0),
                available_to_this_line=_dec(shares.get("available_to_this_line")),
                pool_free=(
                    max(self._free_at(product_id, str(pool.id)) - claimed, _ZERO)
                    if pool
                    else _ZERO
                ),
                pool_claimed_qty=claimed if pool else _ZERO,
                pool_claimed_lines=int(claim.get("lines") or 0) if pool else 0,
                pool_reorder_level=levels.get(
                    (product_id or "", str(pool.id) if pool else ""), _ZERO
                ),
                is_hot_selling=(product_id or "") in hot,
                hot_selling_where=list(hot_where.get(product_id or "", [])),
                classification_unavailable=(product_id or "") in unavailable,
                is_discontinued=(product_id or "") in discontinued,
                timely_qty=shares.get(TIMELY_SPO, _ZERO),
                timely_refs=timely_refs,
                advisory_refs=[
                    row for row in spo.get(key, []) if row not in timely_refs
                ],
            )
        return facts

    # -------------------------------------------------------------- fact readers

    def _product_codes(self, product_ids: Iterable[str]) -> Dict[str, str]:
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        return {
            str(row[0]): row[1] or ""
            for row in self.db.query(Product.id, Product.product_code)
            .filter(Product.id.in_(ids))
            .all()
        }

    def _discontinued(self, product_ids: Iterable[str]) -> set:
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return set()
        return {
            str(row[0])
            for row in self.db.query(Product.id)
            .filter(Product.id.in_(ids), Product.is_discontinued.is_(True))
            .all()
        }

    def _warehouses(self, warehouse_ids: Iterable[str]) -> Dict[str, Warehouse]:
        ids = [wid for wid in warehouse_ids if wid]
        if not ids:
            return {}
        return {
            str(row.id): row
            for row in self.db.query(Warehouse).filter(Warehouse.id.in_(ids)).all()
        }

    def _warehouse_row(self, warehouse_id: str) -> Optional[Warehouse]:
        return (
            self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
            if warehouse_id
            else None
        )

    def held_stock_by_location(
        self, product_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Decimal]:
        """What CONFIRMED decisions are holding, per `(product_id, warehouse_id)`.

        The third term of the free-stock arithmetic, exposed so a screen can print it: on hand,
        less reserved, less THIS, is what `free_stock_by_location` answers. Without it a strip
        showing 478 on hand and 478 free looks like a rounding error rather than the truth that
        nothing is committed yet.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        out: Dict[Tuple[str, str], Decimal] = {}
        for key, _project_id, qty in self._hold_rows(ids, exclude_order_id=None):
            out[key] = out.get(key, _ZERO) + qty
        return out

    def stock_levels_by_location(
        self, product_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Tuple[Decimal, Decimal]]:
        """`(on hand, reserved)` per `(product_id, warehouse_id)`, straight off the rows.

        The raw pair behind `free_stock_by_location`, read from the same `stock` rows so a
        screen can show what the planner asked to see - "what is the quantity on hand" - beside
        what the engine may actually use, and the two can never come from different reads. The
        subtraction stays in `_free_stock`; this states its inputs, it does not repeat them.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        rows = (
            self.db.query(Stock)
            .join(Warehouse, Warehouse.id == Stock.warehouse_id)
            .filter(Stock.product_id.in_(ids), Warehouse.is_active.is_(True))
            .all()
        )
        return {
            (str(stock.product_id), str(stock.warehouse_id)): (
                _dec(stock.quantity_on_hand),
                _dec(stock.quantity_reserved),
            )
            for stock in rows
        }

    def free_stock_by_location(
        self, product_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Decimal]:
        """Free stock per `(product_id, warehouse_id)`, as THIS service computes it.

        The public seam for readers outside one order's sheet - today the multi-order planning
        board. It exists so the board asks this service what is free rather than growing a
        second opinion about availability, which would be the same defect two rankings would
        have been (`app/services/scm/priority.py`).

        No order is excluded, because a cross-order reader is not composing any one order.

        It carries `_free_stock`'s known limit, and the board is built to SHOW that limit
        rather than hide it (PLAN 13.5.1): only CONFIRMED holds are netted off, so two orders
        composed separately can both still be proposed the same stock. The board answers that
        by serving one pile down the ranking and marking the rows it could not cover as
        contested. The locking fix belongs to the confirmation path.
        """
        return self._free_stock(product_ids, exclude_order_id=None)

    def _free_stock(
        self, product_ids: Iterable[str], *, exclude_order_id: Optional[str]
    ) -> Dict[Tuple[str, str], Decimal]:
        """On hand, minus reserved, minus what confirmed decisions already hold.

        A hold counts when its allocation belongs to no decision (every row written before
        Stage 1C) or to an ACTIVE one. A superseded revision's rows are history and hold
        nothing, and the order being composed is excluded so its own previous revision does
        not compete with the one replacing it.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        rows = (
            self.db.query(Stock, Warehouse)
            .join(Warehouse, Warehouse.id == Stock.warehouse_id)
            .filter(Stock.product_id.in_(ids), Warehouse.is_active.is_(True))
            .all()
        )
        free = {
            (str(stock.product_id), str(stock.warehouse_id)): max(
                _dec(stock.quantity_on_hand) - _dec(stock.quantity_reserved), _ZERO
            )
            for stock, _warehouse in rows
        }
        for (product_id, warehouse_id), _project_id, qty in self._hold_rows(
            ids, exclude_order_id=exclude_order_id
        ):
            key = (product_id, warehouse_id)
            if key in free:
                free[key] = max(free[key] - qty, _ZERO)
        return free

    def _hold_rows(
        self, product_ids: Sequence[str], *, exclude_order_id: Optional[str]
    ) -> List[Tuple[Tuple[str, str], str, Decimal]]:
        """Confirmed holds, per (product, warehouse) and holding project.

        Ported from `project_allocation_service._holds` and narrowed by decision state,
        because a superseded revision must stop holding stock the moment it is superseded.
        """
        query = (
            self.db.query(
                ProjectSalesOrderLine.product_id,
                SOLineAllocation.warehouse_id,
                ProjectSalesOrder.project_id,
                SOLineAllocation.qty,
            )
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.id == SOLineAllocation.so_line_id,
            )
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
            )
            .outerjoin(
                SOSupplyDecision, SOSupplyDecision.id == SOLineAllocation.decision_id
            )
            .filter(
                ProjectSalesOrderLine.product_id.in_(list(product_ids)),
                SOLineAllocation.confirmed_at.isnot(None),
                SOLineAllocation.warehouse_id.isnot(None),
                SOLineAllocation.source_type != ALLOC_SOURCE_ORDER,
                or_(
                    SOLineAllocation.decision_id.is_(None),
                    SOSupplyDecision.state == DECISION_ACTIVE,
                ),
            )
        )
        if exclude_order_id:
            query = query.filter(
                ProjectSalesOrder.id != exclude_order_id
            )
        # An ADOPTED order holds stock with no project behind it (section 4), and the
        # holding project is a dict KEY here - so it is the empty string rather than the
        # string "None", which is a value that looks like an id and matches nothing. The
        # hold still nets out of free stock either way; what it cannot be is a cross-project
        # Borrow donor, because there is no project to borrow FROM.
        return [
            ((str(product_id), str(warehouse_id)), str(project_id) if project_id else "",
             _dec(qty))
            for product_id, warehouse_id, project_id, qty in query.all()
        ]

    def _holds_by_project(
        self, product_ids: Iterable[str], *, exclude_order_id: Optional[str]
    ) -> Dict[Tuple[str, str, str], Decimal]:
        out: Dict[Tuple[str, str, str], Decimal] = {}
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return out
        for (product_id, warehouse_id), project_id, qty in self._hold_rows(
            ids, exclude_order_id=exclude_order_id
        ):
            key = (product_id, warehouse_id, project_id)
            out[key] = out.get(key, _ZERO) + qty
        return out

    def _free_at(self, product_id: Optional[str], warehouse_id: str) -> Decimal:
        return self._free_cache.get(
            (product_id or "", warehouse_id), _ZERO
        )

    def _held_at(
        self, product_id: Optional[str], warehouse_id: str, project_id: str
    ) -> Decimal:
        return self._holds_cache.get(
            (product_id or "", warehouse_id, project_id), _ZERO
        )

    def _classification(
        self, product_ids: Iterable[str]
    ) -> Tuple[set, set, Dict[str, List[str]]]:
        """PLAN 3.3's dealer hot-selling predicate, and the "no evidence" case.

        `computed_at` is display evidence, never a freshness gate: the existing ABC facts
        are the test, and adding an age threshold would be a new knob this contract forbids.

        Returns the hot set, the unclassified set, and WHERE each hot product earned it - the
        dealer locations holding it as ABC A, by code and sorted. The captain, reading a trail
        that never mentioned it: "where is the consideration of dealer hot selling?" A bare
        boolean would be something to take on trust; "ABC A at BRW" is something to check.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return set(), set(), {}
        rows = (
            self.db.query(
                ItemClassification.product_id,
                ItemClassification.abc_class,
                Warehouse.warehouse_code,
            )
            .join(Warehouse, Warehouse.id == ItemClassification.warehouse_id)
            .filter(
                ItemClassification.product_id.in_(ids),
                Warehouse.segment == DEALER_SEGMENT,
                Warehouse.is_active.is_(True),
                Warehouse.counts_as_available.is_(True),
            )
            .all()
        )
        seen = {str(product_id) for product_id, _abc, _code in rows}
        where: Dict[str, List[str]] = {}
        for product_id, abc, code in rows:
            if (abc or "").upper() == "A":
                where.setdefault(str(product_id), []).append(code or "")
        for codes in where.values():
            codes.sort()
        return set(where), {pid for pid in ids if pid not in seen}, where

    def _reorder_levels(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Decimal]:
        """Per-location levels. An absent row and a NULL level both contribute 0 (Q7)."""
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        return {
            (str(row.product_id), str(row.warehouse_id)): _dec(row.level)
            for row in self.db.query(ReorderLevel)
            .filter(
                ReorderLevel.product_id.in_(pids),
                ReorderLevel.warehouse_id.in_(wids),
            )
            .all()
        }

    def incoming_by_location(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], List[_SpoRow]]:
        """Undelivered SPO allocations per `(product_id, warehouse_id)`.

        The public seam beside `free_stock_by_location`, and there for the same reason: the
        board shares one location's opening stock AND its dated incoming through the same
        engine the sheet uses, so the two surfaces cannot come to differ about what is on the
        water.
        """
        return self._spo_rows(product_ids, warehouse_ids)

    def _spo_rows(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], List[_SpoRow]]:
        """Undelivered SPO allocations at these locations, with their current ETA.

        `eta_delay_date` wins over `estimated_arrival_date` because the revised date is
        the accurate one, and a line promised against a date that has already slipped is
        the promise this whole contract is trying not to make.
        """
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        rows = (
            self.db.query(
                SPOAllocation.id,
                SPOAllocation.spo_number,
                SPOAllocation.spo_line_number,
                SPOAllocation.product_id,
                SPOAllocation.warehouse_id,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received,
                InboundShipment.eta_delay_date,
                InboundShipment.estimated_arrival_date,
                Supplier.supplier_name,
            )
            .join(
                InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
            )
            .outerjoin(Supplier, Supplier.id == InboundShipment.supplier_id)
            .filter(
                SPOAllocation.product_id.in_(pids),
                SPOAllocation.warehouse_id.in_(wids),
                InboundShipment.actual_arrival_date.is_(None),
                or_(
                    SPOAllocation.receipt_status.is_(None),
                    SPOAllocation.receipt_status != "received",
                ),
            )
            .all()
        )
        out: Dict[Tuple[str, str], List[_SpoRow]] = {}
        for row in rows:
            balance = _dec(row.allocated_quantity) - _dec(row.quantity_received)
            if balance <= _ZERO:
                continue
            out.setdefault((str(row.product_id), str(row.warehouse_id)), []).append(
                _SpoRow(
                    spo_number=str(row.spo_number or ""),
                    spo_line_no=row.spo_line_number,
                    allocation_id=str(row.id),
                    arrival_date=row.eta_delay_date or row.estimated_arrival_date,
                    qty=balance,
                    supplier_name=row.supplier_name,
                )
            )
        return out

    def _decided_elsewhere(self, exclude_order_id: Optional[str]) -> set:
        """Core lines an ACTIVE decision covers, other than the one being composed.

        The carve-out matters as much as the rule. A line covered by a decision holds stock,
        and that hold is already out of `_free_stock`, so counting its demand again as ranked
        ahead would subtract the same units twice. But `_free_stock` EXCLUDES the order being
        composed - its own previous revision must not compete with the one replacing it - so
        for that order the hold is NOT netted out, and its covered lines therefore have to stay
        in the queue. Miss this and re-confirming an order that reserved everything is refused
        as "nothing free for this line", which is what the sheet's own suite caught.
        """
        rows = (
            self.db.query(
                SOSupplyDecision.project_sales_order_id, SOSupplyDecision.line_snapshots
            )
            .filter(SOSupplyDecision.state == DECISION_ACTIVE)
            .all()
        )
        out: set = set()
        for pso_id, snapshots in rows:
            if exclude_order_id and str(pso_id) == str(exclude_order_id):
                continue
            for snapshot in snapshots or []:
                core_line_id = (snapshot or {}).get("core_line_id")
                if core_line_id:
                    out.add(str(core_line_id))
        return out

    def _pile_book(
        self,
        product_ids: Iterable[str],
        warehouse_ids: Iterable[str],
        *,
        exclude_order_id: Optional[str] = None,
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """Every line still competing for each (product, location) pile, IN RANK ORDER.

        Ranked by the active `scm.priority_policy` - the one policy that also ranks the
        planning board and the loading plan - with sales-order number then line number then
        line id as the total tie-break, so the queue is reproducible.

        **Lines a confirmed decision already covers are excluded, and that is the
        double-count rule.** Such a line's claim on this pile is already expressed once, as a
        hold that `_free_stock` has taken out of the opening stock. Counting its outstanding
        quantity again as demand ranked ahead would subtract the same units twice and
        understate what is left for everybody behind it. The exception is the order being
        composed, whose own holds `_free_stock` deliberately does not net - see
        `_decided_elsewhere`.
        """
        pids = [pid for pid in product_ids if pid]
        wids = [wid for wid in warehouse_ids if wid]
        if not pids or not wids:
            return {}
        rows = (
            self.db.query(
                SalesOrderLine.id,
                SalesOrderLine.product_id,
                SalesOrderLine.warehouse_id,
                SalesOrderLine.qty_ordered,
                SalesOrderLine.qty_delivered,
                SalesOrderLine.required_date,
                SalesOrder.id.label("sales_order_id"),
                SalesOrder.so_number,
                SalesOrder.order_date,
                SalesOrder.demand_class,
                SalesOrder.customer_id,
                SalesOrder.requested_delivery_date,
                ProjectSalesOrderLine.line_no,
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
            )
            .filter(
                SalesOrderLine.product_id.in_(pids),
                SalesOrderLine.warehouse_id.in_(wids),
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .all()
        )
        if not rows:
            return {}
        decided = self._decided_elsewhere(exclude_order_id)
        rows = [row for row in rows if str(row.id) not in decided]
        if not rows:
            return {}

        terms = priority.payment_terms_by_customer(
            self.db, [str(row.customer_id) for row in rows if row.customer_id]
        )
        weights, class_weights = priority.policy_weights(priority.active_policy(self.db))

        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for row in rows:
            key = (str(row.product_id), str(row.warehouse_id))
            open_qty = max(_dec(row.qty_ordered) - _dec(row.qty_delivered), _ZERO)
            if open_qty <= _ZERO:
                continue
            grouped.setdefault(key, []).append(
                {
                    # The CORE line id is the key, so two lines of one order that nobody has
                    # mirrored cannot collapse onto `(so_number, None)` and lose their share.
                    "key": str(row.id),
                    "so_number": row.so_number or "",
                    # Addressing only, and only because the queue is now READ: a screen showing
                    # who is ahead of you has to be able to link to their sales order and name
                    # their customer.
                    "sales_order_id": str(row.sales_order_id),
                    "customer_id": str(row.customer_id) if row.customer_id else None,
                    "line_no": row.line_no,
                    "line_id": str(row.id),
                    "open_qty": open_qty,
                    "required_date": row.required_date or row.requested_delivery_date,
                    "order_date": row.order_date,
                    "demand_class": row.demand_class,
                    "payment_terms_days": terms.get(str(row.customer_id or "")),
                }
            )

        for key, lines in grouped.items():
            factors = priority.factors_for_demand_rows(
                self.db,
                [
                    {
                        "row_key": line["line_id"],
                        "required_date": line["required_date"],
                        "order_date": line["order_date"],
                        "payment_terms_days": line["payment_terms_days"],
                        "demand_class": line["demand_class"],
                    }
                    for line in lines
                ],
                weights=weights,
                class_weights=class_weights,
            )
            scores = priority.scores_for(factors)
            for line in lines:
                line["rank_score"] = scores[line["line_id"]]
                # The terms behind the score, KEPT rather than thrown away with the local. A
                # queued line has to be able to say which factor put it in front of the line
                # behind it ("why do the orders stand ahead of me?"), and re-ranking the pile a
                # second time to answer that is how two rankings of one pile appear.
                line["factors"] = factors[line["line_id"]]
            # Score first, then PLAN 3.5's own order as the tie-break: required date (missing
            # last), sales-order number, line number, line id. The tie-break is load-bearing
            # rather than decorative - a database with no policy configured scores every demand
            # row 0.0 (the default weights name only `po_document_sequence`, which no
            # sales-order line has), and without the date here the queue for a scarce pile
            # would be alphabetical by sales-order number.
            lines.sort(
                key=lambda line: (
                    -line["rank_score"],
                    line["required_date"] is None,
                    line["required_date"] or date.min,
                    line["so_number"],
                    line["line_no"] if line["line_no"] is not None else 0,
                    line["line_id"],
                )
            )
        return grouped

    def pile_book(
        self, product_id: str, warehouse_id: str, *, exclude_order_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """The queue at ONE pile, in the active policy's order. The read behind the screen.

        Public because the captain asked to see it - "I need to know what is ahead of me to have
        the visibility, and why they are ahead of me, meaning I need to know their rank also" -
        and it is `_pile_book` itself rather than a second query shaped like it: a queue drawn a
        second way would eventually disagree with the one the proposal was computed from, and
        then the screen would be arguing with the plan.
        """
        book = self._pile_book(
            [product_id], [warehouse_id], exclude_order_id=exclude_order_id
        )
        return book.get((str(product_id), str(warehouse_id)), [])

    def pool_claims(
        self,
        product_ids: Iterable[str],
        pool_ids: Iterable[str],
        members: Sequence[Dict[str, Any]],
        *,
        exclude_order_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """What a shared pool's OWN book claims ahead of each line that would draw on it.

        The pool is a pile like any other: the lines fulfilled directly from it want it too,
        and a member location's shortfall queues behind whichever of them the policy ranks
        first. Without this a pool draw promised stock the pool's own outstanding orders had
        already been sold - the same defect as the own-location one, one location along.

        `members` are the lines asking, each stating `key`, `product_id`, `pool_id`,
        `required_date`, `order_date`, `payment_terms_days`, `demand_class`, `so_number` and
        `line_no`. Returns, per member key, the quantity ranked ahead (`qty`) and how many of
        the pool's lines that is (`lines`) - the count travels with the sum because the trail
        prints both ("BRW's own orders ranked ahead of this line claim 1").
        """
        book = self._pile_book(product_ids, pool_ids, exclude_order_id=exclude_order_id)
        if not members:
            return {}
        weights, class_weights = priority.policy_weights(priority.active_policy(self.db))
        out: Dict[str, Dict[str, Any]] = {}
        by_pile: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for member in members:
            key = (str(member["product_id"]), str(member["pool_id"]))
            by_pile.setdefault(key, []).append(member)

        for key, asking in by_pile.items():
            pool_lines = book.get(key, [])
            # Rank the askers against the pool's own book, in one candidate set, so "ahead"
            # means the same thing for both.
            everyone = [
                {
                    "row_key": line["line_id"],
                    "required_date": line["required_date"],
                    "order_date": line["order_date"],
                    "payment_terms_days": line["payment_terms_days"],
                    "demand_class": line["demand_class"],
                }
                for line in pool_lines
            ] + [
                {
                    "row_key": member["key"],
                    "required_date": member.get("required_date"),
                    "order_date": member.get("order_date"),
                    "payment_terms_days": member.get("payment_terms_days"),
                    "demand_class": member.get("demand_class"),
                }
                for member in asking
            ]
            scores = priority.scores_for(
                priority.factors_for_demand_rows(
                    self.db, everyone, weights=weights, class_weights=class_weights
                )
            )

            def sort_key(entry: Tuple[float, str, Any, str]) -> Tuple[Any, ...]:
                score, so_number, line_no, ident = entry
                return (-score, so_number, line_no if line_no is not None else 0, ident)

            ordered_pool = sorted(
                (
                    (
                        scores[line["line_id"]],
                        line["so_number"],
                        line["line_no"],
                        line["line_id"],
                        line["open_qty"],
                    )
                    for line in pool_lines
                ),
                key=lambda row: sort_key(row[:4]),
            )
            for member in asking:
                mine = sort_key(
                    (
                        scores[member["key"]],
                        member.get("so_number") or "",
                        member.get("line_no"),
                        str(member["key"]),
                    )
                )
                ahead = [row for row in ordered_pool if sort_key(row[:4]) < mine]
                out[str(member["key"])] = {
                    "qty": sum((row[4] for row in ahead), _ZERO),
                    "lines": len(ahead),
                }
        return out

    def _attribution(
        self,
        product_ids: Iterable[str],
        warehouse_ids: Iterable[str],
        warehouses: Dict[str, Warehouse],
        spo: Dict[Tuple[str, str], List[_SpoRow]],
        exclude_order_id: Optional[str] = None,
        detail_for: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], Dict[str, Dict[str, Any]]]:
        """Share each product-location pile across every line still competing for it.

        The section 3.5 projection, now served in the ACTIVE POLICY's order rather than by
        required date alone (`_pile_book`), which is what makes a Reserve mean "what is left
        for this line after the demand ranked ahead of it" - the rule the captain asked for on
        reading a strip that said Available -8013 beside a proposed Reserve of 80.

        Per line it answers the components AND the arithmetic behind them: what is ranked
        ahead, how many lines that is, and what was therefore left.
        """
        grouped = self._pile_book(
            product_ids, warehouse_ids, exclude_order_id=exclude_order_id
        )

        out: Dict[Tuple[str, str], Dict[str, Dict[str, Decimal]]] = {}
        for key, demand_lines in grouped.items():
            product_id, warehouse_id = key
            warehouse = warehouses.get(warehouse_id)
            attributed = attribute_sources(
                warehouse_code=(
                    warehouse.warehouse_code if warehouse else warehouse_id
                ),
                opening_stock=self._free_at(product_id, warehouse_id),
                supply_events=[
                    {
                        "spo_number": row.spo_number,
                        "spo_line_no": row.spo_line_no,
                        "allocation_id": row.allocation_id,
                        "arrival_date": row.arrival_date,
                        "qty": row.qty,
                    }
                    for row in spo.get(key, [])
                ],
                demand_lines=demand_lines,
                # `_pile_book` has already ordered them by the active policy; re-sorting by
                # required date here would serve the pile in one order and report the queue
                # in another.
                preserve_demand_order=True,
            )
            opening = self._free_at(product_id, warehouse_id)
            per_line: Dict[str, Dict[str, Any]] = {}
            ahead = _ZERO
            lines_ahead = 0
            queued: List[Dict[str, Any]] = []
            for line in demand_lines:
                line_id = line["line_id"]
                totals: Dict[str, Decimal] = {}
                for component in attributed.get(line_id, ()):  # type: ignore[arg-type]
                    totals[component.kind] = (
                        totals.get(component.kind, _ZERO) + component.qty
                    )
                per_line[line_id] = {
                    **totals,
                    # The arithmetic behind the share, in the strip's own words: what the
                    # queue in front of this line still wants, how long that queue is, and
                    # what was therefore left of the pile when this line was reached.
                    "so_qty_ahead": ahead,
                    "lines_ahead": lines_ahead,
                    "available_to_this_line": max(opening - ahead, _ZERO),
                }
                # WHO is in that queue, for the lines somebody is about to ask about. Computed
                # here, where the queue is already walked in rank order and every entry still
                # carries the factors it was ranked on - and only for the asked-for lines,
                # because naming the queue in front of all 2000 lines of a crowded pile would
                # be quadratic work nobody reads.
                if detail_for is None or line_id in detail_for:
                    per_line[line_id]["ahead_detail"] = _ahead_detail(line, queued)
                queued.append(line)
                ahead += line["open_qty"]
                lines_ahead += 1
            out[key] = per_line
        return out

    # ------------------------------------------------------------ borrow candidates

    def _borrow_candidates(
        self, fact: _LineFacts, *, need: Decimal = _ZERO
    ) -> List[Dict[str, Any]]:
        """Where else this line could be met from, with what it costs the holder.

        Two shapes, and they are answered differently: free stock at a location outside
        the Reserve pool has no donor to ask, so it carries no claim; stock another
        project is holding names that project and its impact, so CS is deciding with the
        donor's position in front of them (AC-B09).

        **Every donor states AutoCount's own triple beside the engine's figures** (PLAN
        13.11). Free stock alone nets reserved and confirmed holds only, and on this book
        almost nothing is confirmed, so "6,990 free" reads as a donor with plenty when
        47,000 is owed there. `qty_on_hand`, `so_qty`, `spo_qty` and the signed
        `available_qty` are the sentence the planner needs before taking somebody's stock.

        **The list is RANKED by what meeting THIS line would leave the donor with**, which is
        the answer to the captain's "I assume this list is ranked by recommendation, is it?" -
        it was not. The key is `available_after_need = available_qty - need`, where `need` is
        the line's residual at this rung (what the ladder was otherwise going to buy),
        descending, then availability descending, then free descending. The first row, and
        only the first, is `recommended`.

        A donor is never judged on giving away the WHOLE of its free stock. That was the first
        rule here and it was wrong in the way that matters: a location holding 11,000 with 140
        owed against it ranked below one holding 7,000 with nothing owed, so the screen
        recommended the smaller pile to cover 21 units.

        The typed quantity never re-orders the list either: a list that reshuffles under the
        cursor is not a recommendation.
        """
        if not fact.product_id:
            return []
        # Everything Reserve cannot reach. For a hot-selling product that INCLUDES the
        # line's own dealer location: Reserve may not touch it, and CS borrowing it with a
        # reason is the sanctioned way to use it (PLAN 3.3).
        inside = self._reserve_location_ids(fact)
        out: List[Dict[str, Any]] = []

        free_cache = self._free_cache
        warehouse_ids = [
            warehouse_id
            for (product_id, warehouse_id), qty in free_cache.items()
            if product_id == fact.product_id and qty > _ZERO and warehouse_id not in inside
        ]
        warehouses = self._warehouses(warehouse_ids)
        for warehouse_id in sorted(warehouse_ids):
            warehouse = warehouses.get(warehouse_id)
            if warehouse is None:
                continue
            free = free_cache[(fact.product_id, warehouse_id)]
            committed = sum(
                (
                    qty
                    for (product_id, held_warehouse, _project), qty in self._holds_cache.items()
                    if product_id == fact.product_id and held_warehouse == warehouse_id
                ),
                _ZERO,
            )
            out.append(
                {
                    "source": ALLOC_SOURCE_OTHER_LOCATION,
                    "warehouse_code": warehouse.warehouse_code,
                    "warehouse_id": warehouse_id,
                    "free_qty": qty_text(free),
                    **self._donor_pile(fact.product_id, warehouse_id, committed, need),
                    "donor_impact": {
                        "free_before": qty_text(free),
                        "free_after_full_borrow": qty_text(_ZERO),
                        "committed_qty": qty_text(committed),
                    },
                }
            )

        holds = [
            (warehouse_id, project_id, qty)
            for (product_id, warehouse_id, project_id), qty in self._holds_cache.items()
            # `project_id` empty means an adopted order holds it and there is no project to
            # name as the donor. Offering it would be offering a Borrow that cannot be
            # confirmed, so it is not offered - the stock stays netted out of free either way.
            if product_id == fact.product_id and qty > _ZERO and project_id
        ]
        if holds:
            projects = {
                str(row.id): row
                for row in self.db.query(Project)
                .filter(Project.id.in_([project_id for _w, project_id, _q in holds]))
                .all()
            }
            donor_warehouses = self._warehouses([w for w, _p, _q in holds])
            for warehouse_id, project_id, qty in sorted(holds):
                warehouse = donor_warehouses.get(warehouse_id)
                donor = projects.get(project_id)
                if warehouse is None or donor is None:
                    continue
                free = free_cache.get((fact.product_id, warehouse_id), _ZERO)
                out.append(
                    {
                        "source": ALLOC_SOURCE_OTHER_PROJECT,
                        "warehouse_code": warehouse.warehouse_code,
                        "warehouse_id": warehouse_id,
                        "donor_project_ref": donor.project_code,
                        "donor_project_id": project_id,
                        "free_qty": qty_text(qty),
                        **self._donor_pile(fact.product_id, warehouse_id, qty, need),
                        "donor_impact": {
                            "free_before": qty_text(free + qty),
                            "free_after_full_borrow": qty_text(free),
                            "committed_qty": qty_text(qty),
                        },
                    }
                )
        return self._ranked(out)

    def _donor_pile(
        self,
        product_id: str,
        warehouse_id: str,
        committed: Decimal,
        need: Decimal = _ZERO,
    ) -> Dict[str, Any]:
        """The (product, location) pile behind a donor, in AutoCount's vocabulary.

        `available_qty` is on hand, less what the whole book still owes there, plus what is
        on the water. SIGNED and never clamped: "this donor is oversold by 46,531" is the
        fact that decides whether taking from them is safe, and a floor of zero would report
        it as "nothing left", which is a different and much weaker statement.

        `available_after_need` is that figure once THIS line is met, and `need_qty` is the
        quantity it was computed against, so the screen can state the default "After borrow"
        before anybody types anything and the planner can check the subtraction.
        """
        pile = self._pile_facts().get(
            (product_id, warehouse_id),
            {"on_hand": _ZERO, "so_qty": _ZERO, "spo_qty": _ZERO},
        )
        available = pile["on_hand"] - pile["so_qty"] + pile["spo_qty"]
        return {
            "qty_on_hand": qty_text(pile["on_hand"]),
            "so_qty": qty_text(pile["so_qty"]),
            "spo_qty": qty_text(pile["spo_qty"]),
            "available_qty": qty_text(available),
            "qty_free": qty_text(self._free_cache.get((product_id, warehouse_id), _ZERO)),
            "qty_committed": qty_text(committed),
            "need_qty": qty_text(need),
            # Signed like availability itself: a donor that cannot meet the line without going
            # short says so here, and that is the row the impact line turns red on.
            "available_after_need": qty_text(available - need),
        }

    @staticmethod
    def _ranked(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Least-damaging donor first, and only that one carries `recommended`.

        Damage is measured against THIS line's residual (`available_after_need`), not against
        the donor's whole free stock. Availability then free break the ties, so of two donors
        that could both meet the line comfortably the one with more room to spare wins.
        """
        candidates.sort(
            key=lambda candidate: (
                -_dec(candidate["available_after_need"]),
                -_dec(candidate["available_qty"]),
                -_dec(candidate["free_qty"]),
                candidate["warehouse_code"],
            )
        )
        for index, candidate in enumerate(candidates):
            candidate["recommended"] = index == 0
        return candidates

    def _pile_facts(self) -> Dict[Tuple[str, str], Dict[str, Decimal]]:
        """`on hand / SO qty / SPO qty` for every pile this request could borrow from.

        Read ONCE per request and only when a donor list is actually asked for: three
        queries, spanning every (product, location) the free and hold caches already know
        about, rather than three per donor row. A board of 800 products offering donors on
        every line would otherwise pay for thousands of round trips.

        `so_qty` is the shared `is_open_demand()` rule over every demand class, exactly as
        the cell's own stock strip counts it (13.7) - a dealer order occupies the donor's
        stock as completely as a project one does.
        """
        if self._pile_cache is not None:
            return self._pile_cache

        self._pile_cache = self._pile_read(
            {product_id for product_id, _w in self._free_cache}
            | {product_id for product_id, _w, _p in self._holds_cache},
            {warehouse_id for _p, warehouse_id in self._free_cache}
            | {warehouse_id for _p, warehouse_id, _project in self._holds_cache},
        )
        return self._pile_cache

    def _pile_read(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Dict[str, Decimal]]:
        """The three reads behind `_pile_facts`, over a stated span and cached by nobody."""
        product_ids = {pid for pid in product_ids if pid}
        warehouse_ids = {wid for wid in warehouse_ids if wid}
        pile: Dict[Tuple[str, str], Dict[str, Decimal]] = {}
        if not product_ids or not warehouse_ids:
            return pile

        for key, (on_hand, _reserved) in self.stock_levels_by_location(
            product_ids
        ).items():
            if key[1] in warehouse_ids:
                pile[key] = {"on_hand": on_hand, "so_qty": _ZERO, "spo_qty": _ZERO}

        owed = demand_qty()
        rows = (
            self.db.query(
                SalesOrderLine.product_id,
                SalesOrderLine.warehouse_id,
                func.coalesce(func.sum(owed), 0).label("owed"),
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(
                SalesOrderLine.product_id.in_(list(product_ids)),
                SalesOrderLine.warehouse_id.in_(list(warehouse_ids)),
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .group_by(SalesOrderLine.product_id, SalesOrderLine.warehouse_id)
            .all()
        )
        for row in rows:
            key = (str(row.product_id), str(row.warehouse_id))
            pile.setdefault(
                key, {"on_hand": _ZERO, "so_qty": _ZERO, "spo_qty": _ZERO}
            )["so_qty"] = _dec(row.owed)

        for key, refs in self._spo_rows(product_ids, warehouse_ids).items():
            pile.setdefault(
                key, {"on_hand": _ZERO, "so_qty": _ZERO, "spo_qty": _ZERO}
            )["spo_qty"] = sum((ref.qty for ref in refs), _ZERO)

        return pile

    def pile_triples(
        self, product_ids: Iterable[str], warehouse_ids: Iterable[str]
    ) -> Dict[Tuple[str, str], Dict[str, Decimal]]:
        """AutoCount's `on hand / SO qty / SPO qty` per (product, location), over a stated span.

        Public for the board's pool rung: `Pool BRW | Had 0` beside an Inventory screen saying
        `Available 1` is two true numbers with nothing between them, and the trail has to print
        the pile the pool's queue was netted from. The same three reads the donor list is built
        on (`_pile_read`), so the pool rung and a Borrow row can never describe one pile two
        ways. One batched read for every pool pile a board touches, never one per rung.
        """
        return self._pile_read(product_ids, warehouse_ids)

    def donor_availability(
        self, pairs: Iterable[Tuple[str, str]]
    ) -> Dict[Tuple[str, str], Decimal]:
        """Signed `available_qty` per (product, location), for the confirmation.

        Public because the confirm path asks the same question the donor list answers: a
        borrow that pushes a donor's availability below zero opens a hole somebody has to
        buy (PLAN 13.11), and asking it twice in two ways is how the screen and the
        confirmation come to disagree about who was hurt.
        """
        wanted = [(str(product_id), str(warehouse_id)) for product_id, warehouse_id in pairs]
        if not wanted:
            return {}
        # Its own read, deliberately: the request-wide caches belong to the composition
        # that is mid-flight when the confirmation asks this, and refilling them here would
        # answer a later question with the wrong span.
        facts = self._pile_read(
            {product_id for product_id, _w in wanted},
            {warehouse_id for _p, warehouse_id in wanted},
        )
        out: Dict[Tuple[str, str], Decimal] = {}
        for key in wanted:
            pile = facts.get(key, {"on_hand": _ZERO, "so_qty": _ZERO, "spo_qty": _ZERO})
            out[key] = pile["on_hand"] - pile["so_qty"] + pile["spo_qty"]
        return out
