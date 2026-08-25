"""Order promising: what covers a Project SO line, and why (PLAN 3.2, 3.3, 3.5, and the
25 August 2026 ruling, "ladder v3").

PURE arithmetic, the same discipline as ``coverage_timeline`` and ``reorder_engine``'s top
half: no database, no LLM, no optimizer, no configuration knob. Every number here is
derived from the rule that produced it, and every rule states itself in a sentence that
travels with the quantity, because a proposal that shows a number without saying why is a
number CS has to go and verify somewhere else (AC-B14).

Two functions, and they answer two different questions.

``propose_line`` answers "how should THIS line be met" - ladder v3's own order, per the
captain's 25 August ruling (``PLAN-scm-cs-planning-uat.md`` section 1b): "if delivery date
exceed lead time, directly buy; if within lead time, consider the group location first
(only available quantity); if group location don't have then consider the pool (BRW, MWH,
DC1, WH3); if pool also don't have then consider borrowing from other location's available
quantity".

0. beyond the reserve window (``as_of + lead time + RESERVE_BUFFER_DAYS``) or beyond
   purchasing's reorder-coverage date -> rung 1 runs and NOTHING ELSE: incoming supply
   covering the whole line is proposed, and anything short of that is a whole-line ``Buy``;
1. timely incoming (an SPO arriving by the required date) counts toward cover;
2. the OWNERSHIP GROUP, this line's own location included, each location capped at
   ``max(min(free, available), 0)`` - the caller hands them over in draw order;
3. the shared pool, own site first then the other site pools, capped the same way, with
   the dealer/project hot-selling gate of 3.3a retained;
4. cross-group borrow: free stock outside the ownership group, offered by the caller only
   within the small-quantity cap;
5. the whole-line rule: if 1-4 together reach the whole of Q, that composition is proposed,
   in rung order; otherwise NONE of it is proposed and the whole line is a Buy - never a
   partial mix of "reserve 213, buy 145".

Borrowing another SALES ORDER's committed quantity is not a rung here at all (ruled 25
August 2026): it is a manual pick in Amend, made by a person who has the donor's position
in front of them, never something the engine composes on their behalf.

``attribute_sources`` answers "who gets the one pile" - several lines competing for one
location's opening stock and its dated incoming, resolved in section 3.5's fixed order so
the same facts always produce the same answer and the database's row order never
participates. Unchanged by ladder v3.

Quantities are ``Decimal`` throughout. These figures are compared for exact equality at
confirmation, and a binary float does not survive that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ZERO = Decimal("0")

# The four component kinds of the balance invariant (PLAN 3.1):
#   open_so_qty = timely_spo_coverage + reserve_qty + borrow_qty + buy_qty
TIMELY_SPO = "timely_spo"
RESERVE = "reserve"
BORROW = "borrow"
BUY = "buy"

#: How each kind reads on screen. Kept beside the kinds so `Component.stated` and the UI
#: cannot spell the same component two ways.
COMPONENT_LABELS = {
    TIMELY_SPO: "Timely SPO",
    RESERVE: "Reserve",
    BORROW: "Borrow",
    BUY: "Buy",
}

#: The ladder's own rung vocabulary, finer-grained than `kind`: several rungs
#: share a `kind` (the pool and group-take rungs are both `reserve`; group borrow and
#: cross-group borrow are both `borrow`) and the UI names the rung, not the kind, in the
#: trail and the donor list.
RUNG_INCOMING = "incoming"
RUNG_POOL = "pool"
RUNG_GROUP_TAKE = "group_take"
RUNG_GROUP_BORROW = "group_borrow"
RUNG_CROSS_GROUP_BORROW = "cross_group_borrow"
RUNG_BUY = "buy"

BUY_REASON = "remaining uncovered need"

# --------------------------------------------------------------------------- #
# The ATP reserve window
# --------------------------------------------------------------------------- #
#
# A line due long after purchasing could simply buy for it must not take stock that
# nearer-dated demand needs. The window it may reserve inside is
#
#     as_of + (the product's lead time) + RESERVE_BUFFER_DAYS
#
# and a line due beyond it takes NO STOCK (ladder v3, section 1b rung 0: "if delivery date
# exceed lead time, directly buy"). v2 still walked the two surplus rungs for such a line
# and refused it only the borrow rungs; v3 walks no stock rung at all, because "surplus" is
# a reading of one moment and the purchase order has months to be raised in.
#
# INCOMING IS THE EXCEPTION, and it is not really one: rung 1 is unchanged (section 1b), so
# supply already on its way still counts toward cover. It is already bought. Buying it a
# second time is a double purchase, not a conservative choice - and it is what a blanket
# "beyond the window means Buy" did. What incoming cannot cover in FULL still falls to the
# whole-line rule, with the window named as the reason rather than the arithmetic.
#
# BOTH CONSTANTS ARE FUTURE POLICY FIELDS. They belong beside `reorder_coverage_until` on
# `PriorityPolicy` (the same admin screen, the same revisioned row) the day somebody needs
# to tune them per tenant; they are literals here because one number that nobody has asked
# to configure does not need a table, a migration and a form first. The trigger for
# promoting them: the first request to change either without a deploy.

#: Days of slack on top of the lead time. Purchasing needs the order raised before the
#: lead time runs out, not on the last possible day, and a fortnight is the smallest
#: interval anybody in this business plans in.
RESERVE_BUFFER_DAYS = 14

#: The lead time to assume for a product nobody has stated one for. MEASURED, not guessed:
#: `product_suppliers.standard_lead_time_days` on the live book is 90 days on 11,671 of its
#: 17,667 rows (median 90; the other two values are 14 and 45), and `system_settings
#: .default_product_standard_lead_time_days` independently defaults to 90.
DEFAULT_LEAD_TIME_DAYS = 90


def reserve_window_end(as_of: date, lead_time_days: Optional[int] = None) -> date:
    """The last day a line may still reserve stock for, from `as_of`.

    ONE place for the arithmetic, so the engine, the service that decides which side of it a
    line falls on, and the sentence a planner reads cannot disagree about the day. A line due
    ON this date is INSIDE the window - the same boundary rule rung 0's coverage date follows.
    """
    days = DEFAULT_LEAD_TIME_DAYS if lead_time_days is None else max(int(lead_time_days), 0)
    return as_of + timedelta(days=days + RESERVE_BUFFER_DAYS)


def _reserve_window_buy_reason() -> str:
    return (
        "Delivery date beyond the lead time window; stock kept for nearer orders"
    )

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def qty_text(value: Decimal) -> str:
    """A quantity as a person writes it.

    ``Decimal("40").normalize()`` is ``4E+1``, which inside a reason string reads as a
    defect rather than as forty units.
    """
    return format(_dec(value).normalize(), "f")


def _date_text(value: date) -> str:
    """"31 Oct 2026" - the captain's own wording, day first, no leading zero."""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


