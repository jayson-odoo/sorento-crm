"""`supply_assignment.assign()` - the golden set (S2, AC-S2-1 to AC-S2-5).

PURE, no database: the module takes plain events and answers plain numbers, the same
discipline `coverage_timeline` and `reorder_engine`'s top half already keep. Every case
lives in `fixtures/supply_assignment/*.json` as INPUT + EXPECTED, so the arithmetic can be
read and argued about without reading the code that produces it - which is what makes it a
golden set rather than a restatement of the implementation.

The cases beyond the fixtures pin behaviour the fixtures cannot state in one table: which
pile a line may draw (its OWN ownership group and no other, R40), that the other groups'
piles are still OFFERED at the asker's date (`free_piles_at`, which is what makes the offer
a proposal rather than an assumption), that a confirmed hold outranks the span it was read
in, and that the assignment is stable under input order.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.scm.supply_assignment import (
    DemandLine,
    Hold,
    SupplyEvent,
    assign,
    effective_date,
    month_key,
)

FIXTURES = Path(__file__).parent / "fixtures" / "supply_assignment"


def _date(value):
    return date.fromisoformat(value) if value else None


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _run(case: dict):
    return assign(
        "zzt-product",
        as_of=_date(case["as_of"]),
        tba_from=_date(case["tba_from"]),
        lead_days=case["lead_days"],
        supply=[
            SupplyEvent(
                key=row["key"],
                kind=row["kind"],
                warehouse=row["warehouse"],
                at=_date(row["at"]),
                qty=float(row["qty"]),
                ref=row.get("ref"),
                bought_for=_date(row.get("bought_for")),
            )
            for row in case["supply"]
        ],
        demand=[
            DemandLine(
                key=row["key"],
                so_number=row["so_number"],
                line_no=row["line_no"],
                warehouse=row["warehouse"],
                agent_code=row.get("agent_code"),
                required_date=_date(row["required_date"]),
                open_qty=float(row["open_qty"]),
            )
            for row in case["demand"]
        ],
        pinned=[
            Hold(line_key=row["line"], supply_key=row["supply"], qty=float(row["qty"]))
            for row in case["pinned"]
        ],
    )


def _assert_case(name: str) -> None:
    case = _load(name)
    result = _run(case)
    expected = case["expect"]

    by_key = {line.line.key: line for line in result.lines}
    assert sorted(by_key) == sorted(row["key"] for row in expected["lines"])
    for row in expected["lines"]:
        got = by_key[row["key"]]
        where = f"{case['case']} line {row['key']}"
        assert got.status == row["status"], where
        assert got.uncovered == pytest.approx(row["uncovered"]), where
        # What the line's own month books (R37). Stated per line in the fixture, so the
        # month figures below can be read as a sum of the lines rather than taken on trust.
        assert got.short_at_date == pytest.approx(row["short_at_date"]), where
        assert got.bucket == row["bucket"], where
        assert [
            [item.event.key, item.qty] for item in got.assigned
        ] == [list(pair) for pair in row["assigned"]], where

    assert [
        {"key": m.key, "balance": m.balance, "tone": m.tone} for m in result.months
    ] == expected["months"], case["case"]
    # R37, stated as arithmetic rather than as a table of numbers somebody typed: every
    # month is the supply dated in it that stayed free, less the shortfalls it books.
    as_of = _date(case["as_of"])
    # The month a free quantity is credited to, read off the INPUT: the event's own arrival,
    # never before today (the axis starts today).
    event_month = {
        row["key"]: month_key(effective_date(_date(row["at"]), as_of))
        for row in case["supply"]
    }
    for month in result.months:
        free = sum(
            qty
            for key, qty in result.free.items()
            if event_month.get(key) == month.key
        )
        short = sum(
            line.short_at_date
            for line in result.lines
            if line.bucket == month.key
        )
        assert month.balance == pytest.approx(free - short), (
            f"{case['case']} {month.key}"
        )
    assert result.tba == pytest.approx(expected["tba"])
    assert result.undated == pytest.approx(expected["undated"])
    assert [
        {"key": event.key, "overdue": overdue}
        for event, overdue in (
            (event, event.at is not None and event.at < _date(case["as_of"]))
            for event in result.uncounted
        )
    ] == expected["uncounted"], case["case"]


# --------------------------------------------------------------------------- the golden set


def test_ac_s2_1_first_come_by_date():
    """The worked example: A covered, B late, C late, D short, and the running balance."""
    _assert_case("ac_s2_1_first_come_by_date")


def test_ac_s2_2_a_pinned_hold_binds_before_any_first_come_draw():
    _assert_case("ac_s2_2_pinned_hold_binds_first")


def test_ac_s2_3_tba_and_undated_lines_draw_nothing():
    _assert_case("ac_s2_3_tba_and_undated_draw_nothing")


def test_ac_s2_4b_a_dead_document_counts_as_nothing_and_is_still_listed():
    """R31, as R-O leaves it (3 Sep 2026): a document past `overdue_dead_days` counts as
    nothing. The fixture's document was re-dated to 1 April when R-O landed - at 16 days
    late it is now alive and counted at its assumed date, which is a different case (the
    R-O block at the bottom of this file)."""
    _assert_case("ac_s2_4b_overdue_supply_counts_nothing")


def test_ac_s2_5_past_due_debt_lands_in_the_current_month():
    _assert_case("ac_s2_5_past_due_lands_in_the_current_month")


# --------------------------------------------------------------------------- the rest


AS_OF = date(2026, 9, 1)
TBA = date(2029, 1, 1)


def _line(key, warehouse, required_date, qty, **kw) -> DemandLine:
    return DemandLine(
        key=key,
        so_number=f"SO{key}",
        line_no=1,
        warehouse=warehouse,
        agent_code="JAY",
        required_date=required_date,
        open_qty=qty,
        **kw,
    )


def _hand(warehouse, qty) -> SupplyEvent:
    return SupplyEvent(
        key=f"on_hand:{warehouse}",
        kind="on_hand",
        warehouse=warehouse,
        at=AS_OF,
        qty=qty,
    )


def test_an_undecided_line_draws_its_own_group_and_never_another_groups_pile():
    """R40, ruled 30 Aug by the captain, partially reversing AC-S2-1b.

    The 30 August draft gave an undecided line the other project groups' free piles, on
    "free is free". The captain refused it on the live book - a BB line of 507 with no
    inquiry and no planning had silently eaten the IB pile - "who is us to decide those BB
    group takes our IB pile". So an undecided line draws its OWN group and stops: the 30 at
    BRW-BB, then short 70, while IB's 100 and NTC's container are untouched and free.

    The month still foots (R37): 150 stayed free (IB's 100 and NTC's 50) and 70 went
    short, so +80.
    """
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[
            _hand("BRW-BB", 30),
            _hand("BRW-IB", 100),
            SupplyEvent(
                key="spo:ntc",
                kind="spo",
                warehouse="BRW-NTC",
                at=date(2026, 9, 5),
                qty=50,
                ref="SPO NTC",
            ),
        ],
        demand=[_line("only", "BRW-BB", date(2026, 9, 20), 100)],
    )
    line = result.lines[0]
    assert line.status == "short"
    assert line.uncovered == 70.0
    assert [(item.event.key, item.qty) for item in line.assigned] == [
        ("on_hand:BRW-BB", 30.0),
    ]
    assert result.free["on_hand:BRW-IB"] == 100.0, "IB's pile is untouched"
    assert result.free["spo:ntc"] == 50.0
    assert [m.balance for m in result.months] == [80.0]


def test_the_ladder_still_offers_the_other_groups_free_pile_at_the_askers_date():
    """R40's other half: refusing to ASSUME is not refusing to OFFER.

    `free_piles_at` is what ladder step 1's second half is built from (PLAN 3.2, read by
    `use_candidates_for`): the other groups' piles as they stood on the asker's own date,
    net of what is pinned and of what that group's own earlier lines took. On Confirm the
    proposal becomes a pinned hold, and only THEN does IB's pile deplete for everybody else.
    """
    from app.services.scm.supply_assignment import free_piles_at

    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[
            _hand("BRW-BB", 30),
            _hand("BRW-IB", 100),
        ],
        demand=[
            _line("only", "BRW-BB", date(2026, 9, 20), 100),
            # IB's own earlier line takes 40 of its pile before the asker's date, so the
            # offer is 60 and not 100.
            _line("ib_early", "BRW-IB", date(2026, 9, 10), 40),
        ],
    )
    piles = free_piles_at(result, at=date(2026, 9, 20), as_of=AS_OF)
    assert [(event.warehouse, qty) for event, qty in piles.get("IB", [])] == [
        ("BRW-IB", 60.0),
    ]
    assert "BB" not in piles, "BB's own 30 was drawn by the asker itself"


def test_an_arrival_clears_only_its_own_groups_shortfall():
    """The R40 rule from the supply side: an SPO landing in ANOTHER project group does not
    reach across and clear a BB shortfall, so the line stays `short` rather than `late`."""
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[
            SupplyEvent(
                key="spo:ib",
                kind="spo",
                warehouse="BRW-IB",
                at=date(2026, 10, 10),
                qty=100,
                ref="SPO IB",
            )
        ],
        demand=[_line("only", "BRW-BB", date(2026, 9, 20), 100)],
    )
    line = result.lines[0]
    assert line.status == "short"
    assert line.uncovered == 100.0
    assert line.assigned == ()
    assert result.free["spo:ib"] == 100.0


def test_the_site_pool_is_its_own_group():
    """A pool is reached through `pool_warehouse_id`, never as an ownership group, so its
    book nets on its own (plan 3.2 rung 4) - a BB line does not silently eat it.

    This is the ONE exclusion the cross-group rule above keeps (AC-S2-1b: "pools never").
    Taking pool stock is the pool RUNG, which raises an ORDER_BACK against the pool order
    (R34); free stock in another project group raises nothing. The two are different acts,
    so only one of them happens here.
    """
    pool = SupplyEvent(
        key="on_hand:BRW", kind="on_hand", warehouse="BRW", at=AS_OF, qty=50, is_pool=True
    )
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[pool],
        demand=[
            _line("bb", "BRW-BB", date(2026, 9, 20), 50),
            _line("pool", "BRW", date(2026, 9, 25), 20, is_pool=True),
        ],
    )
    by_key = {line.line.key: line for line in result.lines}
    assert by_key["bb"].status == "short"
    assert by_key["pool"].status == "covered"


def test_the_answer_does_not_depend_on_the_order_the_rows_arrive_in():
    """Two reads of the same book give the same assignment: the walk sorts, it does not
    trust its caller's ordering. A view whose figures move when a query plan changes is
    worse than no view."""
    supply = [
        _hand("BRW-BB", 40),
        SupplyEvent(
            key="spo:1", kind="spo", warehouse="BRW-BB", at=date(2026, 10, 1), qty=60
        ),
    ]
    demand = [
        _line("early", "BRW-BB", date(2026, 9, 10), 50),
        _line("later", "BRW-BB", date(2026, 11, 1), 50),
    ]
    forward = assign(
        "p", as_of=AS_OF, tba_from=TBA, lead_days=90, supply=supply, demand=demand
    )
    backward = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=list(reversed(supply)),
        demand=list(reversed(demand)),
    )

    def shape(result):
        return sorted(
            (
                line.line.key,
                line.status,
                line.uncovered,
                tuple((item.event.key, item.qty) for item in line.assigned),
            )
            for line in result.lines
        )

    assert shape(forward) == shape(backward)
    assert shape(forward) == [
        ("early", "late", 0.0, (("on_hand:BRW-BB", 40.0), ("spo:1", 10.0))),
        ("later", "covered", 0.0, (("spo:1", 50.0),)),
    ]


def test_a_hold_larger_than_the_document_takes_only_what_the_document_holds():
    """A stale hold (the shipment shrank, the allocation did not) may not conjure supply."""
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_hand("BRW-BB", 10)],
        demand=[_line("x", "BRW-BB", date(2026, 9, 20), 40)],
        pinned=[Hold(line_key="x", supply_key="on_hand:BRW-BB", qty=40)],
    )
    line = result.lines[0]
    assert [(item.event.key, item.qty) for item in line.assigned] == [
        ("on_hand:BRW-BB", 10.0)
    ]
    assert line.uncovered == 30
    assert line.status == "short"


def test_a_product_with_no_movement_at_all_still_answers_the_current_month():
    """The axis starts at the current month even when nothing is dated in it: a row of
    dashes is a row nobody can read."""
    result = assign("p", as_of=AS_OF, tba_from=TBA, lead_days=90, supply=[], demand=[])
    assert [(m.key, m.balance, m.tone) for m in result.months] == [
        ("2026-09", 0.0, "green")
    ]
    assert result.tba == 0 and result.undated == 0


# --------------------------------------------------------------------------- the golden
# set cannot state in a table: same-day ties and a hold larger than its own line


def test_supply_and_demand_on_the_same_date_supply_goes_first():
    """A container cleared and a despatch due the same day: the arrival is on the books
    before the day's shipment (`_walk_group`'s `kind` tie-break), so the line draws it
    rather than reading short for one day it was never actually short on."""
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[
            SupplyEvent(
                key="spo:1", kind="spo", warehouse="BRW-BB", at=date(2026, 9, 20), qty=50
            )
        ],
        demand=[_line("x", "BRW-BB", date(2026, 9, 20), 50)],
    )
    line = result.lines[0]
    assert line.status == "covered"
    assert [(item.event.key, item.qty) for item in line.assigned] == [("spo:1", 50.0)]


def test_two_lines_of_one_order_on_the_same_date_draw_by_line_number_deterministically():
    """Same required date, same group, same SO: `_identity`'s tie-break is the SO number
    then the line number, never the order the rows happened to arrive in - so the earlier
    line number takes the pile first, on every run."""
    supply = [_hand("BRW-BB", 10)]
    demand = [
        DemandLine(
            key="l2", so_number="SOA", line_no=2, warehouse="BRW-BB", agent_code="JAY",
            required_date=date(2026, 9, 20), open_qty=10,
        ),
        DemandLine(
            key="l1", so_number="SOA", line_no=1, warehouse="BRW-BB", agent_code="JAY",
            required_date=date(2026, 9, 20), open_qty=10,
        ),
    ]
    forward = assign(
        "p", as_of=AS_OF, tba_from=TBA, lead_days=90, supply=supply, demand=demand
    )
    backward = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=list(reversed(supply)),
        demand=list(reversed(demand)),
    )

    def shape(result):
        return {line.line.key: line.status for line in result.lines}

    assert shape(forward) == shape(backward) == {"l1": "covered", "l2": "short"}


def test_a_pinned_hold_larger_than_the_lines_open_qty_leaves_the_excess_in_the_pile():
    """The hold cannot take more than the LINE needs, whatever quantity it claims: the
    excess is never removed from `left`, so it stays free for whoever queues next rather
    than being lost or double-counted."""
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_hand("BRW-BB", 100)],
        demand=[
            _line("pinned", "BRW-BB", date(2026, 9, 20), 10),
            _line("later", "BRW-BB", date(2026, 9, 25), 50),
        ],
        pinned=[Hold(line_key="pinned", supply_key="on_hand:BRW-BB", qty=40)],
    )
    by_key = {line.line.key: line for line in result.lines}
    pinned_line = by_key["pinned"]
    assert pinned_line.status == "pinned"
    assert [(item.event.key, item.qty) for item in pinned_line.assigned] == [
        ("on_hand:BRW-BB", 10.0)
    ]
    # 100 on hand - 10 the pin actually took = 90 still free; the later line draws its own
    # 50 from what is left, proving the pin's excess 30 claim was never subtracted.
    later_line = by_key["later"]
    assert later_line.status == "covered"
    assert later_line.uncovered == 0


# --------------------------------------------------------------------------- AC-S2-1b:
# a pin outranks the span it was read in


def test_a_pinned_hold_binds_even_when_its_supply_is_outside_the_span():
    """AC-S2-1b / R21. The hold IS the supply.

    The three ways a confirmed hold's bin falls outside a read: it is a SITE POOL, it is a
    bin flagged out of fulfilment planning, or the reader narrowed to one ownership group
    and the stock sits in another. In every one of them the hold was confirmed against real
    stock, so honouring it is not optimism - dropping it is a lie. Before this, a hold whose
    key was not in the span was skipped silently and a board-covered line printed `short`:
    16 pool holds (163 units) and ~103 units at unflagged bins on the 30 Aug dev copy.
    """
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        # Nothing at all in the span - the span is what the caller narrowed it to.
        supply=[],
        demand=[
            _line("pool_held", "BRW-BB", date(2026, 9, 20), 40),
            _line("unflagged", "BRW-BB", date(2026, 9, 25), 30),
        ],
        pinned=[
            Hold(
                line_key="pool_held",
                supply_key="on_hand:pool-uuid",
                qty=40,
                warehouse="BRW",
            ),
            Hold(
                line_key="unflagged",
                supply_key="on_hand:hp-uuid",
                qty=30,
                warehouse="BRW-HP",
            ),
        ],
    )
    by_key = {line.line.key: line for line in result.lines}
    assert by_key["pool_held"].status == "pinned"
    assert by_key["pool_held"].uncovered == 0
    # The source the drill prints is the bin the HOLD names, not a blank.
    assert [
        (item.event.warehouse, item.qty, item.pinned)
        for item in by_key["pool_held"].assigned
    ] == [("BRW", 40.0, True)]
    assert by_key["unflagged"].status == "pinned"
    assert [
        (item.event.warehouse, item.qty) for item in by_key["unflagged"].assigned
    ] == [("BRW-HP", 30.0)]
    # And the month agrees: 70 pinned against 70 owed nets to nothing owed.
    assert [m.balance for m in result.months] == [0.0]


def test_a_pinned_document_outside_the_span_is_named_by_its_reference():
    """The same rule for a placement link. An `order_inquiry_links` row names an SPO or a PO
    line, not a bin, so the stood-up event carries the DOCUMENT reference and the drill
    reads `SPO 2026/09-0088` rather than `On hand None`."""
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[],
        demand=[_line("linked", "BRW-BB", date(2026, 10, 1), 25)],
        pinned=[
            Hold(
                line_key="linked",
                supply_key="spo:allocation-uuid",
                qty=25,
                kind="spo",
                warehouse="DC1-IB",
                ref="SPO 2026/09-0088",
            )
        ],
    )
    line = result.lines[0]
    assert line.status == "pinned"
    assert [(item.event.kind, item.event.ref, item.qty) for item in line.assigned] == [
        ("spo", "SPO 2026/09-0088", 25.0)
    ]


def test_a_pin_never_conjures_more_than_the_line_needs():
    """The stood-up event is worth exactly what the pin took, never the hold's whole claim -
    a stale hold (the shipment shrank, the allocation did not) must not inflate the month."""
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[],
        demand=[_line("x", "BRW-BB", date(2026, 9, 20), 10)],
        pinned=[Hold(line_key="x", supply_key="on_hand:elsewhere", qty=999, warehouse="BRW")],
    )
    assert result.lines[0].status == "pinned"
    assert [item.qty for item in result.lines[0].assigned] == [10.0]
    assert [m.balance for m in result.months] == [0.0]


# --------------------------------------------------------------------------- the unlocated
# bucket


def test_a_line_with_no_warehouse_draws_nothing_and_lands_in_its_own_bucket():
    """2,312 open lines on the 30 Aug dev copy carry no warehouse. They are in no group's
    pile, so they can draw nothing - and a screen that lists what is owed while silently
    omitting them answers the wrong question. Counted, in a bucket of their own, and BEFORE
    the date is read: no location holds whatever the date says.
    """
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_hand("BRW-BB", 500)],
        demand=[
            DemandLine(
                key="nowhere",
                so_number="SO1",
                line_no=1,
                warehouse=None,
                agent_code="JAY",
                required_date=date(2026, 9, 20),
                open_qty=45,
            ),
            DemandLine(
                key="nowhere_tba",
                so_number="SO2",
                line_no=1,
                warehouse=None,
                agent_code="JAY",
                required_date=date(2030, 1, 1),
                open_qty=5,
            ),
        ],
    )
    by_key = {line.line.key: line for line in result.lines}
    assert by_key["nowhere"].bucket == "unlocated"
    assert by_key["nowhere"].assigned == ()
    assert by_key["nowhere"].uncovered == 45
    # Dated 2030 AND unlocated: unlocated wins, because that is the fact somebody must fix.
    assert by_key["nowhere_tba"].bucket == "unlocated"
    assert result.unlocated == -50
    assert result.tba == 0
    # The 500 on hand is untouched and the months never saw the unlocated demand.
    assert [m.balance for m in result.months] == [500.0]


def test_a_pin_on_a_dead_document_holds_the_line_without_counting_the_document():
    """R31 and R21 at once, and they do not cancel each other out.

    An SPO so late that the grace period has given up on it (R-O: later than
    `overdue_dead_days`) is NOT supply until somebody re-dates it, so it adds nothing to
    the month. But somebody was already promised it, and that promise still stands: the
    line reads `pinned`, and the drill can still say WHICH order the document is placed
    against instead of showing it as free.

    Dated 5 January against a walk taken on 1 September - 239 days late. Under R31 any
    past arrival was this case; under R-O only a dead one is.
    """
    overdue = SupplyEvent(
        key="spo:old",
        kind="spo",
        warehouse="BRW-BB",
        at=date(2026, 1, 5),
        qty=40,
        ref="SPO OLD",
    )
    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[overdue],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 40)],
        pinned=[Hold(line_key="waiting", supply_key="spo:old", qty=40, kind="spo")],
    )
    line = result.lines[0]
    assert line.status == "pinned"
    assert line.uncovered == 0
    # The REAL event, so the drill's `assigned_to` finds it by key and the row keeps its
    # `overdue` flag.
    assert [(item.event.key, item.qty) for item in line.assigned] == [("spo:old", 40.0)]
    assert [event.key for event in result.uncounted] == ["spo:old"]
    # Counted as nothing: the month still owes the 40 (R31).
    assert [m.balance for m in result.months] == [-40.0]


# --------------------------------------------------------------------------- R-M (3 Sep)


def test_a_groups_book_position_nets_its_whole_open_book_not_the_asking_date():
    """R-M's arithmetic, from the production cell (SO419417, SRTWT7443, 3 Sep 2026).

    BRW-IB holds 2,237 on hand against 2,684 of open IB demand - 1,708 due on or before the
    asking BB line's 5 October and 976 after it - so IB's own book is 447 SHORT. The
    date-bounded pile the offer used to be made of reads 529 free on 5 October, because
    demand due AFTER that day is not subtracted from it; the book position is the figure
    that says the group has nothing to spare.
    """
    from app.services.scm.supply_assignment import group_book_positions

    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_hand("BRW-IB", 2237)],
        demand=[
            _line("ib_near", "BRW-IB", date(2026, 10, 1), 1708),
            _line("ib_far", "BRW-IB", date(2026, 11, 20), 976),
            _line("bb_asker", "BRW-BB", date(2026, 10, 5), 4),
        ],
    )

    assert group_book_positions(result)["IB"] == -447.0
    assert group_book_positions(result)["BB"] == -4.0


def test_a_groups_book_position_counts_the_supply_the_assignment_counted():
    """The book is on hand PLUS the counted supply (R31, as R-O leaves it: a DEAD document
    is not supply).

    2,237 on hand and an SPO of 256 landing inside the span reads -191 against the same
    2,684 of demand; a dead SPO of 500 adds nothing at all. The dead one was dated 1 August
    until R-O landed, which is 31 days late and therefore alive now - the live-and-late
    half of the same rule is `test_a_group_book_counts_a_late_alive_document_and_not_a_dead_one`.
    """
    from app.services.scm.supply_assignment import group_book_positions

    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[
            _hand("BRW-IB", 2237),
            SupplyEvent(
                key="spo:ib", kind="spo", warehouse="BRW-IB",
                at=date(2026, 10, 20), qty=256, ref="SPO IB",
            ),
            SupplyEvent(
                key="spo:overdue", kind="spo", warehouse="BRW-IB",
                at=date(2026, 1, 5), qty=500, ref="SPO OVERDUE",
            ),
        ],
        demand=[
            _line("ib_near", "BRW-IB", date(2026, 10, 1), 1708),
            _line("ib_far", "BRW-IB", date(2026, 11, 20), 976),
        ],
    )

    assert group_book_positions(result)["IB"] == -191.0


def test_a_cross_group_hold_leaves_the_lending_groups_book_by_what_it_pinned():
    """A confirmed hold at IB's bin taken by a BB line is not in IB's demand, so the book
    has to subtract it or the same 40 would read as IB's twice."""
    from app.services.scm.supply_assignment import group_book_positions

    result = assign(
        "p",
        as_of=AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_hand("BRW-IB", 100), _hand("BRW-BB", 0)],
        demand=[
            _line("ib_own", "BRW-IB", date(2026, 10, 1), 20),
            _line("bb_pinned", "BRW-BB", date(2026, 9, 20), 40),
        ],
        pinned=[Hold(line_key="bb_pinned", supply_key="on_hand:BRW-IB", qty=40)],
    )

    positions = group_book_positions(result)
    assert positions["IB"] == 40.0, "100 on hand, 20 of its own owed, 40 pinned away"
    assert positions["BB"] == -40.0


