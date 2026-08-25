"""The golden set for the Stage 1C front-planning engine, written before the engine.

PRINCIPLES.md phase 2 is explicit about deterministic engines: "the golden-set expected
numbers are written as failing tests first, and the code is built to satisfy them". This
module is those numbers. It holds no assertions and touches no database - it is plain data,
so the expected answers cannot quietly drift to match whatever the implementation ends up
doing, and so the same cases can be read by a route test, a service test or a fixture
builder later without any of them owning the numbers.

Seven cases, each traced to the criterion it comes from in
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
* **AC-L1** ladder v3's rung 0, both sides: a line due beyond the lead-time window walks no
  STOCK rung however much sits beside it, but rung 1 is unchanged, so supply already on its
  way still covers it; incoming short of the whole line is dropped and the line is bought
  entire. Under v2 such a line still walked the two surplus rungs.

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
        "dealer hot-selling product: the shared pool contributes nothing at all, and with "
        "no own-location Reserve any more (ladder v2, section E rule 7) the whole line is "
        "a Buy"
    ),
    inputs={
        "open_qty": Decimal("70"),
        "line_no": 10,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": DEALER_LOCATION,
        "is_dealer_hot_selling": True,
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("120"), "available": Decimal("120")}
        ],
        # No SPO arrives by the required date, so timely coverage is zero and is not
        # proposed at all.
        "timely_spo_qty": Decimal("0"),
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
        "project hot-selling product: the shared pool is drawn only while its own signed "
        "availability stays positive (PLAN 3.3a), and covers the whole line here"
    ),
    inputs={
        "open_qty": Decimal("40"),
        "line_no": 12,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": OWN_LOCATION,
        "is_project_hot_selling": True,
        "pools": [
            # The pool's own signed availability (on hand - SO qty + SPO qty) is thinner
            # than its free balance, and the draw stops there - which is the whole line.
            {"location": POOL_LOCATION, "free": Decimal("120"), "available": Decimal("40")}
        ],
        "timely_spo_qty": Decimal("0"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("40"),
            reason="Pool BRW has 40 available",
            source_location=POOL_LOCATION,
        ),
    ),
)


# --------------------------------------------------------------------------- AC-B12


BALANCE_INVARIANT_CASE = ProposalCase(
    ac="AC-B12",
    title="every component carries its reason and the terms add up to the open quantity",
    inputs={
        "open_qty": Decimal("70"),
        "line_no": 10,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": OWN_LOCATION,
        "is_dealer_hot_selling": False,
        # Ten arrives on time, and the pool covers the rest - together the WHOLE line, so
        # the whole-line rule (section E rule 6) keeps both components rather than
        # collapsing them into a single Buy.
        "timely_spo_qty": Decimal("10"),
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("60"), "available": Decimal("60")}
        ],
        "is_discontinued": False,
    },
    components=(
        # The two sentences AC-B14 quotes verbatim.
        Component(
            kind=TIMELY_SPO,
            qty=Decimal("10"),
            reason="incoming supply arrives by the required date",
            source_location=OWN_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("60"),
            reason="Pool BRW has 60 available",
            source_location=POOL_LOCATION,
        ),
    ),
)

#: The exact strings AC-B14 prints. Pinned separately so a reworded reason fails the test
#: that owns the criterion rather than four unrelated ones.
BALANCE_INVARIANT_STATED = (
    "Timely SPO 10: incoming supply arrives by the required date",
    "Reserve 60: Pool BRW has 60 available",
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
                reason="SPO 202703-S0011 arrives on 2027-03-01, by the required date",
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
                reason="SPO 202703-S0012 arrives on 2027-03-01, by the required date",
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
        "ladder v3: the ownership group is drawn before the shared pool, this line's own "
        "location first"
    ),
    inputs={
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
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("1000"), "available": Decimal("1000")}
        ],
        "timely_spo_qty": Decimal("0"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=RESERVE,
            qty=Decimal("40"),
            reason="BRW-BB has 40 available in the BB group",
            source_location=GROUP_OWN_LOCATION,
        ),
        Component(
            kind=RESERVE,
            qty=Decimal("30"),
            reason="DC1-BB has 30 available in the BB group",
            source_location=GROUP_SIBLING_LOCATION,
        ),
        # Only what the group could not meet reaches the shared pile.
        Component(
            kind=RESERVE,
            qty=Decimal("30"),
            reason="Pool BRW has 1000 available",
            source_location=POOL_LOCATION,
        ),
    ),
)


BEYOND_THE_WINDOW_CASE = ProposalCase(
    ac="AC-L1",
    title=(
        "ladder v3 rung 0: a line due beyond the lead-time window takes no STOCK however "
        "much sits beside it, but still takes the supply already on its way"
    ),
    inputs={
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
        # Already bought and on the water: buying it a second time is a double purchase.
        "timely_spo_qty": Decimal("40"),
        "is_discontinued": False,
    },
    components=(
        Component(
            kind=TIMELY_SPO,
            qty=Decimal("40"),
            reason="incoming supply arrives by the required date",
            source_location=GROUP_OWN_LOCATION,
        ),
    ),
)


BEYOND_THE_WINDOW_SHORT_CASE = ProposalCase(
    ac="AC-L1",
    title=(
        "ladder v3 rung 0, the other side: incoming that does not reach the whole line is "
        "dropped rather than mixed with a Buy, and the reason names the window"
    ),
    inputs={
        "open_qty": Decimal("71"),
        "line_no": 18,
        "required_date": REQUIRED_DATE,
        "fulfilment_location": GROUP_OWN_LOCATION,
        "group_code": "BB",
        "outside_reserve_window": True,
        "pools": [
            {"location": POOL_LOCATION, "free": Decimal("400"), "available": Decimal("400")}
        ],
        # 40 of the 71 arrives in time. "Incoming 40, Buy 31" is the mix AC-L5 refuses at
        # confirm, so the whole-line rule takes the lot.
        "timely_spo_qty": Decimal("40"),
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


PROPOSAL_CASES = (
    HOT_SELLING_WORKED_CASE,
    PROJECT_HOT_SELLING_WORKED_CASE,
    BALANCE_INVARIANT_CASE,
    GROUP_BEFORE_POOL_CASE,
    BEYOND_THE_WINDOW_CASE,
    BEYOND_THE_WINDOW_SHORT_CASE,
)
ATTRIBUTION_CASES = (TWO_LINE_ATTRIBUTION_CASE, CONFIRMED_COVER_CASE)