@dataclass(frozen=True)
class Component:
    """One proposed component: how much, from where, and why."""

    kind: str
    qty: Decimal
    #: The rule's own sentence. Deterministic for the same snapshot, never LLM-written,
    #: and frozen with the line snapshot at confirmation.
    reason: str
    #: Where the quantity comes from: the pool warehouse for a pool Reserve, the sibling
    #: location for group take, the donor's location for group/cross-group Borrow. Buy has
    #: none - it is not held anywhere yet.
    source_location: Optional[str] = None
    #: Which rung of the ladder produced this component (section E). Finer than `kind`,
    #: which only carries the balance-invariant bucket (`reserve`/`borrow`/...).
    rung: Optional[str] = None
    #: The donor sales order, for a `group_borrow` component only (AC section E.4): its
    #: number, line, and the agent who owns it, so the sheet can show "Borrow 145 from
    #: SO371334 line 2 · agent JEREMY" and the planner can phone her.
    donor_so_number: Optional[str] = None
    donor_line_no: Optional[int] = None
    donor_agent_code: Optional[str] = None
    #: The donor SO shares this line's own agent - "she can authorise CS to move stock
    #: between her own orders" (section 8). Always `False` outside `group_borrow`.
    same_agent: bool = False
    #: The order-back this component raises: an Order Inquiry Buy for the donor's own
    #: line, at the donor's own required date, equal to what was taken (section E.4 -
    #: "every borrow carries an order-back"). `None` outside `group_borrow`.
    order_back_qty: Optional[Decimal] = None
    #: Addressing only, never rendered: the donor's own CORE sales-order line id, so a
    #: caller re-confirming this proposal AS PROPOSED can re-identify the same donor line
    #: (`_check_group_borrow` re-reads its live committed quantity, AC-C03) without a
    #: second lookup. `None` outside `group_borrow`.
    donor_core_line_id: Optional[str] = None
    #: The DONOR's own required date (section E.4: "urgency = the donor's required
    #: date") - the order-back Order Inquiry row's urgency, not this line's own.
    #: `None` outside `group_borrow`, and on a donor whose own required date is unset
    #: (the order-back then falls back to the borrowing line's own date).
    donor_required_date: Optional[date] = None

    @property
    def stated(self) -> str:
        """The whole phrase AC-B14 quotes: "Reserve 10: free stock at BRW ..."."""
        return f"{COMPONENT_LABELS[self.kind]} {qty_text(self.qty)}: {self.reason}"