# --------------------------------------------------------------------------- R-O (3 Sep)
#
# AN OVERDUE DOCUMENT COUNTS AS SUPPLY AFTER A GRACE PERIOD (`PLAN-scm-pool-chain-first.md`
# ruling R-O, issue #586), superseding R31 for everything that is not yet dead.
#
# The captain on SO419417, 3 September 2026: "Available for Project" at BRW read 355 off
# 725 SPO units dated 24 July and 6 August and still unreceived, while the ladder lent 4
# off the 11 standing on the floor. The display was right; the engine was ignoring a late
# document. A document whose arrival has passed with nothing received now counts as supply
# landing on `today + overdue_grace_days`, and one later than `overdue_dead_days` counts as
# nothing at all - which is R31 kept for the dead.
#
# These cases are inline rather than JSON fixtures because `_assert_case` credits a month
# off the INPUT arrival date, and the whole point here is that the walk plans against a
# DIFFERENT one.

#: The captain's own day, and the document's own dates, so the arithmetic in the UAC
#: ("41 days late, assumed by 17 Sep 2026") is the arithmetic here.
R_O_AS_OF = date(2026, 9, 3)
R_O_STATED = date(2026, 7, 24)
R_O_ASSUMED = date(2026, 9, 17)


def _late_spo(at: date, qty: float = 100) -> SupplyEvent:
    return SupplyEvent(
        key="spo:late",
        kind="spo",
        warehouse="BRW-BB",
        at=at,
        qty=qty,
        ref="SPO 2026/07-0031",
    )


