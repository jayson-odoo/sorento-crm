"""Order promising: what covers a Project SO line, and why.

LADDER V7.1 (`PLAN-scm-borrow-ladder-v7-stock-debt.md` section 3.2, rulings R1-R37).

PURE arithmetic, the same discipline as ``coverage_timeline`` and ``supply_assignment``: no
database, no LLM, no optimizer, no configuration knob. Every number here is derived from the
rule that produced it, and every rule states itself in a sentence that travels with the
quantity, because a proposal that shows a number without saying why is a number CS has to go
and verify somewhere else (AC-B14).

Two functions, and they answer two different questions.

``walk_line`` (and ``propose_line``, which is its components alone) answers "how should this
PLANNING UNIT be met" - five steps, in this order, each of them ASKED and answered whether or
not it is taken:

0. beyond the reserve window (``as_of + lead time + RESERVE_BUFFER_DAYS``) or beyond
   purchasing's reorder-coverage date -> no step runs and the whole unit is a ``Buy``;
1. **use** - the asker's own ownership group's FREE pile at its own date (R24), then the
   OTHER project groups' free piles (R5). Free means owed to nobody, so this step raises no
   debt, which is why it is walked before either borrow;
2. **order_borrow** - ON HAND held by a LATER order (R3, R4, R9, R12, R19, R25). The donor
   receives an order-back at its OWN required date, and a decided donor's decision falls
   with it, inside the same Confirm;
3. **supply_borrow** - the SPO a later order is waiting on, ONE document whole
   (R32, R33): eligible when it arrives by the asker's date or before a fresh buy would
   land, and the donor receives an order-back at its own date. Incoming means SPO
   (31 Aug ruling, R-A) - a PO is still ON ORDER, not arriving, and is never offered here;
4. **pool** - the site pools' own book: its free pile, then a later POOL order's on hand,
   which does raise an order-back (R34). The dealer hot-selling gate refuses the whole step;
5. **buy** - the whole unit at ``as_of + lead``.

**A STEP COVERS THE WHOLE UNIT OR IT GIVES NOTHING** (R10, R33). Sources combine INSIDE one
step - two bins of the group, two on-hand donors (R35) - and never across two: half a promise
off the free pile and half off somebody else's order is two different stories about one
delivery, and the captain ruled it out on AC-S4-2b ("the PO is taken whole ... the 16 on hand
stays free").

**Every step is also an OPTION** (R36): the date it would fulfil the unit, how many days late
that is, and whose order pays for it. Five of them travel with every walked unit, in step
order, at most one chosen - the contract is written out in
``fulfilmentPlanningService.ts`` ("LADDER v7.1: THE OPTIONS CONTRACT") and mirrored by
``schemas/project_board.py::BoardLadderOption``.

**What the caller does and this module does not.** Every candidate list arrives already read,
already windowed and already ORDERED (``ProjectSupplyService.use_candidates_for`` /
``order_borrow_candidates_for``, off the ONE ``supply_assignment.assign()`` the Stock Debt
view also reads, R21). This module walks them in the order given and never re-sorts or
re-derives a capacity.

**Incoming is not a step of its own.** An SPO is inside the ownership group's net already -
AutoCount's Available is ``on hand + SPO - SO`` - so step 1 answers with it where it is free
by the asker's date, as ``timely_spo`` rather than as a Reserve, because a hold cannot be
written against goods a picker cannot walk to. A document whose arrival has PASSED with
nothing received is not supply at all until somebody re-dates it (R31).

``attribute_sources`` answers "who gets the one pile" - several lines competing for one
location's opening stock and its dated incoming, resolved in PLAN 3.5's fixed order so the
same facts always produce the same answer and the database's row order never participates.
Untouched by v7.1.

Quantities are ``Decimal`` throughout. These figures are compared for exact equality at
confirmation, and a binary float does not survive that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: `YYYY-MM` - the Stock Debt cell a debt lands in. IMPORTED, never restated: the option's
#: `debt_month` and the view's own column key are the same string, and two spellings of one
#: key is how a lightbox comes to open on a month the cell did not mean.
from app.services.scm.supply_assignment import month_key

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
#: Retired by ladder v7.1 (R5): another group's FREE stock is step 1's second half now, and
#: free stock owes nobody a thing, so it is a Reserve rather than a Borrow. The constant
#: survives for reading frozen snapshots, exactly as `RUNG_INCOMING` does.
RUNG_CROSS_GROUP_BORROW = "cross_group_borrow"
#: Ladder v7.1 (`PLAN-scm-borrow-ladder-v7-stock-debt.md` 3.2). Step 2 borrows ON HAND held
#: by a LATER order; step 3 (S4) borrows the DOCUMENT a later order is waiting on. Both are
#: `borrow` kinds and both raise an order-back at the DONOR's own required date.
RUNG_ORDER_BORROW = "order_borrow"
RUNG_SUPPLY_BORROW = "supply_borrow"
RUNG_BUY = "buy"

# --------------------------------------------------------------------------- #
# The five options (R36, AC-S3-14)
# --------------------------------------------------------------------------- #
#
# The ladder walks five steps and the screen shows all five, answered, whether or not they
# were taken: a step the server omitted reads as a step nobody walked. The keys are the
# wire's own (`fulfilmentPlanningService.ts`, "LADDER v7.1: THE OPTIONS CONTRACT").

STEP_USE = "use"
STEP_ORDER_BORROW = "order_borrow"
STEP_SUPPLY_BORROW = "supply_borrow"
STEP_POOL = "pool"
STEP_BUY = "buy"

#: In walk order, always. The client renders what it is given and never sorts.
OPTION_STEPS = (
    STEP_USE,
    STEP_ORDER_BORROW,
    STEP_SUPPLY_BORROW,
    STEP_POOL,
    STEP_BUY,
)

#: The step in a planner's words. The SERVER's sentence, so two screens cannot spell one
#: step two ways.
STEP_LABELS = {
    STEP_USE: "Use our locations",
    STEP_ORDER_BORROW: "Borrow on hand from a later order",
    STEP_SUPPLY_BORROW: "Borrow incoming from a later order",
    STEP_POOL: "Take from the pool",
    STEP_BUY: "Buy",
}

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
    #: STEP 3 (`supply_borrow`, S4): WHICH DOCUMENT this quantity comes off, by ADDRESS -
    #: `supply_assignment`'s own event key, `spo:<allocation id>` or `po:<purchase order
    #: line id>`. PLAN 3.2 step 3 writes it `spo:<n> | po:<n>/<line>`; the id is the
    #: spelling of `<n>` that survives a re-import of the document, which the number is
    #: not. Addressing only, never rendered: the Confirm moves the placement link onto
    #: exactly this row (3.3) without a second lookup.
    supply_key: Optional[str] = None
    #: The same document as a PERSON names it - `SPO 202607-S0105`, `PO 202607-P0031
    #: line 3`. The SERVER's spelling, taken off the assignment event's own `ref`, so the
    #: sentence here and the row the Stock Debt drill prints cannot come to name one
    #: document two ways.
    supply_document: Optional[str] = None
    #: The day it lands: the SPO's arrival, or a PO line's `issue_date + lead time` (R29).
    #: This is the option's `fulfil_date` for step 3 and the date inside its sentence.
    arrival_date: Optional[date] = None

    @property
    def stated(self) -> str:
        """The whole phrase AC-B14 quotes: "Reserve 10: free stock at BRW ..."."""
        return f"{COMPONENT_LABELS[self.kind]} {qty_text(self.qty)}: {self.reason}"


@dataclass(frozen=True)
class Option:
    """One step of the ladder, answered (R36, AC-S3-14).

    Five of these travel with every walked line, in step order, whether or not the step
    was taken. `fulfil_date` and `days_late` are null TOGETHER and exactly when the step
    offered nothing: "nothing was offered" and "offered, on time" are different answers.
    `days_late` is never negative - landing before the required date is on time, not minus
    six days late.
    """

    step: str
    label: str
    #: Does this step cover the WHOLE planning unit (R10, R33)? A step that covers part of
    #: it is not an option, because half a unit is not a proposal.
    whole: bool
    fulfil_date: Optional[date] = None
    days_late: Optional[int] = None
    #: Whose order pays for it, by DOCUMENT NUMBER. Set on the two borrow steps only: `use`
    #: draws the free pile and `buy` orders new stock, so neither owes anybody.
    debt_so_number: Optional[str] = None
    debt_month: Optional[str] = None
    #: The step the engine proposed. At most ONE option carries it - the first whole one in
    #: step order - and none does when nothing covers the unit.
    chosen: bool = False


@dataclass(frozen=True)
class Walk:
    """What one walk produced: the composition, and every step it asked about."""

    components: Tuple[Component, ...]
    options: Tuple[Option, ...]


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
    """v4's sentence, kept for reading FROZEN snapshots that still carry the retired rung.

    Under v7.1 another group's free stock is step 1's second half and reads through
    `other_group_reason`: free means owed to nobody, so taking it is a Reserve and it
    raises no debt.
    """
    return f"{location} can lend {qty_text(qty)} from outside this group"


def other_group_reason(
    location: str,
    qty: Decimal,
    group_code: Optional[str],
    arrival_date: Optional[date] = None,
) -> str:
    """Step 1's second half (v7.1, R5, AC-S3-1): another PROJECT group's FREE pile.

    Free means owed to nobody, so there is no debt and no donor to name - which is exactly
    why it is walked before either borrow step and why it is a Reserve rather than a
    Borrow. The sentence says whose stock it is, because "40 from DC1-NT" beside a `-BB`
    line reads as an error until it says the pile was free.

    `arrival_date` is set when the free quantity is ON THE WATER rather than on a floor, and
    it is the day the WHOLE of the draw has landed by - the same rule the own half's
    `group_water_reason` follows. Without it an incoming container in another group read as
    stock available today, and the option table dated the whole proposal `today`.
    """
    whose = f" the {group_code} group" if group_code else " this line's group"
    when = f", arriving {date_text(arrival_date)}" if arrival_date else ""
    return (
        f"{location} has {qty_text(qty)} free outside{whose}{when}, and free stock is owed "
        "to nobody"
    )


def order_borrow_reason(
    qty: Decimal,
    location: str,
    donor_so_number: Optional[str],
    donor_line_no: Optional[int],
    donor_agent_code: Optional[str],
    donor_required_date: Optional[date],
) -> str:
    """Step 2's sentence (AC-S3-11, R27): what is borrowed, from whom, when they are due,
    and the month the debt lands in.

    `Borrow 30 on hand at MWH-IB from SO414285 line 4 (JEREMY, due 12 Nov 2026); its debt
    lands in Nov 2026`. Every clause is a fact the planner acts on: the quantity, that it
    is ON HAND (not a promise), where it physically is, whose order gives it up, and the
    column of the Stock Debt view it will appear in.
    """
    return f"Borrow {qty_text(qty)} on hand at {location}" + _donor_clause(
        donor_so_number, donor_line_no, donor_agent_code, donor_required_date
    )


def _donor_clause(
    donor_so_number: Optional[str],
    donor_line_no: Optional[int],
    donor_agent_code: Optional[str],
    donor_required_date: Optional[date],
) -> str:
    """" from SO414285 line 4 (JEREMY, due 12 Nov 2026); its debt lands in Nov 2026".

    The tail both borrow steps put on their own sentence, spelled ONCE: who gives the
    quantity up, when they are due, and the Stock Debt column the debt appears in. Two
    copies of it agreed by coincidence until step 3 needed a different opening clause.
    """
    who = donor_so_number or "an unnamed sales order"
    line_text = f" line {donor_line_no}" if donor_line_no is not None else ""
    inside: List[str] = []
    if donor_agent_code:
        inside.append(str(donor_agent_code))
    if donor_required_date is not None:
        inside.append(f"due {date_text(donor_required_date)}")
    named = f" ({', '.join(inside)})" if inside else ""
    debt = (
        f"; its debt lands in {month_text(donor_required_date)}"
        if donor_required_date is not None
        else "; its debt lands in the month it is due"
    )
    return f" from {who}{line_text}{named}{debt}"


def supply_borrow_reason(
    qty: Decimal,
    *,
    kind: str,
    document: Optional[str],
    arrival_date: Optional[date],
    donor_so_number: Optional[str] = None,
    donor_line_no: Optional[int] = None,
    donor_agent_code: Optional[str] = None,
    donor_required_date: Optional[date] = None,
) -> str:
    """Step 3's sentence (AC-S4-1).

    `Borrow 50 arriving 15 Sep 2026 (SPO 202607-S0105) from SO414285 line 4 (JEREMY, due
    12 Nov 2026); its debt lands in Nov 2026`. Incoming means SPO (31 Aug ruling, R-A): a
    PO is still ON ORDER rather than arriving, and step 3 no longer offers one, so `kind`
    reaching this function is always `"spo"` from a LIVE walk.

    The `kind == "po"` branch below is DEAD for every new proposal and kept only for an OLD
    stored decision being re-rendered: a frozen `SOSupplyDecision.line_snapshots` component
    saved before this ruling can still carry a `po:` supply key, and
    `_borrow_shortfalls`/`ProjectSupplyService` rebuilds that snapshot's sentence through
    this same function (`parse_supply_key(supply_key)[0]`) rather than a second one. Once no
    such snapshot is reachable any more this branch and the `kind` parameter can go.

    **TAKE, not Borrow, when nobody is waiting on the document.** A free document is owed to
    nobody, so there is no donor to name and no debt to state, and calling that a Borrow
    would put a debt month on a screen where none exists.
    """
    verb = "Borrow" if donor_so_number else "Take"
    named = document or "an unnamed document"
    when = date_text(arrival_date) if arrival_date else "an unstated date"
    if kind == "po":
        # Historical snapshot only - see the docstring above.
        head = f"{verb} {qty_text(qty)} on order ({named}, arriving about {when})"
    else:
        head = f"{verb} {qty_text(qty)} arriving {when} ({named})"
    if not donor_so_number:
        return head
    return head + _donor_clause(
        donor_so_number, donor_line_no, donor_agent_code, donor_required_date
    )


def pool_borrow_reason(
    qty: Decimal,
    location: str,
    donor_so_number: Optional[str],
    donor_required_date: Optional[date],
) -> str:
    """Step 4's borrow half (R34): a LATER pool order lends its on hand and is owed it back.

    The pool's free pile raises nothing (`pool_reason`); this does, because the quantity
    was already promised to somebody's order.
    """
    who = donor_so_number or "a later pool order"
    when = f", due {date_text(donor_required_date)}" if donor_required_date else ""
    debt = (
        f"; its debt lands in {month_text(donor_required_date)}"
        if donor_required_date is not None
        else ""
    )
    return f"Borrow {qty_text(qty)} on hand at pool {location} from {who}{when}{debt}"


def month_text(value: date) -> str:
    """"Nov 2026" - the Stock Debt column a debt lands in, spelled once."""
    return f"{_MONTHS[value.month - 1]} {value.year}"


def _whole_line_buy_reason(covered: Decimal, open_qty: Decimal) -> str:
    return (
        f"Only {qty_text(covered)} of {qty_text(open_qty)} can be covered from stock - buy "
        "the whole line"
    )


# --------------------------------------------------------------------------- #
# One line's composition (PLAN 3.2, amended by section E)
# --------------------------------------------------------------------------- #


def walk_line(
    *,
    open_qty: Any,
    line_no: Optional[int] = None,
    required_date: Optional[date] = None,
    #: Today, for the option dates (R36). `None` reads the clock, which is what a caller
    #: with no pinned simulation wants; the board states its own so a pinned run is
    #: reproducible.
    as_of: Optional[date] = None,
    #: The product's lead time, for Buy's own fulfil date. `None` is the documented default.
    lead_time_days: Optional[int] = None,
    #: The asking line's own bin. READ since v7.1, and only for the option dates: a
    #: quantity that is not already there costs a transfer, `transfer_days` below (R36).
    fulfilment_location: Optional[str] = None,
    #: Days a transfer between two bins costs an option's fulfil date, when the quantity is
    #: not already at the asking line's own location (R36). Default 0 (31 Aug ruling, R-B):
    #: the policy field `app.services.scm.priority.FULFILMENT_SETTINGS_DEFAULTS` carries,
    #: the caller reads off `_fulfilment_settings()` and passes through.
    transfer_days: int = 0,
    group_code: Optional[str] = None,
    is_dealer_hot_selling: bool = False,
    #: Accepted and NOT read since ladder v4 (section 1d). 3.3a capped a project
    #: hot-selling line's pool draw at the pool's own signed availability; the pile's net
    #: now bounds every draw the same way, for every item.
    is_project_hot_selling: bool = False,
    pools: Optional[Sequence[Mapping[str, Any]]] = None,
    is_discontinued: bool = False,
    reorder_coverage_until: Optional[date] = None,
    group_take_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    other_group_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    order_borrow_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    supply_borrow_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    pool_borrow_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    outside_reserve_window: bool = False,
    group_offer: Optional[Decimal] = None,
    pools_net: Optional[Decimal] = None,
) -> Walk:
    """LADDER V7.1: the five steps, in order, each answered (PLAN 3.2, R1/R13/R33/R36).

    0. beyond the reserve window, or beyond `reorder_coverage_until` -> no step runs and
       the whole of `open_qty` is a single Buy naming the bound that fired. An UNDATED line
       is never beyond either bound - both comparisons need two dates - so it falls through
       to the full walk;
    1. **use** (`group_take`): the asker's own ownership group's FREE pile at its own date,
       drawn own location first then the siblings by code (`group_take_candidates`, already
       date-aware and already capped by the caller), and then the OTHER project groups'
       free piles (`other_group_candidates`). Free means owed to nobody, so this step
       raises no debt and is walked before either borrow;
    2. **order_borrow**: ON HAND held by a LATER order (`order_borrow_candidates`, already
       windowed and ordered by the caller: same agent, latest date, same group, same
       warehouse). Several donors may combine for one unit (R35). Every take raises an
       order-back at the DONOR's own required date;
    3. **supply_borrow**: the SPO a later order is waiting on (`supply_borrow_candidates`,
       already narrowed by the caller to the ONE document that covers the whole unit,
       R33). Incoming means SPO (31 Aug ruling, R-A) - a PO never reaches this list. A row
       with no donor is free supply and is taken rather than borrowed;
    4. **pool**: the site pools' own book - its free pile (`pools`/`pools_net`, the dealer
       hot-selling gate in front of the whole step), then a later POOL order's on hand
       (`pool_borrow_candidates`), which does raise an order-back (R34);
    5. **buy**: the whole unit.

    **A STEP COVERS THE WHOLE UNIT OR IT GIVES NOTHING** (R10, R33). Sources COMBINE inside
    one step - two bins of the group, two donors of step 2 - and never across two, because
    half a promise from the free pile and half from somebody else's order is two different
    stories about one delivery. The first step that covers the whole of `open_qty` is the
    proposal; if none does, the whole unit is a Buy.

    Each step's inputs are already computed and already ORDERED by the caller; this
    function walks them in the order given and never re-sorts or re-derives a capacity.

    Returns the composition AND the five options (R36): every step with the date it would
    fulfil the unit, how late that is, and whose order pays for it.
    """
    today = as_of or date.today()
    lead = DEFAULT_LEAD_TIME_DAYS if lead_time_days is None else max(int(lead_time_days), 0)
    buy_date = today + timedelta(days=lead)
    open_amount = max(_dec(open_qty), ZERO)
    if open_amount <= ZERO:
        return Walk(components=(), options=())

    # 0. Beyond either bound, NO step runs at all and the whole line is bought. Two bounds,
    #    one rule: whichever of them the line is beyond decides it, and the reason names the
    #    one that fired. Purchasing's stated coverage date is checked first because it is a
    #    date a person set and can point at; the window is the derived one.
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
        return Walk(
            components=(Component(kind=BUY, qty=open_amount, reason=beyond, rung=RUNG_BUY),),
            options=_options(
                required_date=required_date,
                buy_date=buy_date,
                offers={},
                chosen=STEP_BUY,
                need=open_amount,
            ),
        )

    offers: Dict[str, "_Offer"] = {}

    # 1. use -----------------------------------------------------------------------------
    step_use = _Offer()
    _draw_group(step_use, group_take_candidates, open_amount, group_code, group_offer)
    _draw_other_groups(step_use, other_group_candidates, open_amount, group_code)
    offers[STEP_USE] = step_use

    # 2. order_borrow ---------------------------------------------------------------------
    offers[STEP_ORDER_BORROW] = _draw_order_borrow(
        order_borrow_candidates, open_amount, RUNG_ORDER_BORROW
    )

    # 3. supply_borrow - the DOCUMENT a later order is waiting on, ONE document whole
    #    (R33). The caller has already chosen which document that is and refused every
    #    combination of two, so this walks one document's rows and nothing else.
    offers[STEP_SUPPLY_BORROW] = _draw_supply_borrow(
        supply_borrow_candidates, open_amount
    )

    # 4. pool ------------------------------------------------------------------------------
    step_pool = _Offer()
    if not is_dealer_hot_selling:
        _draw_pool(step_pool, pools, pools_net, open_amount)
        if step_pool.qty < open_amount:
            # The pool's FREE pile could not cover it, so its own later orders are asked -
            # and that half raises a debt (R34). Never mixed with the free half: one step,
            # one story.
            borrowed = _draw_order_borrow(pool_borrow_candidates, open_amount, RUNG_POOL)
            if borrowed.qty >= open_amount:
                step_pool = borrowed
    offers[STEP_POOL] = step_pool

    chosen: Optional[str] = None
    for step in (STEP_USE, STEP_ORDER_BORROW, STEP_SUPPLY_BORROW, STEP_POOL):
        if offers[step].qty >= open_amount and offers[step].components:
            chosen = step
            break

    options = _options(
        required_date=required_date,
        buy_date=buy_date,
        offers=offers,
        chosen=chosen or STEP_BUY,
        need=open_amount,
        as_of=today,
        own_location=fulfilment_location,
        transfer_days=transfer_days,
    )
    if chosen is None:
        covered = max(
            (offer.qty for offer in offers.values()), default=ZERO
        )
        return Walk(
            components=(
                Component(
                    kind=BUY,
                    qty=open_amount,
                    reason=_whole_line_buy_reason(min(covered, open_amount), open_amount),
                    rung=RUNG_BUY,
                ),
            ),
            options=options,
        )
    return Walk(components=tuple(offers[chosen].components), options=options)


def propose_line(**kwargs: Any) -> Tuple[Component, ...]:
    """The proposed composition for one line - `walk_line`'s components, and nothing else.

    Two names because two questions: most callers want what to promise, and only the board
    also wants the five options behind it. One implementation, so they cannot drift.
    """
    return walk_line(**kwargs).components


@dataclass
class _Offer:
    """What one step put on the table, while the walk is building it."""

    qty: Decimal = ZERO
    components: List[Component] = None  # type: ignore[assignment]
    #: The day the WHOLE of this step has landed by - today for stock on a floor, the
    #: latest arrival when part of it is on the water.
    arrival: Optional[date] = None
    #: Whether anything in it has to be carried to the asking line's own bin.
    locations: List[str] = None  # type: ignore[assignment]
    #: The largest donor, for the option's `debt_so_number` / `debt_month`.
    donor_so_number: Optional[str] = None
    donor_qty: Decimal = ZERO
    donor_required_date: Optional[date] = None

    def __post_init__(self) -> None:
        if self.components is None:
            self.components = []
        if self.locations is None:
            self.locations = []

    def add(self, component: Component, *, arrival: Optional[date] = None) -> None:
        self.components.append(component)
        self.qty += component.qty
        if component.source_location:
            self.locations.append(component.source_location)
        if arrival is not None and (self.arrival is None or arrival > self.arrival):
            self.arrival = arrival
        if component.donor_so_number and component.qty > self.donor_qty:
            self.donor_qty = component.qty
            self.donor_so_number = component.donor_so_number
            self.donor_required_date = component.donor_required_date


def _draw_group(
    offer: "_Offer",
    candidates: Optional[Sequence[Mapping[str, Any]]],
    need: Decimal,
    group_code: Optional[str],
    group_offer: Optional[Decimal],
) -> None:
    """Step 1a: the asker's OWN ownership group, in the caller's own draw order.

    A candidate marked `water` is the share of the group's offer that is on the water
    rather than on a floor; it is composed as `timely_spo` and never as a Reserve, because
    a hold cannot be written against goods a picker cannot walk to.
    """
    for candidate in candidates or []:
        left = need - offer.qty
        if left <= ZERO:
            break
        location = candidate.get("location")
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if not location or capacity <= ZERO:
            continue
        take = min(left, capacity)
        water = bool(candidate.get("water"))
        arrival = candidate.get("arrival_date") if water else None
        offer.add(
            Component(
                kind=TIMELY_SPO if water else RESERVE,
                qty=take,
                reason=(
                    group_water_reason(
                        str(location), take, group_code, group_offer, arrival
                    )
                    if water
                    else group_take_reason(str(location), take, group_code, group_offer)
                ),
                source_location=str(location),
                rung=RUNG_GROUP_TAKE,
            ),
            arrival=arrival,
        )


def _draw_other_groups(
    offer: "_Offer",
    candidates: Optional[Sequence[Mapping[str, Any]]],
    need: Decimal,
    group_code: Optional[str],
) -> None:
    """Step 1b (R5, AC-S3-1): the OTHER project groups' free piles.

    Same step, same rung, no debt: free stock is owed to nobody, whichever group's bin it
    happens to sit in. The site pools are never here - they are step 4, and taking one does
    raise a debt (R34).

    A candidate marked `water` is composed as `timely_spo` and dated by its arrival, exactly
    as the own half does it: another group's incoming document is no more pickable than this
    group's, and composing it as a Reserve wrote a hold against goods on a ship and dated
    the whole option `today`.
    """
    for candidate in candidates or []:
        left = need - offer.qty
        if left <= ZERO:
            break
        location = candidate.get("location")
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if not location or capacity <= ZERO:
            continue
        take = min(left, capacity)
        water = bool(candidate.get("water"))
        arrival = candidate.get("arrival_date") if water else None
        offer.add(
            Component(
                kind=TIMELY_SPO if water else RESERVE,
                qty=take,
                reason=other_group_reason(str(location), take, group_code, arrival),
                source_location=str(location),
                rung=RUNG_GROUP_TAKE,
            ),
            arrival=arrival,
        )


def _draw_order_borrow(
    candidates: Optional[Sequence[Mapping[str, Any]]],
    need: Decimal,
    rung: str,
) -> "_Offer":
    """Steps 2, 3 and 4b: a LATER order's supply, with an order-back at the donor's date.

    Several donors may combine for one unit (R35): they are one timing, because the stock
    is on a floor today whichever order it was promised to. The caller has already ordered
    them (same agent, latest date, same group, same warehouse - R4, R19) and this walks
    that order.
    """
    offer = _Offer()
    for candidate in candidates or []:
        left = need - offer.qty
        if left <= ZERO:
            break
        location = candidate.get("location")
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if not location or capacity <= ZERO:
            continue
        take = min(left, capacity)
        donor_date = candidate.get("donor_required_date")
        arrival = candidate.get("arrival_date")
        offer.add(
            Component(
                kind=BORROW,
                qty=take,
                reason=(
                    pool_borrow_reason(
                        take, str(location), candidate.get("donor_so_number"), donor_date
                    )
                    if rung == RUNG_POOL
                    else order_borrow_reason(
                        take,
                        str(location),
                        candidate.get("donor_so_number"),
                        candidate.get("donor_line_no"),
                        candidate.get("donor_agent_code"),
                        donor_date,
                    )
                ),
                source_location=str(location),
                rung=rung,
                donor_so_number=candidate.get("donor_so_number"),
                donor_line_no=candidate.get("donor_line_no"),
                donor_agent_code=candidate.get("donor_agent_code"),
                same_agent=bool(candidate.get("same_agent")),
                order_back_qty=take,
                donor_core_line_id=candidate.get("donor_core_line_id"),
                donor_required_date=donor_date,
            ),
            arrival=arrival,
        )
    return offer


def _draw_supply_borrow(
    candidates: Optional[Sequence[Mapping[str, Any]]],
    need: Decimal,
) -> "_Offer":
    """Step 3: ONE document, whole (R33), in the rows the caller chose it as.

    Every row here belongs to the SAME document - the caller picks the nearest arriving SPO
    (incoming means SPO, 31 Aug ruling R-A) and returns nothing at all when no single
    document covers the unit. So this never has to decide between two of them, which is
    the point: half a promise off one document and half off another is two arrival dates
    for one delivery.

    A row with no donor is FREE - nobody is waiting on that part of the document - so it is
    taken rather than borrowed, and it carries no order-back: free supply is owed to nobody,
    exactly as step 1's free pile is.
    """
    offer = _Offer()
    for candidate in candidates or []:
        left = need - offer.qty
        if left <= ZERO:
            break
        capacity = max(_dec(candidate.get("qty")), ZERO)
        if capacity <= ZERO:
            continue
        take = min(left, capacity)
        arrival = candidate.get("arrival_date")
        donor_so_number = candidate.get("donor_so_number")
        donor_date = candidate.get("donor_required_date")
        location = candidate.get("location")
        offer.add(
            Component(
                kind=BORROW,
                qty=take,
                reason=supply_borrow_reason(
                    take,
                    kind=str(candidate.get("supply_kind") or "spo"),
                    document=candidate.get("supply_document"),
                    arrival_date=arrival,
                    donor_so_number=donor_so_number,
                    donor_line_no=candidate.get("donor_line_no"),
                    donor_agent_code=candidate.get("donor_agent_code"),
                    donor_required_date=donor_date,
                ),
                source_location=str(location) if location else None,
                rung=RUNG_SUPPLY_BORROW,
                donor_so_number=donor_so_number,
                donor_line_no=candidate.get("donor_line_no"),
                donor_agent_code=candidate.get("donor_agent_code"),
                same_agent=bool(candidate.get("same_agent")),
                # Only what a DONOR gives up is owed back. A free document owes nobody.
                order_back_qty=take if donor_so_number else None,
                donor_core_line_id=candidate.get("donor_core_line_id"),
                donor_required_date=donor_date,
                supply_key=candidate.get("supply_key"),
                supply_document=candidate.get("supply_document"),
                arrival_date=arrival,
            ),
            arrival=arrival,
        )
    return offer


def _draw_pool(
    offer: "_Offer",
    pools: Optional[Sequence[Mapping[str, Any]]],
    pools_net: Optional[Decimal],
    need: Decimal,
) -> None:
    """Step 4a: the site pools as ONE pile, own site first (the caller's draw order).

    The pile offers `max(pools_net, 0)` and not a unit more - `BRW -103` beside `DC1 +1`
    nets -102 and offers NOTHING, where per-pool arithmetic would have offered the 1, which
    is stock the shared book already owes at BRW. Each pool's own `free` says WHERE the
    quantity can come from; the net says HOW MUCH. Nobody is owed a free pool draw back
    (AC-L13 as it applies to the free half; the BORROW half is 4b).
    """
    left_in_pile = max(_dec(pools_net), ZERO)
    for pool in pools or []:
        left = need - offer.qty
        if left <= ZERO or left_in_pile <= ZERO:
            break
        location = pool.get("location")
        if not location:
            continue
        capacity = min(max(_dec(pool.get("free")), ZERO), left_in_pile)
        if capacity <= ZERO:
            continue
        take = min(left, capacity)
        offer.add(
            Component(
                kind=RESERVE,
                qty=take,
                reason=pool_reason(str(location), take, pools_net),
                source_location=str(location),
                rung=RUNG_POOL,
            )
        )
        left_in_pile -= take


def _options(
    *,
    required_date: Optional[date],
    buy_date: date,
    offers: Mapping[str, "_Offer"],
    chosen: str,
    need: Decimal = ZERO,
    as_of: Optional[date] = None,
    own_location: Optional[str] = None,
    transfer_days: int = 0,
) -> Tuple[Option, ...]:
    """The five rows the trail and the decision panel print (R36, AC-S3-14).

    FIVE, always, in step order. A step that offered nothing sends `fulfil_date` and
    `days_late` NULL together - "nothing was offered" and "offered, on time" are different
    answers and the table shows them differently - and `days_late` is never negative,
    because landing before the required date is on time rather than minus six days late.
    """
    today = as_of or date.today()
    out: List[Option] = []
    for step in OPTION_STEPS:
        if step == STEP_BUY:
            out.append(
                Option(
                    step=step,
                    label=STEP_LABELS[step],
                    whole=True,
                    fulfil_date=buy_date,
                    days_late=_days_late(buy_date, required_date),
                    chosen=chosen == STEP_BUY,
                )
            )
            continue
        offer = offers.get(step)
        whole = bool(offer and offer.components and offer.qty >= need > ZERO)
        if not whole:
            out.append(Option(step=step, label=STEP_LABELS[step], whole=False))
            continue
        fulfil = offer.arrival or today
        if transfer_days and any(code != own_location for code in offer.locations):
            fulfil = max(fulfil, today + timedelta(days=transfer_days))
        debt = step in (STEP_ORDER_BORROW, STEP_SUPPLY_BORROW, STEP_POOL)
        out.append(
            Option(
                step=step,
                label=STEP_LABELS[step],
                whole=True,
                fulfil_date=fulfil,
                days_late=_days_late(fulfil, required_date),
                debt_so_number=offer.donor_so_number if debt else None,
                debt_month=(
                    month_key(offer.donor_required_date)
                    if debt and offer.donor_required_date is not None
                    else None
                ),
                chosen=chosen == step,
            )
        )
    return tuple(out)


def _days_late(fulfil: date, required_date: Optional[date]) -> int:
    """Never negative: landing before the required date is ON TIME, not minus six days."""
    if required_date is None:
        return 0
    return max((fulfil - required_date).days, 0)


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
