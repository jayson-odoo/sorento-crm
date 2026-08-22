"""The dated running balance and source resolution.

Two cases here are not ordinary tests, they are the reason the module exists:

* ``test_late_supply_does_not_cover_earlier_demand`` - a PO arriving 25 Aug must NOT cover
  an order due 3 Aug. Monthly buckets would net both inside August and report no problem.
* ``test_SRTWT7408_uses_the_pool_and_never_buys`` - demand 67 against customer bins with
  4,397 in the shared pool must resolve to "use the pool". Per-warehouse netting would
  recommend buying 67 units of an item holding 4,397.

Figures are from the real Tuju Residence extract and the real Summary Order Report, so the
arithmetic is checkable against a document rather than invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.scm.coverage_timeline import (
    DEMAND,
    SOURCE_ORDER,
    SOURCE_OTHER,
    SOURCE_OWN,
    SOURCE_POOL,
    SUPPLY,
    SUPPLY_IN_TRANSIT,
    SUPPLY_ON_ORDER,
    SourceAvailability,
    TimelineEvent,
    build_timeline,
    buy_quantity,
    closing_balance,
    group_by_month,
    is_use_stock,
    resolve_sources,
)


def _demand(d: date, qty: float, ref: str, label: str = "") -> TimelineEvent:
    return TimelineEvent(at=d, qty=-abs(qty), kind=DEMAND, ref=ref, label=label)


def _supply(d: date, qty: float, ref: str, stage: str = SUPPLY_ON_ORDER) -> TimelineEvent:
    return TimelineEvent(at=d, qty=abs(qty), kind=SUPPLY, ref=ref, supply_stage=stage)


# --------------------------------------------------------------------------- #
# the case the whole design turns on
# --------------------------------------------------------------------------- #

def test_late_supply_does_not_cover_earlier_demand():
    """SRTWC8613-RL at BRW-BB, from the Tuju extract.

    Opening 140, so July is genuinely covered and August is the FIRST breach. That framing
    matters: an earlier draft of this example opened at 40, which put the first breach in
    July at -95 while still captioning August as where the shortfall starts. The arithmetic
    and the caption disagreed, and the engine was right - so the example was fixed, not the
    code.

    72 due 03 Aug against 200 arriving 25 Aug. The August supply is nearly triple what is
    needed and lands 22 days too late.
    """
    res = build_timeline(
        140,
        [
            _demand(date(2026, 7, 1), 135, "SO397450", "TUJU RESIDENCE"),
            _demand(date(2026, 8, 3), 72, "SO397450", "TUJU RESIDENCE"),
            _supply(date(2026, 8, 25), 200, "PO-2026/06-0044"),
        ],
    )

    balances = [r.balance for r in res.rows]
    assert balances == [140, 5, -67, 133]

    assert res.shortfall is not None
    assert res.shortfall.at == date(2026, 8, 3), "the FIRST breach, and August is the first"
    assert res.shortfall.qty == 67
    assert res.shortfall.ref == "SO397450"

    # Closing is comfortably positive. A dateless net position would have reported no
    # problem at all, which is precisely the error being prevented.
    assert res.closing_balance == 133


def test_the_first_breach_is_reported_even_when_a_later_one_is_worse():
    """The opening-40 variant of the case above. July already breaches, so July is what
    gets reported: a plan that names August while July is short is worse than useless."""
    res = build_timeline(
        40,
        [
            _demand(date(2026, 7, 1), 135, "SO397450"),
            _supply(date(2026, 7, 12), 100, "PO-2026/05-0031"),
            _demand(date(2026, 8, 3), 72, "SO397450"),
        ],
    )
    assert [r.balance for r in res.rows] == [40, -95, 5, -67]
    assert res.shortfall is not None
    assert res.shortfall.at == date(2026, 7, 1)
    assert res.peak_deficit == 95


def test_a_monthly_bucket_would_have_hidden_that_shortfall():
    """Guards the decision, not just the code. If someone later aggregates by month, the
    August bucket nets -72 against +200 and the shortfall disappears."""
    august_demand, august_supply = 72, 200
    assert august_supply - august_demand > 0, "the bucket looks healthy"

    res = build_timeline(
        5,  # balance carried into August from the July rows above
        [
            _demand(date(2026, 8, 3), august_demand, "SO397450"),
            _supply(date(2026, 8, 25), august_supply, "PO-2026/06-0044"),
        ],
    )
    assert res.shortfall is not None, "date order must still find it"
    assert res.shortfall.at == date(2026, 8, 3)


# --------------------------------------------------------------------------- #
# ROP is the one-bucket case: the parity bridge
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "on_hand,on_order,committed",
    [(0, 0, 0), (100, 50, 30), (0, 489, 852), (4397, 0, 67), (3590, 0, 7646)],
)
def test_closing_balance_equals_the_dateless_net_position(on_hand, on_order, committed):
    """The bridge that makes the existing formulae untouched.

    With every event on one date, the timeline's closing balance IS
    on_hand + on_order - committed, which is what scm.net_position_v computes and what
    `trigger` and `order_qty` already consume. So ROP is the degenerate one-bucket case and
    the M3 golden set stays valid structurally, not by luck.
    """
    one_day = date(2026, 8, 4)
    events = []
    if committed:
        events.append(_demand(one_day, committed, "committed"))
    if on_order:
        events.append(_supply(one_day, on_order, "on-order"))

    assert closing_balance(on_hand, events) == pytest.approx(on_hand + on_order - committed)


def test_floor_is_how_a_reorder_point_expresses_itself():
    """A continuous SKU triggers when the balance falls below its reorder point, which is
    the same statement as a floor above zero."""
    events = [_demand(date(2026, 8, 4), 30, "demand")]
    assert build_timeline(100, events, floor=0).shortfall is None
    breached = build_timeline(100, events, floor=80)
    assert breached.shortfall is not None
    assert breached.shortfall.qty == 10  # 80 floor - 70 balance


# --------------------------------------------------------------------------- #
# balance mechanics
# --------------------------------------------------------------------------- #

def test_peak_deficit_is_deeper_than_the_first_gap():
    """Buying only the first gap would leave the plan short a second time."""
    res = build_timeline(
        0,
        [
            _demand(date(2026, 7, 1), 10, "A"),
            _demand(date(2026, 8, 1), 40, "B"),
            _supply(date(2026, 9, 1), 100, "PO"),
        ],
    )
    assert res.shortfall is not None
    assert res.shortfall.qty == 10       # first breach
    assert res.peak_deficit == 50        # what actually has to be covered


def test_same_day_supply_is_ordered_before_demand_and_covers_it():
    """PLAN-scm-front-planning.md 3.5: incoming SPO is DATED location supply, not a CS
    decision, and an SPO arriving on the required date "counts at that date". Stage 1C
    flips the shared ``_sort_key`` from demand-first to supply-first on a same-day tie, so
    a container that clears and is put away the same morning covers a despatch due that
    same day, instead of the despatch being treated as though the stock never arrived.

    This test and ``_sort_key`` change together (PLAN 3.5's own instruction); until the
    flip lands this reports a shortfall that the new contract says must not exist.
    """
    res = build_timeline(
        0,
        [
            _supply(date(2026, 7, 1), 100, "PO"),
            _demand(date(2026, 7, 1), 100, "SO"),
        ],
    )
    assert res.shortfall is None, "same-day supply must cover same-day demand, not miss it"
    assert res.closing_balance == 0


# --------------------------------------------------------------------------- #
# PLAN 3.5's full tie-break chain: date, kind (supply before demand), ref, line_no
# (missing last), line_id. ``line_no`` / ``line_id`` do not exist on ``TimelineEvent``
# yet, so every test below fails with a TypeError on construction until Stage 1C adds
# them alongside the ``_sort_key`` flip -- which is the point: these fail for the same
# reason the pinned test above fails, not for an unrelated fixture bug.
# --------------------------------------------------------------------------- #


def _demand_line(d: date, qty: float, ref: str, *, line_no=None, line_id=None) -> TimelineEvent:
    return TimelineEvent(
        at=d, qty=-abs(qty), kind=DEMAND, ref=ref, line_no=line_no, line_id=line_id
    )


def _supply_line(d: date, qty: float, ref: str, *, line_no=None, line_id=None) -> TimelineEvent:
    return TimelineEvent(
        at=d, qty=abs(qty), kind=SUPPLY, ref=ref, line_no=line_no, line_id=line_id
    )


def test_ac_b02_two_line_worked_case_orders_opening_stock_before_the_same_day_spo():
    """PLAN 3.5's worked attribution, walked through the shared timeline rather than the
    engine: eligible opening stock 10, one same-day SPO of 10, and SO-100's two 10-unit
    lines at line numbers 10 and 20, both due that date. The timeline proves the ordering
    that lets line 10 take the opening stock and line 20 take the SPO: the SPO row sorts
    ahead of both demand rows (supply before demand), and line 10 sorts ahead of line 20
    (line_no order) so it is offered the balance first.
    """
    required_date = date(2027, 3, 1)
    events = [
        _supply_line(required_date, 10, "202703-S0011"),
        _demand_line(
            required_date, 10, "SO-100", line_no=10,
            line_id="aaaaaaaa-0000-0000-0000-000000000010",
        ),
        _demand_line(
            required_date, 10, "SO-100", line_no=20,
            line_id="aaaaaaaa-0000-0000-0000-000000000020",
        ),
    ]

    res = build_timeline(10, events)

    ordered = [(r.event.kind, r.event.line_no) for r in res.rows[1:]]
    assert ordered == [(SUPPLY, None), (DEMAND, 10), (DEMAND, 20)]
    assert [r.balance for r in res.rows] == [10, 20, 10, 0]
    assert res.shortfall is None
    assert res.closing_balance == 0


def test_ac_b02_worked_case_is_identical_when_event_input_order_is_reversed():
    """AC-B02 / AC-B04: "database return order never participates". The same three events
    handed to ``build_timeline`` in the opposite order must sort back to the identical
    sequence and the identical running balance.
    """
    required_date = date(2027, 3, 1)
    forward = [
        _supply_line(required_date, 10, "202703-S0011"),
        _demand_line(
            required_date, 10, "SO-100", line_no=10,
            line_id="aaaaaaaa-0000-0000-0000-000000000010",
        ),
        _demand_line(
            required_date, 10, "SO-100", line_no=20,
            line_id="aaaaaaaa-0000-0000-0000-000000000020",
        ),
    ]
    backward = list(reversed(forward))

    res_forward = build_timeline(10, forward)
    res_backward = build_timeline(10, backward)

    assert [r.balance for r in res_backward.rows] == [r.balance for r in res_forward.rows]
    assert [(r.event.kind, r.event.line_no) for r in res_backward.rows] == [
        (r.event.kind, r.event.line_no) for r in res_forward.rows
    ]


def test_a_missing_line_no_sorts_after_a_present_one_on_the_same_day_and_ref():
    """PLAN 3.5: "then line_no with missing numbers last". Two demand lines tied on date
    and SO number, one carrying a line number and one without, must not let the blank one
    jump ahead of the numbered one.
    """
    d = date(2027, 3, 1)
    events = [
        _demand_line(d, 5, "SO-400", line_no=None, line_id="cccccccc-0000-0000-0000-000000000099"),
        _demand_line(d, 5, "SO-400", line_no=7, line_id="cccccccc-0000-0000-0000-000000000007"),
    ]

    res = build_timeline(0, events)

    ordered_line_nos = [r.event.line_no for r in res.rows[1:]]
    assert ordered_line_nos == [7, None]


def test_a_tied_line_no_is_broken_by_the_internal_line_id():
    """PLAN 3.5: line_no ties break on "the internal SO-line ID" as the final stable key.
    The id is never displayed, so this only proves the sort order, not any UI concern.
    """
    d = date(2027, 3, 1)
    events = [
        _demand_line(d, 5, "SO-400", line_no=10, line_id="bbbbbbbb-0000-0000-0000-000000000020"),
        _demand_line(d, 5, "SO-400", line_no=10, line_id="bbbbbbbb-0000-0000-0000-000000000010"),
    ]

    res = build_timeline(0, events)

    ordered_ids = [r.event.line_id for r in res.rows[1:]]
    assert ordered_ids == [
        "bbbbbbbb-0000-0000-0000-000000000010",
        "bbbbbbbb-0000-0000-0000-000000000020",
    ]


def test_horizon_excludes_later_events_without_touching_earlier_ones():
    res = build_timeline(
        0,
        [
            _demand(date(2026, 8, 1), 10, "near"),
            _demand(date(2027, 8, 1), 999, "far"),
        ],
        horizon_end=date(2026, 12, 31),
    )
    refs = [r.event.ref for r in res.rows]
    assert "near" in refs and "far" not in refs
    assert res.closing_balance == -10


def test_opening_only_timeline_is_valid():
    res = build_timeline(250, [])
    assert res.closing_balance == 250
    assert res.shortfall is None
    assert len(res.rows) == 1


def test_month_grouping_cannot_change_a_balance():
    events = [
        _demand(date(2026, 7, 1), 135, "SO397450"),
        _supply(date(2026, 7, 12), 100, "PO-A"),
        _demand(date(2026, 8, 3), 72, "SO397450"),
    ]
    res = build_timeline(40, events)
    grouped = group_by_month(res.rows)
    flattened = [r.balance for _, rows in grouped for r in rows]
    assert flattened == [r.balance for r in res.rows]
    assert [k for k, _ in grouped] == [None, "2026-07", "2026-08"]


def test_supply_stage_is_carried_not_flattened():
    """On-order can still be cancelled or re-dated; in-transit cannot. The sum drives the
    balance and the split is what a person deciding a quantity reads."""
    res = build_timeline(
        0,
        [
            _supply(date(2026, 8, 1), 400, "PO-A", SUPPLY_ON_ORDER),
            _supply(date(2026, 8, 2), 89, "SHIP-1", SUPPLY_IN_TRANSIT),
        ],
    )
    stages = [r.event.supply_stage for r in res.rows if r.event.kind == SUPPLY]
    assert stages == [SUPPLY_ON_ORDER, SUPPLY_IN_TRANSIT]
    assert res.closing_balance == 489  # the real "400 + 89 = 489" from the printed sheet


# --------------------------------------------------------------------------- #
# source resolution
# --------------------------------------------------------------------------- #

def test_SRTWT7408_uses_the_pool_and_never_buys():
    """The regression case. Demand 67 (60 project + 7 dealer) sits against customer bins
    while 4,397 sits in the BRW pool. Recommending a purchase here would discredit every
    other number on the report."""
    allocs = resolve_sources(67, SourceAvailability(own=0, pool=4397, pool_location="BRW"))

    assert [a.source_type for a in allocs] == [SOURCE_POOL]
    assert allocs[0].qty == 67
    assert allocs[0].location == "BRW"
    assert buy_quantity(allocs) == 0
    assert is_use_stock(allocs) is True


def test_own_bin_is_consumed_before_the_pool():
    allocs = resolve_sources(100, SourceAvailability(own=40, pool=500, pool_location="BRW"))
    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_OWN, 40), (SOURCE_POOL, 60)]
    assert buy_quantity(allocs) == 0


def test_borrowing_is_offered_before_buying_and_is_flagged_as_needing_a_claim():
    allocs = resolve_sources(
        100,
        SourceAvailability(own=10, pool=20, other=30, pool_location="BRW",
                           other_locations=("BRW-SMC",)),
    )
    assert [(a.source_type, a.qty) for a in allocs] == [
        (SOURCE_OWN, 10),
        (SOURCE_POOL, 20),
        (SOURCE_OTHER, 30),
        (SOURCE_ORDER, 40),
    ]
    borrow = next(a for a in allocs if a.source_type == SOURCE_OTHER)
    assert borrow.needs_claim is True, "nothing moves on silence"
    assert borrow.location == "BRW-SMC"
    assert buy_quantity(allocs) == 40


def test_declining_to_borrow_turns_the_remainder_into_a_purchase():
    allocs = resolve_sources(
        100,
        SourceAvailability(own=0, pool=0, other=90, other_locations=("BRW-SMC",)),
        allow_borrow=False,
    )
    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_ORDER, 100)]


def test_nothing_available_is_a_pure_purchase():
    allocs = resolve_sources(852, SourceAvailability())
    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_ORDER, 852)]
    assert is_use_stock(allocs) is False


def test_zero_demand_resolves_to_nothing_at_all():
    assert resolve_sources(0, SourceAvailability(pool=100)) == []


def test_partial_pool_cover_still_reduces_the_buy():
    """B2155-NL-BLUE from the sheet: 3,590 on hand against 7,646 project demand."""
    allocs = resolve_sources(7646, SourceAvailability(pool=3590, pool_location="BRW"))
    assert buy_quantity(allocs) == 4056
    assert is_use_stock(allocs) is False


# --------------------------------------------------------------------------- #
# opening below the floor
# --------------------------------------------------------------------------- #

def test_stock_already_below_the_floor_is_a_shortfall_today_not_a_silent_deficit():
    """The most urgent shortfall of all, and the one the timeline used to stay quiet about.

    `peak_deficit` was seeded from the opening gap while `shortfall` was only ever set
    inside the event loop, so a SKU sitting under its reorder point right now reported a
    deficit and no shortfall. Two figures on one screen disagreeing about whether there is
    a problem is worse than either answer alone: the panel reads "nothing is short" beside
    a non-zero deficit, and the planner trusts the sentence over the number.

    Real case that surfaced it: B2155-NL-BLUE opens at 10,831 against a reorder point of
    12,369.66. Nothing arrives before the next event, so the gap is real today.
    """
    result = build_timeline(
        10831,
        [TimelineEvent(at=date(2026, 6, 29), qty=8600, kind=SUPPLY,
                       supply_stage=SUPPLY_IN_TRANSIT, ref="SH-1")],
        floor=12369.655534,
    )

    assert result.shortfall is not None, "below the reorder point today, reported as nothing"
    assert result.shortfall.qty == 1538.6555
    # No event caused it, so there is no date and no document to point at. Saying "today"
    # by stamping date.today() would be a fact the data does not carry.
    assert result.shortfall.at is None
    assert result.peak_deficit == 1538.6555


def test_a_deficit_and_a_shortfall_never_disagree_about_existence():
    """The invariant, stated once so neither half can drift away from the other again."""
    cases = [
        (10831, [], 12369.655534),                       # opening under the floor
        (500, [TimelineEvent(at=date(2026, 7, 1), qty=-600, kind=DEMAND, ref="SO1")], 0),
        (500, [], 0),                                    # nothing wrong at all
        (0, [], 0),                                      # empty and at the floor
        (5000, [TimelineEvent(at=date(2026, 7, 1), qty=-100, kind=DEMAND, ref="SO2")], 100),
        # A gap the shortfall's epsilon (1e-9) calls real and `peak_deficit`'s rounding
        # (4 places) flattens to 0.0. Anything in (1e-9, 5e-5) lands in that window, and the
        # window is reachable in production because the floor is a COMPUTED reorder point,
        # not a figure a person typed. The panel then prints "Short 0 today" beside a tile
        # reading 0 with the hint "never goes short" - two contradictory sentences about the
        # same SKU, which costs more trust than either answer alone. One threshold has to
        # govern both.
        (100, [], 100.00004),
    ]
    for opening, events, floor in cases:
        r = build_timeline(opening, events, floor=floor)
        assert (r.peak_deficit > 0) == (r.shortfall is not None), (
            f"opening={opening} floor={floor} deficit={r.peak_deficit} "
            f"shortfall={r.shortfall}"
        )
