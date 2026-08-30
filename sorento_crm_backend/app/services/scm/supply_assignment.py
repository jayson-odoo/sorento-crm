"""Who gets what, and what is left over: one product's supply assigned to its demand.

PURE maths, no I/O, golden-tested in isolation - the same discipline `coverage_timeline`
keeps. Months are a DISPLAY grouping of dated arithmetic (ADR-0011): no quantity is ever
netted inside a bucket, so supply arriving on the 25th cannot cover demand due on the 3rd.

**A month states its own month, and nothing else** (R37, 30 Aug 2026). What is debted in
August stays in August. The balance of month M is the supply DATED IN M that is still free
when the whole walk is over, minus, for each line due in M, what that line was short AT ITS
OWN DATE. A running balance was carried before, and it read as a fresh debt every month
after: `1/2" ULTRA CIRCULAR` printed -4 in August and -4 again in every later column, while
the drill for those columns was empty, because the cell was an accumulation and the drill
was a month. A line that later supply clears (`late`) still books its shortfall in its own
month - it went without on its own date, and that is the fact a planner acts on - and the
supply that cleared it is no longer free, so it is never counted a second time.

**The question.** "Is this product short, when, and whose order is the one that goes
without?" The balance alone answers the first two; the assignment answers the third, and
that is the one a planner acts on. The Stock Debt view (S2) prints both; the ladder (S3/S4)
reads the same answer so the board and the view can never disagree about what is free.

**The walk** (`PLAN-scm-borrow-ladder-v7-stock-debt.md` 3.1, rulings R14 / R21 / R24 / R31).

1. **Pinned holds bind first, at any date, and PINNED MEANS PINNED** (R21, AC-S2-1b). A
   confirmed decision or a placement link is a promise already made; re-deciding it every
   time somebody opens a screen is what pinning exists to prevent. The pinned quantity
   leaves the pile before anybody queues for it - and when the supply it names is OUTSIDE
   this call's span (a site pool, a bin flagged out of planning, another group when the
   caller narrowed with `group=`), the hold is honoured anyway, off the bin the hold itself
   names. The hold IS the supply: somebody confirmed it against real stock, and dropping it
   because the reader narrowed the question printed a board-covered line as `short`.
2. **Then ONE chronological walk, with a pile per ownership group.** The group is the
   warehouse code's suffix (`BRW-BB` -> `BB`), which is the pile ladder v4 nets
   (`group_netting`); the site pools are one further group of their own, because a pool is
   reached through `pool_warehouse_id` and is nobody's ownership group.
   Supply lands in ITS OWN group's free pile at its arrival date. A demand line, at its
   date, draws from its own group's pile oldest-first, and then - ladder step 1, PLAN 3.2 -
   from the OTHER PROJECT groups' free piles, oldest first. Free means owed to nobody, so
   using it raises no debt and needs no borrow. A SITE POOL never covers a project line and
   a project group never covers a pool line: the pool is walked by its own rung (R34), which
   does raise a debt. One walk rather than a walk per group is the whole point - per-group
   walks hid a cross-group shortfall, so the product-wide month balance said green while the
   drill said `short`.
   What a line cannot draw is an OPEN SHORTFALL, and the next supply to arrive clears open
   shortfalls (its own group first, then the other project groups, earliest required date
   within each) BEFORE it becomes free for a later line - which is what makes this
   first-come by REQUIRED DATE rather than by arrival, and it is the case AC-S2-1 pins.
3. **A past-due line is read at today.** Its date has gone; a column for a month that has
   gone is a column nobody can act in. So it queues at `as_of` (ahead of everything dated
   later) and its debt lands in the CURRENT month (AC-S2-5).
4. **Unlocated, TBA and undated lines draw nothing** (R14). A line with no warehouse cannot
   be sourced at all, a line dated on or after the policy's `tba_date_from` is a placeholder
   and a line with no date states nothing, so none of them may take stock a dated, located
   line will need. Their whole quantity is debt, in their own bucket. Unlocated is tested
   FIRST: no location is a fact about what can be done, and it holds whatever the date says.
5. **Overdue incoming counts as nothing** (R31). A document whose arrival has passed with
   nothing received is not supply until somebody re-dates it. It is RETURNED (`uncounted`)
   rather than dropped: a document nobody mentions reads as a document that is not there,
   and chasing it is the action the screen exists to prompt. Undated incoming is uncounted
   for the same reason from the other side - there is no date to place it on.

**Status.** `short` when anything is left uncovered, `pinned` when a decision holds it,
`late` when what covers it arrives after its date, `covered` otherwise. Short outranks late
because a line half covered late is still a line that goes without.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.scm.coverage_timeline import QTY_PRECISION

#: Quantities below this are noise from Decimal -> float, never a real shortfall.
EPSILON = 10 ** -QTY_PRECISION / 2

KIND_ON_HAND = "on_hand"
KIND_SPO = "spo"
KIND_PO = "po"

STATUS_COVERED = "covered"
STATUS_LATE = "late"
STATUS_SHORT = "short"
STATUS_PINNED = "pinned"

TONE_RED = "red"
TONE_AMBER = "amber"
TONE_GREEN = "green"

#: The three buckets that are not months. They are keys the FE addresses a cell by, so they
#: are strings beside `YYYY-MM` rather than a second field nobody would render.
BUCKET_TBA = "tba"
BUCKET_UNDATED = "undated"
#: A sales-order line with no warehouse on it. 2,312 open lines over 427 products on the
#: 30 Aug dev copy - counted rather than silently dropped, because a screen that lists what
#: is owed and quietly omits a tenth of it is worse than one that says "somebody has to give
#: these a location".
BUCKET_UNLOCATED = "unlocated"

#: The ownership group the site pools share. A pool carries no group suffix of its own
#: (`BRW`, `MWH`), and reading one as a group would let a `-BB` line eat the pool silently.
POOL_GROUP = "__pool__"


def _group_of(warehouse: Optional[str], is_pool: bool) -> str:
    """The ownership group a location belongs to, in ONE spelling.

    Delegates to `group_netting.group_of_warehouse_code` (which delegates to
    `sales_agent_service`) rather than restating the suffix rule, so the pile this module
    walks and the pile ladder v4 nets can never come to disagree about what `BRW-BB` is.
    Imported inside the function to keep this module importable with nothing behind it.
    """
    if is_pool:
        return POOL_GROUP
    from app.services.scm.group_netting import group_of_warehouse_code

    return group_of_warehouse_code(warehouse) or ""


@dataclass(frozen=True)
class SupplyEvent:
    """One dated quantity that could cover something.

    `key` is this module's identity for the event and the string a `Hold` names: the SPO
    allocation id, the PO line id, or `on_hand:<warehouse id>`. `ref` is what a person
    reads (`SPO 2026/09-0088`); `bought_for` is a PO line's `expected_date`, which is the
    SO delivery date the line was TYPED against and never an arrival (R29) - carried for
    display and read by nothing here (R30).
    """

    key: str
    kind: str
    warehouse: Optional[str]
    at: Optional[date]
    qty: float
    ref: Optional[str] = None
    bought_for: Optional[date] = None
    is_pool: bool = False


@dataclass(frozen=True)
class DemandLine:
    """One open sales-order line, at the location it is booked in."""

    key: str
    so_number: str
    line_no: Optional[int]
    warehouse: Optional[str]
    agent_code: Optional[str]
    required_date: Optional[date]
    open_qty: float
    is_pool: bool = False


@dataclass(frozen=True)
class Hold:
    """A decision or a placement link, binding a quantity of one event to one line.

    `kind` / `warehouse` / `ref` describe the supply the hold NAMES, and they are read only
    when that supply is absent from this call's span (AC-S2-1b): the walk then stands an
    event of its own up from them, so the drill can still say `On hand BRW` or `SPO ...`
    rather than leaving a pinned line looking unsourced. When the event IS in the span they
    are ignored - the real one is better than a description of it.
    """

    line_key: str
    supply_key: str
    qty: float
    kind: str = KIND_ON_HAND
    warehouse: Optional[str] = None
    ref: Optional[str] = None


@dataclass(frozen=True)
class Assigned:
    event: SupplyEvent
    qty: float
    #: True when the hold was pinned rather than queued for.
    pinned: bool = False


@dataclass(frozen=True)
class LineResult:
    line: DemandLine
    assigned: Tuple[Assigned, ...]
    uncovered: float
    status: str
    #: `YYYY-MM`, `tba` or `undated` - the cell this line is drilled from.
    bucket: str
    #: What the line was short ON ITS OWN DATE - open qty less what it could draw from the
    #: supply available by then. This is the figure its month books (R37), and it differs
    #: from `uncovered` for a `late` line: later supply cleared it, so it ends covered, but
    #: it still went without on the date it was promised. A TBA / undated / unlocated line
    #: draws nothing at all, so its whole quantity is short.
    short_at_date: float = 0.0


@dataclass(frozen=True)
class MonthBalance:
    """One month, on its own: free supply dated in it, less the shortfalls it books (R37)."""

    key: str
    balance: float
    tone: str


@dataclass(frozen=True)
class Assignment:
    lines: Tuple[LineResult, ...]
    months: Tuple[MonthBalance, ...]
    #: Event key -> quantity nobody took, once the whole walk is over. The other half of a
    #: month's balance (R37), and the number the drill prints beside a supply row, so a
    #: reader can add the lightbox up and get the cell they pressed.
    free: Dict[str, float]
    #: Signed totals: demand that draws nothing is debt, so all three are <= 0.
    tba: float
    undated: float
    #: Demand booked with no warehouse at all. It cannot be sourced and it is not in any
    #: group's pile, so it is stated on its own rather than netted into a month.
    unlocated: float
    #: Supply that contributed nothing - overdue, or with no arrival date at all (R31).
    uncounted: Tuple[SupplyEvent, ...]


@dataclass
class _Open:
    """A line's mutable state during the walk."""

    line: DemandLine
    remaining: float
    taken: List[Assigned] = field(default_factory=list)
    late: bool = False
    pinned: bool = False
    #: What was still missing when this line's own date came round (R37). Written once, by
    #: the walk, at the line's own step.
    short_at_date: float = 0.0
    #: Pinned to a document that is NOT supply - an overdue one (R31). The promise stands,
    #: so the line reads `pinned`, and the goods are still not there, so the month is still
    #: owed the quantity. Without this the two rulings would cancel each other out.
    uncounted_pinned: float = 0.0