def test_an_alive_late_document_counts_as_supply_at_the_assumed_date():
    """AC-O.1. 41 days late on 3 September, a 14-day grace: the 100 lands 17 September and
    the line due 20 September is covered by it, off a bin holding nothing."""
    result = assign(
        "p",
        as_of=R_O_AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_late_spo(R_O_STATED)],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
        overdue_grace_days=14,
        overdue_dead_days=90,
    )

    assert [event.key for event in result.uncounted] == [], (
        "a late-but-alive document is no longer uncounted (R-O supersedes R31)"
    )
    counted = {event.key: event for event in result.supply}
    assert counted["spo:late"].at == R_O_ASSUMED, "the walk plans against the ASSUMED date"
    assert counted["spo:late"].stated_at == R_O_STATED, (
        "and it still carries the date the document itself states"
    )
    line = result.lines[0]
    assert line.status == "covered"
    assert line.uncovered == 0
    assert [(item.event.key, item.qty) for item in line.assigned] == [("spo:late", 50.0)]


def test_a_line_due_inside_the_grace_gets_nothing_from_the_late_document():
    """AC-O.2. The same document against a line due 10 September: the goods are not
    assumed to be there before the 17th, so the line goes without ON ITS OWN DATE and the
    walk carries on (the ladder reads `short_at_date`, so it is offered nothing)."""
    result = assign(
        "p",
        as_of=R_O_AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_late_spo(R_O_STATED)],
        demand=[_line("early", "BRW-BB", date(2026, 9, 10), 50)],
        overdue_grace_days=14,
        overdue_dead_days=90,
    )

    line = result.lines[0]
    assert line.short_at_date == 50.0, "nothing had arrived by the 10th"
    assert line.status == "late", "the 17th clears it afterwards, which is not a promise"


