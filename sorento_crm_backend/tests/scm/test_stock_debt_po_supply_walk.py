"""R42 (owner, 28 Sep 2026, #1331): purchase orders as Stock Debt supply, the pure half.

No database. `book_so_pins` (the S/O pin arithmetic) and `supply_assignment.assign` (the
walk) are both pure, so the owner's two screenshots are fixtures here, walked on the day
the ruling was made (`AS_OF`, 28 Sep 2026) so the overdue arithmetic is fixed:

* ACC6001: SO395635 (LEENA, BRW-BB, 108 due 16/12/2026) and SO398322 (48 due 21/12/2026),
  no purchase order. Dec 2026 reads -156 and both lines are short.
* CSK14A-NL, PO 202609-S0029: 41 to BRW (a site pool) with no S/O, delivery 10/09/2026;
  1,305 to BRW-BB naming SO419208, delivery 14/09/2026; 4 to BRW-BB naming SO419208 and
  already Placed 4, delivery 14/09/2026.

The route half (the reads, the wire, the parity with the board) is
`test_stock_debt_po_supply_routes.py`.
"""
from __future__ import annotations

from datetime import date

from app.services.scm.stock_debt_service import book_so_pins
from app.services.scm.supply_assignment import (
    KIND_PO,
    POOL_GROUP,
    STATUS_PINNED,
    STATUS_SHORT,
    DemandLine,
    Hold,
    SupplyEvent,
    assign,
    free_piles_at,
)

AS_OF = date(2026, 9, 28)
TBA_FROM = date(2029, 1, 1)
LEAD = 90


def _po(key, qty, at, warehouse, *, is_pool=False, line_no=1):
    return SupplyEvent(
        key=f"po:{key}",
        kind=KIND_PO,
        warehouse=warehouse,
        at=at,
        qty=qty,
        ref=f"PO 202609-S0029 line {line_no}",
        is_pool=is_pool,
        po_number="202609-S0029",
        po_line_number=line_no,
        purchase_order_id="po-202609-S0029",
    )


def _line(key, so, qty, due, warehouse="BRW-BB", *, sales_order_id=None):
    return DemandLine(
        key=key,
        so_number=so,
        line_no=1,
        warehouse=warehouse,
        agent_code="LEENA",
        required_date=due,
        open_qty=qty,
        sales_order_id=sales_order_id or f"id-{so}",
    )


def _walk(supply, demand, pinned, *, grace=0, dead=0):
    return assign(
        "P",
        as_of=AS_OF,
        tba_from=TBA_FROM,
        lead_days=LEAD,
        supply=supply,
        demand=demand,
        pinned=pinned,
        overdue_grace_days=grace,
        overdue_dead_days=dead,
    )


def _months(result):
    return {month.key: month.balance for month in result.months}


# ---------------------------------------------------------------- the owner's screenshots


def test_acc6001_with_no_purchase_order_reads_minus_156_in_december():
    """AC-PO-7: nothing to cover either line, so both are short and December books both.
    A month states its own month (R37): no earlier column carries any of it."""
    demand = [
        _line("l1", "SO395635", 108, date(2026, 12, 16)),
        _line("l2", "SO398322", 48, date(2026, 12, 21)),
    ]
    result = _walk([], demand, [])

    assert [line.status for line in result.lines] == [STATUS_SHORT, STATUS_SHORT]
    assert [line.short_at_date for line in result.lines] == [108, 48]
    months = _months(result)
    assert months["2026-12"] == -156
    assert all(balance == 0 for key, balance in months.items() if key != "2026-12")


def _csk14a(grace=14, dead=90):
    """PO 202609-S0029 for CSK14A-NL, and SO419208's open line for it at BRW-BB."""
    free_41 = _po("l41", 41, date(2026, 9, 10), "BRW", is_pool=True, line_no=1)
    named_1305 = _po("l1305", 1305, date(2026, 9, 14), "BRW-BB", line_no=2)
    placed_4 = _po("l4", 4, date(2026, 9, 14), "BRW-BB", line_no=3)
    so_line = _line(
        "so419208", "SO419208", 1309, date(2026, 10, 20), sales_order_id="id-SO419208"
    )
    placement = Hold(
        line_key="so419208",
        supply_key=placed_4.key,
        qty=4,
        kind=KIND_PO,
        oi_number="OI-1",
        oi_id="oi-1",
        # R43: the view marks every hold on a PO line `fulfils` (`_assignments`).
        fulfils=True,
    )
    placed_by_key = {named_1305.key: 0.0, placed_4.key: 4.0}
    # R43 (#1346): every PO line naming the order is asked, whatever the overdue rule says
    # of its date. `grace`/`dead` are the walk's, below.
    pins = book_so_pins(
        [
            ("P", event, "id-SO419208", placed_by_key[event.key])
            for event in (named_1305, placed_4)
        ],
        {"P": [so_line]},
        [placement],
        tba_from=TBA_FROM,
    )
    return [free_41, named_1305, placed_4], so_line, placement, pins