def _own_reason(location: str) -> str:
    return f"free stock at {location} covers the need by the required date"


def _spo_reason(spo_number: str, arrival_date: Optional[date]) -> str:
    when = arrival_date.isoformat() if arrival_date else "an unstated date"
    return f"SPO {spo_number} arrives on {when}, by the required date"


# --------------------------------------------------------------------------- #
# Ladder v2 rung helpers (PLAN-demo-followups-19aug-ladder-v2.md section E)
# --------------------------------------------------------------------------- #


def _coverage_date_reason(coverage_until: date) -> str:
    return f"Beyond purchasing's coverage ({_date_text(coverage_until)}) - buy now"


def pool_reserve_capacity(
    *,
    is_dealer_hot_selling: bool,
    is_project_hot_selling: bool,
    pools: Sequence[Mapping[str, Any]],
) -> List[Tuple[str, Decimal, str]]:
    """Rung 3: the shared pool, own site first then the other site pools.

    `pools` is already in draw order - the caller's own site pool first, then the other
    site pools - each stating `location`, `free` and `available` (the pool's own SIGNED
    position, `on hand - SO qty + SPO qty`). Every pool is capped the same way now,
    `max(min(free, available), 0)`, whether the product is project hot-selling or neither -
    a change from 3.3a's "neither: uncapped", made because ladder v2 can draw a SECOND and
    THIRD pool that were never this line's own, and an uncapped draw on one of those would
    ignore what its own book already owes. Dealer hot-selling still excludes the pool rung
    entirely, exactly as 3.3a states.
    """
    if is_dealer_hot_selling:
        return []
    out: List[Tuple[str, Decimal, str]] = []
    for pool in pools:
        location = pool.get("location")
        if not location:
            continue
        free = max(_dec(pool.get("free")), ZERO)
        available = _dec(pool.get("available"))
        capacity = max(min(free, available), ZERO)
        if capacity <= ZERO:
            continue
        out.append(
            (
                str(location),
                capacity,
                f"Pool {location} has {qty_text(capacity)} available",
            )
        )
    return out


def _group_take_reason(location: str, qty: Decimal, group_code: Optional[str]) -> str:
    where = f" in the {group_code} group" if group_code else ""
    return f"{location} has {qty_text(qty)} available{where}"


def _cross_group_borrow_reason(location: str, qty: Decimal) -> str:
    return (
        f"{location} has {qty_text(qty)} free outside this group, within the cross-group "
        "borrow limit"
    )


def _whole_line_buy_reason(covered: Decimal, open_qty: Decimal) -> str:
    return (
        f"Only {qty_text(covered)} of {qty_text(open_qty)} can be covered from stock - buy "
        "the whole line"
    )


# --------------------------------------------------------------------------- #
# One line's composition (PLAN 3.2, amended by section E)
# --------------------------------------------------------------------------- #