def _round(value: float) -> float:
    """Rounded, and NEVER negative zero: `-0.0` reaches a screen as `-0`, which reads as a
    debt of nothing rather than as nothing owed."""
    out = round(float(value), QTY_PRECISION)
    return 0.0 if out == 0 else out


def month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_start(key: str) -> date:
    year, month = key.split("-")
    return date(int(year), int(month), 1)


def _next_month(key: str) -> str:
    year, month = (int(part) for part in key.split("-"))
    return f"{year + 1}-01" if month == 12 else f"{year}-{month + 1:02d}"


def month_axis(first: str, last: str) -> List[str]:
    """Every month key from `first` to `last` inclusive, gaps included.

    A missing column is not the same as a zero one: a month with nothing due and nothing
    arriving reads 0 (nothing owed, nothing spare, R37), and leaving it out would make the
    calendar jump a month.
    """
    out = [first]
    while out[-1] < last:
        out.append(_next_month(out[-1]))
    return out


def tone_for(balance: float, key: str, *, as_of: date, lead_days: int) -> str:
    """Red when the debt cannot be bought in time, amber when it still can, green in surplus.

    The horizon is `as_of + lead` - the earliest a fresh purchase could land - so a month
    that STARTS before it is a month no buying decision can still rescue. That is the whole
    reading: red is not "worse", it is "too late to buy".
    """
    if balance >= -EPSILON:
        return TONE_GREEN
    return TONE_RED if _month_start(key) < _horizon(as_of, lead_days) else TONE_AMBER