def test_a_dead_late_document_counts_as_nothing_exactly_as_r31_said():
    """AC-O.3. 125 days late against a 90-day dead line: not supply, and still RETURNED as
    uncounted so the screen can ask somebody to chase it."""
    result = assign(
        "p",
        as_of=R_O_AS_OF,
        tba_from=TBA,
        lead_days=90,
        supply=[_late_spo(date(2026, 5, 1))],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
        overdue_grace_days=14,
        overdue_dead_days=90,
    )

    assert [event.key for event in result.uncounted] == ["spo:late"]
    assert result.supply == ()
    line = result.lines[0]
    assert line.status == "short"
    assert line.uncovered == 50.0


def test_the_grace_and_the_dead_line_are_read_off_the_arguments():
    """The two numbers are POLICY (`scm.priority_policy`, migration 464), so the module
    obeys what it is handed: a 0-day grace lands the document today, and a dead line of 30
    kills the same 41-day-late document the 90-day one keeps."""
    landed_today = assign(
        "p", as_of=R_O_AS_OF, tba_from=TBA, lead_days=90,
        supply=[_late_spo(R_O_STATED)],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
        overdue_grace_days=0, overdue_dead_days=90,
    )
    assert {e.key: e.at for e in landed_today.supply}["spo:late"] == R_O_AS_OF

    dead_sooner = assign(
        "p", as_of=R_O_AS_OF, tba_from=TBA, lead_days=90,
        supply=[_late_spo(R_O_STATED)],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
        overdue_grace_days=14, overdue_dead_days=30,
    )
    assert [event.key for event in dead_sooner.uncounted] == ["spo:late"]