def propose_line(
    *,
    open_qty: Any,
    line_no: Optional[int] = None,
    required_date: Optional[date] = None,
    fulfilment_location: Optional[str] = None,
    group_code: Optional[str] = None,
    is_dealer_hot_selling: bool = False,
    is_project_hot_selling: bool = False,
    pools: Optional[Sequence[Mapping[str, Any]]] = None,
    timely_spo_qty: Any = ZERO,
    timely_spo_refs: Optional[Sequence[Mapping[str, Any]]] = None,
    is_discontinued: bool = False,
    reorder_coverage_until: Optional[date] = None,
    group_take_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    cross_group_borrow_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    outside_reserve_window: bool = False,
) -> Tuple[Component, ...]:
    """The proposed composition for one line, ladder v3's own order (section 1b).

    0. beyond the reserve window, or beyond `reorder_coverage_until` -> rung 1 runs and
       nothing else does. Incoming supply covering the WHOLE of `open_qty` is proposed as
       it stands; anything short of that is a single whole-line Buy naming the bound that
       fired, never "incoming 40, buy 31" (that mix is what AC-L5 refuses at confirm). An
       UNDATED line (`required_date=None`) is never beyond either bound - both comparisons
       need two dates - so it falls straight through to the full walk;
    1. timely incoming, for supply arriving on or before the required date;
    2. the ownership group: `group_take_candidates`, already capped by the caller
       (`max(min(free, available), 0)`) and already in draw order - this line's own
       location first, then its siblings by site;
    3. the shared pool(s), `pool_reserve_capacity`, own site first;
    4. cross-group borrow: `cross_group_borrow_candidates` - the caller passes ONLY the
       donors within the small-quantity cap;
    5. the whole-line rule: if 1-4 reach the whole of `open_qty`, that composition is
       returned, in rung order; otherwise every partial component is DROPPED and the whole
       line is proposed as a single Buy - never "reserve 213, buy 145".

    Each candidate rung's inputs are already computed live and already ordered by the
    caller (`own location first, then the siblings` for the group rung; `own site pool
    first` for the pool rung); this function only walks them in the order given and never
    re-sorts or re-derives a capacity.

    A component contributing nothing is not proposed at all: emitting a zero would force a
    reason for a quantity that does not exist.

    `outside_reserve_window` is the ATP rule (see the constants at the top of this module):
    the line is due beyond `as_of + lead time + RESERVE_BUFFER_DAYS`, so purchasing can still
    buy for it in time and it must not take stock a nearer-dated order needs. Under v3 no
    STOCK rung runs for such a line; rung 1 still does, because incoming supply is already
    bought. The CALLER decides which side of the window a line falls on, because only it
    knows the product's lead time.
    """
    open_amount = max(_dec(open_qty), ZERO)
    if open_amount <= ZERO:
        return ()

    timely = max(_dec(timely_spo_qty), ZERO)

    # 0. Beyond either bound, rung 1 runs and NOTHING ELSE does. Two bounds, one rule:
    #    whichever of them the line is beyond decides it, and the reason names the one that
    #    fired. Purchasing's stated coverage date is checked first because it is a date a
    #    person set and can point at; the window is the derived one.
    #
    #    Incoming still counts, because it is already bought (see the constants block).
    #    Incoming that does not reach the WHOLE line is dropped rather than mixed with a
    #    Buy - the whole-line rule holds on both sides of the window.
    beyond: Optional[str] = None
    if (
        reorder_coverage_until is not None
        and required_date is not None
        and required_date > reorder_coverage_until
    ):
        beyond = _coverage_date_reason(reorder_coverage_until)
    elif outside_reserve_window:
        beyond = _reserve_window_buy_reason()
    if beyond is not None:
        if timely >= open_amount:
            return tuple(
                _incoming_rung(open_amount, timely_spo_refs, fulfilment_location)
            )
        return (
            Component(kind=BUY, qty=open_amount, reason=beyond, rung=RUNG_BUY),
        )

    remaining = open_amount
    components: List[Component] = []

    # 1. timely incoming.
    if remaining > ZERO and timely > ZERO:
        take = min(remaining, timely)
        components.extend(_incoming_rung(take, timely_spo_refs, fulfilment_location))
        remaining -= take

    # 2. the ownership group: positive Available at the line's own location and at its
    #    siblings, in the draw order the caller states (own location first).
    for candidate in group_take_candidates or []:
        if remaining <= ZERO:
            break
        location = candidate.get("location")
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if not location or capacity <= ZERO:
            continue
        take = min(remaining, capacity)
        components.append(
            Component(
                kind=RESERVE,
                qty=take,
                reason=_group_take_reason(str(location), take, group_code),
                source_location=str(location),
                rung=RUNG_GROUP_TAKE,
            )
        )
        remaining -= take

    # 3. the shared pool(s), own site first.
    for location, capacity, reason in pool_reserve_capacity(
        is_dealer_hot_selling=is_dealer_hot_selling,
        is_project_hot_selling=is_project_hot_selling,
        pools=pools or [],
    ):
        if remaining <= ZERO:
            break
        take = min(remaining, capacity)
        if take <= ZERO:
            continue
        components.append(
            Component(
                kind=RESERVE, qty=take, reason=reason, source_location=location,
                rung=RUNG_POOL,
            )
        )
        remaining -= take

    # 4. cross-group borrow: free stock outside this group, already cap-filtered by the
    #    caller. Borrowing another SALES ORDER's committed quantity is not a rung here and
    #    never becomes one: ruled 25 August 2026 as a manual pick in Amend, taken by a
    #    person with the donor's position in front of them.
    for candidate in cross_group_borrow_candidates or []:
        if remaining <= ZERO:
            break
        location = candidate.get("location")
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if not location or capacity <= ZERO:
            continue
        take = min(remaining, capacity)
        components.append(
            Component(
                kind=BORROW,
                qty=take,
                reason=_cross_group_borrow_reason(str(location), take),
                source_location=str(location),
                rung=RUNG_CROSS_GROUP_BORROW,
            )
        )
        remaining -= take

    # 5. the whole-line rule: cover Q entirely in rung order, or Buy the whole of it.
    if remaining > ZERO:
        covered = open_amount - remaining
        return (
            Component(
                kind=BUY,
                qty=open_amount,
                reason=_whole_line_buy_reason(covered, open_amount),
                rung=RUNG_BUY,
            ),
        )

    return tuple(components)


