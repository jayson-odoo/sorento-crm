"""The golden set for the Stage 1C front-planning engine, written before the engine.

PRINCIPLES.md phase 2 is explicit about deterministic engines: "the golden-set expected
numbers are written as failing tests first, and the code is built to satisfy them". This
module is those numbers. It holds no assertions and touches no database - it is plain data,
so the expected answers cannot quietly drift to match whatever the implementation ends up
doing, and so the same cases can be read by a route test, a service test or a fixture
builder later without any of them owning the numbers.

Every case is traced to the criterion it comes from in
`documentation/plans/scm/UAC-scm-front-planning.md` and, for the last two, in
`documentation/plans/scm/scm-cs-planning-uat-acceptance-criteria.md`:

* **AC-B08** the hot-selling worked case, exactly as PLAN section 3.3 writes it: dealer
  stock is untouchable and the BRW pool is only usable above its own reorder level.
* **AC-B02** the two-line attribution, which is where the shared ordering in PLAN section
  3.5 earns its keep: opening stock before same-day SPO, lines by required date then SO
  number then line number, and the SAME answer when the database hands the rows back in the
  other order.
* **AC-B13** confirmed cover is gone from the pool: the SPO a project line was promised is
  not free for the retail line behind it.
* **AC-B12** the balance invariant, with the reason string PLAN section 3.2 requires beside
  every proposed component - a quantity shown with raw evidence and no stated reason does
  not satisfy AC-B14.
* **AC-L2** ladder v3's reordering (25 August 2026): the ownership group, this line's own
  location included, is drawn BEFORE the shared pool. Under v2 the pool went first and a
  group that held the stock sat untouched while the shared pile paid for the line.
* **AC-L1** ladder v5's rung 0, both sides: a line due beyond the lead-time window walks NO
  rung at all however much sits beside it, and is bought entire. Under v2 such a line still
  walked the two surplus rungs; under v3 and v4 it still ran rung 1, incoming, on the
  grounds that supply already on its way is already bought.
* **AC-L7 / AC-L8 / AC-L10** ladder v4 (26 August 2026): availability is the OWNERSHIP
  GROUP's and the five site pools' respectively, never one warehouse's. A group that nets
  negative offers nothing however much sits at one of its sites; the pools net as one pile,
  so `BRW -103` beside `DC1 +1` offers nothing rather than the 1; and an SPO inside a
  negative group net is owed to that backlog, so it covers no line of it.
* **AC-V7** ladder v5 (26 August 2026, section 1e): the four questions, and the pool is the
  second of them. 24 needed against 268 free in the pile and 100 at another group within
  the cap is Pool 24 - the borrow question is never reached.

**WHAT LADDER V5 MOVED IN THIS FILE**, regenerated with the captain's sign-off (AC-V9):
`timely_spo` is a kind the engine no longer proposes, because an SPO is inside the ownership
group's net where AutoCount already counts it. `AC-L1`'s first case answered `timely_spo 40`
and now answers `buy 40`; `AC-B12`'s balance invariant demonstrated `timely_spo 10 + pool 60`
and now demonstrates `group 10 + pool 60` (same 70, same two reasons stated, one rung
different); `AC-L10` keeps its `buy 10` and loses the sentence about netting rung 1. Nothing
else changed answer.

Quantities are `Decimal`, never float: these numbers are compared for exact equality and a
binary-float 0.1 does not survive that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

# The four component kinds of the balance invariant, in the order PLAN section 3.1 writes
# it: open_so_qty = timely_spo_coverage + reserve_qty + borrow_qty + buy_qty.
TIMELY_SPO = "timely_spo"
RESERVE = "reserve"
BORROW = "borrow"
BUY = "buy"

#: How a component reads on screen. `Reserve` and `Buy` are the words CS uses, and the
#: allocation `source_type` values they map onto are the module's own (`own`/`brw` are
#: Reserve, `other_project`/`other_location` are Borrow, `order` is Buy).
COMPONENT_LABELS = {
    TIMELY_SPO: "Timely SPO",
    RESERVE: "Reserve",
    BORROW: "Borrow",
    BUY: "Buy",
}

REQUIRED_DATE = date(2027, 3, 1)

#: The day every walk below is taken on. PINNED rather than `date.today()`: ladder v8's share
#: rule reads which side of `immediate_window_days` a line falls on, so a case that let the
#: clock decide would answer one way this year and another the next.
AS_OF = date(2026, 9, 2)

# The locations the cases talk about. Codes, not ids: nothing here is a UUID, and a golden
# case that named one would be unreadable in a failure message.
DEALER_LOCATION = "DLR-KL"
POOL_LOCATION = "BRW"
OWN_LOCATION = "SRT-KL"
#: Ladder v3's group rung talks in ownership-group codes: a `*-BB` location and its sibling
#: at another site. The line's OWN location is a group source again (section 1b rung 2).
GROUP_OWN_LOCATION = "BRW-BB"
GROUP_SIBLING_LOCATION = "DC1-BB"


def qty_text(value: Decimal) -> str:
    """A quantity as a person writes it, with no scientific notation.

    `Decimal("40").normalize()` is `4E+1`, which in a reason string would read as a defect
    rather than forty units.
    """
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Component:
    """One proposed component: how much, from where, and WHY (PLAN 3.2, AC-B14)."""

    kind: str
    qty: Decimal
    #: The rule's own sentence. Deterministic for the same snapshot, never LLM-written,
    #: frozen with the line snapshot at confirmation.
    reason: str
    #: Where the quantity comes from. The line fulfilment location for own-location Reserve
    #: and timely SPO cover, the pool warehouse for BRW-pool Reserve, the donor location for
    #: Borrow. Buy has none: it is not held anywhere yet.
    source_location: str | None = None

    @property
    def stated(self) -> str:
        """The whole phrase as AC-B14 quotes it: "Reserve 10: free stock at BRW ..."."""
        return f"{COMPONENT_LABELS[self.kind]} {qty_text(self.qty)}: {self.reason}"


@dataclass(frozen=True)
class ProposalCase:
    """One line's composition: what the engine is given, and what it must propose."""

    ac: str
    title: str
    #: Keyword arguments for `front_planning_engine.propose_line`.
    inputs: Mapping[str, Any]
    #: Only the NON-ZERO components. A component that contributes nothing is not proposed,
    #: and pinning a zero here would force the engine to emit a reason for a quantity that
    #: does not exist.
    components: tuple[Component, ...]

    @property
    def open_qty(self) -> Decimal:
        return self.inputs["open_qty"]

    def qty_of(self, kind: str) -> Decimal:
        return sum(
            (c.qty for c in self.components if c.kind == kind), Decimal("0")
        )

    def qty_from(self, location: str) -> Decimal:
        return sum(
            (c.qty for c in self.components if c.source_location == location),
            Decimal("0"),
        )


@dataclass(frozen=True)
class AttributionCase:
    """Several lines competing for one location's dated supply (PLAN 3.5)."""

    ac: str
    title: str
    #: Keyword arguments for `front_planning_engine.attribute_sources`. `demand_lines` and
    #: `supply_events` are lists, so `reversed_inputs` can hand them back the other way up.
    inputs: Mapping[str, Any]
    #: Expected components per line, keyed by `(so_number, line_no)`. Two lines numbered 10
    #: on two different orders are a real case, so the SO number is part of the key; the
    #: internal line id is the engine's own stable key and is never displayed.
    expected: Mapping[tuple[str, int], tuple[Component, ...]]

    @property
    def reversed_inputs(self) -> dict[str, Any]:
        """The same case with the database's row order flipped.

        AC-B02 requires an identical answer either way, which is the whole reason the
        ordering contract exists: "database return order never participates".
        """
        flipped = dict(self.inputs)
        flipped["demand_lines"] = list(reversed(self.inputs["demand_lines"]))
        flipped["supply_events"] = list(reversed(self.inputs["supply_events"]))
        return flipped

    def open_qty_of(self, key: tuple[str, int]) -> Decimal:
        so_number, line_no = key
        for line in self.inputs["demand_lines"]:
            if (line["so_number"], line["line_no"]) == (so_number, line_no):
                return line["open_qty"]
        raise KeyError(key)


