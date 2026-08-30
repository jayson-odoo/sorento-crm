"""`supply_assignment.assign()` - the golden set (S2, AC-S2-1 to AC-S2-5).

PURE, no database: the module takes plain events and answers plain numbers, the same
discipline `coverage_timeline` and `reorder_engine`'s top half already keep. Every case
lives in `fixtures/supply_assignment/*.json` as INPUT + EXPECTED, so the arithmetic can be
read and argued about without reading the code that produces it - which is what makes it a
golden set rather than a restatement of the implementation.

The cases beyond the fixtures pin behaviour the fixtures cannot state in one table: which
pile a line may draw (its own group, then the other project groups, never a site pool), that
a confirmed hold outranks the span it was read in, and that the assignment is stable under
input order.
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
        assert got.bucket == row["bucket"], where
        assert [
            [item.event.key, item.qty] for item in got.assigned
        ] == [list(pair) for pair in row["assigned"]], where

    assert [
        {"key": m.key, "balance": m.balance, "tone": m.tone} for m in result.months
    ] == expected["months"], case["case"]
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


def test_ac_s2_4b_overdue_supply_counts_as_nothing_and_is_still_listed():
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


def test_a_line_draws_its_own_group_first_then_the_other_project_groups():
    """AC-S2-1b, ruled 30 Aug: free is free.

    Ladder step 1 is "use the own ownership group, then the other PROJECT groups' free
    piles" (PLAN 3.2), and free means owed to nobody - so drawing it raises no debt and
    needs no borrow. Walking each group on its own hid exactly this: the BB line read
    `short` while IB stock sat unused, so the product-wide month balance printed green over
    a drill that printed red. The two now agree by construction.

    Own group first (30 at BRW-BB), then the others OLDEST FIRST - the IB stock held today
    before the NTC container that lands on the 5th.
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
    assert line.status == "covered"
    assert line.uncovered == 0
    assert [(item.event.key, item.qty) for item in line.assigned] == [
        ("on_hand:BRW-BB", 30.0),
        ("on_hand:BRW-IB", 70.0),
    ]
    # 30 + 100 + 50 held or arriving, 100 owed: the month says +80 and the line says
    # covered. One book, one answer.
    assert [m.balance for m in result.months] == [80.0]


def test_a_cross_group_draw_clears_a_shortfall_the_asking_group_could_not():
    """The other half of the same rule: supply arriving in ANOTHER project group clears an
    open shortfall, so the line reads `late` rather than `short` - and the balance, which
    counted that arrival all along, stops contradicting it."""
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
    assert line.status == "late"
    assert line.uncovered == 0
    assert [(item.event.key, item.qty) for item in line.assigned] == [("spo:ib", 100.0)]


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


def test_a_pin_on_an_overdue_document_holds_the_line_without_counting_the_document():
    """R31 and R21 at once, and they do not cancel each other out.

    An SPO whose arrival has passed with nothing received is NOT supply until somebody
    re-dates it, so it adds nothing to the month. But somebody was already promised it, and
    that promise still stands: the line reads `pinned`, and the drill can still say WHICH
    order the overdue document is placed against instead of showing it as free.
    """
    overdue = SupplyEvent(
        key="spo:old",
        kind="spo",
        warehouse="BRW-BB",
        at=date(2026, 7, 1),
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