def _horizon(as_of: date, lead_days: int):
    from datetime import timedelta

    return as_of + timedelta(days=max(int(lead_days or 0), 0))


def effective_date(at: Optional[date], as_of: date) -> date:
    """Where an event actually sits on the axis: never before today (AC-S2-5).

    PUBLIC because the caller has to place the SAME event in the same cell when it lists the
    drill - a document the balance counted in September and the drill filed under July is a
    lightbox that does not foot with the cell that opened it.
    """
    return as_of if at is None or at < as_of else at


def assign(
    product: str,
    *,
    as_of: date,
    tba_from: date,
    lead_days: int,
    supply: Sequence[SupplyEvent],
    demand: Sequence[DemandLine],
    pinned: Sequence[Hold] = (),
) -> Assignment:
    """Assign `supply` to `demand` for one product, and state the balance it leaves.

    `product` is carried for the caller's own error messages and logging only - one call is
    one product, and mixing two would net a shortage away against another item's surplus.
    """
    counted: List[SupplyEvent] = []
    uncounted: List[SupplyEvent] = []
    for event in supply:
        if float(event.qty) <= EPSILON:
            continue
        # On hand is held NOW, whatever date the caller stamped it with; only a document
        # can be overdue, and an undated document cannot be placed on the axis at all.
        if event.kind == KIND_ON_HAND:
            counted.append(event)
        elif event.at is None or event.at < as_of:
            uncounted.append(event)
        else:
            counted.append(event)

    dated: List[DemandLine] = []
    totals = {BUCKET_UNLOCATED: 0.0, BUCKET_TBA: 0.0, BUCKET_UNDATED: 0.0}
    results: List[LineResult] = []

    for line in demand:
        # Unlocated FIRST: a line with no warehouse is in no group's pile, so it could not
        # draw whatever its date said, and filing it under TBA would hide the thing that
        # actually has to be fixed about it.
        if not line.warehouse and not line.is_pool:
            bucket = BUCKET_UNLOCATED
        elif line.required_date is None:
            bucket = BUCKET_UNDATED
        elif line.required_date >= tba_from:
            bucket = BUCKET_TBA
        else:
            dated.append(line)
            continue
        totals[bucket] += float(line.open_qty)
        results.append(
            LineResult(
                line=line,
                assigned=(),
                uncovered=_round(line.open_qty),
                status=STATUS_SHORT,
                bucket=bucket,
                short_at_date=_round(line.open_qty),
            )
        )

    left = {event.key: float(event.qty) for event in counted}
    events = {event.key: event for event in counted}
    uncounted_by_key = {event.key: event for event in uncounted}
    states = {
        line.key: _Open(line=line, remaining=float(line.open_qty)) for line in dated
    }

    # 1. pinned holds, at any date -------------------------------------------------------
    #
    # A hold whose supply is not in this call's span is honoured off an event stood up from
    # the hold itself (AC-S2-1b). It never enters `left`, so nothing else can queue for it -
    # the pin consumed the whole of it - but it IS counted in the month balance, or the cell
    # would print red over a drill in which every line reads `pinned`.
    for hold in pinned:
        state = states.get(hold.line_key)
        if state is None:
            continue
        if hold.supply_key in left:
            take = min(float(hold.qty), state.remaining, left[hold.supply_key])
            if take <= EPSILON:
                continue
            left[hold.supply_key] -= take
            event = events[hold.supply_key]
        elif hold.supply_key in uncounted_by_key:
            # An OVERDUE document somebody has already been promised. The promise stands
            # (the line reads `pinned`) and the drill names the order the document is
            # placed against - but the document is still not supply (R31), so it adds
            # nothing to the month. Chasing it is the action the red cell is asking for.
            take = min(float(hold.qty), state.remaining)
            if take <= EPSILON:
                continue
            event = uncounted_by_key[hold.supply_key]
            state.uncounted_pinned += take
        else:
            take = min(float(hold.qty), state.remaining)
            if take <= EPSILON:
                continue
            event = SupplyEvent(
                key=hold.supply_key,
                kind=hold.kind,
                warehouse=hold.warehouse,
                # Placed at `as_of`: the promise is in force now, and the span this call was
                # given holds no arrival date to place it on.
                at=as_of,
                qty=_round(take),
                ref=hold.ref,
            )
            counted.append(event)
        state.remaining -= take
        state.pinned = True
        state.taken.append(Assigned(event=event, qty=_round(take), pinned=True))

    # 2. ONE chronological walk, with a pile per ownership group ---------------------------
    _walk(
        as_of=as_of,
        events=[event for event in counted if left.get(event.key, 0.0) > EPSILON],
        left=left,
        states=[states[line.key] for line in dated],
    )

    for line in dated:
        state = states[line.key]
        uncovered = _round(max(state.remaining, 0.0))
        if uncovered > EPSILON:
            status = STATUS_SHORT
        elif state.pinned:
            status = STATUS_PINNED
        elif state.late:
            status = STATUS_LATE
        else:
            status = STATUS_COVERED
        results.append(
            LineResult(
                line=line,
                assigned=tuple(state.taken),
                uncovered=uncovered,
                status=status,
                bucket=month_key(effective_date(line.required_date, as_of)),
                short_at_date=state.short_at_date,
            )
        )

    free = {
        event.key: _round(max(left.get(event.key, 0.0), 0.0)) for event in counted
    }
    months = _months(
        as_of=as_of,
        lead_days=lead_days,
        supply=counted,
        free=free,
        states=[states[line.key] for line in dated],
    )

    return Assignment(
        lines=tuple(results),
        months=tuple(months),
        free=free,
        tba=_round(-totals[BUCKET_TBA]),
        undated=_round(-totals[BUCKET_UNDATED]),
        unlocated=_round(-totals[BUCKET_UNLOCATED]),
        uncounted=tuple(uncounted),
    )