# --------------------------------------------------------------------------- AC-B08


HOT_SELLING_WORKED_CASE = ProposalCase(
    ac="AC-B08",
    title=(
        "dealer hot-selling product: the pool contributes nothing and the whole line is a "
        "Buy - under ladder v8 because 70 is more than the 60 the pool can spare a far "
        "line (R-B), not because the item is hot (R-A retired that gate)"
    ),
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("70"),
        "line_no": 10,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": DEALER_LOCATION,
        "is_dealer_hot_selling": True,
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("120"), "available": Decimal("120")}
        ],
        "pools_net": Decimal("120"),
        # No SPO arrives by the required date, so timely coverage is zero and is not
        # proposed at all.
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=BUY,
            qty=Decimal("70"),
            reason="Only 0 of 70 can be covered from stock - buy the whole line",
        ),
    ),
)


PROJECT_HOT_SELLING_WORKED_CASE = ProposalCase(
    ac="AC-B08",
    title=(
        "project hot-selling product: the pile's own net bounds the draw exactly as it "
        "bounds a cold item's (ladder v4 replaces 3.3a's per-pool cap) - and under ladder "
        "v8 the SHARE of that net bounds it again, so a far line of 40 against an allowance "
        "of 20 takes nothing and buys (R-B: there is time to buy)"
    ),
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("40"),
        "line_no": 12,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": OWN_LOCATION,
        "is_project_hot_selling": True,
        "pools": [
            # 120 sit free at the pool and the five pools net 40 between them, so 40 is
            # what may be drawn - which is the whole line. Under 3.3a the same answer came
            # from this pool's OWN signed availability; under v4 it comes from the pile's,
            # and the reason says whose number it is.
            {"location": POOL_LOCATION, "free": Decimal("120"), "available": Decimal("40")}
        ],
        "pools_net": Decimal("40"),
        "is_discontinued": False,
    },
    components=(
        # v4 to v7.1: `Reserve 40` off the pool, because the whole net was on the table.
        # v8 keeps half of it for dealers, so 20 is what a project may have, and a line due
        # in six months takes the pool WHOLE or not at all - 40 does not fit in 20.
        Component(
            kind=BUY,
            qty=Decimal("40"),
            reason="Only 0 of 40 can be covered from stock - buy the whole line",
        ),
    ),
)


# --------------------------------------------------------------------------- AC-B12


BALANCE_INVARIANT_CASE = ProposalCase(
    ac="AC-B12",
    title="every component carries its reason and the terms add up to the open quantity",
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("70"),
        "line_no": 10,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_LOCATION,
        "group_code": "BB",
        "is_dealer_hot_selling": False,
        # LADDER V7.1 (R33): the components of one proposal come from ONE step. So the
        # invariant is stated over step 1's two halves - the ownership group's 10 and
        # another project group's 60, both FREE stock and both owed to nobody - rather than
        # over the group plus the pool, which v7.1 no longer mixes.
        "group_take_candidates": [
            {"location": GROUP_OWN_LOCATION, "qty": Decimal("10")},
        ],
        "group_offer": Decimal("70"),
        "other_group_candidates": [
            {"location": "DC1-NTC", "qty": Decimal("60")},
        ],
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("60"), "available": Decimal("60")}
        ],
        "pools_net": Decimal("60"),
        "is_discontinued": False,
    },
    components=(
        # The two sentences AC-B14 quotes verbatim.
        Component(
            kind=RESERVE,
            qty=Decimal("10"),
            reason="BRW-BB gives 10 of the 70 the BB group can cover this line with",
            source_location=GROUP_OWN_LOCATION,
        ),
        # RE-BLESSED under R-M (3 Sep 2026): the sentence states the PILE and what the cap
        # now makes true of it. Old reading: "DC1-NTC has 60 free outside the BB group, and
        # free stock is owed to nobody". The quantity is unchanged - the take and the pile
        # are both 60 here - and this case pins the wording where the caller names neither
        # the lending group nor the day the pile was measured on.
        Component(
            kind=RESERVE,
            qty=Decimal("60"),
            reason=(
                "DC1-NTC has 60 free outside the BB group, none of it owed to a later order"
            ),
            source_location="DC1-NTC",
        ),
    ),
)

#: The exact strings AC-B14 prints. Pinned separately so a reworded reason fails the test
#: that owns the criterion rather than four unrelated ones.
BALANCE_INVARIANT_STATED = (
    "Reserve 10: BRW-BB gives 10 of the 70 the BB group can cover this line with",
    "Reserve 60: DC1-NTC has 60 free outside the BB group, none of it owed to a later order",
)


# --------------------------------------------------------------------------- AC-B02


TWO_LINE_ATTRIBUTION_CASE = AttributionCase(
    ac="AC-B02",
    title="opening stock goes to the first line, the same-day SPO to the second",
    inputs={
        "product_code": "CB6633",
        "warehouse_code": OWN_LOCATION,
        "opening_stock": Decimal("10"),
        "supply_events": [
            # One SPO of 10 arriving ON the required date. Same-day counts, and supply is
            # processed before demand on the same date.
            {
                "kind": "spo",
                "arrival_date": REQUIRED_DATE,
                "qty": Decimal("10"),
                "spo_number": "202703-S0011",
                "spo_line_no": 1,
            }
        ],
        "demand_lines": [
            {
                "so_number": "SO-100",
                "line_no": 10,
                "line_id": "aaaaaaaa-0000-0000-0000-000000000010",
                "open_qty": Decimal("10"),
                "required_date": REQUIRED_DATE,
            },
            {
                "so_number": "SO-100",
                "line_no": 20,
                "line_id": "aaaaaaaa-0000-0000-0000-000000000020",
                "open_qty": Decimal("10"),
                "required_date": REQUIRED_DATE,
            },
        ],
    },
    expected={
        ("SO-100", 10): (
            Component(
                kind=RESERVE,
                qty=Decimal("10"),
                reason="free stock at SRT-KL covers the need by the required date",
                source_location=OWN_LOCATION,
            ),
        ),
        ("SO-100", 20): (
            Component(
                kind=TIMELY_SPO,
                qty=Decimal("10"),
                reason="SPO 202703-S0011 arrives on 1 Mar 2027, by the required date",
                source_location=OWN_LOCATION,
            ),
        ),
    },
)


# --------------------------------------------------------------------------- AC-B13


CONFIRMED_COVER_CASE = AttributionCase(
    ac="AC-B13",
    title="the SPO a project line was promised is not free for the retail line behind it",
    inputs={
        "product_code": "CB6633",
        "warehouse_code": OWN_LOCATION,
        # Nothing on hand: the SPO is the only supply at this location.
        "opening_stock": Decimal("0"),
        "supply_events": [
            {
                "kind": "spo",
                "arrival_date": REQUIRED_DATE,
                "qty": Decimal("10"),
                "spo_number": "202703-S0012",
                "spo_line_no": 1,
            }
        ],
        "demand_lines": [
            # The confirmed project line comes first: its cover is already claimed, so it
            # must not be offered to anybody else.
            {
                "so_number": "SO-200",
                "line_no": 10,
                "line_id": "bbbbbbbb-0000-0000-0000-000000000010",
                "open_qty": Decimal("10"),
                "required_date": REQUIRED_DATE,
                "demand_class": "project",
                "is_confirmed": True,
            },
            {
                "so_number": "SO-201",
                "line_no": 10,
                "line_id": "bbbbbbbb-0000-0000-0000-000000000020",
                "open_qty": Decimal("10"),
                "required_date": REQUIRED_DATE,
                "demand_class": "retail",
                "is_confirmed": False,
            },
        ],
    },
    expected={
        ("SO-200", 10): (
            Component(
                kind=TIMELY_SPO,
                qty=Decimal("10"),
                reason="SPO 202703-S0012 arrives on 1 Mar 2027, by the required date",
                source_location=OWN_LOCATION,
            ),
        ),
        # The retail line behind it. The SPO is spoken for and the location holds nothing,
        # so its whole quantity is uncovered need - which is the criterion's point.
        ("SO-201", 10): (
            Component(
                kind=BUY,
                qty=Decimal("10"),
                reason="remaining uncovered need",
            ),
        ),
    },
)

