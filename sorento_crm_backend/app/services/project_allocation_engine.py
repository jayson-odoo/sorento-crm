"""Ranking the sources a sales order line can be filled from (P9, AC-H1 and AC-H2).

Pure arithmetic over rows somebody else read. No session, no clock, no writes: hand it the
live stock rows and the live project holds and it answers "where can this line come from,
best first". That separation is the design, not tidiness. Ranked candidates are computed on
EVERY request and never stored, because a stored snapshot of another project's on-hand goes
stale the moment they ship, and acting on a stale figure is exactly the failure this slice
exists to prevent. What lands in the database is the DECISION.

Four source types, in the order the client reads them:

* ``brw`` - the master location, BRW-BB. Identified by warehouse CODE, resolved by the
  caller, because the four sites each run a ``-BB`` bin (BRW-BB, DC1-BB, MWH-BB, WH3-BB)
  and only the Bukit Raja one is the master.
* ``own`` - stock this project may take without asking anybody. That is its own location
  first (a warehouse where this project already holds confirmed stock, flagged
  ``is_project_location``), then any other location whose stock is spoken for by nobody.
  Both are the same DECISION when stamped, which is why they share the type.
* ``other_project`` - physically present, held for someone else. Offered so a person can
  see it and ASK, never planned: taking it needs that project's CS to accept a claim.
* ``order`` - the honest fourth option. It carries no warehouse, which is what makes it
  different from a location that happens to hold zero.

``plan`` is what happens if the proposal is accepted as-is: a greedy fill in rank order
over what is genuinely free. It deliberately excludes every ``other_project`` holding, so
a proposal can never quietly spend stock nobody has agreed to release.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

_ZERO = Decimal("0")

SOURCE_BRW = "brw"
SOURCE_OWN = "own"
SOURCE_OTHER_PROJECT = "other_project"
SOURCE_ORDER = "order"

# Rank buckets, in the order AC-H1 names them.
_BUCKET = {SOURCE_BRW: 0, SOURCE_OWN: 1, SOURCE_OTHER_PROJECT: 2, SOURCE_ORDER: 3}


@dataclass(frozen=True)
class LineNeed:
    """The line being sourced: what, how much, and for whom."""

    line_id: str
    product_id: str
    project_id: str
    qty: Decimal


@dataclass(frozen=True)
class StockRow:
    """One live `stock` row for this product, already scoped to a sellable warehouse."""

    warehouse_id: str
    warehouse_code: str
    warehouse_name: Optional[str]
    on_hand: Decimal
    reserved: Decimal


@dataclass(frozen=True)
class ProjectHold:
    """Stock at a warehouse already confirmed to a project, with the CS who owns it."""

    warehouse_id: str
    project_id: str
    project_code: str
    project_title: Optional[str]
    cs_user_id: Optional[str]
    cs_name: Optional[str]
    qty: Decimal


@dataclass(frozen=True)
class Candidate:
    """One place the line could come from, with the figures a person decides on."""

    rank: int
    source_type: str
    warehouse_id: Optional[str]
    warehouse_code: Optional[str]
    warehouse_name: Optional[str]
    on_hand: Decimal
    reserved: Decimal
    held_for_this_project: Decimal
    held_for_other_projects: Decimal
    #: Everything spoken for: the core reservation plus every project's hold but ours.
    committed: Decimal
    available: Decimal
    #: How much of the need this candidate can cover on its own, without asking anybody.
    allocatable: Decimal
    #: How much could be ASKED for, when the stock is held by another project.
    claimable: Decimal
    requires_claim: bool
    #: True when this project already holds confirmed stock here.
    is_project_location: bool
    holders: List[ProjectHold] = field(default_factory=list)


@dataclass(frozen=True)
class RankedSources:
    """The answer for one line."""

    line_id: str
    qty: Decimal
    candidates: List[Candidate]
    #: Greedy fill over free stock, in rank order, as (warehouse_id, qty).
    plan: List[Tuple[str, Decimal]]
    shortfall: Decimal
    covered: bool


def _sum(values) -> Decimal:
    total = _ZERO
    for value in values:
        total += value
    return total


def _floor_zero(value: Decimal) -> Decimal:
    return value if value > _ZERO else _ZERO


def rank_sources(
    line: LineNeed,
    *,
    stock_rows: Sequence[StockRow],
    holds: Sequence[ProjectHold],
    brw_warehouse_id: Optional[str],
) -> RankedSources:
    """Rank every source for one line. Pure: same inputs, same answer, every time."""
    needed = _floor_zero(line.qty)

    holds_by_warehouse: dict[str, List[ProjectHold]] = {}
    for hold in holds:
        if hold.qty <= _ZERO:
            continue
        holds_by_warehouse.setdefault(hold.warehouse_id, []).append(hold)

    # A warehouse with no stock row can still matter: it may hold nothing free while a
    # project holds a pile there, which is the case a claim exists for.
    warehouse_ids = {row.warehouse_id for row in stock_rows} | set(holds_by_warehouse)
    rows_by_warehouse = {row.warehouse_id: row for row in stock_rows}

    scored: List[Candidate] = []
    for warehouse_id in warehouse_ids:
        row = rows_by_warehouse.get(warehouse_id)
        warehouse_holds = holds_by_warehouse.get(warehouse_id, [])
        mine = _sum(h.qty for h in warehouse_holds if h.project_id == line.project_id)
        theirs = _sum(h.qty for h in warehouse_holds if h.project_id != line.project_id)
        others = [h for h in warehouse_holds if h.project_id != line.project_id]

        on_hand = row.on_hand if row else _ZERO
        reserved = row.reserved if row else _ZERO
        if on_hand <= _ZERO and not warehouse_holds:
            # A location holding nothing and owing nothing is noise on a 99 line order.
            continue

        # Our own hold is not a commitment AGAINST us, so it is not netted off.
        committed = reserved + theirs
        available = _floor_zero(on_hand - committed)

        if warehouse_id == brw_warehouse_id:
            source_type = SOURCE_BRW
        elif others and mine <= _ZERO:
            source_type = SOURCE_OTHER_PROJECT
        else:
            source_type = SOURCE_OWN

        scored.append(
            Candidate(
                rank=0,  # assigned once the whole list is ordered
                source_type=source_type,
                warehouse_id=warehouse_id,
                warehouse_code=row.warehouse_code if row else None,
                warehouse_name=row.warehouse_name if row else None,
                on_hand=on_hand,
                reserved=reserved,
                held_for_this_project=mine,
                held_for_other_projects=theirs,
                committed=committed,
                available=available,
                allocatable=min(available, needed),
                claimable=min(theirs, needed) if others else _ZERO,
                requires_claim=bool(others) and available < needed,
                is_project_location=mine > _ZERO,
                holders=sorted(others, key=lambda h: h.project_code),
            )
        )

    def _order(candidate: Candidate) -> tuple:
        return (
            _BUCKET[candidate.source_type],
            # Inside `own`, the project's OWN location comes before free stock elsewhere.
            0 if candidate.is_project_location else 1,
            -candidate.available,
            candidate.warehouse_code or "",
        )

    scored.sort(key=_order)

    # The proposal: greedy over free stock only. Held stock is never spent on silence.
    plan: List[Tuple[str, Decimal]] = []
    remaining = needed
    for candidate in scored:
        if remaining <= _ZERO:
            break
        take = min(candidate.available, remaining)
        if take <= _ZERO:
            continue
        plan.append((candidate.warehouse_id or "", take))
        remaining -= take

    shortfall = _floor_zero(remaining)
    scored.append(
        Candidate(
            rank=0,
            source_type=SOURCE_ORDER,
            warehouse_id=None,
            warehouse_code=None,
            warehouse_name=None,
            on_hand=_ZERO,
            reserved=_ZERO,
            held_for_this_project=_ZERO,
            held_for_other_projects=_ZERO,
            committed=_ZERO,
            available=_ZERO,
            allocatable=shortfall,
            claimable=_ZERO,
            requires_claim=False,
            is_project_location=False,
            holders=[],
        )
    )

    ranked = [
        Candidate(**{**candidate.__dict__, "rank": index + 1})
        for index, candidate in enumerate(scored)
    ]

    return RankedSources(
        line_id=line.line_id,
        qty=needed,
        candidates=ranked,
        plan=plan,
        shortfall=shortfall,
        covered=shortfall <= _ZERO,
    )