def _walk(
    *,
    as_of: date,
    events: Sequence[SupplyEvent],
    left: dict,
    states: Sequence[_Open],
) -> None:
    """The whole product's book, in date order, with a pile per ownership group.

    ONE walk over every group, not a walk per group (AC-S2-1b). Each group keeps its own
    free pile and its own queue of open shortfalls; a line draws its own group's pile first
    and then the other PROJECT groups' piles, oldest first. That is ladder step 1 exactly -
    "use free supply: own group, then the other project groups, no debt" (PLAN 3.2) - and
    it is why the product-wide month balance and the per-line status now say the same thing.
    Walking group by group could not: a BB line went `short` while IB stock sat unused, so
    the cell was green and the drill was red.

    A SITE POOL is sealed off in both directions. Its stock is nobody's free supply (taking
    it is the pool RUNG, which raises an ORDER_BACK, R34), and a pool line has no claim on a
    project group's pile. So `__pool__` neither lends to nor borrows from anybody here.

    Mutates `left` and the line states.
    """
    steps: List[Tuple[date, int, int, object]] = []
    for event in events:
        if left.get(event.key, 0.0) <= EPSILON:
            continue
        at = effective_date(event.at, as_of)
        # Supply BEFORE demand on a same-day tie, the ordering `coverage_timeline._sort_key`
        # already fixes for every consumer: a container cleared in the morning covers a
        # despatch due the same day.
        steps.append((at, 0, 0, event))
    for index, state in enumerate(states):
        at = effective_date(state.line.required_date, as_of)
        steps.append((at, 1, index, state))
    # The required date, then the document/line identity, so two rows that agree on
    # everything a person can see still sort the same way on every run.
    steps.sort(
        key=lambda step: (
            step[0],
            step[1],
            _identity(step[3]),
        )
    )

    #: group -> arrived, not yet taken, oldest first
    piles: Dict[str, List[SupplyEvent]] = {}
    #: group -> open, earliest required date first
    shortfalls: Dict[str, List[_Open]] = {}

    for _at, kind, _index, item in steps:
        if kind == 0:
            event: SupplyEvent = item  # type: ignore[assignment]
            group = _group_of(event.warehouse, event.is_pool)
            for state in _shortfall_order(shortfalls, group):
                if left[event.key] <= EPSILON:
                    break
                take = min(state.remaining, left[event.key])
                if take <= EPSILON:
                    continue
                left[event.key] -= take
                state.remaining -= take
                state.late = True
                state.taken.append(Assigned(event=event, qty=_round(take)))
                if state.remaining <= EPSILON:
                    shortfalls[_group_of(state.line.warehouse, state.line.is_pool)].remove(
                        state
                    )
            if left[event.key] > EPSILON:
                piles.setdefault(group, []).append(event)
            continue

        state: _Open = item  # type: ignore[assignment]
        group = _group_of(state.line.warehouse, state.line.is_pool)
        if state.remaining > EPSILON:
            for pile, event in _draw_order(piles, group):
                if state.remaining <= EPSILON:
                    break
                take = min(state.remaining, left[event.key])
                if take <= EPSILON:
                    pile.remove(event)
                    continue
                left[event.key] -= take
                state.remaining -= take
                state.taken.append(Assigned(event=event, qty=_round(take)))
                if left[event.key] <= EPSILON:
                    pile.remove(event)
        # Its own date has now passed in the walk, so whatever is left is what this line
        # went without ON ITS DATE - the figure its month books (R37). Later supply may
        # still clear it (it becomes `late`), and that does not give the month back: the
        # order was still short in the month it was promised for.
        state.short_at_date = _round(
            max(state.remaining, 0.0) + state.uncounted_pinned
        )
        if state.remaining > EPSILON:
            shortfalls.setdefault(group, []).append(state)