#: AC-B13's own sentence: "Given Project open 10 covered by SPO 10, Retail outstanding 10,
#: and stock 0 at one location, then Retail need is 10, not 0."
CONFIRMED_COVER_RETAIL_KEY = ("SO-201", 10)
CONFIRMED_COVER_RETAIL_NEED = Decimal("10")


GROUP_BEFORE_POOL_CASE = ProposalCase(
    ac="AC-L2",
    title=(
        "ladder v8 (R-A) REVERSES this case: the site pool is asked FIRST, and 100 inside "
        "its 500 allowance is taken whole from the pool - the group's 70 is never reached"
    ),
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("100"),
        "line_no": 14,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_LOCATION,
        "group_code": "BB",
        # The caller hands the group over in draw order: own location, then the siblings by
        # site. The engine walks what it is given and never re-sorts.
        "group_take_candidates": [
            {"location": GROUP_OWN_LOCATION, "qty": Decimal("40")},
            {"location": GROUP_SIBLING_LOCATION, "qty": Decimal("30")},
        ],
        # Ladder v4 (26 August 2026): the two bounds the rungs obey. The group can cover 70
        # of this line and the pools hold 1000 between them, so the SHAPE of the answer is
        # what it always was - what changed is that both numbers are now the set's, and the
        # reason beside each quantity says whose.
        "group_offer": Decimal("70"),
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("1000"), "available": Decimal("1000")}
        ],
        "pools_net": Decimal("1000"),
        "is_discontinued": False,
    },
    components=(
        # v3 drew the group first and let the pool pay the difference (40 + 30 + 30), which
        # ladder v7.1 had already refused - R10 gives a step the whole unit or nothing. v8
        # asks the pool BEFORE the group (R-A): 100 fits inside half of the 1000 the pools
        # net, so the pool answers the line whole and the group keeps its 70.
        Component(
            kind=RESERVE,
            qty=Decimal("100"),
            reason="Pool BRW spares 100 of the 500 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
)


BEYOND_THE_WINDOW_CASE = ProposalCase(
    ac="AC-L1",
    title=(
        "ladder v5 rung 0: a line due beyond the lead-time window takes NOTHING however "
        "much sits beside it, incoming included - it is bought whole"
    ),
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("40"),
        "line_no": 16,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_LOCATION,
        "group_code": "BB",
        "outside_reserve_window": True,
        # 400 in the group and 400 in the pool, neither of them touched.
        "group_take_candidates": [
            {"location": GROUP_SIBLING_LOCATION, "qty": Decimal("400")},
        ],
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("400"), "available": Decimal("400")}
        ],
        "pools_net": Decimal("400"),
        "is_discontinued": False,
    },
    components=(
        # v4 answered this case with `timely_spo 40`, because rung 1 ran on both sides of
        # the window. v5 has no rung 1: an SPO is inside the group's own net, and the one
        # that covers THIS line reaches it through Link SPO on its order-inquiry row, after
        # purchasing has read the buy.
        Component(
            kind=BUY,
            qty=Decimal("40"),
            reason="Delivery date beyond the lead time window; stock kept for nearer orders",
        ),
    ),
)


BEYOND_THE_WINDOW_SHORT_CASE = ProposalCase(
    ac="AC-L1",
    title=(
        "ladder v5 rung 0, the other side: a far line with 400 in the pool beside it is "
        "still bought whole, and the reason names the window rather than the arithmetic"
    ),
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("71"),
        "line_no": 18,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_LOCATION,
        "group_code": "BB",
        "outside_reserve_window": True,
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("400"), "available": Decimal("400")}
        ],
        "pools_net": Decimal("400"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=BUY,
            qty=Decimal("71"),
            reason="Delivery date beyond the lead time window; stock kept for nearer orders",
        ),
    ),
)


#: The ownership group `B2155-NL-BLUE` is booked in, and the site the stock sits at.
GROUP_OWN_IB_LOCATION = "BRW-IB"
GROUP_SIBLING_IB_LOCATION = "MWH-IB"


GROUP_NET_NEGATIVE_BUYS_CASE = ProposalCase(
    ac="AC-L7",
    title=(
        "ladder v4: the IB group nets -15514, so nothing is offered and the line buys - "
        "MWH-IB's 7000 is never on the table"
    ),
    inputs={
        # B2155-NL-BLUE on SO381895, measured on the dev copy 26 August 2026: BRW-IB holds
        # 5290 against 27,804 owed, MWH-IB holds 7000 against nothing, and the group nets
        # -15514. The CALLER applies that bound, so what the engine is handed for rung 2 is
        # an EMPTY list - which is the contract this case pins: a group in deficit produces
        # no candidate, not a candidate of zero.
        "open_qty": Decimal("60"),
        "line_no": 20,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_IB_LOCATION,
        "group_code": "IB",
        "group_take_candidates": [],
        "group_offer": Decimal("0"),
        # The pools are 9 short too, so nothing comes from there either.
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("1"), "available": Decimal("-9")}
        ],
        "pools_net": Decimal("-9"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=BUY,
            qty=Decimal("60"),
            reason="Only 0 of 60 can be covered from stock - buy the whole line",
        ),
    ),
)


POOLS_NET_NEGATIVE_CASE = ProposalCase(
    ac="AC-L8",
    title=(
        "ladder v4: the five site pools are ONE pile - BRW -103 beside DC1 +1 nets -102, "
        "and the +1 is not offered"
    ),
    inputs={
        # SRTWCY8605-PJ, measured 26 August 2026. Per-pool arithmetic alone would offer the
        # single unit at DC1; it is stock the shared book already owes at BRW.
        "open_qty": Decimal("10"),
        "line_no": 22,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_IB_LOCATION,
        "group_code": "IB",
        "group_take_candidates": [],
        "group_offer": Decimal("0"),
        "pools": [
            {"location": "BRW", "free": Decimal("0"), "available": Decimal("-103")},
            {"location": "DC1", "free": Decimal("1"), "available": Decimal("1")},
        ],
        "pools_net": Decimal("-102"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=BUY,
            qty=Decimal("10"),
            reason="Only 0 of 10 can be covered from stock - buy the whole line",
        ),
    ),
)


INCOMING_INSIDE_A_NEGATIVE_GROUP_NET_CASE = ProposalCase(
    ac="AC-L10",
    title=(
        "ladder v5: an SPO of 110 at BRW-IB is owed to a group that nets -1893 with it "
        "counted, so it covers no line of that group and this one buys"
    ),
    inputs={
        # SRTWC7405-SC, measured 26 August 2026: BRW 2, BRW-IB 2 on hand against 2335 owed
        # with the SPO's 110 already inside it, MWH-IB 330. Under v4 the caller netted rung
        # 1 against the group before handing it over; under v5 there is no rung 1 to net -
        # the 110 is simply part of the -1893, which is the whole of what the group offers
        # (nothing). The document exists and is named on the order-inquiry row; what it is
        # not is free.
        "open_qty": Decimal("10"),
        "line_no": 24,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_IB_LOCATION,
        "group_code": "IB",
        "group_take_candidates": [],
        "group_offer": Decimal("0"),
        "pools": [],
        "pools_net": Decimal("637"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=BUY,
            qty=Decimal("10"),
            reason="Only 0 of 10 can be covered from stock - buy the whole line",
        ),
    ),
)


