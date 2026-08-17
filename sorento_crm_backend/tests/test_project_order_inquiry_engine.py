"""P10 netting and the verb rule: the pure engine behind AC-I2, AC-I3 and AC-I3a.

No database. The engine is handed demand rows and covering pools and returns the
instructions purchasing acts on. Everything it decides is arithmetic on quantities and
dates, so it is testable as a table, and the golden cases below are the shapes the
client's own order inquiry produces.

The one that matters is the PARTIAL SPLIT. A pool that covers the first two dates and
part of the third is where a netting rule either tells purchasing exactly which dates
still need buying, or quietly rounds and sends them to buy something already on the
water. The client's own file has an ORDER row for 600 CB6633 that a 5,950 pre-order
already covered; that row is the bug this engine exists to remove.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.project_so import (
    IV_ADVANCE,
    IV_ALREADY_INBOUND,
    IV_CANCEL_BALANCE,
    IV_CHANGE_SO,
    IV_DELAY,
    IV_ORDER,
    IV_PRE_ORDERED,
    IV_RESERVE_AND_ORDER,
)
from app.services.project_order_inquiry_engine import (
    CHANGE_DATE_EARLIER,
    CHANGE_DATE_LATER,
    CHANGE_NEW,
    CHANGE_QTY_DECREASE,
    CHANGE_QTY_INCREASE,
    CHANGE_REPOINT,
    COVERAGE_INBOUND,
    COVERAGE_NONE,
    COVERAGE_PRE_ORDER,
    POOL_INBOUND_SPO,
    POOL_PRE_ORDER,
    CoveringPool,
    DemandRow,
    net_demand,
    verb_for,
)

# Far enough out that nothing falls inside the reserve window unless a case says so.
TODAY = date(2026, 4, 2)
GRATING = "prod-cb6633"
WC = "prod-srtwc8613"


def _demand(
    qty: str,
    delivery_date: date | None,
    *,
    product_id: str = GRATING,
    item_code: str = "CB6633",
    line_id: str | None = None,
    change: str = CHANGE_NEW,
    stock_location: str | None = "BRW-BB",
    note: str | None = None,
) -> DemandRow:
    return DemandRow(
        line_id=line_id or f"line-{item_code}-{delivery_date}-{qty}",
        product_id=product_id,
        item_code=item_code,
        qty=Decimal(qty),
        delivery_date=delivery_date,
        stock_location=stock_location,
        change=change,
        note=note,
    )


def _pre_order(qty: str, reference: str = "SO383057", product_id: str = GRATING) -> CoveringPool:
    return CoveringPool(
        kind=POOL_PRE_ORDER, reference=reference, product_id=product_id, qty=Decimal(qty)
    )


def _inbound(
    qty: str,
    reference: str = "202511-S0022",
    product_id: str = GRATING,
    eta: date | None = None,
) -> CoveringPool:
    return CoveringPool(
        kind=POOL_INBOUND_SPO,
        reference=reference,
        product_id=product_id,
        qty=Decimal(qty),
        available_from=eta,
    )


def _verbs(rows) -> list[str]:
    return [row.verb for row in rows]


# --------------------------------------------------------------------- netting


def test_no_pool_at_all_orders_every_line():
    demand = [
        _demand("135", date(2026, 7, 1)),
        _demand("72", date(2026, 8, 3)),
    ]

    rows = net_demand(demand, [], today=TODAY)

    assert _verbs(rows) == [IV_ORDER, IV_ORDER]
    assert [row.qty for row in rows] == [Decimal("135"), Decimal("72")]
    assert all(row.covered_by is None for row in rows)
    assert all(row.spo_ref is None for row in rows)


def test_a_pool_larger_than_all_demand_orders_nothing():
    demand = [
        _demand("135", date(2026, 7, 1)),
        _demand("72", date(2026, 8, 3)),
    ]

    rows = net_demand(demand, [_pre_order("5950")], today=TODAY)

    assert _verbs(rows) == [IV_PRE_ORDERED, IV_PRE_ORDERED]
    assert IV_ORDER not in _verbs(rows)
    assert all(row.covered_by == "Pre-order SO383057" for row in rows)


def test_a_pool_exactly_equal_to_demand_leaves_no_balance_row():
    demand = [
        _demand("100", date(2026, 7, 1)),
        _demand("50", date(2026, 8, 3)),
    ]

    rows = net_demand(demand, [_pre_order("150")], today=TODAY)

    assert _verbs(rows) == [IV_PRE_ORDERED, IV_PRE_ORDERED]
    # A zero balance is not an instruction. Emitting one would put "ORDER 0" in front
    # of purchasing, which is worse than saying nothing.
    assert all(row.qty > 0 for row in rows)
    assert sum((row.qty for row in rows), Decimal("0")) == Decimal("150")


def test_the_5950_pre_ordered_gratings_cover_the_earliest_dates_first():
    """AC-I3a, in the client's own numbers.

    Four dated deliveries of CB6633 against the SO383057 pre-order. The first two
    dates and part of the third are covered; the balance of the third and the whole
    fourth still have to be bought, and each row says which it is.
    """
    demand = [
        _demand("2000", date(2026, 7, 1)),
        _demand("2000", date(2026, 8, 3)),
        _demand("2000", date(2026, 9, 1)),
        _demand("600", date(2026, 10, 1)),
    ]

    rows = net_demand(demand, [_pre_order("5950")], today=TODAY)

    assert [(row.delivery_date, row.verb, row.qty) for row in rows] == [
        (date(2026, 7, 1), IV_PRE_ORDERED, Decimal("2000")),
        (date(2026, 8, 3), IV_PRE_ORDERED, Decimal("2000")),
        (date(2026, 9, 1), IV_PRE_ORDERED, Decimal("1950")),
        (date(2026, 9, 1), IV_ORDER, Decimal("50")),
        (date(2026, 10, 1), IV_ORDER, Decimal("600")),
    ]
    covered = [row for row in rows if row.verb == IV_PRE_ORDERED]
    assert all(row.covered_by == "Pre-order SO383057" for row in covered)
    assert all(row.covered_by is None for row in rows if row.verb == IV_ORDER)


def test_the_pool_goes_to_the_earliest_date_regardless_of_input_order():
    """FIFO is by DELIVERY DATE, not by the order the lines happen to be numbered."""
    demand = [
        _demand("100", date(2026, 12, 1), line_id="late"),
        _demand("100", date(2026, 7, 1), line_id="early"),
    ]

    rows = net_demand(demand, [_pre_order("100")], today=TODAY)

    by_line = {row.line_id: row for row in rows}
    assert by_line["early"].verb == IV_PRE_ORDERED
    assert by_line["late"].verb == IV_ORDER
    # The instruction list still reads in the order the lines were given, so an SO's
    # rows print in line order even though the pool was allocated by date.
    assert [row.line_id for row in rows] == ["late", "early"]


def test_undated_demand_is_served_after_every_dated_one():
    demand = [
        _demand("100", None, line_id="undated"),
        _demand("100", date(2027, 6, 1), line_id="dated"),
    ]

    rows = net_demand(demand, [_pre_order("100")], today=TODAY)

    by_line = {row.line_id: row for row in rows}
    assert by_line["dated"].verb == IV_PRE_ORDERED
    assert by_line["undated"].verb == IV_ORDER


def test_two_products_never_bleed_into_each_others_pools():
    demand = [
        _demand("100", date(2026, 7, 1), product_id=GRATING, item_code="CB6633"),
        _demand("100", date(2026, 7, 1), product_id=WC, item_code="SRTWC8613-RL"),
    ]

    rows = net_demand(demand, [_pre_order("500", product_id=GRATING)], today=TODAY)

    by_code = {row.item_code: row for row in rows}
    assert by_code["CB6633"].verb == IV_PRE_ORDERED
    assert by_code["SRTWC8613-RL"].verb == IV_ORDER
    assert by_code["SRTWC8613-RL"].covered_by is None


def test_an_inbound_spo_carries_its_reference_onto_the_row():
    demand = [_demand("100", date(2026, 7, 1))]

    rows = net_demand(demand, [_inbound("100", "202511-S0022")], today=TODAY)

    assert len(rows) == 1
    assert rows[0].verb == IV_ALREADY_INBOUND
    assert rows[0].spo_ref == "202511-S0022"
    assert rows[0].covered_by == "Inbound SPO 202511-S0022"


def test_one_line_split_across_a_pre_order_an_inbound_and_the_balance():
    demand = [_demand("200", date(2026, 7, 1), line_id="split")]

    rows = net_demand(
        demand,
        [_pre_order("120"), _inbound("30", "202511-S0022")],
        today=TODAY,
    )

    assert [(row.verb, row.qty, row.spo_ref) for row in rows] == [
        (IV_PRE_ORDERED, Decimal("120"), None),
        (IV_ALREADY_INBOUND, Decimal("30"), "202511-S0022"),
        (IV_ORDER, Decimal("50"), None),
    ]
    assert all(row.line_id == "split" for row in rows)


def test_two_inbound_shipments_are_consumed_by_arrival_then_reference():
    demand = [_demand("150", date(2026, 7, 1))]

    rows = net_demand(
        demand,
        [
            _inbound("100", "202512-S0100", eta=date(2026, 6, 1)),
            _inbound("100", "202511-S0022", eta=date(2026, 5, 1)),
        ],
        today=TODAY,
    )

    assert [(row.qty, row.spo_ref) for row in rows] == [
        (Decimal("100"), "202511-S0022"),
        (Decimal("50"), "202512-S0100"),
    ]


def test_an_order_row_is_never_emitted_for_a_covered_quantity():
    """AC-I3, asserted directly across every mix of pools."""
    demand = [
        _demand("300", date(2026, 7, 1)),
        _demand("300", date(2026, 8, 3)),
    ]

    for pools in (
        [_pre_order("600")],
        [_inbound("600")],
        [_pre_order("300"), _inbound("300")],
    ):
        rows = net_demand(demand, pools, today=TODAY)
        assert IV_ORDER not in _verbs(rows)
        assert IV_RESERVE_AND_ORDER not in _verbs(rows)
        assert sum((row.qty for row in rows), Decimal("0")) == Decimal("600")


def test_every_covered_row_states_what_covered_it():
    demand = [_demand("100", date(2026, 7, 1)), _demand("100", date(2026, 8, 3))]

    rows = net_demand(demand, [_pre_order("100"), _inbound("100")], today=TODAY)

    for row in rows:
        assert row.covered_by, f"{row.verb} row carries no coverage note"


def test_the_netted_quantity_always_equals_the_demand():
    demand = [
        _demand("2000", date(2026, 7, 1)),
        _demand("2000", date(2026, 8, 3)),
        _demand("2000", date(2026, 9, 1)),
        _demand("600", date(2026, 10, 1)),
    ]

    rows = net_demand(demand, [_pre_order("5950")], today=TODAY)

    assert sum((row.qty for row in rows), Decimal("0")) == Decimal("6600")


def test_a_line_asking_for_nothing_produces_no_instruction():
    rows = net_demand([_demand("0", date(2026, 7, 1))], [_pre_order("500")], today=TODAY)

    assert rows == []


def test_stock_location_rides_through_untouched_including_when_it_is_unknown():
    demand = [
        _demand("100", date(2026, 7, 1), stock_location="BRW-BB", line_id="confirmed"),
        _demand("100", date(2026, 7, 1), stock_location=None, line_id="unallocated"),
    ]

    rows = net_demand(demand, [], today=TODAY)

    by_line = {row.line_id: row for row in rows}
    assert by_line["confirmed"].stock_location == "BRW-BB"
    # Never invented: no confirmed allocation means the column is empty and says so.
    assert by_line["unallocated"].stock_location is None


# ------------------------------------------------------- amendment instructions


def test_a_delay_passes_through_and_never_touches_the_pool():
    demand = [
        _demand(
            "600",
            date(2027, 1, 7),
            change=CHANGE_DATE_LATER,
            note="was 01/07/2026",
            line_id="delayed",
        ),
        _demand("100", date(2026, 7, 1), line_id="fresh"),
    ]

    rows = net_demand(demand, [_pre_order("100")], today=TODAY)

    by_line = {row.line_id: row for row in rows}
    assert by_line["delayed"].verb == IV_DELAY
    assert by_line["delayed"].qty == Decimal("600")
    assert by_line["delayed"].note == "was 01/07/2026"
    assert by_line["delayed"].covered_by is None
    # The pool was still whole when the new line asked for it.
    assert by_line["fresh"].verb == IV_PRE_ORDERED


def test_each_amendment_change_maps_to_its_own_verb():
    changes = {
        CHANGE_DATE_LATER: IV_DELAY,
        CHANGE_DATE_EARLIER: IV_ADVANCE,
        CHANGE_QTY_DECREASE: IV_CANCEL_BALANCE,
        CHANGE_REPOINT: IV_CHANGE_SO,
    }
    for change, expected in changes.items():
        rows = net_demand(
            [_demand("10", date(2026, 7, 1), change=change)], [_pre_order("500")], today=TODAY
        )
        assert _verbs(rows) == [expected]


def test_an_increase_is_new_demand_and_does_consume_the_pool():
    rows = net_demand(
        [_demand("40", date(2026, 7, 1), change=CHANGE_QTY_INCREASE)],
        [_pre_order("40")],
        today=TODAY,
    )

    assert _verbs(rows) == [IV_PRE_ORDERED]


# ------------------------------------------------------------------ verb table


def test_the_verb_table_is_exactly_what_ac_i2_names():
    far = date(2027, 1, 7)
    near = date(2026, 5, 1)  # inside the 60 day reserve window from TODAY

    table = [
        ((CHANGE_NEW, COVERAGE_PRE_ORDER, far), IV_PRE_ORDERED),
        ((CHANGE_NEW, COVERAGE_INBOUND, far), IV_ALREADY_INBOUND),
        ((CHANGE_NEW, COVERAGE_NONE, far), IV_ORDER),
        ((CHANGE_NEW, COVERAGE_NONE, near), IV_RESERVE_AND_ORDER),
        ((CHANGE_QTY_INCREASE, COVERAGE_PRE_ORDER, far), IV_PRE_ORDERED),
        ((CHANGE_QTY_INCREASE, COVERAGE_INBOUND, far), IV_ALREADY_INBOUND),
        ((CHANGE_QTY_INCREASE, COVERAGE_NONE, far), IV_ORDER),
        ((CHANGE_QTY_INCREASE, COVERAGE_NONE, near), IV_RESERVE_AND_ORDER),
        ((CHANGE_DATE_LATER, COVERAGE_NONE, far), IV_DELAY),
        ((CHANGE_DATE_LATER, COVERAGE_PRE_ORDER, near), IV_DELAY),
        ((CHANGE_DATE_EARLIER, COVERAGE_NONE, far), IV_ADVANCE),
        ((CHANGE_DATE_EARLIER, COVERAGE_INBOUND, near), IV_ADVANCE),
        ((CHANGE_QTY_DECREASE, COVERAGE_NONE, far), IV_CANCEL_BALANCE),
        ((CHANGE_QTY_DECREASE, COVERAGE_PRE_ORDER, near), IV_CANCEL_BALANCE),
        ((CHANGE_REPOINT, COVERAGE_NONE, far), IV_CHANGE_SO),
        ((CHANGE_REPOINT, COVERAGE_INBOUND, near), IV_CHANGE_SO),
    ]
    for (change, coverage, delivery_date), expected in table:
        assert (
            verb_for(change, coverage, delivery_date=delivery_date, today=TODAY) == expected
        ), f"{change} + {coverage} on {delivery_date}"


def test_demand_with_no_date_at_all_is_ordered_not_reserved():
    """A reserve is a promise about a date. With no date there is nothing to reserve for."""
    assert (
        verb_for(CHANGE_NEW, COVERAGE_NONE, delivery_date=None, today=TODAY) == IV_ORDER
    )


def test_demand_already_past_its_date_is_reserved_as_well_as_ordered():
    assert (
        verb_for(CHANGE_NEW, COVERAGE_NONE, delivery_date=date(2026, 3, 1), today=TODAY)
        == IV_RESERVE_AND_ORDER
    )