def test_defaults_unset_reproduce_r31_a_day_late_is_dead_today_still_counts():
    """SHIPPED default (captain's ruling, 3 Sep 2026): with NEITHER argument passed, the
    module falls back to `DEFAULT_OVERDUE_GRACE_DAYS` / `DEFAULT_OVERDUE_DEAD_DAYS`, both 0
    at ship. Dead at 0 makes ANY lateness dead - which is R31 exactly - so production keeps
    today's behaviour until someone raises the two numbers through the settings route.
    """
    one_day_late = assign(
        "p", as_of=R_O_AS_OF, tba_from=TBA, lead_days=90,
        supply=[_late_spo(date(2026, 9, 2))],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
    )
    assert [event.key for event in one_day_late.uncounted] == ["spo:late"], (
        "a document one day late counts as nothing at all, exactly as R31 always had it"
    )

    arrives_today = assign(
        "p", as_of=R_O_AS_OF, tba_from=TBA, lead_days=90,
        supply=[_late_spo(R_O_AS_OF)],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
    )
    assert [event.key for event in arrives_today.uncounted] == [], (
        "arriving TODAY is not late at all, and it still counts"
    )
    assert {e.key: e.at for e in arrives_today.supply}["spo:late"] == R_O_AS_OF


def test_the_dead_line_itself_is_still_counted_not_uncounted():
    """Review fix round nit: the boundary `days_late == overdue_dead_days` is pinned
    explicitly beside the two arguments above. `counted_event` refuses only what is
    STRICTLY past the dead line (`days_late > dead`), so a document exactly as late as the
    dead line still counts - the 41-day-late document against a dead line of 41 lands, not
    uncounted."""
    exactly_dead_line = assign(
        "p", as_of=R_O_AS_OF, tba_from=TBA, lead_days=90,
        supply=[_late_spo(R_O_STATED)],
        demand=[_line("waiting", "BRW-BB", date(2026, 9, 20), 50)],
        overdue_grace_days=14, overdue_dead_days=41,
    )
    assert [event.key for event in exactly_dead_line.uncounted] == []
    assert {e.key: e.at for e in exactly_dead_line.supply}["spo:late"] == R_O_ASSUMED