#: Ladder v5's own case (section 1e), the captain's numbers on SO381895: 24 needed, the
#: five site pools free 268 between them, and another ownership group holding 100 within
#: the cross-group cap. The pool is question 2 and the other group is question 3, so the
#: whole 24 comes off the pool and the donor is never reached.
POOL_BEFORE_ANOTHER_GROUP_CASE = ProposalCase(
    ac="AC-V7",
    title=(
        "ladder v8 restores v5's answer: the pool is asked FIRST again (R-A), so 24 needed "
        "against an allowance of 134 is Pool 24 - v7.1's pool-last order gave it to DC1-NTC"
    ),
    inputs={
        "as_of": AS_OF,
        "open_qty": Decimal("24"),
        "line_no": 26,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_IB_LOCATION,
        "group_code": "IB",
        # The group itself is short, which is why the question reaches the pool at all.
        "group_take_candidates": [],
        "group_offer": Decimal("0"),
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("268"), "available": Decimal("268")}
        ],
        "pools_net": Decimal("268"),
        # v7.1 reversed this case - the pool went LAST and DC1-NTC's free 100 answered
        # first - and v8 reverses it back (R-A): the site pool of the asking bin is step 0,
        # so DC1-NTC is not reached. It stays in the inputs because the case is about WHICH
        # of the two answers, not about either of them being absent.
        "other_group_candidates": [
            {"location": "DC1-NTC", "qty": Decimal("100"), "group_code": "NTC"},
        ],
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("24"),
            reason="Pool BRW spares 24 of the 134 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
)


PROPOSAL_CASES = (
    HOT_SELLING_WORKED_CASE,
    PROJECT_HOT_SELLING_WORKED_CASE,
    BALANCE_INVARIANT_CASE,
    GROUP_BEFORE_POOL_CASE,
    BEYOND_THE_WINDOW_CASE,
    BEYOND_THE_WINDOW_SHORT_CASE,
    GROUP_NET_NEGATIVE_BUYS_CASE,
    POOLS_NET_NEGATIVE_CASE,
    INCOMING_INSIDE_A_NEGATIVE_GROUP_NET_CASE,
    POOL_BEFORE_ANOTHER_GROUP_CASE,
)
ATTRIBUTION_CASES = (TWO_LINE_ATTRIBUTION_CASE, CONFIRMED_COVER_CASE)


# --------------------------------------------------------------------------- LADDER v8
#
# `PLAN-scm-fulfilment-feedback-2sep.md` S2, rulings R-A to R-E, and the six walks the UAC
# (`scm-fulfilment-feedback-2sep-acceptance-criteria.md`) writes as AC-2.1 to AC-2.7. The
# site pool of the asking bin is asked FIRST and may cover PART of a line - the one step
# that may, because the share it keeps back for dealers is the whole point of the rule.
#
# Every case below pins `as_of` and dates itself off it: the share rule reads which side of
# `immediate_window_days` a line falls on, so a case that let the clock decide would answer
# one way this year and another way next.

#: Inside `immediate_window_days` (30) and well outside it. Both still inside the ATP
#: reserve window, so what is under test is the SHARE rule and never rung 0.
IMMEDIATE_DATE = date(2026, 9, 12)
FAR_DATE = date(2026, 11, 1)


@dataclass(frozen=True)
class OptionRow:
    """One row of the options table, as the UAC writes it (R36 + R-B)."""

    step: str
    whole: bool
    #: How much this step alone can give. `pool_share` is the one step that may answer with
    #: less than the whole line (R-B); every other row states what it would contribute to
    #: what is left after the share.
    gives_qty: Decimal
    #: The step's own sentence, where it has something to say a quantity does not (AC-2.4).
    reason: str | None = None
    chosen: bool = False
    #: The row's own words, where the case turns on WHICH pool answered (review round 2,
    #: S3): `pool_share` names the pool it asks, and on the R-L path that is not the pool
    #: the walk started at. `None` means the case does not pin the label.
    label: str | None = None


@dataclass(frozen=True)
class WalkCase:
    """One walk: what the engine is given, what it must propose, and the rows behind it.

    A `ProposalCase` with the OPTIONS pinned as well. The ladder-v8 rulings are as much
    about what the table says (AC-2.1's "Use BRW stock 450 (not whole)", AC-2.4's reason)
    as about the composition, and a case that pinned only the components would let the
    sentence beside the number drift.
    """

    ac: str
    title: str
    inputs: Mapping[str, Any]
    components: tuple[Component, ...]
    options: tuple[OptionRow, ...]

    @property
    def open_qty(self) -> Decimal:
        return self.inputs["open_qty"]


#: The bin that asks, its ownership group, and the site pool behind it - the shape every
#: case below shares, so only the numbers under test differ between them.
V8_OWN_LOCATION = "BRW-BB"
V8_SIBLING_LOCATION = "MWH-BB"
V8_GROUP = "BB"


def _v8_inputs(**overrides: Any) -> dict[str, Any]:
    """The common walk inputs, with the case's own numbers written over them."""
    base: dict[str, Any] = {
        "as_of": AS_OF,
        "line_no": 2,
        "fulfilment_location": V8_OWN_LOCATION,
        "group_code": V8_GROUP,
        "group_take_candidates": [],
        "group_offer": Decimal("0"),
        "pool_share_pct": 50,
        "immediate_window_days": 30,
        "is_discontinued": False,
    }
    base.update(overrides)
    return base


IMMEDIATE_SHARE_CASE = WalkCase(
    ac="AC-2.1",
    title=(
        "immediate share, pile base: 650 due in 10 days against 900 free at BRW takes the "
        "450 half and walks the other 200"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("650"),
        required_date=IMMEDIATE_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("900"), "available": Decimal("900")}
        ],
        pools_net=Decimal("900"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("450"),
            reason="Pool BRW spares 450 of the 450 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=BUY,
            qty=Decimal("200"),
            reason=(
                "Only 0 of the remaining 200 can be covered from stock - buy the rest"
            ),
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("450"),
            # RE-BLESSED under R-N: a step 0 that ANSWERED writes its row from the pools
            # that answered, in their own sentences, because the chain may now be several
            # of them and one option-row sentence about the asking pool could not state a
            # split. One pool, one sentence, and it is the component's own.
            reason="Pool BRW spares 450 of the 450 it may lend a project",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("200"), chosen=True),
    ),
)


SMALL_LINE_WHOLE_FROM_POOL_CASE = WalkCase(
    ac="AC-2.2",
    title=(
        "a small line takes its whole quantity from the pool: 3 against an allowance of 23 "
        "is Pool 3, never Pool 1 and Own 2"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("3"),
        required_date=date(2026, 9, 4),
        group_take_candidates=[
            {"location": V8_SIBLING_LOCATION, "qty": Decimal("84")},
        ],
        group_offer=Decimal("84"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("47"), "available": Decimal("47")}
        ],
        pools_net=Decimal("47"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("3"),
            reason="Pool BRW spares 3 of the 23 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("3"),
            # RE-BLESSED under R-N (the answered row speaks in its components' sentences).
            reason="Pool BRW spares 3 of the 23 it may lend a project",
            chosen=True,
        ),
        OptionRow(step="use", whole=True, gives_qty=Decimal("3")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("3")),
    ),
)