def test_the_s_o_pins_1305_and_the_placement_4_never_1309_twice():
    """AC-PO-3: the placement binds its 4 first; the book S/O pins what is left of each PO
    line - 1,305 on the unplaced line and 0 on the placed one - so SO419208 is held 1,309
    in all, never 1,309 from the book plus 4 from the placement."""
    _supply, _line_, _placement, pins = _csk14a()

    assert [(pin.line_key, pin.supply_key, pin.qty) for pin in pins] == [
        ("so419208", "po:l1305", 1305),
    ]
    assert pins[0].kind == KIND_PO
    assert pins[0].po_number == "202609-S0029"


def test_csk14a_at_14_90_is_pinned_and_the_41_is_free_in_the_pool():
    """AC-PO-6 (recommended policy): 18 and 14 days late, inside 90, so all three count on
    `as_of + 14` (12 Oct). SO419208 reads pinned for 1,309 with no shortfall; the 41 at
    BRW is free in the POOL group (it cannot cover a BB line, R40), credited to October."""
    supply, so_line, placement, pins = _csk14a()
    result = _walk(supply, [so_line], [placement, *pins], grace=14, dead=90)

    [line] = result.lines
    assert line.status == STATUS_PINNED
    assert line.short_at_date == 0
    assert sorted((item.event.key, item.qty) for item in line.assigned) == [
        ("po:l1305", 1305),
        ("po:l4", 4),
    ]
    assert result.free["po:l41"] == 41
    assert result.free["po:l1305"] == 0
    assert all(event.at == date(2026, 10, 12) for event in result.supply)
    assert _months(result)["2026-10"] == 41
    assert result.uncounted == ()
    assert [event.key for event, _qty in free_piles_at(
        result, at=date(2026, 10, 31), as_of=AS_OF
    )[POOL_GROUP]] == ["po:l41"]


def test_csk14a_at_0_0_the_s_o_still_fulfils_1309():
    """AC-PO-6 as R43 (#1346) amends it: at the SHIPPED 0 / 0 every PO line is past the rule
    and counts as nothing as SUPPLY, but the S/O pin no longer depends on the rule ("i
    prefer it to be 0 days set, and when it is assigned, then it will fulfil the demand
    ady"). The book pins 1,305, the placement 4, and SO419208 reads pinned with nothing
    short; the 41 with no S/O stays uncounted."""
    supply, so_line, placement, pins = _csk14a(grace=0, dead=0)
    assert [(pin.supply_key, pin.qty) for pin in pins] == [("po:l1305", 1305)]
    result = _walk(supply, [so_line], [placement, *pins])

    [line] = result.lines
    assert line.status == STATUS_PINNED
    assert line.short_at_date == 0
    assert sorted((item.event.key, item.qty) for item in line.assigned) == [
        ("po:l1305", 1305),
        ("po:l4", 4),
    ]
    assert {event.key for event in result.uncounted} == {"po:l41", "po:l1305", "po:l4"}
    assert result.free == {}
    assert all(month.balance == 0 for month in result.months)


def test_a_past_due_po_naming_an_order_fulfils_it_and_the_stock_stays_free():
    """R43 (#1346) replaces this lane's first review ruling (a dead PO pinned nothing). A PO
    one day late at 0 / 0 names SO X, and 100 sits on hand at the same bin. The pin
    fulfils the line, so it reads pinned with nothing short and the on hand stays free."""
    on_hand = SupplyEvent(key="on_hand:bb", kind="on_hand", warehouse="BRW-BB",
                          at=AS_OF, qty=100)
    po = _po("x", 100, date(2026, 9, 27), "BRW-BB")
    line = _line("x", "SOX", 100, date(2026, 10, 20), sales_order_id="id-SOX")
    pins = book_so_pins(
        [("P", po, "id-SOX", 0.0)], {"P": [line]}, [], tba_from=TBA_FROM,
    )
    result = _walk([on_hand, po], [line], pins)

    assert [(pin.supply_key, pin.qty) for pin in pins] == [("po:x", 100)]
    assert result.lines[0].status == STATUS_PINNED
    assert result.lines[0].short_at_date == 0
    assert result.free["on_hand:bb"] == 100


# ---------------------------------------------------------------- the pin rule


def test_the_pin_stops_at_what_the_order_needs_and_the_rest_is_free():
    """AC-PO-4: a PO line of 100 naming an order whose line needs 30 pins 30; the other 70
    is free on the delivery date and the walk gives it first-come to a later line."""
    po = _po("a", 100, date(2026, 10, 5), "BRW-BB")
    named = _line("n", "SO1", 30, date(2026, 11, 1), sales_order_id="id-SO1")
    other = _line("o", "SO2", 90, date(2026, 11, 10), sales_order_id="id-SO2")
    pins = book_so_pins([("P", po, "id-SO1", 0.0)], {"P": [named, other]}, [],
                        tba_from=TBA_FROM)
    assert [(pin.line_key, pin.qty) for pin in pins] == [("n", 30)]

    result = _walk([po], [named, other], pins)
    by_key = {line.line.key: line for line in result.lines}
    assert by_key["n"].status == STATUS_PINNED
    assert sum(item.qty for item in by_key["o"].assigned) == 70
    assert by_key["o"].short_at_date == 20