def _incoming_rung(
    qty: Decimal,
    refs: Optional[Sequence[Mapping[str, Any]]],
    location: Optional[str],
) -> List[Component]:
    """Rung 1's components, stamped with the rung.

    ONE builder, because rung 1 now has two callers - the full walk and rung 0's
    short-circuit for a line beyond its window - and two copies would be two chances for a
    far line's incoming to read differently from a near line's.
    """
    return [
        Component(
            kind=component.kind,
            qty=component.qty,
            reason=component.reason,
            source_location=component.source_location,
            rung=RUNG_INCOMING,
        )
        for component in _timely_components(qty, refs, location)
    ]


def _timely_components(
    qty: Decimal,
    refs: Optional[Sequence[Mapping[str, Any]]],
    location: Optional[str],
) -> List[Component]:
    """Timely cover, named by the SPO rows that supply it when they are known.

    Named is the useful form: "SPO 202703-S0011 arrives on 2027-03-01" is something CS can
    look up, and an unnamed quantity is not.
    """
    if not refs:
        return [
            Component(
                kind=TIMELY_SPO,
                qty=qty,
                reason="incoming supply arrives by the required date",
                source_location=location,
            )
        ]
    out: List[Component] = []
    remaining = qty
    for ref in _sorted_supply(refs):
        if remaining <= ZERO:
            break
        take = min(remaining, max(_dec(ref.get("qty")), ZERO))
        if take <= ZERO:
            continue
        out.append(
            Component(
                kind=TIMELY_SPO,
                qty=take,
                reason=_spo_reason(
                    str(ref.get("spo_number") or ""), _as_date(ref.get("arrival_date"))
                ),
                source_location=location,
            )
        )
        remaining -= take
    return out


# --------------------------------------------------------------------------- #
# Several lines against one location's supply (PLAN 3.5)
# --------------------------------------------------------------------------- #


def _as_date(value: Any) -> Optional[date]:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _demand_sort_key(line: Mapping[str, Any]) -> tuple:
    """Required date, SO number, line number (missing last), then internal line id.

    The line id is a final stable key only and is never displayed: two lines that agree on
    everything a person can see still have to be ordered the same way on every run.
    """
    when = _as_date(line.get("required_date"))
    line_no = line.get("line_no")
    return (
        when is None,
        when or date.min,
        str(line.get("so_number") or ""),
        line_no is None,
        int(line_no) if line_no is not None else 0,
        str(line.get("line_id") or ""),
    )