BEYOND_WINDOW_FITS_THE_ALLOWANCE_CASE = WalkCase(
    ac="AC-2.3",
    title=(
        "beyond the immediate window and inside the allowance: 100 due in 60 days against "
        "an allowance of 450 is taken WHOLE from the pool"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("100"),
        required_date=FAR_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("900"), "available": Decimal("900")}
        ],
        pools_net=Decimal("900"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("100"),
            reason="Pool BRW spares 100 of the 450 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("100"),
            # RE-BLESSED under R-N (the answered row speaks in its components' sentences).
            reason="Pool BRW spares 100 of the 450 it may lend a project",
            chosen=True,
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("100")),
    ),
)


BEYOND_WINDOW_EXCEEDS_THE_ALLOWANCE_CASE = WalkCase(
    ac="AC-2.4",
    title=(
        "beyond the immediate window and OVER the allowance: 600 against 450 takes nothing "
        "from the pool - there is time to buy - and the group covers it whole"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("600"),
        required_date=FAR_DATE,
        group_take_candidates=[
            {"location": V8_OWN_LOCATION, "qty": Decimal("700")},
        ],
        group_offer=Decimal("700"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("900"), "available": Decimal("900")}
        ],
        pools_net=Decimal("900"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("600"),
            reason="BRW-BB gives 600 of the 700 the BB group can cover this line with",
            source_location=V8_OWN_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            reason="600 is more than the 450 BRW can spare",
        ),
        OptionRow(step="use", whole=True, gives_qty=Decimal("600"), chosen=True),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("600")),
    ),
)


NET_BOUNDS_THE_SHARE_CASE = WalkCase(
    ac="AC-2.5",
    title=(
        "the five-pool net bounds the share: 3,034 free at BRW with the pools netting 1 "
        "spares 1, never 1,517 (TPE-9204 on SO381895 line 74)"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("30"),
        required_date=date(2026, 9, 7),
        pools=[
            {
                "location": POOL_LOCATION,
                "free": Decimal("3034"),
                "available": Decimal("3034"),
            }
        ],
        pools_net=Decimal("1"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("1"),
            reason="Pool BRW spares 1 of the 1 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=BUY,
            qty=Decimal("29"),
            reason="Only 0 of the remaining 29 can be covered from stock - buy the rest",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("1"),
            # RE-BLESSED under R-N (the answered row speaks in its components' sentences).
            reason="Pool BRW spares 1 of the 1 it may lend a project",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("29"), chosen=True),
    ),
)


DEALER_HOT_SELLING_TAKES_THE_POOL_CASE = WalkCase(
    ac="AC-2.7",
    title=(
        "the dealer hot-selling gate is retired (R-A): 6,500 free at the pool answers a 40 "
        "line, where ladder v4 to v7.1 refused the step outright and bought"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("40"),
        required_date=IMMEDIATE_DATE,
        is_dealer_hot_selling=True,
        pools=[
            {
                "location": POOL_LOCATION,
                "free": Decimal("6500"),
                "available": Decimal("6500"),
            }
        ],
        pools_net=Decimal("6500"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("40"),
            reason="Pool BRW spares 40 of the 3250 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("40"),
            # RE-BLESSED under R-N (the answered row speaks in its components' sentences).
            reason="Pool BRW spares 40 of the 3250 it may lend a project",
            chosen=True,
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("40")),
    ),
)


#: AC-2.6b's own arithmetic, away from any walk: what a site-pool ROW may show a planner as
#: "Available for Project" - `min(floor(available x (100 - share) / 100), max(net, 0))`.
#: `(available, five_pool_net, share_pct, expected)`.
AVAILABLE_FOR_PROJECT_CASES = (
    # The captain's own lightbox reading: 590 available, half kept for dealers, the pools
    # netting more than the share so the share is what shows.
    (Decimal("590"), Decimal("900"), 50, Decimal("295")),
    # R-K's worked line: "BRW 47 free reads 23" - the floor, not 23.5.
    (Decimal("47"), Decimal("900"), 50, Decimal("23")),
    # The five-pool net is the bound (R-D): 1,517 would be the share and 1 is the pile.
    (Decimal("3034"), Decimal("1"), 50, Decimal("1")),
    # A pool with nothing to give reads 0, never blank (R-K).
    (Decimal("-103"), Decimal("-102"), 50, Decimal("0")),
    (Decimal("590"), Decimal("-1"), 50, Decimal("0")),
    # 0 % keeps nothing back for dealers; 100 % keeps everything.
    (Decimal("590"), Decimal("900"), 0, Decimal("590")),
    (Decimal("590"), Decimal("900"), 100, Decimal("0")),
)


OTHER_POOL_COVERS_THE_REMAINDER_CASE = WalkCase(
    ac="AC-N.8",
    title=(
        "R-L's own worked case, unchanged in every number and reached at STEP 0 under R-N: "
        "DC1's own pool is empty, the group holds 110 of a 300 line, and BRW spares 400 - "
        "so BRW covers it whole"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("300"),
        required_date=IMMEDIATE_DATE,
        fulfilment_location="DC1-IB",
        group_code="IB",
        group_take_candidates=[
            {"location": "DC1-IB", "qty": Decimal("110")},
        ],
        group_offer=Decimal("110"),
        pools=[
            {"location": "DC1", "free": Decimal("0"), "available": Decimal("0")},
            {"location": POOL_LOCATION, "free": Decimal("800"), "available": Decimal("800")},
        ],
        pools_net=Decimal("800"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("300"),
            reason="Pool BRW spares 300 of the 400 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
    options=(
        # RE-BLESSED, review round 2 (S3): the row names the pool that ANSWERED. It used to
        # read `Use DC1 stock` / "DC1 has nothing to spare for projects" beside a chosen
        # Reserve of 300 at BRW, which is the row telling the reader the opposite of what
        # the composition beside it says.
        #
        # R-N changes WHEN this answer is composed and not WHAT it is: the `use` row below
        # still reports the 110 the group could have given, and the pool chain is asked
        # before it rather than after both borrows have failed.
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("300"),
            reason="Pool BRW spares 300 of the 400 it may lend a project",
            chosen=True,
            label="Use BRW stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("110")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("300")),
    ),
)


NET_BOUNDS_THE_WHOLE_POOL_CHAIN_CASE = WalkCase(
    ac="R-D/R-L",
    title=(
        "the five-pool net bounds the WHOLE chain, not each step of it: a line of 200 with "
        "two pools holding 1,000 each but the pools netting only 100 takes 100 and buys "
        "the rest, never 100 from each pool"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("200"),
        required_date=IMMEDIATE_DATE,
        fulfilment_location="DC1-IB",
        group_code="IB",
        pools=[
            {
                "location": "DC1",
                "free": Decimal("1000"),
                "available": Decimal("1000"),
            },
            {
                "location": POOL_LOCATION,
                "free": Decimal("1000"),
                "available": Decimal("1000"),
            },
        ],
        # A third pool oversold by 1,900 is what leaves two piles of 1,000 netting 100
        # between them: the pile is one book (v4 section 1d), and step 0 drawing 100 leaves
        # the R-L step nothing at all rather than a second 100.
        pools_net=Decimal("100"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("100"),
            reason="Pool DC1 spares 100 of the 100 it may lend a project",
            source_location="DC1",
        ),
        Component(
            kind=BUY,
            qty=Decimal("100"),
            reason="Only 0 of the remaining 100 can be covered from stock - buy the rest",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("100"),
            # RE-BLESSED under R-N (the answered row speaks in its components' sentences).
            reason="Pool DC1 spares 100 of the 100 it may lend a project",
            label="Use DC1 stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("100"), chosen=True),
    ),
)


BEYOND_WINDOW_FREE_PILE_SHORT_CASE = WalkCase(
    ac="AC-2.3b",
    title=(
        "beyond the window the pool is whole or nothing IN FACT, not only in intention: "
        "an allowance of 450 with 60 on the floor gives nothing at all, never a part share"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("100"),
        required_date=FAR_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("60"), "available": Decimal("900")}
        ],
        pools_net=Decimal("900"),
    ),
    components=(
        Component(
            kind=BUY,
            qty=Decimal("100"),
            reason="Only 0 of 100 can be covered from stock - buy the whole line",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            # C8 (code review round 3 batch 2): re-blessed - 60 IS free on the floor, so
            # the OLD sentence ("nothing free on the floor to spare") sent a planner
            # looking for stock that was actually there. The floor just cannot cover the
            # whole line, and beyond the window the pool gives nothing less than whole.
            reason="BRW gives whole lines only beyond 30 days, and 60 on the floor cannot cover 100",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("100"), chosen=True),
    ),
)


BORROW_HALF_ANSWERS_THE_POOL_SHARE_ROW_CASE = WalkCase(
    ac="C8",
    title=(
        "the pool's own BORROW half answers the remainder: the chosen pool_share row "
        "names the DONOR pool it actually borrowed from, not the asking pool's own "
        "pre-borrow label and reason (code review round 3 batch 2)"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("650"),
        required_date=IMMEDIATE_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("0"), "available": Decimal("0")}
        ],
        pools_net=Decimal("0"),
        pool_borrow_candidates=[
            {
                "so_number": "SO900001",
                "donor_so_number": "SO900001",
                "line_no": 1,
                "donor_line_no": 1,
                "warehouse_id": "wh-mwh",
                "location": "MWH",
                "qty": Decimal("650"),
            }
        ],
    ),
    components=(
        Component(
            kind=BORROW,
            qty=Decimal("650"),
            source_location="MWH",
            reason="Borrow 650 on hand at pool MWH from SO900001",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("650"),
            chosen=True,
            label="Use MWH stock",
            reason="Borrow 650 on hand at pool MWH from SO900001",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("650")),
    ),
)


