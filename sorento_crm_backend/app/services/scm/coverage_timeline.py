"""Coverage Timeline: the dated running balance, and where a demand line's stock comes from.

PURE maths, no I/O, golden-testable in isolation - the same discipline as
``reorder_engine``'s top half and ``cash_ranking``.

Two things live here.

**1. The dated running balance.** Every dated event (opening on hand, each committed demand
line at its required date, each open supply line at its expected date) sorted by date and
accumulated. The first event that pushes the balance below the floor is the shortfall, and
that event's date is the need-by date.

There are deliberately NO time buckets in the arithmetic. Months are a display grouping
only (`group_by_month`). Aggregating a month would let supply arriving on the 25th cover
demand due on the 3rd, so the report would understate shortfall - the one class of error
that destroys trust in a planning tool in week one. See ADR-0011.

**Why this does not endanger the M3 golden set.** The blessed goldens cover the pure
formulae (`safety_stock`, `reorder_point`, `order_up_to`, `trigger`, `order_qty`) and feed
them plain values. Those functions are untouched. What changes is where `net` comes from:
`closing_balance` over a timeline is arithmetically identical to
``on_hand + on_order - committed`` when every event shares one date, which is exactly the
continuous-replenishment case. So ROP is the one-bucket degenerate case of this, and the
parity is structural rather than coincidental.

**2. Source resolution.** A shortage is not automatically a purchase. A demand line is
covered from its own reserved bin, then the shared pool at the same site, then another
holder's bin (which needs their agreement), and only then bought. Those four are the
existing ``so_line_allocations.source_type`` values, reused rather than reinvented.

The case that forced this: item SRTWT7408 carries demand of 67 against customer bins while
4,397 sit in the BRW pool. Netting per warehouse reports a shortfall and recommends buying
67 units of an item holding 4,397 - on the first row of the first report anyone reads.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional, Sequence

# --------------------------------------------------------------------------- #
# event kinds and source types
# --------------------------------------------------------------------------- #

# The one threshold that governs BOTH the shortfall trigger and the reported figure.
# They used to differ: the trigger was 1e-9 while the quantity was rounded to 4 decimals,
# so any gap in (1e-9, 5e-5) reported "Short 0" beside a peak deficit of 0 and the hint
# "never goes short". Since the floor is a computed reorder point (12369.655534 in the
# fixtures), that window is reachable. Rounding first, then comparing on the SAME
# precision, is what makes the two figures agree by construction.
QTY_PRECISION = 4
EPSILON = 10 ** -QTY_PRECISION / 2

OPENING = "opening"
DEMAND = "demand"
SUPPLY = "supply"

# Mirrors so_line_allocations.source_type in the project-sales work. Do NOT invent a
# parallel vocabulary: one of these strings ends up persisted on the allocation.
SOURCE_OWN = "own"
SOURCE_POOL = "brw"
SOURCE_OTHER = "other_project"
SOURCE_ORDER = "order"

# Incoming stock is the SPO allocation against a shipment, and it is the ONLY supply the
# balance counts (decision, 6 Aug 2026). `SUPPLY_ON_ORDER` is no longer emitted by any
# producer: a purchase order is an order placed, not stock on the water, so its quantity is
# reported beside the timeline (`Coverage.qty_ordered_not_incoming`) and never on it. The
# constant stays because persisted rows and API consumers still carry the string.
SUPPLY_ON_ORDER = "on_order"
SUPPLY_IN_TRANSIT = "in_transit"


@dataclass(frozen=True)
class TimelineEvent:
    """One dated movement. ``qty`` is signed: negative consumes, positive replenishes."""

    at: Optional[date]          # None only for the opening balance
    qty: float
    kind: str                   # opening | demand | supply
    ref: str = ""               # document number, shown on screen. Never a UUID.
    label: str = ""             # human context: project or customer or supplier
    location: str = ""          # the bin or pool the movement sits in
    supply_stage: Optional[str] = None   # in_transit, for SUPPLY only (see above)
    # The last two keys of PLAN-scm-front-planning.md 3.5's ordering. `line_no` is the
    # human line number on the document (missing sorts last); `line_id` is the internal
    # SO-line id, a final stable key that is NEVER displayed - two rows agreeing on
    # everything a person can see still have to sort the same way on every run.
    line_no: Optional[int] = None
    line_id: Optional[str] = None


@dataclass(frozen=True)
class TimelineRow:
    event: TimelineEvent
    balance: float


@dataclass(frozen=True)
class Shortfall:
    """The first point the balance falls below the floor.

    Carries a date as well as a quantity because a quantity alone cannot be acted on:
    buying it late is indistinguishable from not buying it.
    """

    at: Optional[date]
    qty: float                  # how much is missing at that point, positive
    ref: str                    # the document that tipped it
    label: str = ""


@dataclass(frozen=True)
class TimelineResult:
    rows: list[TimelineRow]
    closing_balance: float
    shortfall: Optional[Shortfall]
    # The worst the balance ever gets, which is what has to be covered. Distinct from the
    # first shortfall's own gap: a later event can dig deeper, and buying only the first
    # gap would leave the plan short a second time.
    peak_deficit: float
    # How many events fell beyond the horizon and are therefore absent from `rows`. An
    # omission a screen does not mention reads as data that is not there, so the count
    # travels with the result rather than the caller having to re-derive it.
    excluded_event_count: int = 0


def _sort_key(e: TimelineEvent) -> tuple:
    """PLAN-scm-front-planning.md 3.5's ordering, and the ONLY one any consumer uses.

    Date, then kind with SUPPLY BEFORE DEMAND, then SO number, then line number with
    missing numbers last, then the internal line id as a final stable key.

    Supply-first on a same-day tie is Stage 1C's deliberate reversal of the earlier
    demand-first order. Incoming SPO is dated location supply, and an SPO arriving on a
    line's required date "counts at that date" (Q2): a container that clears and is put
    away in the morning covers a despatch due the same day, and treating the despatch as
    though the stock never arrived reports a shortfall that does not exist. There is one
    ordering contract - the reorder engine, the Coverage Timeline panel, plan exceptions
    and the coverage routes all inherit this, with no per-consumer divergence.
    """
    return (
        e.at or date.min,
        0 if e.kind == OPENING else (1 if e.kind == SUPPLY else 2),
        e.ref,
        e.line_no is None,
        e.line_no if e.line_no is not None else 0,
        e.line_id or "",
    )


def build_timeline(
    opening: float,
    events: Iterable[TimelineEvent],
    *,
    floor: float = 0.0,
    horizon_end: Optional[date] = None,
) -> TimelineResult:
    """Accumulate dated events into a running balance and find the first shortfall.

    ``floor`` is the level the balance must not fall below - 0 for project demand, or the
    reorder point for a continuous SKU, which is what makes ROP the one-bucket case.

    ``horizon_end`` drops events beyond the planning horizon. Excluded events are absent
    from ``rows`` but COUNTED into ``excluded_event_count``: a bound is necessary (a
    ten-year tail makes the report unreadable) and the count is what keeps it honest,
    because a planner who cannot see that nine years of demand was dropped reads the
    visible shortfall as the whole picture.
    """
    kept: list[TimelineEvent] = []
    excluded = 0
    for e in events:
        if horizon_end is not None and e.at is not None and e.at > horizon_end:
            excluded += 1
            continue
        kept.append(e)
    ordered = sorted(kept, key=_sort_key)

    rows: list[TimelineRow] = [
        TimelineRow(
            event=TimelineEvent(at=None, qty=0.0, kind=OPENING, ref="", label="opening on hand"),
            balance=float(opening),
        )
    ]
    balance = float(opening)
    shortfall: Optional[Shortfall] = None
    peak_deficit = max(0.0, floor - balance)
    # Stock ALREADY under the floor is a shortfall, and the most urgent kind: it is short
    # now rather than on some future date. Seeding only `peak_deficit` from it left the two
    # figures disagreeing about whether anything was wrong, and a screen that prints
    # "nothing is short" beside a non-zero deficit gets believed over the number.
    # `at` stays None because no event caused it and the opening balance carries no date;
    # stamping today would assert a fact the data does not hold.
    peak_deficit = round(peak_deficit, QTY_PRECISION)
    if peak_deficit >= EPSILON:
        shortfall = Shortfall(
            at=None, qty=peak_deficit, ref="", label="opening on hand"
        )

    for e in ordered:
        balance += float(e.qty)
        rows.append(TimelineRow(event=e, balance=balance))
        gap = round(floor - balance, QTY_PRECISION)
        if gap >= EPSILON:
            if shortfall is None:
                shortfall = Shortfall(at=e.at, qty=gap, ref=e.ref, label=e.label)
            peak_deficit = max(peak_deficit, gap)

    return TimelineResult(
        rows=rows,
        closing_balance=round(balance, 4),
        shortfall=shortfall,
        peak_deficit=peak_deficit,
        excluded_event_count=excluded,
    )


def closing_balance(opening: float, events: Iterable[TimelineEvent]) -> float:
    """The dateless net position, expressed through the timeline.

    This is the bridge that makes ROP the one-bucket case: with every event on one date
    this returns exactly ``on_hand + on_order - committed``, which is what
    ``scm.net_position_v`` computes and what `trigger` and `order_qty` already consume.
    Those formulae are therefore untouched by the date axis.
    """
    return build_timeline(opening, events).closing_balance


def group_by_month(rows: Sequence[TimelineRow]) -> list[tuple[Optional[str], list[TimelineRow]]]:
    """Group rows under month headings for display. Presentation only.

    Changing the grouping cannot change a balance, which is the property that makes the
    no-buckets decision safe to render as if it had buckets.
    """
    out: list[tuple[Optional[str], list[TimelineRow]]] = []
    for key, grp in itertools.groupby(
        rows, key=lambda r: r.event.at.strftime("%Y-%m") if r.event.at else None
    ):
        out.append((key, list(grp)))
    return out


# --------------------------------------------------------------------------- #
# source resolution: a shortage is not automatically a purchase
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SourceAvailability:
    """What could cover a demand line, by source, at the moment of asking.

    Computed live and never stored: a snapshot of somebody else's on-hand is stale the
    moment they ship, and acting on a stale figure is the failure this exists to prevent.
    """

    own: float = 0.0                     # the line's own reserved bin
    pool: float = 0.0                    # shared pool at the SAME site
    other: float = 0.0                   # other holders' bins, needs their agreement
    pool_location: str = ""
    other_locations: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceAllocation:
    source_type: str
    qty: float
    location: str = ""
    needs_claim: bool = False


def resolve_sources(
    demand_qty: float,
    availability: SourceAvailability,
    *,
    allow_borrow: bool = True,
) -> list[SourceAllocation]:
    """Cover a demand quantity from the cheapest source outward.

    Order is own bin, then same-site pool, then another holder's bin behind a claim, then
    buy. Only the last needs a quantity and a supplier, which is the whole point: treating
    "buy" as the only answer to a shortage is what would recommend purchasing an item that
    is already sitting in the pool.

    ``allow_borrow=False`` skips the claim step for callers that will not chase another
    holder - the remainder becomes a purchase instead, which is a slower but honest answer.

    A cross-site pool is deliberately NOT a source. Stock at another site is real but needs
    a physical movement with a cost and a lead time, so covering from it is a separate
    proposal a person accepts, never a silent netting.
    """
    remaining = max(0.0, float(demand_qty))
    out: list[SourceAllocation] = []

    for qty_available, source_type, location, needs_claim in (
        (availability.own, SOURCE_OWN, "", False),
        (availability.pool, SOURCE_POOL, availability.pool_location, False),
        (availability.other if allow_borrow else 0.0, SOURCE_OTHER,
         ", ".join(availability.other_locations), True),
    ):
        if remaining <= 1e-9:
            break
        take = min(remaining, max(0.0, float(qty_available)))
        if take <= 1e-9:
            continue
        out.append(
            SourceAllocation(
                source_type=source_type,
                qty=round(take, 4),
                location=location,
                needs_claim=needs_claim,
            )
        )
        remaining -= take

    if remaining > 1e-9:
        out.append(SourceAllocation(source_type=SOURCE_ORDER, qty=round(remaining, 4)))

    return out


def buy_quantity(allocations: Sequence[SourceAllocation]) -> float:
    """How much of a resolved demand actually has to be bought. Zero means use stock."""
    return round(sum(a.qty for a in allocations if a.source_type == SOURCE_ORDER), 4)


def is_use_stock(allocations: Sequence[SourceAllocation]) -> bool:
    """True when existing stock covers the whole line, i.e. Mr Loo's "BRW" answer."""
    return buy_quantity(allocations) <= 1e-9