def _lends_to(donor_group: str, asking_group: str) -> bool:
    """Whose free pile a group may draw on: its own, and any other PROJECT group's.

    The site pool is neither a donor nor a borrower here - see `_walk`.
    """
    if donor_group == asking_group:
        return True
    return POOL_GROUP not in (donor_group, asking_group)


def _shortfall_order(
    shortfalls: "Dict[str, List[_Open]]", group: str
) -> List[_Open]:
    """Who this arrival clears, in order: our own queue, then the other project groups'.

    A snapshot list, because the caller removes from the underlying queues as it goes.
    Within the others, the earliest REQUIRED DATE first - the same first-come rule the
    single-group queue already follows, applied across the groups it now reaches.
    """
    own = list(shortfalls.get(group, ()))
    others: List[_Open] = []
    for other, queue in shortfalls.items():
        if other == group or not _lends_to(group, other):
            continue
        others.extend(queue)
    others.sort(key=lambda state: _identity(state))
    return own + others


def _draw_order(
    piles: "Dict[str, List[SupplyEvent]]", group: str
) -> List[Tuple[List[SupplyEvent], SupplyEvent]]:
    """What this line may draw, in order: our own pile, then the other project groups'.

    Each entry carries the pile it came from, so the caller can take the event OUT of the
    right list once it is exhausted. Own pile in arrival order (it was appended that way);
    the others merged oldest first, because free stock that has been sitting longest is the
    stock to move.
    """
    out: List[Tuple[List[SupplyEvent], SupplyEvent]] = []
    own = piles.get(group)
    if own:
        out.extend((own, event) for event in list(own))
    others: List[Tuple[List[SupplyEvent], SupplyEvent]] = []
    for other, pile in piles.items():
        if other == group or not _lends_to(other, group):
            continue
        others.extend((pile, event) for event in list(pile))
    others.sort(key=lambda pair: _identity(pair[1]))
    return out + others