# --------------------------------------------------------------------------- R-M (3 Sep)
#
# ANOTHER GROUP'S FREE PILE IS CAPPED BY THAT GROUP'S OWN BOOK. The captain, on the
# production cell of 3 September 2026: SO419417's SRTWT7443 line, 4 due 5 October at BRW-BB,
# was proposed "Use own location: 4 from BRW-IB. BRW-IB has 4 free outside the BB group, and
# free stock is owed to nobody" - while BRW-IB held 2,237 on hand against 2,684 of open IB
# demand, 447 short on its own book. The date-bounded pile said 785 was free on 5 October
# only because IB demand due AFTER that day was never subtracted from it.
#
# The engine is handed the CAPPED lists (`project_supply_service.use_candidates_for`), so
# the case for the refusal is stated as the engine sees it: no other-group candidate at all,
# and `other_group_short` naming what the lending group is short by, which is what the `use`
# row says instead of a silent 0.

#: The line the two cases below are the two readings of.
R_M_DATE = date(2026, 10, 5)
R_M_OWN_LOCATION = "BRW-BB"
R_M_OTHER_LOCATION = "BRW-IB"
#: The site pool of the asking bin, oversold on the day (BRW Available -91), so step 0 is
#: out of the way and what is under test is step 1's second half and nothing else.
R_M_POOLS = [{"location": POOL_LOCATION, "free": Decimal("0"), "available": Decimal("0")}]


OTHER_GROUP_SHORT_BOOK_CASE = WalkCase(
    ac="AC-2.12a",
    title=(
        "the IB group is 447 short on its own book, so its 785 free on 5 October is not "
        "free at all: the 4 is borrowed from a later IB order, never reserved at BRW-IB"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("4"),
        required_date=R_M_DATE,
        fulfilment_location=R_M_OWN_LOCATION,
        group_code=V8_GROUP,
        # Capped away by the caller: IB's whole open book is negative, so it offers nothing.
        other_group_candidates=[],
        other_group_short={"IB": Decimal("447")},
        pools=R_M_POOLS,
        pools_net=Decimal("0"),
        order_borrow_candidates=[
            {
                "location": R_M_OTHER_LOCATION,
                "qty": Decimal("4"),
                "donor_so_number": "SO419100",
                "donor_line_no": 7,
                "donor_agent_code": "JEREMY",
                "donor_required_date": date(2026, 11, 20),
            }
        ],
    ),
    components=(
        Component(
            kind=BORROW,
            qty=Decimal("4"),
            reason=(
                "Borrow 4 on hand at BRW-IB from SO419100 line 7 (JEREMY, due 20 Nov 2026); "
                "its debt lands in Nov 2026"
            ),
            source_location=R_M_OTHER_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            reason="BRW has nothing to spare for projects",
            label="Use BRW stock",
        ),
        OptionRow(
            step="use",
            whole=False,
            gives_qty=Decimal("0"),
            reason="IB group is 447 short on its own book, nothing to spare",
        ),
        OptionRow(
            step="order_borrow", whole=True, gives_qty=Decimal("4"), chosen=True
        ),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("4")),
    ),
)


OTHER_GROUP_WHOLE_BOOK_CASE = WalkCase(
    ac="AC-2.12b",
    title=(
        "the same cell with IB's book POSITIVE (2,237 on hand against 1,708 owed): the take "
        "stands, and the sentence states the PILE and the date it was measured on, not the 4"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("4"),
        required_date=R_M_DATE,
        fulfilment_location=R_M_OWN_LOCATION,
        group_code=V8_GROUP,
        other_group_candidates=[
            {
                "location": R_M_OTHER_LOCATION,
                "qty": Decimal("529"),
                "group": "IB",
                "free_at": R_M_DATE,
            }
        ],
        pools=R_M_POOLS,
        pools_net=Decimal("0"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("4"),
            reason=(
                "BRW-IB has 529 free outside the BB group at 5 Oct 2026, none of it owed to "
                "a later IB order"
            ),
            source_location=R_M_OTHER_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            reason="BRW has nothing to spare for projects",
            label="Use BRW stock",
        ),
        OptionRow(
            step="use",
            whole=True,
            gives_qty=Decimal("4"),
            chosen=True,
            label="Use IB group stock",
        ),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("4")),
    ),
)


# --------------------------------------------------------------------------- R-N (3 Sep)
#
# THE POOL STEP WALKS EVERY SITE POOL BEFORE ANOTHER SITE'S GROUP BIN.
#
# `PLAN-scm-pool-chain-first.md`, from SO419417 on 3 September 2026: the board proposed
# `BRW pool 4 + WH3-BB 4` for SRTWC8840-SC while WH3's SITE POOL held 687 on hand (343
# Available for Project) and the five pools netted 1,605. The captain: "the pool got a lot
# though". Step 0 asked the asking bin's OWN pool alone (`pools[:1]`) and the other site
# pools were reached only by R-L's spill, which fired only when own locations and both
# borrows had all failed to cover the remainder whole - so a group bin that happened to
# hold stock decided whether the pool chain was asked at all, and the SAME rule gave two
# different answers on two lines of one order.
#
# Under R-N step 0 walks the WHOLE chain in `_pool_chain`'s own draw order (the asking
# bin's pool first, then the rest by on hand), each pool lending under its own allowance
# and the one five-pool net bounding the total - which is exactly what
# `pool_share_capacity` already computed for the board's proof.
#
# The four cases below are the four SO419417 rows, with the production numbers on them.

#: The other site pool of the SO419417 cases: fuller than BRW, and never asked before R-N.
V8_OTHER_POOL = "WH3"