def test_the_named_order_is_covered_before_an_earlier_unnamed_one():
    """R42 point 3: the S/O covers THAT order first, even when another line of the group is
    due earlier and would otherwise take the PO first-come by required date."""
    po = _po("a", 50, date(2026, 10, 5), "BRW-BB")
    early = _line("e", "SO-EARLY", 50, date(2026, 10, 10), sales_order_id="id-early")
    named = _line("n", "SO-NAMED", 50, date(2026, 11, 20), sales_order_id="id-named")
    pins = book_so_pins([("P", po, "id-named", 0.0)], {"P": [early, named]}, [],
                        tba_from=TBA_FROM)
    result = _walk([po], [early, named], pins)

    by_key = {line.line.key: line for line in result.lines}
    assert by_key["n"].status == STATUS_PINNED
    assert by_key["e"].status == STATUS_SHORT
    assert by_key["e"].short_at_date == 50


def test_an_order_with_two_lines_fills_the_earlier_first_net_of_its_holds():
    """Two open lines of the named order: the earlier-dated line first, each only up to
    what its confirmed holds leave it needing."""
    po = _po("a", 60, date(2026, 10, 5), "BRW-BB")
    first = _line("f", "SO1", 40, date(2026, 10, 20), sales_order_id="id-SO1")
    second = _line("s", "SO1", 40, date(2026, 11, 20), sales_order_id="id-SO1")
    held = Hold(line_key="f", supply_key="on_hand:x", qty=25)
    pins = book_so_pins([("P", po, "id-SO1", 0.0)], {"P": [second, first]}, [held],
                        tba_from=TBA_FROM)

    assert [(pin.line_key, pin.qty) for pin in pins] == [("f", 15), ("s", 40)]


def test_tba_undated_and_unlocated_lines_are_never_pinned():
    """R14: those lines draw nothing, so pinning to them would lose the quantity; it stays
    free instead."""
    po = _po("a", 60, date(2026, 10, 5), "BRW-BB")
    lines = [
        _line("t", "SO1", 10, date(2030, 1, 1), sales_order_id="id-SO1"),
        _line("u", "SO1", 10, None, sales_order_id="id-SO1"),
        _line("x", "SO1", 10, date(2026, 11, 1), warehouse=None, sales_order_id="id-SO1"),
    ]
    assert book_so_pins([("P", po, "id-SO1", 0.0)], {"P": lines}, [],
                        tba_from=TBA_FROM) == []


def test_a_po_landing_after_the_line_fulfils_it_all_the_same():
    """R43 (#1346) withdraws this lane's review ruling that a book pin landing after the
    line's date still booked the line short (R37). Assigned means fulfilled: a line of 100
    due 20 Oct named by a PO delivering 15 Dec is pinned to it and short nothing, and the
    PO is spent, free in no month."""
    po = _po("a", 100, date(2026, 12, 15), "BRW-BB")
    line = _line("n", "SO1", 100, date(2026, 10, 20), sales_order_id="id-SO1")
    pins = book_so_pins([("P", po, "id-SO1", 0.0)], {"P": [line]}, [], tba_from=TBA_FROM)
    result = _walk([po], [line], pins)

    [row] = result.lines
    assert row.status == STATUS_PINNED
    assert row.short_at_date == 0
    months = _months(result)
    assert months["2026-10"] == 0
    assert months["2026-12"] == 0


def test_an_s_o_never_pins_across_an_ownership_group():
    """R40: only a Confirm moves supply across a group. A PO to BRW (a site pool) or to
    MWH-IB naming an order booked at BRW-BB pins nothing; its quantity stays in its own
    group's pile."""
    pool_po = _po("p", 41, date(2026, 10, 5), "BRW", is_pool=True)
    ib_po = _po("i", 20, date(2026, 10, 5), "MWH-IB")
    line = _line("n", "SO1", 50, date(2026, 11, 1), sales_order_id="id-SO1")
    assert book_so_pins(
        [("P", pool_po, "id-SO1", 0.0), ("P", ib_po, "id-SO1", 0.0)],
        {"P": [line]}, [], tba_from=TBA_FROM,
    ) == []


def test_a_po_line_wholly_placed_pins_nothing_more():
    po = _po("a", 10, date(2026, 10, 5), "BRW-BB")
    line = _line("n", "SO1", 50, date(2026, 11, 1), sales_order_id="id-SO1")
    assert book_so_pins([("P", po, "id-SO1", 10.0)], {"P": [line]}, [],
                        tba_from=TBA_FROM) == []


def test_a_free_po_is_credited_to_its_own_delivery_month():
    """Month bucketing unchanged (R37): a free PO's quantity is spare in the month it is
    parked in, and a line due before it books its shortfall in its own month and is then
    `late` - the PO is spent, so it is free in no month."""
    po = _po("a", 50, date(2026, 11, 5), "BRW-BB")
    early = _line("e", "SO1", 30, date(2026, 10, 20))
    result = _walk([po], [early], [])

    [line] = result.lines
    assert line.status == "late"
    assert line.short_at_date == 30
    months = _months(result)
    assert months["2026-10"] == -30
    assert months["2026-11"] == 20
