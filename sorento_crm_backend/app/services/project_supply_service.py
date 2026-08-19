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
hold. The lines being REPLACED are excluded from that subtraction, or their own previous
revision would compete with the one replacing it - by line and not by order, because a
covered line the confirmation carries forward keeps its hold (13.4, the union is the
server's) and must be read as any other order's covered line.

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
    BORROW,
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

#: The product a hold is keyed by: the CORE line's when the mirror line is reconciled to
#: one, else the mirror's own. Free stock is read against the core product (`_facts_for`
#: prefers it on a remap), so the hold must net out of that pile and not the mirror's.
_hold_product = func.coalesce(SalesOrderLine.product_id, ProjectSalesOrderLine.product_id)


def _pile_order(line: Dict[str, Any]) -> Tuple[Any, ...]:
    """The queue order at one pile: score, then required date (missing last), then
    sales-order number, line number, line id. See `ProjectSupplyService._rank_pile`."""
    return (
        -line["rank_score"],
        line.get("required_date") is None,
        line.get("required_date") or date.min,
        line.get("so_number") or "",
        line["line_no"] if line.get("line_no") is not None else 0,
        line["line_id"],
    )


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

    A factor THEY carry and I do not is a difference too: their score has a term mine has
    nothing to answer, so it counts as `weight * their value` and is named for that factor
    (they have payment terms recorded, I have none). Without it every shared difference was
    zero and the answer fell through to "a lower sales order number", which is not why they
    are ahead.

    Equal scores mean the POLICY separated nothing and the queue was decided by the tie-break
    instead, in `_pile_book`'s own order: the required date first (`earlier_date` - it IS a
    date difference, but a tie-break rather than a factor, so it is named apart from
    `need_by_date`), then an earlier line of the same order, then a lower sales-order number.
    """
    same_order = (theirs.get("so_number") or "") == (mine.get("so_number") or "")
    if round(float(theirs.get("rank_score") or 0.0), 9) == round(
        float(mine.get("rank_score") or 0.0), 9
    ):
        their_date = theirs.get("required_date")
        my_date = mine.get("required_date")
        if their_date is not None and (my_date is None or their_date < my_date):
            return "earlier_date"
        return "line_order" if same_order else "tie_break"
    tie = "line_order" if same_order else "tie_break"
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
        my_value = 0.0 if counterpart is None else float(counterpart.value)
        diff = float(factor.weight) * (float(factor.value) - my_value)
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
    #: ABC A on RETAIL (dealer)-classed demand at an active, available warehouse (PLAN 3.3,
    #: amended 19 August 2026: the demand class the ABC figure was computed against decides
    #: hot-selling now, not the warehouse's own segment). Gates the shared pool to nothing.
    is_dealer_hot_selling: bool = False
    #: The locations holding it as ABC A on retail demand, by code - the evidence behind
    #: `is_dealer_hot_selling`, so the verdict can be checked rather than trusted.
    dealer_hot_selling_where: List[str] = field(default_factory=list)
    #: ABC A on PROJECT-classed demand at an active, available warehouse. Gates the shared
    #: pool to its own signed availability (`pool_available`) rather than removing it.
    is_project_hot_selling: bool = False
    #: The locations holding it as ABC A on project demand, by code.
    project_hot_selling_where: List[str] = field(default_factory=list)
    #: Classified (a non-null letter exists on that column, at an active location) but not
    #: hot - "Cold at retail" / "Cold at project", the plain word for a real, non-A letter.
    #: `False` while the class is hot too; the hot flag above already covers that case.
    dealer_classified: bool = False
    project_classified: bool = False
    #: The shared pool's own signed availability - `on hand - SO qty + SPO qty` - the figure
    #: a project hot-selling line's pool draw is capped against. Unsigned `pool_free` above
    #: is what THIS line's queue left of it; this is the pool's whole position, and can be
    #: negative (an oversold pool offers nothing, never a floor of zero read as "some").
    pool_available: Decimal = _ZERO
    classification_unavailable: bool = False
    is_discontinued: bool = False
    timely_qty: Decimal = _ZERO
    timely_refs: List[_SpoRow] = field(default_factory=list)
    advisory_refs: List[_SpoRow] = field(default_factory=list)
    #: Why nothing can be proposed for this line, when nothing can (a mirror line with no
    #: reconciled AutoCount line). Set, the line is read out with no components and no
    #: donors; it is never carried and cannot be named to a confirmation.
    unplannable_reason: Optional[str] = None

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


@dataclass
class _FrozenComponent:
    """One component read back off a frozen snapshot, in the shape the payload's own
    components have (`.warehouse_id`, `.qty`, and for a borrow `.source`), so the shortfall
    arithmetic can walk a carried line and a named line with one loop."""

    warehouse_id: Optional[str]
    qty: Decimal
    source: Optional[str] = None
    donor_project_id: Optional[str] = None


@dataclass
class _CarriedLine:
    """A line the ACTIVE revision covers that this confirmation did not name.

    Carried into the new revision verbatim: `snapshot` is the previous revision's dict,
    unchanged, and its holds are copied row for row. It is judged against nothing, because
    it was judged when it was decided and nobody has asked to change it.
    """

    line: ProjectSalesOrderLine
    snapshot: Dict[str, Any]
    fact: _LineFacts

    def _components(self, kind: str) -> List[_FrozenComponent]:
        return [
            _FrozenComponent(
                warehouse_id=component.get("source_warehouse_id"),
                qty=_dec(component.get("qty")),
                source=component.get("source"),
                donor_project_id=component.get("donor_project_id"),
            )
            for component in (self.snapshot.get("components") or [])
            if component.get("kind") == kind
        ]

    @property
    def reserve(self) -> List[_FrozenComponent]:
        return self._components(RESERVE)

    @property
    def borrow(self) -> List[_FrozenComponent]:
        return self._components("borrow")

    @property
    def buy_qty(self) -> Decimal:
        return _dec(self.snapshot.get("buy_qty"))


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
        # Warehouse and project rows this request has already read, by id. A donor list is
        # asked for once per line, and a board of hundreds of lines paid two round trips
        # per line to re-read the same handful of rows.
        self._warehouse_memo: Dict[str, Optional[Warehouse]] = {}
        self._project_memo: Dict[str, Optional[Project]] = {}
        # The free / holds caches indexed by product, rebuilt when either cache is
        # replaced (`_by_product`), so a per-line lookup walks that product's rows only.
        self._indexed: Optional[Tuple[Any, Any, Dict[str, Any], Dict[str, Any]]] = None

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
            if fact.unplannable_reason:
                # Nothing to walk the ladder for: no core line, no open quantity, no
                # location. The line is read out with the reason and nothing else.
                payload_lines.append(self._serialize_line(fact, (), None))
                continue
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
            is_dealer_hot_selling=fact.is_dealer_hot_selling,
            is_project_hot_selling=fact.is_project_hot_selling,
            free_stock=free_stock,
            pool_location=fact.pool_code,
            pool_available=fact.pool_available,
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

        self._free_cache = self._free_stock(product_ids, exclude_line_ids=None)
        self._holds_cache = self._holds_by_project(product_ids, exclude_line_ids=None)
        self._pile_cache = None
        # Eager, not lazy: a project hot-selling line's pool draw is capped against the
        # pool's signed availability on every read, not only when a donor list is asked for.
        pool_piles = self._pile_facts()
        (
            dealer_hot, project_hot, unavailable, dealer_where, project_where,
            dealer_classified_set, project_classified_set,
        ) = self._classification(product_ids)
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
                    # The core line, when the caller named one, so a member fulfilled from
                    # the pool itself is not counted ahead of itself.
                    "line_id": row.get("line_id"),
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
            pool_triple = pool_piles.get((product_id, str(pool.id))) if pool and product_id else None
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
                is_dealer_hot_selling=(product_id or "") in dealer_hot,
                dealer_hot_selling_where=list(dealer_where.get(product_id or "", [])),
                is_project_hot_selling=(product_id or "") in project_hot,
                project_hot_selling_where=list(project_where.get(product_id or "", [])),
                dealer_classified=(product_id or "") in dealer_classified_set,
                project_classified=(product_id or "") in project_classified_set,
                pool_available=(
                    pool_triple["on_hand"] - pool_triple["so_qty"] + pool_triple["spo_qty"]
                    if pool_triple
                    else _ZERO
                ),
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
            "product_id": fact.product_id,
            "description": line.description,
            "uom": line.uom,
            "open_qty": qty_text(fact.open_qty),
            "required_date": fact.required_date,
            "fulfilment_location": fact.own_code,
            "is_dealer_hot_selling": fact.is_dealer_hot_selling,
            "is_project_hot_selling": fact.is_project_hot_selling,
            "dealer_classified": fact.dealer_classified,
            "project_classified": fact.project_classified,
            "classification_unavailable": fact.classification_unavailable,
            "is_discontinued": fact.is_discontinued,
            "pool_location": fact.pool_code,
            # The old reorder-level cap never applied above own-location Reserve and it no
            # longer applies to the pool either (19 August 2026): dealer hot-selling offers
            # the pool nothing, project hot-selling caps it by availability instead. Null,
            # never a number a limit nobody set would read as.
            "pool_cap": None,
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
            # An unplannable line is offered nobody's stock: there is no need to rank against.
            "borrow_candidates": (
                []
                if fact.unplannable_reason
                else self._borrow_candidates(
                    fact,
                    need=sum(
                        (
                            component.qty
                            for component in components
                            if component.kind == BUY
                        ),
                        _ZERO,
                    ),
                )
            ),
            "unplannable_reason": fact.unplannable_reason,
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
                "buy_reason": snapshot.get("buy_reason"),
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
        uncover_line_ids: Sequence[str] = (),
    ) -> Dict[str, Any]:
        """One transaction, every CHOSEN line, or nothing (PLAN 3.1, AC-C01 as amended
        by PLAN-fulfilment-planning-from-autocount-so.md 13.4).

        The payload names the lines being confirmed. They commit together or not at all;
        a line it does not name and that NO active revision covers stays undecided and
        keeps flowing to reorder planning. A payload naming NO line is refused, because
        superseding the revision that is holding stock and putting nothing in its place
        is not a decision anybody made.

        **The union is the server's.** A line the ACTIVE revision covers that the payload
        does not name is CARRIED FORWARD into the new revision verbatim: the same frozen
        snapshot dict, the same holds copied row for row, no re-validation against live
        facts. The board posts only what the planner just decided (at day granularity it
        cannot even see every covered line), and re-posting a covered line rebuilt from
        its snapshot re-judged it against facts that had moved since - a discontinued
        product's covered line 422'd the confirmation of an unrelated one. A named line
        REPLACES its frozen one (that is an amendment).

        **The un-decide seam** (PLAN-so-book-diff-replanning.md section 10, defect found
        live 19 August 2026): a covered line this call is meant to DROP - not replace,
        not carry - names itself in `uncover_line_ids` instead of the payload. Without
        this, a planning-change batch's `release`/`replan`/`retire` row deliberately left
        OUT of the payload (so it returns to the board undecided) was carried forward
        verbatim by the rule above the instant any OTHER line on the SAME order WAS named -
        seen live: SO403765 rev 5 kept line 12's old Buy and old date after an ADVANCE was
        raised for it, because line 8's Release was the only line actually posted and line
        12 rode along uninvited. Named here, a line's snapshot is excluded from the carry
        outright: its hold is gone (`_carry_allocations` never runs for it), `_borrow_shortfalls`
        reads it as gone (`checked` no longer contains it), and `refresh_for_decision`
        treats it exactly as a line "absent from `buy_lines`" already does - cancels
        whatever it had raised. The only OTHER way a covered line leaves the decision
        remains a material change superseding the whole revision
        (`supersede_for_material_change`, which carries nothing at all) or a drift
        challenging it.

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
        # What the order's OWN active revision already holds per line, read before the
        # drift check below can flip it to `challenged` (PLAN-so-book-diff-replanning.md
        # section 10, defect A). A resubmitted component this order already holds is not a
        # new ask, challenged or not: the challenge is about the SNAPSHOT (dates/quantities
        # having moved), not about whether the physical hold behind an unrelated component
        # is still this order's own. `_check_line` credits it back so re-affirming a hold
        # this order has held all along does not compete in the queue against itself, or
        # lose to a rival that only appeared after the hold was taken.
        carried_holds = self._frozen_by_line(self.active_decision(str(order.id)))
        # The same drift check the sheet runs, BEFORE the active revision is read for the
        # carry: a revision whose frozen facts have moved is challenged here exactly as it
        # would be on the next read, so its snapshots and holds are not carried verbatim
        # into a fresh revision stamped as confirmed now. Nothing is carried from a
        # challenged revision; the lines it covered are undecided again.
        self.challenge_if_drifted(order, lines=lines)
        self._lock_stock(payload_lines, lines)

        named = {str(entry.project_line_id) for entry in payload_lines}
        # Only the NAMED lines are being replaced. A covered line the payload leaves alone
        # is carried forward with its holds, so it is judged as any other order's covered
        # line - hold netted, out of the queue - and the named lines cannot be offered what
        # it is still holding. An unreconciled line is refused only when it is named.
        facts = self._facts_for(
            order, lines, replacing=named, refuse_unmapped=named
        )
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
            self._check_line(
                entry, fact, pool_left, borrow_left, stale, invalid, carried_holds
            )

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

        carried = self._carried_lines(
            self.active_decision(str(order.id)), named=seen, by_id=by_id, facts=facts,
            uncover=set(uncover_line_ids),
        )
        return self._write_decision(
            order, checked, carried=carried, actor_user_id=actor_user_id
        )

    def _carried_lines(
        self,
        previous: Optional[SOSupplyDecision],
        *,
        named: set,
        by_id: Dict[str, ProjectSalesOrderLine],
        facts: Dict[str, _LineFacts],
        uncover: Optional[set] = None,
    ) -> List[_CarriedLine]:
        """The active revision's lines this confirmation did not name, verbatim - except
        the ones the caller named in `uncover` (the un-decide seam, `confirm`'s docstring):
        those are dropped from the new revision outright rather than carried.

        A snapshot for a line no longer on the order is not carried either: there is no
        row to hold stock for, and the read-side drift check names exactly that case as a
        challenge. Everything else comes across untouched.
        """
        if previous is None:
            return []
        uncover = uncover or set()
        out: List[_CarriedLine] = []
        for snapshot in previous.line_snapshots or []:
            line_id = str(snapshot.get("project_line_id") or "")
            if not line_id or line_id in named or line_id not in by_id or line_id in uncover:
                continue
            out.append(
                _CarriedLine(line=by_id[line_id], snapshot=snapshot, fact=facts[line_id])
            )
        return out

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

    def _carried_component_qty(
        self,
        carried_holds: Dict[str, Dict[str, Any]],
        line_id: str,
        kind: str,
        warehouse_id: str,
        *,
        donor_project_id: Optional[str] = None,
    ) -> Decimal:
        """What this order's own active (or just-challenged) revision already held here.

        Read off the frozen snapshot taken before this `confirm()` call, by exact
        (line, kind, location[, donor]) - not a total, so a component moved to a
        different location or a different donor carries nothing and competes fresh
        (PLAN-so-book-diff-replanning.md section 10, defect A). `kind`/`source_warehouse_id`
        /`donor_project_id` are the same keys `_snapshot` freezes a component under.
        """
        components = (carried_holds.get(line_id) or {}).get("components") or []
        total = _ZERO
        for component in components:
            if str(component.get("kind") or "") != kind:
                continue
            if str(component.get("source_warehouse_id") or "") != warehouse_id:
                continue
            if kind == BORROW and str(
                component.get("donor_project_id") or ""
            ) != (donor_project_id or ""):
                continue
            total += _dec(component.get("qty"))
        return total

    def _check_line(
        self,
        entry: Any,
        fact: _LineFacts,
        pool_left: Dict[str, Decimal],
        borrow_left: "_BorrowLedger",
        stale: List[Dict[str, Any]],
        invalid: List[Dict[str, Any]],
        carried_holds: Dict[str, Dict[str, Any]],
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
                is_dealer_hot_selling=fact.is_dealer_hot_selling,
                is_project_hot_selling=fact.is_project_hot_selling,
                fulfilment_location=fact.own_code,
                pool_location=fact.pool_code,
                free_stock=self._free_for(fact, pool_left),
                pool_available=fact.pool_available,
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
            # What this order's own active revision already holds here, resubmitted:
            # not a new ask, so it is exempt from the recheck entirely - `capacity` is
            # computed from a ZERO baseline for this line (`_facts_for`'s un-netting), so
            # an increase still has to clear the SAME capacity a first-time ask of that
            # total would (PLAN-so-book-diff-replanning.md section 10, defect A). Only the
            # exemption for an unchanged-or-smaller ask is new; the arithmetic for a real
            # increase is untouched, so a genuinely competing sibling hold (another line's
            # own Reserve, never excluded) still refuses it exactly as it always has
            # (`test_a_hold_the_same_order_carries_forward_is_netted_by_the_confirm_as_
            # the_board_nets_it`).
            carried = self._carried_component_qty(
                carried_holds, str(line.id), RESERVE, str(item.warehouse_id)
            )
            ask = qty - carried if qty > carried else _ZERO
            if ask <= _ZERO:
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
                    f"{qty_text(ask)} asked for can be reserved from it. Buy that quantity "
                    "instead, or borrow it on the order's own sheet.",
                )
                continue
            if qty > capacity[warehouse]:
                # Named for the INCREASE, not the whole resubmitted quantity: `capacity`
                # never had the carried part subtracted from it (it was excluded, not
                # credited), so what remains for the increase alone is `capacity` less
                # what this line already carries.
                room = capacity[warehouse] - carried
                refuse(
                    stale,
                    f"{warehouse} now has {qty_text(room if room > _ZERO else _ZERO)} free "
                    f"for this line, and {qty_text(ask)} was asked for.",
                )
                continue
            capacity[warehouse] -= qty
            if fact.pool_code and warehouse == fact.pool_code and fact.pool:
                pool_left[fact.pool_key] = max(
                    pool_left.get(fact.pool_key, fact.pool_free) - qty, _ZERO
                )

        for item in entry.borrow or []:
            self._check_borrow(item, fact, borrow_left, refuse, stale, invalid, carried_holds)

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

        Structural, not "wherever there happens to be stock": the fulfilment location and
        the shared pool, always - hot-selling no longer removes either from Reserve's reach
        (captain, 19 August 2026: own-location Reserve is always eligible, hot-selling or
        not). What hot-selling gates is how much the POOL contributes, not whether the own
        location is inside Reserve at all, so it is never offered as a Borrow source either.
        """
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
        carried_holds: Dict[str, Dict[str, Any]],
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
            # What this order's own active revision already holds here, resubmitted:
            # not a new ask - same "zero baseline" reasoning as the Reserve check above
            # (PLAN-so-book-diff-replanning.md section 10, defect A).
            carried = self._carried_component_qty(
                carried_holds, str(fact.line.id), BORROW, str(warehouse.id)
            )
            ask = qty - carried if qty > carried else _ZERO
            if ask <= _ZERO:
                return
            available = borrow_left.free(
                fact.product_id, str(warehouse.id), self._free_at
            )
            if qty > available:
                room = available - carried
                refuse(
                    stale,
                    f"{warehouse.warehouse_code} has {qty_text(room if room > _ZERO else _ZERO)} "
                    f"free, and {qty_text(ask)} was asked for.",
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
        # What this order's own active revision already holds here FROM THIS SAME donor,
        # resubmitted: not a new ask (PLAN-so-book-diff-replanning.md section 10, defect A).
        carried = self._carried_component_qty(
            carried_holds,
            str(fact.line.id),
            BORROW,
            str(warehouse.id),
            donor_project_id=str(donor.id),
        )
        ask = qty - carried if qty > carried else _ZERO
        if ask <= _ZERO:
            return
        if qty > held + free:
            room = held + free - carried
            refuse(
                stale,
                f"{donor.project_code} has {qty_text(room if room > _ZERO else _ZERO)} at "
                f"{warehouse.warehouse_code}, and {qty_text(ask)} was asked for.",
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
        carried: Sequence[_CarriedLine] = (),
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
        # The named lines as decided now, then the carried ones exactly as they were
        # frozen (`confirm`): the same dicts, not a re-serialisation of them.
        snapshots = [
            self._snapshot(line, entry, fact) for line, entry, fact in checked
        ] + [entry.snapshot for entry in carried]

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
        for entry in carried:
            # Its holds move to this revision row for row, and its Buy stays on
            # purchasing's list: `refresh_for_decision` treats a line absent from
            # `buy_lines` as dropped and cancels its raised rows.
            self._carry_allocations(decision, previous, entry.line)
            buy_lines.append(
                {
                    "line": entry.line,
                    "line_no": entry.line.line_no,
                    "item_code": entry.fact.item_code,
                    "buy_qty": entry.buy_qty,
                    "required_date": entry.fact.required_date or entry.line.delivery_date,
                    "stock_location": entry.line.stock_location,
                    # Re-raised under this revision, but not NEW to purchasing: the
                    # confirm result counts only what this confirmation decided.
                    "carried": True,
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
            borrow_shortfalls=self._borrow_shortfalls(
                order,
                list(checked) + [(entry.line, entry, entry.fact) for entry in carried],
            ),
        )
        decided = len(checked) + len(carried)
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
        reserve out again would count the same quantity twice. **A Borrow from the line's
        own location is never one either, for the same reason** - a dealer hot-selling
        product may only Reserve from the pool, so its own location is a legitimate Borrow
        source, and its demand is still inside that location's SO qty.

        The donor's availability is the AutoCount triple LESS what other confirmed
        decisions already hold there from elsewhere. A borrow, or a pool take, writes a
        hold and no sales-order line at the donor, so `on hand - SO + SPO` cannot see it,
        and a second borrower judged on the triple alone would be offered stock the first
        one has already taken. A hold whose line's own location IS the donor is left out:
        that demand is already inside the donor's SO qty.

        `checked` carries the named lines AND the carried ones (`_CarriedLine`), because
        a carried borrow still holds its donor's stock and the hole is the order's, not the
        revision's.
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
            pool_id = str(fact.pool.id) if fact.pool else None
            own_id = str(fact.warehouse.id) if fact.warehouse else None
            for item in entry.borrow or []:
                qty = _dec(item.qty)
                if qty <= _ZERO or not item.warehouse_id:
                    continue
                if str(item.warehouse_id) == own_id:
                    continue
                pile = pile_for(line, fact, str(item.warehouse_id))
                pile["borrowed"] += qty
                pile["lines"].append(line.line_no)
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
        # The WHOLE order's holds are left out here, named and carried alike, because
        # `checked` re-adds every one of them as `taken` above.
        held_from_elsewhere = self._holds_from_elsewhere(
            piles.keys(),
            exclude_line_ids=[str(line.id) for line, _entry, _fact in checked],
        )
        out: List[Dict[str, Any]] = []
        reference = order.autocount_doc_no or order.provisional_ref or ""
        for key, pile in piles.items():
            taken = pile["borrowed"] + pile["reserved"]
            after = (
                availability.get(key, _ZERO)
                - held_from_elsewhere.get(key, _ZERO)
                - taken
            )
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
                "is_dealer_hot_selling": fact.is_dealer_hot_selling,
                "is_project_hot_selling": fact.is_project_hot_selling,
                "classification_unavailable": fact.classification_unavailable,
                "pool_location": fact.pool_code,
                "pool_cap": None,
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
            is_dealer_hot_selling=fact.is_dealer_hot_selling,
            is_project_hot_selling=fact.is_project_hot_selling,
            fulfilment_location=fact.own_code,
            pool_location=fact.pool_code,
            free_stock=self._free_for(fact, {}),
            pool_available=fact.pool_available,
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

    def _carry_allocations(
        self,
        decision: SOSupplyDecision,
        previous: Optional[SOSupplyDecision],
        line: ProjectSalesOrderLine,
    ) -> None:
        """A carried line's components, copied from the superseded revision row for row.

        Copied rather than re-derived: a hold is an allocation row under an ACTIVE decision
        (`_hold_rows`), and the superseded revision's rows stop holding the moment it is
        superseded, so the new revision needs its own. The copy keeps the same warehouse,
        quantity, source, claim and donor snapshot - the claim was accepted once and is not
        made again, and the donor's position is the one the decision was taken against, not
        today's. `confirmed_by` / `confirmed_at` stay the original's, because that is when
        and by whom the line was decided; this revision only carries it.
        """
        if previous is None:
            return
        rows = (
            self.db.query(SOLineAllocation)
            .filter(
                SOLineAllocation.decision_id == previous.id,
                SOLineAllocation.so_line_id == line.id,
            )
            .all()
        )
        for row in rows:
            self.db.add(
                SOLineAllocation(
                    company_id=row.company_id,
                    so_line_id=row.so_line_id,
                    source_type=row.source_type,
                    warehouse_id=row.warehouse_id,
                    source_project_id=row.source_project_id,
                    qty=row.qty,
                    claim_id=row.claim_id,
                    decision_id=decision.id,
                    reason=row.reason,
                    donor_impact_snapshot=row.donor_impact_snapshot,
                    confirmed_by=row.confirmed_by,
                    confirmed_at=row.confirmed_at,
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
        self,
        order: ProjectSalesOrder,
        lines: Sequence[ProjectSalesOrderLine],
        *,
        replacing: Optional[Set[str]] = None,
        refuse_unmapped: Optional[Set[str]] = None,
    ) -> Dict[str, _LineFacts]:
        """Read every fact the sheet and the commit judge a line against.

        A line with no reconciled core line has no current open quantity, and promising
        supply against the ORIGINAL customer quantity is exactly the double-count this
        contract exists to stop (PLAN 3.1 step 2). Such a line is refused ONLY when
        `refuse_unmapped` names it - the confirmation passes the lines its payload names,
        so one unreconciled sibling cannot stop the lines that are ready. Every other
        unmapped line is read as unplannable (`unplannable_reason`, open quantity 0, no
        location), which is how the sheet still reads while it waits for reconciliation.

        `replacing` names the project lines this composition is about to REPLACE - the ones
        the confirmation payload names. Their holds are un-netted and their demand stays in
        the queue; every other line of the order is read as covered-elsewhere (hold netted,
        out of the queue), which is what the union-is-the-server's carry-forward makes true
        of it. `None` means every line (the sheet, which proposes for all of them).
        """
        unmapped = [
            line
            for line in lines
            if not line.core_sales_order_line_id
            and refuse_unmapped is not None
            and str(line.id) in refuse_unmapped
        ]
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

        # The lines being REPLACED by this composition: their holds are un-netted (a previous
        # revision must not compete with the one replacing it) and their demand stays in the
        # queue. Every other line of the order - a covered line the confirmation carries
        # forward verbatim - is treated exactly as another order's covered line: its hold is
        # netted and it is out of the queue. The board reads it that way (`demand_facts`), and
        # a confirm that un-netted the WHOLE order's holds handed a named line stock its own
        # carried sibling was still holding (`test_fulfilment_board`).
        replaced = [
            str(line.id)
            for line in lines
            if replacing is None or str(line.id) in replacing
        ]
        self._free_cache = self._free_stock(product_ids, exclude_line_ids=replaced)
        self._holds_cache = self._holds_by_project(product_ids, exclude_line_ids=replaced)
        self._pile_cache = None
        # Eager, not lazy: a project hot-selling line's pool draw is capped against the
        # pool's signed availability on every read, not only when a donor list is asked for.
        pool_piles = self._pile_facts()
        # The core sales orders behind the lines, for the SAME factor values the board hands
        # `pool_claims` for a member: document date, demand class, payment terms, and the
        # sales-order number the tie-break sorts on. Passing None for them scored the asking
        # line on need-by date alone against a pool book scored on every factor, so the confirm
        # ranked it lower than the board had, claimed more of the pool ahead of it, and
        # refused the very Reserve the board proposed (SO403765 line 8, live: "BRW has nothing
        # free for this line now" against a board reading "3 claimed ahead, 4 left").
        core_orders = {
            str(row.id): row
            for row in (
                self.db.query(SalesOrder)
                .filter(
                    SalesOrder.id.in_(
                        list({str(core.sales_order_id) for core in cores.values()})
                    )
                )
                .all()
                if cores
                else []
            )
        }
        terms = priority.payment_terms_by_customer(
            self.db,
            [str(row.customer_id) for row in core_orders.values() if row.customer_id],
        )

        members: List[Dict[str, Any]] = []
        for line in lines:
            core = cores.get(str(line.core_sales_order_line_id or ""))
            if core is None or not core.warehouse_id:
                continue
            warehouse = warehouses.get(str(core.warehouse_id))
            if warehouse is None or not warehouse.pool_warehouse_id:
                continue
            core_order = core_orders.get(str(core.sales_order_id))
            members.append(
                {
                    "key": str(line.id),
                    "product_id": str(core.product_id or line.product_id),
                    "pool_id": str(warehouse.pool_warehouse_id),
                    "required_date": core.required_date or line.delivery_date,
                    "order_date": core_order.order_date if core_order else None,
                    "payment_terms_days": (
                        terms.get(str(core_order.customer_id or "")) if core_order else None
                    ),
                    "demand_class": core_order.demand_class if core_order else None,
                    "so_number": (
                        (core_order.so_number if core_order else None)
                        or order.provisional_ref
                    ),
                    "line_no": line.line_no,
                    "line_id": str(core.id),
                }
            )
        pool_ahead = self.pool_claims(
            product_ids, pool_ids, exclude_line_ids=replaced, members=members
        )
        (
            dealer_hot, project_hot, unavailable, dealer_where, project_where,
            dealer_classified_set, project_classified_set,
        ) = self._classification(product_ids)
        levels = self._reorder_levels(product_ids, pool_ids)
        discontinued = self._discontinued(product_ids)
        spo = self._spo_rows(product_ids, warehouse_ids)
        attribution = self._attribution(
            product_ids,
            warehouse_ids,
            warehouses,
            spo,
            exclude_line_ids=replaced,
            # The sheet prints the share and never the names behind it, so it asks for
            # nobody's queue: describing every line of every pile is quadratic work on a
            # crowded location, paid on every sheet read and every confirm, for nothing.
            detail_for=set(),
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
            pool_triple = pool_piles.get((product_id, str(pool.id))) if pool and product_id else None
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
                is_dealer_hot_selling=(product_id or "") in dealer_hot,
                dealer_hot_selling_where=list(dealer_where.get(product_id or "", [])),
                is_project_hot_selling=(product_id or "") in project_hot,
                project_hot_selling_where=list(project_where.get(product_id or "", [])),
                dealer_classified=(product_id or "") in dealer_classified_set,
                project_classified=(product_id or "") in project_classified_set,
                pool_available=(
                    pool_triple["on_hand"] - pool_triple["so_qty"] + pool_triple["spo_qty"]
                    if pool_triple
                    else _ZERO
                ),
                classification_unavailable=(product_id or "") in unavailable,
                is_discontinued=(product_id or "") in discontinued,
                timely_qty=shares.get(TIMELY_SPO, _ZERO),
                timely_refs=timely_refs,
                advisory_refs=[
                    row for row in spo.get(key, []) if row not in timely_refs
                ],
                unplannable_reason=(
                    None
                    if core is not None
                    else "No reconciled AutoCount line. Reconcile the sales order first."
                ),
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
        """Warehouse rows by id, read once per request and remembered (an id that matches
        no row is remembered too, so it is not asked for again)."""
        ids = {str(wid) for wid in warehouse_ids if wid}
        missing = [wid for wid in ids if wid not in self._warehouse_memo]
        if missing:
            for wid in missing:
                self._warehouse_memo[wid] = None
            for row in self.db.query(Warehouse).filter(Warehouse.id.in_(missing)).all():
                self._warehouse_memo[str(row.id)] = row
        return {
            wid: self._warehouse_memo[wid]
            for wid in ids
            if self._warehouse_memo.get(wid) is not None
        }

    def _warehouse_row(self, warehouse_id: str) -> Optional[Warehouse]:
        return self._warehouses([warehouse_id]).get(str(warehouse_id)) if warehouse_id else None

    def _projects(self, project_ids: Iterable[str]) -> Dict[str, Project]:
        """Project rows by id, the same way `_warehouses` remembers warehouses."""
        ids = {str(pid) for pid in project_ids if pid}
        missing = [pid for pid in ids if pid not in self._project_memo]
        if missing:
            for pid in missing:
                self._project_memo[pid] = None
            for row in self.db.query(Project).filter(Project.id.in_(missing)).all():
                self._project_memo[str(row.id)] = row
        return {
            pid: self._project_memo[pid]
            for pid in ids
            if self._project_memo.get(pid) is not None
        }

    def _by_product(
        self,
    ) -> Tuple[
        Dict[str, Dict[str, Decimal]], Dict[str, Dict[Tuple[str, str], Decimal]]
    ]:
        """The free and holds caches, indexed by product.

        `free[product_id][warehouse_id]` and `holds[product_id][(warehouse_id,
        project_id)]`, over the SAME cache dicts `_free_at` / `_held_at` read - rebuilt
        only when `_facts_for` or `demand_facts` replaces them, which is the only way
        they change. A donor list walks one product's rows, not the whole request's.
        """
        view = self._indexed
        if (
            view is None
            or view[0] is not self._free_cache
            or view[1] is not self._holds_cache
        ):
            free: Dict[str, Dict[str, Decimal]] = {}
            for (product_id, warehouse_id), qty in self._free_cache.items():
                free.setdefault(product_id, {})[warehouse_id] = qty
            holds: Dict[str, Dict[Tuple[str, str], Decimal]] = {}
            for (product_id, warehouse_id, project_id), qty in self._holds_cache.items():
                holds.setdefault(product_id, {})[(warehouse_id, project_id)] = qty
            view = self._indexed = (self._free_cache, self._holds_cache, free, holds)
        return view[2], view[3]

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
        for key, _project_id, qty in self._hold_rows(ids, exclude_line_ids=None):
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

        No line is excluded, because a cross-order reader is not replacing any one line.

        It carries `_free_stock`'s known limit, and the board is built to SHOW that limit
        rather than hide it (PLAN 13.5.1): only CONFIRMED holds are netted off, so two orders
        composed separately can both still be proposed the same stock. The board answers that
        by serving one pile down the ranking and marking the rows it could not cover as
        contested. The locking fix belongs to the confirmation path.
        """
        return self._free_stock(product_ids, exclude_line_ids=None)

    def _free_stock(
        self, product_ids: Iterable[str], *, exclude_line_ids: Optional[Sequence[str]]
    ) -> Dict[Tuple[str, str], Decimal]:
        """On hand, minus reserved, minus what confirmed decisions already hold.

        A hold counts when its allocation belongs to no decision (every row written before
        Stage 1C) or to an ACTIVE one. A superseded revision's rows are history and hold
        nothing, and the lines being replaced (`exclude_line_ids`, project line ids) are
        excluded so their own previous revision does not compete with the one replacing it.
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
            ids, exclude_line_ids=exclude_line_ids
        ):
            key = (product_id, warehouse_id)
            if key in free:
                free[key] = max(free[key] - qty, _ZERO)
        return free

    def _hold_rows(
        self, product_ids: Sequence[str], *, exclude_line_ids: Optional[Sequence[str]]
    ) -> List[Tuple[Tuple[str, str], str, Decimal]]:
        """Confirmed holds, per (product, warehouse) and holding project.

        Ported from `project_allocation_service._holds` and narrowed by decision state,
        because a superseded revision must stop holding stock the moment it is superseded.
        """
        query = self._hold_query(product_ids, exclude_line_ids=exclude_line_ids)
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

    def _hold_query(
        self, product_ids: Sequence[str], *, exclude_line_ids: Optional[Sequence[str]]
    ):
        """The one predicate for "this allocation row is holding stock right now".

        A hold counts when its allocation belongs to no decision (every row written before
        Stage 1C) or to an ACTIVE one; the LINES being replaced (`exclude_line_ids`, project
        line ids) are excluded so their own previous revision does not compete with the one
        replacing it. By line and not by order, because a covered line the confirmation
        carries forward keeps its hold - the union is the server's - and un-netting it too
        offered a named sibling stock the order was still holding. Shared by the free-stock
        arithmetic and the donor-shortfall netting so the two cannot come to disagree about
        what is held.

        The hold is keyed by the CORE line's product when the mirror line has one, and by
        the mirror's own product only when it does not (`_hold_product`): free stock is
        read against the core product (`_facts_for` prefers it on a remap), and a hold
        keyed by the mirror's product would net out of the wrong pile.
        """
        query = (
            self.db.query(
                _hold_product,
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
                SalesOrderLine,
                SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id,
            )
            .outerjoin(
                SOSupplyDecision, SOSupplyDecision.id == SOLineAllocation.decision_id
            )
            .filter(
                _hold_product.in_(list(product_ids)),
                SOLineAllocation.confirmed_at.isnot(None),
                SOLineAllocation.warehouse_id.isnot(None),
                SOLineAllocation.source_type != ALLOC_SOURCE_ORDER,
                or_(
                    SOLineAllocation.decision_id.is_(None),
                    SOSupplyDecision.state == DECISION_ACTIVE,
                ),
            )
        )
        if exclude_line_ids:
            query = query.filter(
                SOLineAllocation.so_line_id.notin_(list(exclude_line_ids))
            )
        return query

    def _holds_from_elsewhere(
        self, pairs: Iterable[Tuple[str, str]], *, exclude_line_ids: Optional[Sequence[str]]
    ) -> Dict[Tuple[str, str], Decimal]:
        """What other confirmed decisions hold at each (product, warehouse) FROM ELSEWHERE.

        The holds `_pile_read`'s `SO qty` cannot see: a borrow or a pool take by a line
        whose OWN location (its core line's warehouse) is somewhere else. A hold by a line
        whose own location is this very pile is a Reserve at home, and that line's demand
        is already inside the pile's SO qty - counting the hold too would count it twice.
        """
        wanted = {(str(product_id), str(warehouse_id)) for product_id, warehouse_id in pairs}
        if not wanted:
            return {}
        rows = (
            self._hold_query(
                [product_id for product_id, _w in wanted],
                exclude_line_ids=exclude_line_ids,
            )
            .filter(
                SOLineAllocation.warehouse_id.in_([w for _p, w in wanted]),
                or_(
                    SalesOrderLine.warehouse_id.is_(None),
                    SalesOrderLine.warehouse_id != SOLineAllocation.warehouse_id,
                ),
            )
            .with_entities(
                _hold_product,
                SOLineAllocation.warehouse_id,
                func.coalesce(func.sum(SOLineAllocation.qty), 0),
            )
            .group_by(_hold_product, SOLineAllocation.warehouse_id)
            .all()
        )
        return {
            (str(product_id), str(warehouse_id)): _dec(qty)
            for product_id, warehouse_id, qty in rows
            if (str(product_id), str(warehouse_id)) in wanted
        }

    def _holds_by_project(
        self, product_ids: Iterable[str], *, exclude_line_ids: Optional[Sequence[str]]
    ) -> Dict[Tuple[str, str, str], Decimal]:
        out: Dict[Tuple[str, str, str], Decimal] = {}
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return out
        for (product_id, warehouse_id), project_id, qty in self._hold_rows(
            ids, exclude_line_ids=exclude_line_ids
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
    ) -> Tuple[set, set, set, Dict[str, List[str]], Dict[str, List[str]], set, set]:
        """PLAN 3.3's hot-selling predicate, per demand class, and the "no evidence" case.

        Amended 19 August 2026 (the captain): "you should do the demand over project classed
        demand to judge project hot selling, same for dealer" - hot-selling is read off the
        DEMAND CLASS the ABC figure was computed against (`abc_class_retail` for dealer,
        `abc_class_project` for project), not off the warehouse's own segment. The demand
        class already states who bought it, so a warehouse's segment plays no further part
        and `Warehouse.segment == DEALER_SEGMENT` is dropped. The ranking itself is BY
        QUANTITY delivered in that class, not by value ("hot selling is by quantity, not
        related to money") - unlike the reorder engine's own value-based `abc_class`, which
        this predicate does not read.

        `computed_at` is display evidence, never a freshness gate: the existing ABC facts
        are the test, and adding an age threshold would be a new knob this contract forbids.

        Returns the dealer-hot set, the project-hot set, the unclassified set, WHERE each hot
        verdict earned it - the locations holding it as ABC A by quantity on that demand
        class, by code and sorted - and finally the dealer-classified / project-classified
        sets: every product carrying a NON-NULL letter on that column ANYWHERE, hot or not.
        The captain, reading a trail that never mentioned it: "where is the consideration of
        dealer hot selling?" A bare boolean would be something to take on trust; "ABC A at
        BRW" is something to check. The classified sets are what a "Cold at retail" / "Cold
        at project" chip is told apart from "no evidence of that class at all" with - a
        product can carry a real, non-A letter and still not be hot.

        "Unclassified" means no NON-NULL letter in EITHER column, not merely "a row exists".
        A NULL letter means no DELIVERED demand of that class in the trailing-12mo window -
        "unknown", never a computed verdict of "not hot". Reading that as "seen, therefore
        cold" would print a false "Not dealer hot-selling" for an item nobody has actually
        judged, which is the whole book today: every row is NULL in both columns because
        nothing has been delivered against them yet.
        """
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return set(), set(), set(), {}, {}, set(), set()
        rows = (
            self.db.query(
                ItemClassification.product_id,
                ItemClassification.abc_class_project,
                ItemClassification.abc_class_retail,
                Warehouse.warehouse_code,
            )
            .join(Warehouse, Warehouse.id == ItemClassification.warehouse_id)
            .filter(
                ItemClassification.product_id.in_(ids),
                Warehouse.is_active.is_(True),
                Warehouse.counts_as_available.is_(True),
            )
            .all()
        )
        dealer_classified: set = set()
        project_classified: set = set()
        dealer_where: Dict[str, List[str]] = {}
        project_where: Dict[str, List[str]] = {}
        for product_id, abc_project, abc_retail, code in rows:
            pid = str(product_id)
            if abc_retail is not None:
                dealer_classified.add(pid)
            if abc_project is not None:
                project_classified.add(pid)
            if (abc_retail or "").upper() == "A":
                dealer_where.setdefault(pid, []).append(code or "")
            if (abc_project or "").upper() == "A":
                project_where.setdefault(pid, []).append(code or "")
        for codes in dealer_where.values():
            codes.sort()
        for codes in project_where.values():
            codes.sort()
        seen = dealer_classified | project_classified
        return (
            set(dealer_where),
            set(project_where),
            {pid for pid in ids if pid not in seen},
            dealer_where,
            project_where,
            dealer_classified,
            project_classified,
        )

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

    def _decided_elsewhere(self, exclude_line_ids: Optional[Sequence[str]]) -> set:
        """Core lines an ACTIVE decision covers, other than the ones being replaced.

        The carve-out matters as much as the rule. A line covered by a decision holds stock,
        and that hold is already out of `_free_stock`, so counting its demand again as ranked
        ahead would subtract the same units twice. But `_free_stock` EXCLUDES the lines being
        replaced - their own previous revision must not compete with the one replacing them -
        so for those lines the hold is NOT netted out, and they therefore have to stay in the
        queue. Miss this and re-confirming an order that reserved everything is refused as
        "nothing free for this line", which is what the sheet's own suite caught.

        By PROJECT LINE (`exclude_line_ids`), not by order: a covered line the confirmation
        carries forward keeps its hold, so it stays out of the queue like any other order's
        covered line, and only the named lines come back in.
        """
        rows = (
            self.db.query(
                SOSupplyDecision.project_sales_order_id, SOSupplyDecision.line_snapshots
            )
            .filter(SOSupplyDecision.state == DECISION_ACTIVE)
            .all()
        )
        replaced = {str(line_id) for line_id in (exclude_line_ids or [])}
        out: set = set()
        for _pso_id, snapshots in rows:
            for snapshot in snapshots or []:
                if str((snapshot or {}).get("project_line_id") or "") in replaced:
                    continue
                core_line_id = (snapshot or {}).get("core_line_id")
                if core_line_id:
                    out.add(str(core_line_id))
        return out

    def _pile_book(
        self,
        product_ids: Iterable[str],
        warehouse_ids: Iterable[str],
        *,
        exclude_line_ids: Optional[Sequence[str]] = None,
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """Every line still competing for each (product, location) pile, IN RANK ORDER.

        Ranked by the active `scm.priority_policy` - the one policy that also ranks the
        planning board and the loading plan - with sales-order number then line number then
        line id as the total tie-break, so the queue is reproducible.

        **Lines a confirmed decision already covers are excluded, and that is the
        double-count rule.** Such a line's claim on this pile is already expressed once, as a
        hold that `_free_stock` has taken out of the opening stock. Counting its outstanding
        quantity again as demand ranked ahead would subtract the same units twice and
        understate what is left for everybody behind it. The exception is the lines being
        replaced, whose own holds `_free_stock` deliberately does not net - see
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
        decided = self._decided_elsewhere(exclude_line_ids)
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

        for lines in grouped.values():
            self._rank_pile(lines, weights=weights, class_weights=class_weights)
        return grouped

    def _rank_pile(
        self,
        lines: List[Dict[str, Any]],
        *,
        weights: Dict[str, Any],
        class_weights: Dict[str, Any],
    ) -> None:
        """Score and sort ONE pile's lines in place, in the active policy's order.

        The one ranking rule for a pile, so the queue the sheet and the board serve stock
        down (`_pile_book`) and the queue a pool draw is measured against (`pool_claims`)
        cannot disagree about who is ahead. Each line states `line_id` (its ranking key),
        `required_date`, `order_date`, `payment_terms_days`, `demand_class`, `so_number`
        and `line_no`; scores are normalised across the lines passed in.

        Score first, then PLAN 3.5's own order as the tie-break: required date (missing
        last), sales-order number, line number, line id. The tie-break is load-bearing
        rather than decorative - a database with no policy configured scores every demand
        row 0.0 (the default weights name only `po_document_sequence`, which no
        sales-order line has), and without the date here the queue for a scarce pile
        would be alphabetical by sales-order number.
        """
        factors = priority.factors_for_demand_rows(
            self.db,
            [
                {
                    "row_key": line["line_id"],
                    "required_date": line.get("required_date"),
                    "order_date": line.get("order_date"),
                    "payment_terms_days": line.get("payment_terms_days"),
                    "demand_class": line.get("demand_class"),
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
        lines.sort(key=_pile_order)

    def pile_book(
        self,
        product_id: str,
        warehouse_id: str,
        *,
        exclude_line_ids: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """The queue at ONE pile, in the active policy's order. The read behind the screen.

        Public because the captain asked to see it - "I need to know what is ahead of me to have
        the visibility, and why they are ahead of me, meaning I need to know their rank also" -
        and it is `_pile_book` itself rather than a second query shaped like it: a queue drawn a
        second way would eventually disagree with the one the proposal was computed from, and
        then the screen would be arguing with the plan.
        """
        book = self._pile_book(
            [product_id], [warehouse_id], exclude_line_ids=exclude_line_ids
        )
        return book.get((str(product_id), str(warehouse_id)), [])

    def pool_claims(
        self,
        product_ids: Iterable[str],
        pool_ids: Iterable[str],
        members: Sequence[Dict[str, Any]],
        *,
        exclude_line_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """What a shared pool's OWN book claims ahead of each line that would draw on it.

        The pool is a pile like any other: the lines fulfilled directly from it want it too,
        and a member location's shortfall queues behind whichever of them the policy ranks
        first. Without this a pool draw promised stock the pool's own outstanding orders had
        already been sold - the same defect as the own-location one, one location along.

        `members` are the lines asking, each stating `key`, `product_id`, `pool_id`,
        `required_date`, `order_date`, `payment_terms_days`, `demand_class`, `so_number` and
        `line_no`, and - when the member IS a core line - its `line_id`. Returns, per member
        key, the quantity ranked ahead (`qty`) and how many of the pool's lines that is
        (`lines`) - the count travels with the sum because the trail prints both ("BRW's own
        orders ranked ahead of this line claim 1").

        A member fulfilled from the pool itself (a bare site code is its own pool, migration
        311) is IN the pool's book, and must not be counted ahead of itself: it is one line
        with two keys here, and reading it as a rival took its own quantity out of what it
        could then draw. `line_id` is what excludes it.
        """
        book = self._pile_book(product_ids, pool_ids, exclude_line_ids=exclude_line_ids)
        if not members:
            return {}
        weights, class_weights = priority.policy_weights(priority.active_policy(self.db))
        out: Dict[str, Dict[str, Any]] = {}
        by_pile: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for member in members:
            key = (str(member["product_id"]), str(member["pool_id"]))
            by_pile.setdefault(key, []).append(member)

        for key, asking in by_pile.items():
            # The askers are put INTO the pool's queue and ranked by the one rule the queue
            # itself is ranked by (`_rank_pile`), so "ahead" means exactly what the queue
            # screen shows: score, then required date, then sales-order number and line.
            everyone = [dict(line) for line in book.get(key, [])] + [
                {
                    "line_id": str(member["key"]),
                    "so_number": member.get("so_number") or "",
                    "line_no": member.get("line_no"),
                    "open_qty": _ZERO,
                    "required_date": member.get("required_date"),
                    "order_date": member.get("order_date"),
                    "payment_terms_days": member.get("payment_terms_days"),
                    "demand_class": member.get("demand_class"),
                    "asker": True,
                }
                for member in asking
            ]
            self._rank_pile(everyone, weights=weights, class_weights=class_weights)
            for member in asking:
                own_line_id = str(member["line_id"]) if member.get("line_id") else None
                ahead: List[Dict[str, Any]] = []
                for line in everyone:
                    if line.get("asker"):
                        if line["line_id"] == str(member["key"]):
                            break
                        continue
                    if line["line_id"] == own_line_id:
                        continue
                    ahead.append(line)
                out[str(member["key"])] = {
                    "qty": sum((line["open_qty"] for line in ahead), _ZERO),
                    "lines": len(ahead),
                }
        return out

    def _attribution(
        self,
        product_ids: Iterable[str],
        warehouse_ids: Iterable[str],
        warehouses: Dict[str, Warehouse],
        spo: Dict[Tuple[str, str], List[_SpoRow]],
        exclude_line_ids: Optional[Sequence[str]] = None,
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
            product_ids, warehouse_ids, exclude_line_ids=exclude_line_ids
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

        free_index, holds_index = self._by_product()
        free_here = free_index.get(fact.product_id, {})
        holds_here = holds_index.get(fact.product_id, {})
        committed_at: Dict[str, Decimal] = {}
        for (held_warehouse, _project), qty in holds_here.items():
            committed_at[held_warehouse] = committed_at.get(held_warehouse, _ZERO) + qty
        warehouse_ids = [
            warehouse_id
            for warehouse_id, qty in free_here.items()
            if qty > _ZERO and warehouse_id not in inside
        ]
        warehouses = self._warehouses(warehouse_ids)
        for warehouse_id in sorted(warehouse_ids):
            warehouse = warehouses.get(warehouse_id)
            if warehouse is None:
                continue
            free = free_here[warehouse_id]
            committed = committed_at.get(warehouse_id, _ZERO)
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
            for (warehouse_id, project_id), qty in holds_here.items()
            # `project_id` empty means an adopted order holds it and there is no project to
            # name as the donor. Offering it would be offering a Borrow that cannot be
            # confirmed, so it is not offered - the stock stays netted out of free either way.
            if qty > _ZERO and project_id
        ]
        if holds:
            projects = self._projects([project_id for _w, project_id, _q in holds])
            donor_warehouses = self._warehouses([w for w, _p, _q in holds])
            for warehouse_id, project_id, qty in sorted(holds):
                warehouse = donor_warehouses.get(warehouse_id)
                donor = projects.get(project_id)
                if warehouse is None or donor is None:
                    continue
                free = free_here.get(warehouse_id, _ZERO)
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
