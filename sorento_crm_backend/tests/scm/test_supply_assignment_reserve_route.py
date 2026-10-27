"""BOARD-NO-HOLD, the pure half: a confirmed board Reserve is a ROUTE, not a stock hold.

Owner (27 Oct 2026): "board decision don't hold stock, board decision is just a planning
choice". Card Q1 (a): the plan keeps one job, the line may draw the location its plan names
AT ITS OWN DATE, in date order with everyone else who may draw there. `Hold(route=True)`
carries that. Every other pinned hold (OI placements, landed goods, book S/O pins, Borrow)
still binds first, at any date.

Plan: documentation/plans/scm/PLAN-board-no-hold-27oct.md. No database: `assign()` takes
plain events and answers plain numbers, as `test_stock_debt_lendable.py` does.

Case numbers follow the captain's test list (1 to 8).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.scm.supply_assignment import (
    EPSILON,
    KIND_ON_HAND,
    KIND_SPO,
    STATUS_COVERED,
    STATUS_LATE,
    STATUS_PINNED,
    STATUS_SHORT,
    DemandLine,
    Hold,
    SupplyEvent,
    assign,
)

AS_OF = date(2026, 10, 27)
TBA_FROM = date(2029, 1, 1)
LEAD = 90

POOL_KEY = "on_hand:brw"
IR_KEY = "on_hand:brw-ir"


def _d(days):
    return AS_OF + timedelta(days=days)


def _pool(qty, key=POOL_KEY):
    return SupplyEvent(
        key=key, kind=KIND_ON_HAND, warehouse="BRW", at=AS_OF, qty=qty, is_pool=True
    )


def _ir_bin(qty, key=IR_KEY):
    return SupplyEvent(key=key, kind=KIND_ON_HAND, warehouse="BRW-IR", at=AS_OF, qty=qty)


def _line(key, so, qty, due, *, is_pool=False):
    return DemandLine(
        key=key,
        so_number=so,
        line_no=1,
        warehouse="BRW" if is_pool else "BRW-IR",
        agent_code="LEENA",
        required_date=due,
        open_qty=qty,
        is_pool=is_pool,
    )


def _route(line_key, qty, key=POOL_KEY, warehouse="BRW"):
    return Hold(
        line_key=line_key,
        supply_key=key,
        qty=qty,
        kind=KIND_ON_HAND,
        warehouse=warehouse,
        route=True,
    )


def _pin(line_key, qty, key=IR_KEY, warehouse="BRW-IR"):
    return Hold(
        line_key=line_key,
        supply_key=key,
        qty=qty,
        kind=KIND_ON_HAND,
        warehouse=warehouse,
    )


def _walk(supply, demand, pinned, **extra):
    return assign(
        "P",
        as_of=AS_OF,
        tba_from=TBA_FROM,
        lead_days=LEAD,
        supply=supply,
        demand=demand,
        pinned=pinned,
        overdue_grace_days=0,
        overdue_dead_days=0,
        **extra,
    )


def _by_key(result):
    return {row.line.key: row for row in result.lines}


def _taken(row):
    """Event key -> total quantity the line took from it."""
    out = {}
    for item in row.assigned:
        out[item.event.key] = out.get(item.event.key, 0.0) + item.qty
    return out


def test_1_cb4702_route_line_draws_the_pool_and_an_undecided_project_line_does_not():
    a = _line("a", "SO426986", 364, _d(10))
    b = _line("b", "SO400884", 36, _d(58))
    rows = _by_key(_walk([_pool(36)], [a, b], [_route("b", 36)]))

    assert rows["a"].status == STATUS_SHORT
    assert rows["a"].uncovered == pytest.approx(364)
    assert rows["a"].assigned == ()

    assert rows["b"].status == STATUS_COVERED
    assert rows["b"].status != STATUS_PINNED
    assert rows["b"].uncovered == pytest.approx(0)
    assert _taken(rows["b"]) == {POOL_KEY: pytest.approx(36)}
    assert all(item.pinned is False for item in rows["b"].assigned)


def test_2_route_lines_on_one_bin_take_at_their_own_date_earliest_first():
    a = _line("a", "SO1", 36, _d(10))
    b = _line("b", "SO2", 36, _d(58))
    # Hold order is the LATER line first, so only date order can give A the pile.
    rows = _by_key(_walk([_pool(36)], [a, b], [_route("b", 36), _route("a", 36)]))

    assert rows["a"].status == STATUS_COVERED
    assert _taken(rows["a"]) == {POOL_KEY: pytest.approx(36)}
    assert rows["b"].status == STATUS_SHORT
    assert rows["b"].uncovered == pytest.approx(36)
    assert rows["b"].assigned == ()


def test_3_a_dealer_pool_line_due_first_draws_the_pool_before_the_route_line():
    dealer = _line("dealer", "SO9", 30, _d(5), is_pool=True)
    proj = _line("proj", "SO2", 36, _d(20))
    rows = _by_key(_walk([_pool(36)], [dealer, proj], [_route("proj", 36)]))

    assert rows["dealer"].status == STATUS_COVERED
    assert _taken(rows["dealer"]) == {POOL_KEY: pytest.approx(30)}
    assert _taken(rows["proj"]) == {POOL_KEY: pytest.approx(6)}
    assert rows["proj"].status == STATUS_SHORT
    assert rows["proj"].uncovered == pytest.approx(30)


def test_4_route_quantity_caps_the_take():
    line = _line("l", "SO2", 36, _d(20))
    rows = _by_key(_walk([_pool(36)], [line], [_route("l", 10)]))

    assert _taken(rows["l"]) == {POOL_KEY: pytest.approx(10)}
    assert rows["l"].uncovered == pytest.approx(26)
    assert rows["l"].status == STATUS_SHORT


def test_5_route_then_own_group_pile_covers_the_line():
    line = _line("l", "SO2", 36, _d(20))
    rows = _by_key(_walk([_pool(36), _ir_bin(26)], [line], [_route("l", 10)]))

    assert rows["l"].status == STATUS_COVERED
    assert rows["l"].uncovered == pytest.approx(0)
    assert _taken(rows["l"]) == {
        POOL_KEY: pytest.approx(10),
        IR_KEY: pytest.approx(26),
    }
    # Route first, then the pile: the route take is the first one booked.
    assert rows["l"].assigned[0].event.key == POOL_KEY
    assert rows["l"].assigned[0].pinned is False


def test_6_route_off_a_bin_outside_the_span_is_honoured_up_to_the_floor_for_route_lines_only():
    stand_in_key = "on_hand:brw-gone"
    line = _line("l", "SO2", 36, _d(20))
    other = _line("other", "SO3", 10, _d(5))  # undecided, same group, due earlier
    hold = _route("l", 36, key=stand_in_key, warehouse="BRW-IR")
    result = _walk(
        [], [line, other], [hold], stand_in_floors={stand_in_key: 20},
    )
    rows = _by_key(result)

    assert _taken(rows["l"]) == {stand_in_key: pytest.approx(20)}
    assert rows["l"].uncovered == pytest.approx(16)
    assert rows["l"].status == STATUS_SHORT
    assert rows["l"].assigned[0].pinned is False
    # The stand-in is nobody else's stock.
    assert rows["other"].assigned == ()
    assert rows["other"].status == STATUS_SHORT
    assert rows["other"].uncovered == pytest.approx(10)
    # And none of it is reported as free.
    assert result.free.get(stand_in_key, 0.0) <= EPSILON


def test_6b_the_unused_part_of_a_stand_in_is_not_free_stock_or_month_balance():
    stand_in_key = "on_hand:brw-gone"
    line = _line("l", "SO2", 12, _d(20))
    hold = _route("l", 12, key=stand_in_key, warehouse="BRW-IR")
    result = _walk([], [line], [hold], stand_in_floors={stand_in_key: 20})

    assert _taken(_by_key(result)["l"]) == {stand_in_key: pytest.approx(12)}
    assert result.free.get(stand_in_key, 0.0) <= EPSILON
    assert all(month.balance <= EPSILON for month in result.months)


def test_7_control_a_plain_pinned_hold_still_binds_first_at_any_date():
    early = _line("early", "SO1", 36, _d(10))
    late = _line("late", "SO2", 36, _d(60))
    rows = _by_key(_walk([_ir_bin(36)], [early, late], [_pin("late", 36)]))

    assert rows["late"].status == STATUS_PINNED
    assert rows["late"].assigned[0].pinned is True
    assert _taken(rows["late"]) == {IR_KEY: pytest.approx(36)}
    assert rows["early"].status == STATUS_SHORT
    assert rows["early"].uncovered == pytest.approx(36)


def test_8_a_route_lines_leftover_queues_as_a_shortfall_in_its_own_group():
    line = _line("l", "SO2", 36, _d(10))
    spo = SupplyEvent(
        key="spo:1", kind=KIND_SPO, warehouse="BRW-IR", at=_d(30), qty=26, ref="SPO 1"
    )
    row = _by_key(_walk([_pool(36), spo], [line], [_route("l", 10)]))["l"]

    assert row.status == STATUS_LATE
    assert row.uncovered == pytest.approx(0)
    assert row.short_at_date == pytest.approx(26)
    assert _taken(row) == {POOL_KEY: pytest.approx(10), "spo:1": pytest.approx(26)}


# --------------------------------------------------------------------------- review S7


def _line_at(key, so, qty, due, warehouse):
    return DemandLine(
        key=key, so_number=so, line_no=1, warehouse=warehouse, agent_code="LEENA",
        required_date=due, open_qty=qty,
    )


def _bin(qty, key, warehouse):
    return SupplyEvent(key=key, kind=KIND_ON_HAND, warehouse=warehouse, at=AS_OF, qty=qty)


def test_s7i_a_cross_group_route_on_an_in_span_bin_shares_it_by_date_and_stays_sealed():
    """An IB bin with 36. An IB line (+10) needs 30, no plan. A BB line (+20) is routed to
    the IB bin for 36. An undecided BB line (+5) needs 36. The IB line is covered 30, the
    routed BB line takes the 6 left and is short 30, and the undecided BB line cannot draw
    IB and stays short 36."""
    ib_key = "on_hand:brw-ib"
    ib = _line_at("ib", "SO-IB", 30, _d(10), "BRW-IB")
    routed = _line_at("routed", "SO-BB-ROUTED", 36, _d(20), "BRW-BB")
    undecided = _line_at("undecided", "SO-BB-OPEN", 36, _d(5), "BRW-BB")
    rows = _by_key(
        _walk(
            [_bin(36, ib_key, "BRW-IB")], [ib, routed, undecided],
            [_route("routed", 36, key=ib_key, warehouse="BRW-IB")],
        )
    )

    assert rows["ib"].status == STATUS_COVERED
    assert _taken(rows["ib"]) == {ib_key: pytest.approx(30)}
    assert _taken(rows["routed"]) == {ib_key: pytest.approx(6)}
    assert rows["routed"].status == STATUS_SHORT
    assert rows["routed"].uncovered == pytest.approx(30)
    assert rows["undecided"].assigned == ()
    assert rows["undecided"].status == STATUS_SHORT
    assert rows["undecided"].uncovered == pytest.approx(36)


def test_s7ii_a_route_take_leaves_a_lendable_claim_alone():
    """A 50 floor at the IR bin; a far IR line (+90) holds a LENDABLE claim of 36 on it; a
    nearer routed line (+10, group BB) is routed to the bin for 36. The route takes only the
    14 nobody claimed, is short 22, and the far line keeps its whole claim: it is charged no
    `Lent` by the route and reads pinned with its 36."""
    key = IR_KEY
    far = _line_at("far", "SO-FAR", 36, _d(90), "BRW-IR")
    near = _line_at("near", "SO-NEAR", 36, _d(10), "BRW-BB")
    claim = Hold(
        line_key="far", supply_key=key, qty=36, kind=KIND_ON_HAND, warehouse="BRW-IR",
        landed=True, lendable=True,
    )
    rows = _by_key(
        _walk(
            [_bin(50, key, "BRW-IR")], [far, near],
            [claim, _route("near", 36, key=key, warehouse="BRW-IR")],
        )
    )

    assert _taken(rows["near"]) == {key: pytest.approx(14)}
    assert rows["near"].uncovered == pytest.approx(22)
    assert rows["far"].lent == ()
    assert rows["far"].lent_qty == pytest.approx(0)
    assert _taken(rows["far"]) == {key: pytest.approx(36)}
    assert rows["far"].status == STATUS_PINNED