def _identity(item) -> tuple:
    """A stable tie-break for a step: the document, then the line, then the key."""
    if isinstance(item, _Open):
        line = item.line
        return (
            line.required_date or date.min,
            line.so_number or "",
            line.line_no is None,
            line.line_no or 0,
            line.key,
        )
    return (item.at or date.min, item.ref or "", 0, 0, item.key)


def _months(
    *,
    as_of: date,
    lead_days: int,
    supply: Sequence[SupplyEvent],
    free: Dict[str, float],
    states: Sequence[_Open],
) -> List[MonthBalance]:
    """Each month on its own: what is spare in it, less what goes without in it (R37).

    Two sums, per month key:

    - the supply DATED IN the month that nobody took by the end of the walk. Supply a line
      consumed - including a late line whose shortfall it cleared - is spent, and spent
      stock is not spare in any month.
    - what each line due in the month was short AT ITS OWN DATE.

    Nothing carries. A month with neither reads 0, which is the true statement about it:
    nothing is owed and nothing is spare. The reader who wants the position over time reads
    the row, which is the calendar.
    """
    credit: Dict[str, float] = {}
    debit: Dict[str, float] = {}

    for event in supply:
        spare = free.get(event.key, 0.0)
        if spare <= EPSILON:
            continue
        key = month_key(effective_date(event.at, as_of))
        credit[key] = credit.get(key, 0.0) + spare
    for state in states:
        short = state.short_at_date
        if short <= EPSILON:
            continue
        key = month_key(effective_date(state.line.required_date, as_of))
        debit[key] = debit.get(key, 0.0) + short

    first = month_key(as_of)
    dates = [effective_date(event.at, as_of) for event in supply]
    dates += [effective_date(state.line.required_date, as_of) for state in states]
    last = max((month_key(value) for value in dates), default=first)

    out: List[MonthBalance] = []
    for key in month_axis(first, max(last, first)):
        balance = _round(credit.get(key, 0.0) - debit.get(key, 0.0))
        out.append(
            MonthBalance(
                key=key,
                balance=balance,
                tone=tone_for(balance, key, as_of=as_of, lead_days=lead_days),
            )
        )
    return out


__all__ = [
    "BUCKET_TBA",
    "BUCKET_UNDATED",
    "BUCKET_UNLOCATED",
    "KIND_ON_HAND",
    "KIND_PO",
    "KIND_SPO",
    "POOL_GROUP",
    "STATUS_COVERED",
    "STATUS_LATE",
    "STATUS_PINNED",
    "STATUS_SHORT",
    "TONE_AMBER",
    "TONE_GREEN",
    "TONE_RED",
    "Assigned",
    "Assignment",
    "DemandLine",
    "Hold",
    "LineResult",
    "MonthBalance",
    "SupplyEvent",
    "assign",
    "effective_date",
    "month_axis",
    "month_key",
    "tone_for",
]
