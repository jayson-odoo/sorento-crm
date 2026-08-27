"""Order promising: what covers a Project SO line, and why (PLAN 3.2, 3.3, 3.5, and the
25 August 2026 ruling, "ladder v3").

PURE arithmetic, the same discipline as ``coverage_timeline`` and ``reorder_engine``'s top
half: no database, no LLM, no optimizer, no configuration knob. Every number here is
derived from the rule that produced it, and every rule states itself in a sentence that
travels with the quantity, because a proposal that shows a number without saying why is a
number CS has to go and verify somewhere else (AC-B14).

Two functions, and they answer two different questions.

``propose_line`` answers "how should THIS line be met" - LADDER V5, the captain's four
questions of 26 August (``PLAN-scm-cs-planning-uat.md`` section 1e), which is section 1b's
ladder with incoming taken out of it and nothing else moved:

0. beyond the reserve window (``as_of + lead time + RESERVE_BUFFER_DAYS``) or beyond
   purchasing's reorder-coverage date -> no rung runs and the whole line is a ``Buy``;
1. **Can we use our location?** the OWNERSHIP GROUP, this line's own location included: the
   caller hands over the locations in draw order, already capped so that they total no more
   than what the WHOLE GROUP's net leaves for this line, never one warehouse's own reading
   (ladder v4, section 1d). The rank queue no longer decides availability;
2. **Can we take from the pool?** all five site pools netted as ONE pile (``pools_net``),
   drawn own site first then the others by on hand, with no per-pool cap. 3.3a's dealer
   hot-selling gate is retained and refuses the WHOLE pile (the pool is kept for retail);
   its project hot-selling cap is subsumed by the pile's own net;
3. **Can we borrow from another location?** what a DONOR GROUP nets as a whole, offered by
   the caller only within the small-quantity cap;
4. the whole-line rule: if 1-3 together reach the whole of Q, that composition is proposed,
   in rung order; otherwise NONE of it is proposed and the whole line is a Buy - never a
   partial mix of "reserve 213, buy 145".

**Incoming (SPO) is not a rung** (ladder v5, section 1e). It used to be the first one, and
to run even beyond the reserve window on the grounds that supply already on its way is
already bought. What retired it is that an SPO is INSIDE the ownership group's net already -
AutoCount's Available is ``on hand + SPO - SO`` - so rung 1 and the group rung were two
readings of one pile, netted against each other to keep the arithmetic honest. One reading
is simpler and cannot drift.

It is still a KIND, though, and question 1 still answers with it: part of what the group's
net can cover a line with is on the water rather than on a floor, so the caller marks those
candidates ``water`` and this module composes them as ``timely_spo`` with question 1's own
rung. Only water arriving on or before the line's required date is offered - the caller
applies that test, because only it holds the documents - and late water is named in the
proof's own sentence and never drawn. A LATE SPO reaches a particular line through Link SPO
on that line's order-inquiry row, which is where purchasing was already doing it.

The fourth question - **can we borrow from the same agent's other order in this group?** -
is not a rung here at all (ruled 25 August 2026): it is a manual pick in Amend, made by a
person who has the donor's position in front of them, never something the engine composes
on their behalf. The proof trail states it as a question all the same, so a reader learns it
was considered.

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
#
# `TIMELY_SPO` is no longer a RUNG under ladder v5 (section 1e), but it is still a KIND: what
# question 1 draws off the water inside its own ownership group's net is incoming supply, not
# stock on a floor, and calling it a Reserve would write a hold against goods nobody can pick
# (captain, 27 August 2026). Such a component carries `rung=RUNG_GROUP_TAKE` - it is question
# 1's answer, and the strip totals it under "Use own location" with the rest of that question.
# The old rung-1 spelling (`rung=RUNG_INCOMING`) survives only on decisions frozen under v3
# and v4, which the board still renders: a snapshot is evidence of what was promised.
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
#: Retired by ladder v5 (section 1e); still read, because frozen snapshots carry it.
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
# INCOMING USED TO BE THE EXCEPTION - rung 1 ran on both sides of the window, because supply
# already on its way is already bought and buying it twice is a double purchase. Ladder v5
# (section 1e) retires the exception with the rung: an SPO is inside the ownership group's
# net already, so it is not a second pile that a far line could be refused a share of. What
# reaches a far line's SPO is Link SPO on its order-inquiry row, after purchasing has read
# the buy.
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


def date_text(value: date) -> str:
    """"31 Oct 2026" - the captain's own wording, day first, no leading zero.

    Public beside `qty_text`: the board writes sentences about the same documents this
    module does, and a second spelling of a date is a second vocabulary.
    """
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


def spo_reason(
    spo_number: str, arrival_date: Optional[date], overdue_days: int = 0
) -> str:
    """How a timely incoming row reads, wherever it is named.

    An OVERDUE promise is named as overdue rather than dropped (captain's ruling, 26 Aug
    2026: trust the book). The goods are still owed and are still supply, and the buyer
    reading this is the person who can go and chase the supplier - which they cannot do if
    the row either disappears or reads as though the date were fine.

    Public, because the supply service builds this same sentence for its own reason field.
    Two copies agreed by coincidence until there was something new to say in both.

    The `SPO` prefix is only added to a number that does not already carry one. Every
    shipping order in the book is written `SPO-2026/08-0061`, and "SPO SPO-2026/08-0061"
    is how a label reads when nobody looked at real data; the older `202703-S0011` spelling
    still needs the word.
    """
    when = date_text(arrival_date) if arrival_date else "an unstated date"
    named = spo_number if spo_number.upper().startswith("SPO") else f"SPO {spo_number}"
    if overdue_days > 0:
        day = "day" if overdue_days == 1 else "days"
        return f"{named} arrives on {when} (overdue {overdue_days} {day})"
    return f"{named} arrives on {when}, by the required date"



# --------------------------------------------------------------------------- #
# Ladder v2 rung helpers (PLAN-demo-followups-19aug-ladder-v2.md section E)
# --------------------------------------------------------------------------- #


def _coverage_date_reason(coverage_until: date) -> str:
    return f"Beyond purchasing's coverage ({date_text(coverage_until)}) - buy now"


def pool_reserve_capacity(
    *,
    is_dealer_hot_selling: bool,
    pools: Sequence[Mapping[str, Any]],
    pools_net: Any,
) -> List[Tuple[str, Decimal]]:
    """Rung 3, LADDER V4 (section 1d): the five site pools are ONE pile.

    The rung offers `max(pools_net, 0)` and not a unit more - `BRW -103` beside `DC1 +1`
    nets -102 and offers NOTHING, where per-pool arithmetic would have offered the 1, which
    is stock the shared book already owes at BRW. `pools` is already in draw order (the
    caller's own site pool first, then the others by on hand) and each entry states its
    `free` balance: that is WHERE the quantity can physically come from, and `pools_net` is
    HOW MUCH. Exactly the shape rung 2 has for the ownership group.

    THERE IS NO PER-POOL CAP any more, and 3.3a's project hot-selling gate goes with it:
    that rule capped such a line's draw at the pool's own signed availability, and the
    pile's net now bounds EVERY draw the same way, for every item. Dealer hot-selling still
    excludes the rung entirely, which is a different rule - the pool is kept for retail, so
    it is not offered at all.

    Nothing is un-netted here, unlike rung 2: this line's demand is booked at
    `BRW-<group>`, never at a pool, so none of it is inside `pools_net`.
    """
    if is_dealer_hot_selling:
        return []
    left = max(_dec(pools_net), ZERO)
    out: List[Tuple[str, Decimal]] = []
    for pool in pools:
        if left <= ZERO:
            break
        location = pool.get("location")
        if not location:
            continue
        capacity = min(max(_dec(pool.get("free")), ZERO), left)
        if capacity <= ZERO:
            continue
        out.append((str(location), capacity))
        left -= capacity
    return out


def pool_reason(location: str, qty: Decimal, pools_net: Any) -> str:
    """Why this pool may lend this much.

    Built from what is actually TAKEN, beside the pile's own net - the same shape
    `group_take_reason` has, and for the same reason: under v4 the number is a share of a
    SET's position, so "Pool BRW has 30 available" reads as though BRW alone held it.

    Public because the supply service builds this sentence when it reads a CONFIRMED
    component back off a snapshot, exactly as it does for the group rung.
    """
    return (
        f"Pool {location} lends {qty_text(qty)} of the {qty_text(_dec(pools_net))} the "
        "site pools net between them"
    )


def group_water_reason(
    location: str,
    qty: Decimal,
    group_code: Optional[str],
    group_offer: Optional[Decimal],
    arrival_date: Optional[date],
) -> str:
    """Question 1's OTHER answer: the share of the group's offer that is still on the water.

    The group's net is `on hand + SPO - SO`, so part of what question 1 may hand this line is
    an SPO rather than a unit on a shelf. Drawn only when it lands on or before the required
    date (the caller applies that test and passes the LATEST such arrival here), and never
    called a Reserve: a hold cannot be written against goods that are not on the floor.

    `arrival_date` is the day the whole of this draw has landed by, which is the date a
    planner needs before promising it - not the earliest of several documents.
    """
    when = f", arriving {date_text(arrival_date)}" if arrival_date else ""
    if group_offer is None or not group_code:
        return f"{location} has {qty_text(qty)} on the water{when}"
    return (
        f"{location} has {qty_text(qty)} of the {qty_text(group_offer)} the {group_code} "
        f"group can cover this line with on the water{when}"
    )


def group_take_reason(
    location: str, qty: Decimal, group_code: Optional[str], group_offer: Optional[Decimal]
) -> str:
    """Why this location may give this much (v4: it is the GROUP's number, not the
    location's own).

    Public for the same reason `spo_reason` is: the supply service builds this same sentence
    when it reads a CONFIRMED component back off a snapshot, and two copies agreed only by
    coincidence.

    `BRW-BB has 40 available` was true while a location's own signed availability decided
    what it could lend. Under section 1d the group is one pile - `MWH-IB` holding 7000
    lends nothing while the IB group nets -15514 - so the quantity is a share of what the
    GROUP can cover this line with, and the sentence has to say whose number it is.
    """
    if group_offer is None or not group_code:
        where = f" in the {group_code} group" if group_code else ""
        return f"{location} has {qty_text(qty)} available{where}"
    return (
        f"{location} gives {qty_text(qty)} of the {qty_text(group_offer)} the "
        f"{group_code} group can cover this line with"
    )


def _cross_group_borrow_reason(location: str, qty: Decimal) -> str:
    """v4: what the DONOR GROUP can lend, drawn at this location.

    Never "`{location}` has N free": the offer is capped by the donor group's whole net
    (section 1d rung 4), so a location holding far more than N would be described wrongly
    by its own free balance.
    """
    return (
        f"{location} can lend {qty_text(qty)} from outside this group, within the "
        "cross-group borrow limit"
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
    #: Accepted and NOT read. The rungs name their own `source_location` from the candidate
    #: lists the caller hands over, so the line's own location takes no part in the
    #: arithmetic here. Kept on the signature because every caller states it and the ladder's
    #: own logs read better with it; the day a log stops naming it, it goes.
    fulfilment_location: Optional[str] = None,
    group_code: Optional[str] = None,
    is_dealer_hot_selling: bool = False,
    #: Accepted and NOT read since ladder v4 (section 1d). 3.3a capped a project
    #: hot-selling line's pool draw at the pool's own signed availability; the pile's net
    #: now bounds every draw the same way, for every item. Kept on the signature because
    #: three callers state it and the board's trail still names the classification in
    #: words; the day nothing reads it at all, it goes.
    is_project_hot_selling: bool = False,
    pools: Optional[Sequence[Mapping[str, Any]]] = None,
    is_discontinued: bool = False,
    reorder_coverage_until: Optional[date] = None,
    group_take_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    cross_group_borrow_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    outside_reserve_window: bool = False,
    group_offer: Optional[Decimal] = None,
    pools_net: Optional[Decimal] = None,
) -> Tuple[Component, ...]:
    """The proposed composition for one line, ladder v5's four questions (section 1e).

    0. beyond the reserve window, or beyond `reorder_coverage_until` -> no rung runs and the
       whole of `open_qty` is a single Buy naming the bound that fired. An UNDATED line
       (`required_date=None`) is never beyond either bound - both comparisons need two dates
       - so it falls straight through to the full walk;
    1. the ownership group: `group_take_candidates`, already capped by the caller to the
       GROUP's own position (`group_offer`) and already in draw order - this line's own
       location first, then its siblings by site. An SPO to any of those locations is inside
       that net, which is why there is no incoming rung above this one; a candidate marked
       `water` is that SPO share, and it is composed as `timely_spo` rather than `reserve`;
    2. the shared pool(s), `pool_reserve_capacity`, own site first, the rung as a whole
       bounded by `pools_net` and by each pool's own free stock;
    3. cross-group borrow: `cross_group_borrow_candidates` - the caller passes ONLY the
       donors within the small-quantity cap, each donor group capped at its own net;
    4. the whole-line rule: if 1-3 reach the whole of `open_qty`, that composition is
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
    buy for it in time and it must not take stock a nearer-dated order needs. No rung runs
    for such a line under v5. The CALLER decides which side of the window a line falls on,
    because only it knows the product's lead time.

    `group_offer` and `pools_net` are ladder v4's own numbers (section 1d). `pools_net` is
    what the five site pools hold BETWEEN them, signed, and it caps rung 3's whole draw.
    `group_offer` is what the ownership group's NET leaves for THIS line (its own quantity
    un-netted, every other line's still netted); it is the bound the caller has already
    applied to `group_take_candidates`, and it travels here so each component's reason can
    name the number it is a share OF. Both are `None` for a caller that states neither, and
    the rungs then stand on their per-location caps alone.
    """
    open_amount = max(_dec(open_qty), ZERO)
    if open_amount <= ZERO:
        return ()

    # 0. Beyond either bound, NO rung runs at all and the whole line is bought. Two bounds,
    #    one rule: whichever of them the line is beyond decides it, and the reason names the
    #    one that fired. Purchasing's stated coverage date is checked first because it is a
    #    date a person set and can point at; the window is the derived one.
    #
    #    LADDER V5 (section 1e): incoming used to be the one rung that still ran here,
    #    because supply already on its way is already bought. It is not a rung any more - an
    #    SPO is inside the ownership group's own net, where AutoCount already counts it, and
    #    it reaches a particular line through Link SPO on that line's order-inquiry row. So
    #    "beyond the window" is now literally what section 1b always said it was: buy.
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
        return (
            Component(kind=BUY, qty=open_amount, reason=beyond, rung=RUNG_BUY),
        )

    remaining = open_amount
    components: List[Component] = []

    # 1. the ownership group: what the GROUP's net leaves for this line, drawn at the
    #    locations the caller states in the draw order it states (own location first).
    for candidate in group_take_candidates or []:
        if remaining <= ZERO:
            break
        location = candidate.get("location")
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if not location or capacity <= ZERO:
            continue
        take = min(remaining, capacity)
        # Water inside the group's own net (`candidate["water"]`): incoming supply, and said
        # so. Same rung - it is question 1's answer either way - and a different kind,
        # because a Reserve is a hold on stock a picker can walk to.
        water = bool(candidate.get("water"))
        components.append(
            Component(
                kind=TIMELY_SPO if water else RESERVE,
                qty=take,
                reason=(
                    group_water_reason(
                        str(location),
                        take,
                        group_code,
                        group_offer,
                        candidate.get("arrival_date"),
                    )
                    if water
                    else group_take_reason(str(location), take, group_code, group_offer)
                ),
                source_location=str(location),
                rung=RUNG_GROUP_TAKE,
            )
        )
        remaining -= take

    # 2. the shared pool(s), own site first, the whole rung bounded by what the five pools
    #    net BETWEEN them (v4, section 1d).
    for location, capacity in pool_reserve_capacity(
        is_dealer_hot_selling=is_dealer_hot_selling,
        pools=pools or [],
        pools_net=pools_net,
    ):
        if remaining <= ZERO:
            break
        take = min(remaining, capacity)
        if take <= ZERO:
            continue
        components.append(
            Component(
                kind=RESERVE,
                qty=take,
                # Built from what is TAKEN, never from the rung's own running balance: the
                # reason travels with the quantity beside it, and a sentence naming the
                # capacity while the component names the draw is two numbers for one fact.
                reason=pool_reason(location, take, pools_net),
                source_location=location,
                rung=RUNG_POOL,
            )
        )
        remaining -= take

    # 3. cross-group borrow: free stock outside this group, already cap-filtered by the
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

    # 4. the whole-line rule: cover Q entirely in rung order, or Buy the whole of it.
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
                    reason=spo_reason(
                        event["spo_number"], arrival, int(event.get("overdue_days") or 0)
                    ),
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