def test_a_group_book_counts_a_late_alive_document_and_not_a_dead_one():
    """AC-O.4. `group_book_positions` follows the counted-events rule and nothing else, so
    the board's lending cap and the walk can never disagree about a late document."""
    from app.services.scm.supply_assignment import group_book_positions

    def book(stated: date) -> float:
        result = assign(
            "p",
            as_of=R_O_AS_OF,
            tba_from=TBA,
            lead_days=90,
            supply=[
                SupplyEvent(
                    key="on_hand:BRW-IB", kind="on_hand", warehouse="BRW-IB",
                    at=R_O_AS_OF, qty=2237,
                ),
                SupplyEvent(
                    key="spo:late", kind="spo", warehouse="BRW-IB",
                    at=stated, qty=500, ref="SPO LATE",
                ),
            ],
            demand=[
                _line("ib_near", "BRW-IB", date(2026, 10, 1), 1708),
                _line("ib_far", "BRW-IB", date(2026, 11, 20), 976),
            ],
            overdue_grace_days=14,
            overdue_dead_days=90,
        )
        return group_book_positions(result)["IB"]

    # 2,237 + 500 - 2,684: the late-but-alive document is in the book.
    assert book(date(2026, 8, 1)) == 53.0
    # 2,237 - 2,684: the dead one is not (R31).
    assert book(date(2026, 1, 5)) == -447.0