def _supply_sort_key(event: Mapping[str, Any]) -> tuple:
    """Arrival date, SPO number, SPO line number (missing last), then allocation id."""
    when = _as_date(event.get("arrival_date"))
    line_no = event.get("spo_line_no")
    return (
        when is None,
        when or date.min,
        str(event.get("spo_number") or ""),
        line_no is None,
        int(line_no) if line_no is not None else 0,
        str(event.get("allocation_id") or ""),
    )


def _sorted_supply(events: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return sorted(events, key=_supply_sort_key)


def attribute_sources(
    *,
    product_code: Optional[str] = None,
    warehouse_code: str,
    opening_stock: Any = ZERO,
    supply_events: Optional[Sequence[Mapping[str, Any]]] = None,
    demand_lines: Optional[Sequence[Mapping[str, Any]]] = None,
    preserve_demand_order: bool = False,
) -> Dict[Tuple[str, Optional[int]], Tuple[Component, ...]]:
    """Share one product-location's dated supply across the lines asking for it.

    Keyed by each demand line's own ``key`` when it states one, and by
    ``(so_number, line_no)`` when it does not.

    The explicit key is not a convenience. ``line_no`` comes from the PROJECT mirror, and a
    core sales-order line that nobody has adopted has none - so every unmirrored line of one
    sales order collapsed onto the single key ``(so_number, None)``, and all but one of them
    silently received no share at all while the pile was credited as if they had. Invisible on
    the per-order sheet, which only ever walks mirrored lines; fatal to the multi-order board,
    where most lines at a pile belong to orders nobody has adopted.

    Sources are consumed in PLAN 3.5's order - opening stock first, then SPO arriving on or
    before that line's required date - with lines processed by required date, SO number,
    line number (missing last) and finally the internal line id. An SPO arriving ON the
    required date counts; one arriving the day after contributes nothing at that date and
    is advisory evidence instead.

    ``product_code`` names the pile in a failure message and takes no part in the
    arithmetic; the caller has already narrowed the rows to one product and location.
    """
    stock_left = max(_dec(opening_stock), ZERO)
    supply: List[Dict[str, Any]] = [
        {
            "spo_number": str(event.get("spo_number") or ""),
            "spo_line_no": event.get("spo_line_no"),
            "allocation_id": event.get("allocation_id"),
            "arrival_date": _as_date(event.get("arrival_date")),
            "left": max(_dec(event.get("qty")), ZERO),
        }
        for event in _sorted_supply(supply_events or [])
    ]

    # ``preserve_demand_order`` consumes the lines IN THE ORDER GIVEN. The caller who sets it
    # has already ordered the pile by the active fulfilment-priority policy, and re-sorting by
    # required date here would serve the stock in one order while the screen reports the queue
    # in another. Without it, the documented PLAN 3.5 order applies.
    ordered = (
        list(demand_lines or [])
        if preserve_demand_order
        else sorted(demand_lines or [], key=_demand_sort_key)
    )

    out: Dict[Tuple[str, Optional[int]], Tuple[Component, ...]] = {}
    for line in ordered:
        remaining = max(_dec(line.get("open_qty")), ZERO)
        required_date = _as_date(line.get("required_date"))
        components: List[Component] = []

        take = min(remaining, stock_left)
        if take > ZERO:
            components.append(
                Component(
                    kind=RESERVE,
                    qty=take,
                    reason=_own_reason(warehouse_code),
                    source_location=warehouse_code,
                )
            )
            stock_left -= take
            remaining -= take

        for event in supply:
            if remaining <= ZERO:
                break
            if event["left"] <= ZERO:
                continue
            arrival = event["arrival_date"]
            if required_date is not None and (arrival is None or arrival > required_date):
                # Later than the need: advisory at this date, and it contributes nothing.
                continue
            taken = min(remaining, event["left"])
            components.append(
                Component(
                    kind=TIMELY_SPO,
                    qty=taken,
                    reason=_spo_reason(event["spo_number"], arrival),
                    source_location=warehouse_code,
                )
            )
            event["left"] -= taken
            remaining -= taken

        if remaining > ZERO:
            components.append(Component(kind=BUY, qty=remaining, reason=BUY_REASON))

        stated = line.get("key")
        key = stated if stated is not None else (
            str(line.get("so_number") or ""), line.get("line_no")
        )
        out[key] = tuple(components)
    return out