TWO_POOLS_COVER_ONE_LINE_CASE = WalkCase(
    ac="AC-N.1",
    title=(
        "SRTWC8840-SC: 8 due inside the window at BRW-BB with BRW sparing 4 and WH3's own "
        "pool 343 reads BRW 4 + WH3 4 at step 0, never the WH3-BB group bin"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("8"),
        required_date=IMMEDIATE_DATE,
        group_take_candidates=[
            {"location": "WH3-BB", "qty": Decimal("94")},
        ],
        group_offer=Decimal("94"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("4"), "available": Decimal("710")},
            {"location": V8_OTHER_POOL, "free": Decimal("687"), "available": Decimal("686")},
        ],
        pools_net=Decimal("1605"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("4"),
            reason="Pool BRW spares 4 of the 355 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("4"),
            reason="Pool WH3 spares 4 of the 343 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("8"),
            # Both pools' own sentences, in the order they were drawn: the row states what
            # each of them spared and out of what allowance, which is the arithmetic a
            # planner checks the split against.
            reason=(
                "Pool BRW spares 4 of the 355 it may lend a project "
                "Pool WH3 spares 4 of the 343 it may lend a project"
            ),
            chosen=True,
            label="Use BRW and WH3 stock",
        ),
        # The group bin still ANSWERS - it could have covered the line whole - and is
        # simply not chosen: the pool chain was asked first and covered it (R-N).
        OptionRow(step="use", whole=True, gives_qty=Decimal("8")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("8")),
    ),
)


THE_OWN_POOL_GIVES_WHAT_IT_HAS_AND_THE_CHAIN_FINISHES_CASE = WalkCase(
    ac="AC-N.2",
    title=(
        "SRTWCX8840-S-RL: the own pool has 1 on the floor, so the chain finishes the line "
        "at WH3 - BRW 1 + WH3 7, and the 140 in the WH3-BB group bin is left alone"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("8"),
        required_date=IMMEDIATE_DATE,
        group_take_candidates=[
            {"location": "WH3-BB", "qty": Decimal("140")},
        ],
        group_offer=Decimal("140"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("1"), "available": Decimal("710")},
            {"location": V8_OTHER_POOL, "free": Decimal("682"), "available": Decimal("686")},
        ],
        pools_net=Decimal("1605"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("1"),
            reason="Pool BRW spares 1 of the 355 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("7"),
            reason="Pool WH3 spares 7 of the 343 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("8"),
            reason=(
                "Pool BRW spares 1 of the 355 it may lend a project "
                "Pool WH3 spares 7 of the 343 it may lend a project"
            ),
            chosen=True,
            label="Use BRW and WH3 stock",
        ),
        OptionRow(step="use", whole=True, gives_qty=Decimal("8")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("8")),
    ),
)


THE_OLD_SPILL_ANSWER_ARRIVES_AT_STEP_0_CASE = WalkCase(
    ac="AC-N.3",
    title=(
        "SRTWCY8840, the line R-L's spill already answered: BRW 3 + WH3 5, the SAME "
        "quantities - and now composed at step 0 rather than after both borrows failed"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("8"),
        required_date=IMMEDIATE_DATE,
        group_take_candidates=[
            {"location": V8_OWN_LOCATION, "qty": Decimal("1")},
        ],
        group_offer=Decimal("1"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("3"), "available": Decimal("710")},
            {"location": V8_OTHER_POOL, "free": Decimal("684"), "available": Decimal("686")},
        ],
        pools_net=Decimal("1605"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("3"),
            reason="Pool BRW spares 3 of the 355 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("5"),
            reason="Pool WH3 spares 5 of the 343 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("8"),
            reason=(
                "Pool BRW spares 3 of the 355 it may lend a project "
                "Pool WH3 spares 5 of the 343 it may lend a project"
            ),
            chosen=True,
            label="Use BRW and WH3 stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("1")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("8")),
    ),
)


THE_OWN_POOL_COVERS_AND_THE_CHAIN_STOPS_CASE = WalkCase(
    ac="AC-N.4",
    title=(
        "SRTWT5880-CR: the own pool covers the line on its own, so no other pool is drawn "
        "at all - the chain is a draw ORDER, not a spread"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("10"),
        required_date=IMMEDIATE_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("240"), "available": Decimal("240")},
            {"location": V8_OTHER_POOL, "free": Decimal("687"), "available": Decimal("686")},
        ],
        pools_net=Decimal("1605"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("10"),
            reason="Pool BRW spares 10 of the 120 it may lend a project",
            source_location=POOL_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("10"),
            reason="Pool BRW spares 10 of the 120 it may lend a project",
            chosen=True,
            label="Use BRW stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("10")),
    ),
)


BEYOND_THE_WINDOW_THE_CHAIN_IS_WHOLE_CASE = WalkCase(
    ac="AC-N.5a",
    title=(
        "beyond the window the whole-or-nothing rule is about the CHAIN (R-B restated by "
        "R-N): 300 due in 60 days against 100 + 250 of allowance is taken whole, 100 + 200"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("300"),
        required_date=FAR_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("500"), "available": Decimal("200")},
            {"location": V8_OTHER_POOL, "free": Decimal("700"), "available": Decimal("500")},
        ],
        pools_net=Decimal("1000"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("100"),
            reason="Pool BRW spares 100 of the 100 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("200"),
            reason="Pool WH3 spares 200 of the 250 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("300"),
            reason=(
                "Pool BRW spares 100 of the 100 it may lend a project "
                "Pool WH3 spares 200 of the 250 it may lend a project"
            ),
            chosen=True,
            label="Use BRW and WH3 stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("300")),
    ),
)


BEYOND_THE_WINDOW_THE_CHAIN_IS_SHORT_CASE = WalkCase(
    ac="AC-N.5b",
    title=(
        "the same line with WH3 sparing 150: the chain's 250 cannot cover 300 whole, so "
        "beyond the window step 0 gives NOTHING and the walk falls to the group"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("300"),
        required_date=FAR_DATE,
        group_take_candidates=[
            {"location": V8_OWN_LOCATION, "qty": Decimal("300")},
        ],
        group_offer=Decimal("300"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("500"), "available": Decimal("200")},
            {"location": V8_OTHER_POOL, "free": Decimal("700"), "available": Decimal("300")},
        ],
        pools_net=Decimal("1000"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("300"),
            reason="BRW-BB gives 300 of the 300 the BB group can cover this line with",
            source_location=V8_OWN_LOCATION,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            # THE REFUSAL IS THE CHAIN'S TOO (R-N): the sentence used to name the asking
            # pool's own allowance alone, which read "300 is more than the 100 BRW can
            # spare" over a chain that had 250 on the table and still could not cover the
            # line whole. Both pools are named, and the figure is what they net together.
            reason="300 is more than the 250 BRW and WH3 can spare",
            label="Use BRW and WH3 stock",
        ),
        OptionRow(step="use", whole=True, gives_qty=Decimal("300"), chosen=True),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("300")),
    ),
)


THE_NET_BOUNDS_THE_WHOLE_STEP_0_CHAIN_CASE = WalkCase(
    ac="AC-N.6",
    title=(
        "the five-pool net bounds step 0 across the chain: two pools sparing 100 each with "
        "the pools netting 120 give 100 + 20, and the remaining 30 walks on"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("150"),
        required_date=IMMEDIATE_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("500"), "available": Decimal("200")},
            {"location": V8_OTHER_POOL, "free": Decimal("500"), "available": Decimal("200")},
        ],
        pools_net=Decimal("120"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("100"),
            reason="Pool BRW spares 100 of the 100 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("20"),
            # WH3's allowance is what is LEFT of the one net after BRW's draw, not its own
            # half again: the five pools are one book (v4 section 1d).
            reason="Pool WH3 spares 20 of the 20 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
        Component(
            kind=BUY,
            qty=Decimal("30"),
            reason="Only 0 of the remaining 30 can be covered from stock - buy the rest",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("120"),
            reason=(
                "Pool BRW spares 100 of the 100 it may lend a project "
                "Pool WH3 spares 20 of the 20 it may lend a project"
            ),
            label="Use BRW and WH3 stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("30"), chosen=True),
    ),
)


THE_SHARE_LEDGER_IS_PER_POOL_ACROSS_THE_CHAIN_CASE = WalkCase(
    ac="AC-N.7",
    title=(
        "the share ledger is kept per POOL across the chain: a second line of one walk "
        "finds BRW's share spent and WH3's down to 40, and may take only that 40"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("100"),
        required_date=IMMEDIATE_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("500"), "available": Decimal("200")},
            {"location": V8_OTHER_POOL, "free": Decimal("500"), "available": Decimal("200")},
        ],
        pools_net=Decimal("1000"),
        # What the FIRST line of this walk left: BRW's whole 100 taken, and 60 of WH3's.
        # `compose_lines` keeps this ledger keyed by (product, pool).
        pool_share_left={POOL_LOCATION: Decimal("0"), V8_OTHER_POOL: Decimal("40")},
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("40"),
            reason="Pool WH3 spares 40 of the 40 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
        Component(
            kind=BUY,
            qty=Decimal("60"),
            reason="Only 0 of the remaining 60 can be covered from stock - buy the rest",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("40"),
            reason="Pool WH3 spares 40 of the 40 it may lend a project",
            label="Use WH3 stock",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("60"), chosen=True),
    ),
)


THE_CHAIN_REFUSAL_COUNTS_ONLY_THE_POOLS_IT_WALKED_CASE = WalkCase(
    ac="S1",
    title=(
        "review fix round S1: the refusal's floor is the pools the chain actually WALKED, "
        "not every pool the location holds - WH3's allowance is 0 so it never joins the "
        "chain, and its 250 on the floor must not read as BRW's own free stock"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("300"),
        required_date=FAR_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("100"), "available": Decimal("1200")},
            {"location": V8_OTHER_POOL, "free": Decimal("250"), "available": Decimal("0")},
        ],
        pools_net=Decimal("1000"),
    ),
    components=(
        Component(
            kind=BUY,
            qty=Decimal("300"),
            reason="Only 0 of 300 can be covered from stock - buy the whole line",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            # WH3's allowance is 0, so `pool_share_capacity` never adds it to the chain -
            # the refusal is BRW's alone, and its own 100 on the floor is what cannot cover
            # 300. Summing `free` over every pool the location holds (the bug this pins)
            # added WH3's 250 in and the message read "BRW has nothing free on the floor
            # to spare" over a floor that plainly was not empty.
            reason="BRW gives whole lines only beyond 30 days, and 100 on the floor cannot cover 300",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("300"), chosen=True),
    ),
)


THE_CHAIN_ALLOWANCE_NEVER_EXCEEDS_THE_NET_CASE = WalkCase(
    ac="S1b",
    title=(
        "review fix round S1: two pools each individually allowed close to the net, so a "
        "naive sum of their allowances (120 + 115 = 235) claims almost double the 120 the "
        "five pools actually net - the refusal's 'can spare' figure is capped at the net"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("150"),
        required_date=FAR_DATE,
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("5"), "available": Decimal("1000")},
            {"location": V8_OTHER_POOL, "free": Decimal("200"), "available": Decimal("1000")},
        ],
        pools_net=Decimal("120"),
    ),
    components=(
        Component(
            kind=BUY,
            qty=Decimal("150"),
            reason="Only 0 of 150 can be covered from stock - buy the whole line",
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=False,
            gives_qty=Decimal("0"),
            # BRW's tiny floor (5) barely spends the net, so WH3's own allowance still
            # reads 115 of it - and 120 + 115 is 235, an allowance the five pools do not
            # have between them. The floor (5 + 200 = 205) covers the 150 needed, so the
            # sentence is decided by the allowance and not the floor: capped at the net
            # (120), 150 is still more than the pools can spare.
            reason="150 is more than the 120 BRW and WH3 can spare",
        ),
        OptionRow(step="use", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("150"), chosen=True),
    ),
)


OWN_BIN_FULL_CHAIN_STILL_FIRST_CASE = WalkCase(
    ac="AC-N.13",
    title=(
        "B1 (captain 3 Sep): the own bin BRW-BB holds all 8 free on its own, and the pool "
        "chain is still asked first - BRW 4 + WH3 4, the own bin's 8 is not drawn"
    ),
    inputs=_v8_inputs(
        open_qty=Decimal("8"),
        required_date=IMMEDIATE_DATE,
        group_take_candidates=[
            {"location": V8_OWN_LOCATION, "qty": Decimal("8")},
        ],
        group_offer=Decimal("8"),
        pools=[
            {"location": POOL_LOCATION, "free": Decimal("4"), "available": Decimal("710")},
            {"location": V8_OTHER_POOL, "free": Decimal("687"), "available": Decimal("686")},
        ],
        pools_net=Decimal("1605"),
    ),
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("4"),
            reason="Pool BRW spares 4 of the 355 it may lend a project",
            source_location=POOL_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("4"),
            reason="Pool WH3 spares 4 of the 343 it may lend a project",
            source_location=V8_OTHER_POOL,
        ),
    ),
    options=(
        OptionRow(
            step="pool_share",
            whole=True,
            gives_qty=Decimal("8"),
            reason=(
                "Pool BRW spares 4 of the 355 it may lend a project "
                "Pool WH3 spares 4 of the 343 it may lend a project"
            ),
            chosen=True,
            label="Use BRW and WH3 stock",
        ),
        # The own bin COULD give all 8 on its own (whole) - the row still answers - but
        # step 0 already covered the line, so it is not chosen. This is the reproduction
        # B1 rules on: the pool chain outranks the line's OWN bin, not only the group.
        OptionRow(step="use", whole=True, gives_qty=Decimal("8")),
        OptionRow(step="order_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="supply_borrow", whole=False, gives_qty=Decimal("0")),
        OptionRow(step="buy", whole=True, gives_qty=Decimal("8")),
    ),
)


V8_WALK_CASES = (
    IMMEDIATE_SHARE_CASE,
    SMALL_LINE_WHOLE_FROM_POOL_CASE,
    BEYOND_WINDOW_FITS_THE_ALLOWANCE_CASE,
    BEYOND_WINDOW_EXCEEDS_THE_ALLOWANCE_CASE,
    NET_BOUNDS_THE_SHARE_CASE,
    DEALER_HOT_SELLING_TAKES_THE_POOL_CASE,
    OTHER_POOL_COVERS_THE_REMAINDER_CASE,
    NET_BOUNDS_THE_WHOLE_POOL_CHAIN_CASE,
    BEYOND_WINDOW_FREE_PILE_SHORT_CASE,
    BORROW_HALF_ANSWERS_THE_POOL_SHARE_ROW_CASE,
    OTHER_GROUP_SHORT_BOOK_CASE,
    OTHER_GROUP_WHOLE_BOOK_CASE,
    TWO_POOLS_COVER_ONE_LINE_CASE,
    THE_OWN_POOL_GIVES_WHAT_IT_HAS_AND_THE_CHAIN_FINISHES_CASE,
    THE_OLD_SPILL_ANSWER_ARRIVES_AT_STEP_0_CASE,
    THE_OWN_POOL_COVERS_AND_THE_CHAIN_STOPS_CASE,
    BEYOND_THE_WINDOW_THE_CHAIN_IS_WHOLE_CASE,
    BEYOND_THE_WINDOW_THE_CHAIN_IS_SHORT_CASE,
    THE_NET_BOUNDS_THE_WHOLE_STEP_0_CHAIN_CASE,
    THE_SHARE_LEDGER_IS_PER_POOL_ACROSS_THE_CHAIN_CASE,
    THE_CHAIN_REFUSAL_COUNTS_ONLY_THE_POOLS_IT_WALKED_CASE,
    THE_CHAIN_ALLOWANCE_NEVER_EXCEEDS_THE_NET_CASE,
    OWN_BIN_FULL_CHAIN_STILL_FIRST_CASE,
)
