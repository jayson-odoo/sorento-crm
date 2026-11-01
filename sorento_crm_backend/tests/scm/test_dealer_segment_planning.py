"""DEALER-PLANNING PR 1: a line at a dealer-segment bin can be planned (UAC AC-1 to AC-6).

Dealer sales orders sit at a site pool such as BRW: segment dealer, `fulfilment_planning` off.
The flag verdict refused every one of them, and ticking the flag is not the way out, because it
would add the pool to the planning, netting and Stock Debt reads of every project line. So the
VERDICT moves and the flag does not. These tests hold both halves.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.inventory import Warehouse
from app.models.project_so import OrderInquiryRow
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_fulfilment_board_service import FulfilmentBoardService
from app.services.project_supply_service import ProjectSupplyService, SupplyLinesRefused
from app.services.scm.planning_predicate import (
    OUTSIDE_FULFILMENT_PLANNING,
    outside_fulfilment_planning,
)

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import _core_line, _stock, _uid, _warehouse
from .test_consign_plan import _board_world, _build, _consign_world, _contributions
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _components,
    _project_line,
    _seed_line,
    _world,
)


def _bin(*, segment, active=True, flag=False):
    return SimpleNamespace(is_active=active, fulfilment_planning=flag, segment=segment)


# --------------------------------------------------------------------------- the predicate


@pytest.mark.parametrize("segment", ["dealer", None])
def test_a_flagged_off_dealer_bin_does_not_earn_the_verdict(segment):
    """AC-1, AC-2: unset reads as dealer, the same way `pool_predicate.is_site_pool` reads it."""
    assert outside_fulfilment_planning(_bin(segment=segment)) is False


def test_a_flagged_off_project_bin_still_earns_the_verdict():
    """AC-3: the exemption is the dealer segment, not every flagged-off bin."""
    assert outside_fulfilment_planning(_bin(segment="project")) is True


@pytest.mark.parametrize("segment", ["dealer", "project", None])
def test_an_inactive_bin_keeps_the_verdict_it_had(segment):
    """AC-4."""
    assert outside_fulfilment_planning(_bin(segment=segment, active=False)) is False


def test_the_consignment_exemption_still_answers_first():
    """AC-5: a consignment at a flagged-off project bin was exempt before, and still is."""
    assert outside_fulfilment_planning(_bin(segment="project"), "consignment") is False


# --------------------------------------------------------------------------- the engine


def _dealer_pool(db, on_hand=100, product=None):
    pool = _warehouse(
        db, f"ZZD{_uid()[:6]}", segment="dealer", fulfilment_planning=False,
    )
    db.flush()
    pool.pool_warehouse_id = pool.id
    if product is not None and on_hand:
        _stock(db, product, pool, on_hand=on_hand)
    db.commit()
    return pool


def test_a_line_at_a_dealer_pool_is_plannable_and_gets_a_proposal():
    """AC-1: no verdict, and the ladder is walked rather than skipped."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        fact = next(iter(service._facts_for(order, service.lines_of(str(order.id))).values()))
        components = _components(service.proposal_for(order))

    assert fact.unplannable_reason is None
    assert [(c["kind"], Decimal(str(c["qty"]))) for c in components] == [("reserve", Decimal("40"))]


def test_a_line_at_a_dealer_pool_draws_on_that_pool_before_buying():
    """AC-7: 100 on hand at the line's own pool, 40 wanted. Nothing needs to be bought."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert sum(Decimal(str(c["qty"])) for c in components if c["kind"] == "buy") == 0, components
    assert sum(Decimal(str(c["qty"])) for c in components) == Decimal("40"), components


def test_confirming_a_line_at_a_dealer_pool_is_accepted():
    """AC-7: the refusal `test_confirming_a_line_at_a_flagged_off_bin_is_refused` holds for a
    project bin does not reach a dealer one."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0)
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=str(line.id), buy_qty=Decimal("40"))]
            ),
            actor_user_id=actor,
        )


def test_confirming_a_line_at_a_flagged_off_project_bin_is_still_refused():
    """AC-3."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        off = _warehouse(db, f"ZZP{_uid()[:6]}-BB", segment="project", fulfilment_planning=False)
        db.commit()
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, off, qty_ordered="40",
        )
        with pytest.raises(SupplyLinesRefused) as excinfo:
            ProjectSupplyService(db).confirm(
                order,
                ConfirmSupplyBody(
                    lines=[ConfirmLine(project_line_id=str(line.id), buy_qty=Decimal("40"))]
                ),
                actor_user_id=actor,
            )
        reasons = [row["reason"] for row in excinfo.value.detail["failing_lines"]]

    assert OUTSIDE_FULFILMENT_PLANNING in reasons


def test_the_dealer_pool_stays_out_of_the_planning_reads():
    """AC-6: a project line's netting and proposal do not start reading the pool."""
    with blank_session() as db:
        _company_id, _actor, _project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        planning = ProjectSupplyService(db)._planning_warehouses()
        pool_id = str(pool.id)

    assert pool_id not in planning


def test_a_consignment_at_a_flagged_off_dealer_bin_still_borrows_at_its_own_bin():
    """AC-5: `planned_at_own_bin` answers before the ladder, whatever the bin's segment."""
    with blank_session() as db:
        world = _consign_world(db)
        world["own"].segment = "dealer"
        db.commit()
        components = _components(ProjectSupplyService(db).proposal_for(world["order"]))
        own_code = world["own"].warehouse_code

    assert [c["kind"] for c in components] == ["borrow"], components
    assert components[0]["source_location"] == own_code
    assert Decimal(str(components[0]["qty"])) == Decimal("10")


# --------------------------------------------------------------------------- its own demand
#
# A line at a pool is inside that pool's book, so its own demand is netted against the very
# stock it stands on: 10 on hand and 10 ordered read a net of zero and proposed Buy 10. Every
# case below is the 50% default share (`available_for_project`).


def _totals(components):
    return {
        kind: sum(Decimal(str(c["qty"])) for c in components if c["kind"] == kind)
        for kind in {c["kind"] for c in components}
    }


def _proposal_at_own_pool(*, qty, on_hand, other=0):
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=on_hand, product=product)
        if other:
            _seed_line(
                db, company_id, project, product, pool, qty_ordered=str(other), line_no=20,
            )
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered=str(qty),
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))
    return _totals(components)


def test_its_own_demand_is_not_netted_against_its_own_pool():
    """20 on hand, 10 ordered, nobody else. The share of 20 is 10, so nothing is bought."""
    assert _proposal_at_own_pool(qty=10, on_hand=20) == {"reserve": Decimal("10")}


def test_stock_for_exactly_its_own_quantity_is_not_all_bought():
    """10 on hand, 10 ordered. The dealers' half stays back, and the other half is taken."""
    assert _proposal_at_own_pool(qty=10, on_hand=10) == {
        "reserve": Decimal("5"),
        "buy": Decimal("5"),
    }


def test_every_other_lines_demand_at_the_pool_stays_netted():
    """15 on hand, 10 ordered here and 10 by another order. Available is 15 - 10 = 5, share 2."""
    assert _proposal_at_own_pool(qty=10, on_hand=15, other=10) == {
        "reserve": Decimal("2"),
        "buy": Decimal("8"),
    }


def _one_unit_of_two(*, on_hand):
    """One order, one product, one date, so the walk reads the two lines as one unit."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=on_hand, product=product)
        order, _line, core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        second = _core_line(
            db, core_so, product, pool, qty_ordered="10", required_date=REQUIRED_DATE,
        )
        _project_line(db, order, line_no=20, product=product, core_line=second)
        db.commit()
        proposal = ProjectSupplyService(db).proposal_for(order)
    return _totals([c for line in proposal["lines"] for c in line["components"]])


def test_two_lines_of_one_unit_both_get_their_own_demand_back():
    """40 on hand, 10 and 10 ordered, nobody else: Available is 40, share 20."""
    assert _one_unit_of_two(on_hand=40) == {"reserve": Decimal("20")}


def test_two_lines_of_one_unit_share_what_they_stand_on():
    """20 on hand, all owed to these two: each gets half of its own, and half stays back."""
    assert _one_unit_of_two(on_hand=20) == {"reserve": Decimal("10"), "buy": Decimal("10")}


def test_a_line_at_a_project_bin_drawing_the_pool_gets_nothing_added_back():
    """AC-6. Its demand is booked at its own bin, not the pool's, so there is nothing to
    un-net: 10 at the pool still lends 5, as it does today."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        own = _warehouse(
            db, f"ZZP{_uid()[:6]}-BB", segment="project", pool_warehouse_id=pool.id,
            fulfilment_planning=True,
        )
        db.commit()
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    taken = sum(Decimal(str(c["qty"])) for c in components if c["kind"] == "reserve")
    assert taken == Decimal("5"), components


def test_confirming_the_engines_own_proposal_at_the_pool_raises_the_order_row():
    """AC-7: Reserve at the pool, Buy for the rest, and the Buy reaches purchasing."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=str(line.id),
                        reserve=[{"warehouse_id": str(pool.id), "qty": Decimal("5")}],
                        buy_qty=Decimal("5"),
                    )
                ]
            ),
            actor_user_id=actor,
        )
        db.commit()
        rows = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).all()
        got = [(row.verb, Decimal(str(row.qty)), row.stock_location) for row in rows]
        code = pool.warehouse_code

    assert got == [("ORDER", Decimal("5"), code)]


def test_the_board_plans_a_line_at_a_dealer_pool_with_the_same_answer():
    """AC-1 and AC-7 on the screen's own read: no verdict, and the walk's Reserve and Buy."""
    with blank_session() as db:
        world = _board_world(
            db, doc_type="sales_order", status="open", qty="10", delivered="0", con_stock=10,
            planned_stock=0,
        )
        pool = world["con"]
        pool.segment = "dealer"
        pool.pool_warehouse_id = pool.id
        db.commit()
        board = _build(db, world)
        row = _contributions(board, world["order"].so_number)[0]
        code = pool.warehouse_code

    assert row["unplannable"] is False
    assert [
        (s["kind"], Decimal(s["qty"]), s.get("location")) for s in row["sources"]
    ] == [("reserve", Decimal("5"), code), ("buy", Decimal("5"), None)]


# --------------------------------------------------------------------------- one walk, many lines
#
# The board walks every selected line against ledgers that outlive each line, so a line's own
# demand may be added back for THAT line only. A ledger holding one line's add-back promises
# stock to the next line, and a ledger seeded without it refuses the line that earned it.


def _board_row(board, core):
    return next(
        row
        for cell in board["cells"]
        for row in cell["contributions"]
        if row["so_number"] == core.so_number
    )


def _board(db, *cores):
    return FulfilmentBoardService(db).build(
        [core.so_number for core in cores], granularity="week", as_of=date.today(),
    )


def _project_bin(db, pool):
    own = _warehouse(
        db, f"ZZP{_uid()[:6]}-BB", segment="project", pool_warehouse_id=pool.id,
        fulfilment_planning=True,
    )
    db.commit()
    return own


def _sources(row):
    return _totals(row["sources"])


def test_a_line_at_the_pool_keeps_its_answer_when_a_project_line_walks_first():
    """AC-7a. The project line's earlier date seeds the ledgers, and must not cost the line at
    the pool the demand it stands on."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        own = _project_bin(db, pool)
        _order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5",
            required_date=REQUIRED_DATE - timedelta(days=14),
        )
        board = _board(db, at_pool, at_bin)
        at_pool_row, at_bin_row = _board_row(board, at_pool), _board_row(board, at_bin)

    assert _sources(at_pool_row) == {"reserve": Decimal("5"), "buy": Decimal("5")}
    assert _sources(at_bin_row) == {"buy": Decimal("5")}


def test_a_project_line_is_not_promised_a_line_at_the_pools_add_back():
    """AC-6. 30 at another pool against 100 owed at this one is a net of -70. The line at the
    pool walks first and buys whole, and the project line behind it must still read -70: it
    was offered Reserve 5, and confirming that wrote a decision 5 short with no inquiry row."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0, product=product)
        _dealer_pool(db, on_hand=30, product=product)
        own = _project_bin(db, pool)
        today = date.today()
        _order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="100",
            required_date=today + timedelta(days=40),
        )
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5",
            required_date=today + timedelta(days=47),
        )
        at_bin_row = _board_row(_board(db, at_pool, at_bin), at_bin)

    assert _sources(at_bin_row) == {"buy": Decimal("5")}


def test_two_orders_at_the_pool_read_the_same_on_the_board_as_on_their_sheets():
    """20 on hand, 10 and 10 owed by two orders. Each gets half of its own, on every read."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=20, product=product)
        order_x, _line, core_x, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        _order, _line, core_y, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10", line_no=20,
        )
        sheet = _totals(_components(ProjectSupplyService(db).proposal_for(order_x)))
        board = _board(db, core_x, core_y)
        row_x, row_y = _board_row(board, core_x), _board_row(board, core_y)

    half = {"reserve": Decimal("5"), "buy": Decimal("5")}
    assert (sheet, _sources(row_x), _sources(row_y)) == (half, half, half)


def _far(days):
    return date.today() + timedelta(days=days)


def test_a_project_line_behind_a_line_at_the_pool_reads_the_true_net_across_two_pools():
    """Two other pools hold 25 each, 30 is owed at this one: a true net of 20. Its line can't be
    covered whole and buys. Beyond the window a line takes all or nothing, so 22 must buy too."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0, product=product)
        _dealer_pool(db, on_hand=25, product=product)
        _dealer_pool(db, on_hand=25, product=product)
        own = _project_bin(db, pool)
        _order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="30", required_date=_far(40),
        )
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="22", required_date=_far(47),
        )
        row = _board_row(_board(db, at_pool, at_bin), at_bin)

    assert _sources(row) == {"buy": Decimal("22")}


def test_a_project_line_behind_a_unit_at_the_pool_reads_the_true_net():
    """One order's two lines at the pool, 30 and 30, buy whole. 50 at another pool against 60
    owed is a net of -10, so the project line behind them buys as well."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0, product=product)
        _dealer_pool(db, on_hand=50, product=product)
        own = _project_bin(db, pool)
        order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="30", required_date=_far(40),
        )
        second = _core_line(
            db, at_pool, product, pool, qty_ordered="30", required_date=_far(40),
        )
        _project_line(db, order, line_no=20, product=product, core_line=second)
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5", required_date=_far(47),
        )
        db.commit()
        row = _board_row(_board(db, at_pool, at_bin), at_bin)

    assert _sources(row) == {"buy": Decimal("5")}


def test_what_a_line_takes_beyond_its_own_half_comes_off_the_pools_share():
    """20 on hand, 10 owed here: the pile's project share is 5. The line takes 10, half of what
    it stands on, which spends that share, so the project line behind it buys."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=20, product=product)
        own = _project_bin(db, pool)
        _order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5",
            required_date=REQUIRED_DATE + timedelta(days=1),
        )
        board = _board(db, at_pool, at_bin)
        at_pool_row, at_bin_row = _board_row(board, at_pool), _board_row(board, at_bin)

    assert _sources(at_pool_row) == {"reserve": Decimal("10")}
    assert _sources(at_bin_row) == {"buy": Decimal("5")}


def test_the_pools_share_is_seeded_from_the_true_net():
    """As above, with 8 owed at another pool that holds nothing: a true net of 2, so the share
    is 2 and the line at the pool spends it."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=20, product=product)
        short = _dealer_pool(db, on_hand=0, product=product)
        own = _project_bin(db, pool)
        _seed_line(db, company_id, project, product, short, qty_ordered="8", line_no=30)
        _order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10", required_date=_far(10),
        )
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5", required_date=_far(20),
        )
        row = _board_row(_board(db, at_pool, at_bin), at_bin)

    assert _sources(row) == {"buy": Decimal("5")}


def test_three_orders_at_the_pool_each_keep_their_own_half():
    """60 on hand, all owed to these three. A draw within a line's own quantity costs the net
    nothing, because the net already counted it, so the third still gets its half."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=60, product=product)
        cores = [
            _seed_line(
                db, company_id, project, product, pool, qty_ordered="20", line_no=number,
            )[2]
            for number in (10, 20, 30)
        ]
        board = _board(db, *cores)
        rows = [_sources(_board_row(board, core)) for core in cores]

    half = {"reserve": Decimal("10"), "buy": Decimal("10")}
    assert rows == [half, half, half]


def test_another_pool_lends_a_line_at_the_pool_nothing_while_the_pools_are_short():
    """100 at another pool, 130 owed at this one: a net of -30. The add-back is what the line
    stands on, not a claim on another pool's stock, so the line of 40 buys."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0, product=product)
        _dealer_pool(db, on_hand=100, product=product)
        own = _project_bin(db, pool)
        _seed_line(db, company_id, project, product, pool, qty_ordered="90", line_no=30)
        _order, _line, at_pool, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        _order, _line, at_bin, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5",
            required_date=REQUIRED_DATE - timedelta(days=14),
        )
        row = _board_row(_board(db, at_pool, at_bin), at_pool)

    assert _sources(row) == {"buy": Decimal("40")}


# --------------------------------------------------------------------------- what the book counted
#
# 10 on hand, all owed to another line, so the pool's net is 0. A line the pool's book never
# counted has nothing to add back, whatever it says it owes.


def _line_the_book_may_not_count(mutate):
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        _seed_line(db, company_id, project, product, pool, qty_ordered="10", line_no=20)
        order, _line, core_so, core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        mutate(core_so, core_line)
        db.commit()
        return _totals(_components(ProjectSupplyService(db).proposal_for(order)))


def test_a_closed_order_adds_nothing_back():
    got = _line_the_book_may_not_count(lambda so, _line: setattr(so, "status", "closed"))
    assert "reserve" not in got, got


def test_a_non_transferable_order_adds_nothing_back():
    got = _line_the_book_may_not_count(lambda so, _line: setattr(so, "is_transferable", False))
    assert "reserve" not in got, got


def test_a_covered_line_adds_nothing_back():
    got = _line_the_book_may_not_count(
        lambda _so, line: setattr(line, "purchasing_status", "covered")
    )
    assert "reserve" not in got, got


def test_what_goes_back_is_the_required_quantity_not_the_ordered_one():
    """Required 4 of ordered 10, another line owes 6, 10 on hand. Available is 4, share 2."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        _seed_line(db, company_id, project, product, pool, qty_ordered="6", line_no=20)
        order, _line, _core_so, core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        core_line.qty_required = Decimal("4")
        db.commit()
        got = _totals(_components(ProjectSupplyService(db).proposal_for(order)))

    assert got["reserve"] == Decimal("2"), got


def test_a_part_delivered_line_adds_back_what_it_still_owes():
    """10 ordered, 3 delivered, 10 on hand: the book counted 7, so the net goes from 3 to 10."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        order, _line, _core_so, core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        core_line.qty_delivered = Decimal("3")
        db.commit()
        service = ProjectSupplyService(db)
        fact = next(iter(service._facts_for(order, service.lines_of(str(order.id))).values()))
        net, available = fact.pools_net, fact.pool_available

    assert (net, available) == (Decimal("10"), Decimal("10"))


def test_a_retired_pool_adds_nothing_back():
    """A line at an inactive pool is not in anybody's pool book, and the pool rung cannot draw it."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        _dealer_pool(db, on_hand=10, product=product)
        other = _dealer_pool(db, on_hand=0, product=product)
        _seed_line(db, company_id, project, product, other, qty_ordered="10", line_no=20)
        retired = _warehouse(
            db, f"ZZD{_uid()[:6]}", segment="dealer", active=False, fulfilment_planning=False,
        )
        db.flush()
        retired.pool_warehouse_id = retired.id
        db.commit()
        order, _line, _core_so, _core = _seed_line(
            db, company_id, project, product, retired, qty_ordered="10",
        )
        service = ProjectSupplyService(db)
        fact = next(iter(service._facts_for(order, service.lines_of(str(order.id))).values()))
        back = fact.pool_book_back
        got = _totals(_components(service.proposal_for(order)))

    assert back == 0
    assert "reserve" not in got, got


# --------------------------------------------------------------------------- confirm
#
# Confirming what the engine itself proposed must take what it proposed. The confirm ledger is
# shared across a whole confirmation, as the walk's are across a walk, and the same rule holds:
# a line's add-back is its own.


def _confirm_the_proposal(db, order, actor):
    """Confirm the engine's own proposal, line by line. Returns (reserved, bought, short)."""
    service = ProjectSupplyService(db)
    proposal = service.proposal_for(order)
    lines, wanted_reserve, wanted_buy = [], Decimal("0"), Decimal("0")
    for line in proposal["lines"]:
        reserve, buy = [], Decimal("0")
        for component in line["components"]:
            qty = Decimal(str(component["qty"]))
            if component["kind"] == "reserve":
                warehouse = (
                    db.query(Warehouse)
                    .filter(Warehouse.warehouse_code == component["source_location"])
                    .one()
                )
                reserve.append({"warehouse_id": str(warehouse.id), "qty": qty})
                wanted_reserve += qty
            elif component["kind"] == "buy":
                buy += qty
                wanted_buy += qty
        lines.append(
            ConfirmLine(project_line_id=line["project_line_id"], reserve=reserve, buy_qty=buy)
        )
    fresh = ProjectSupplyService(db)
    fresh.confirm(order, ConfirmSupplyBody(lines=lines), actor_user_id=actor)
    db.commit()
    short = sum(
        (entry["short"] for entries in fresh._stock_short.values() for entry in entries),
        Decimal("0"),
    )
    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.in_([line.project_line_id for line in lines]))
        .all()
    )
    bought = sum((Decimal(str(row.qty)) for row in rows), Decimal("0"))
    return wanted_reserve, wanted_buy, bought, short


def test_confirming_two_dates_at_the_pool_takes_what_was_proposed():
    """40 on hand, nobody else, 10 and then 30. The proposal is Reserve 5 + Buy 5 and Reserve
    15 + Buy 15. Confirm said "only 5 free, 10 short" on the second date, and those 10 were
    neither reserved nor bought with 40 on hand."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=40, product=product)
        order, _line, core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
            required_date=_far(10), line_no=10,
        )
        second = _core_line(
            db, core_so, product, pool, qty_ordered="30", required_date=_far(17),
        )
        _project_line(db, order, line_no=20, product=product, core_line=second)
        db.commit()
        reserved, buy, bought, short = _confirm_the_proposal(db, order, actor)

    assert (reserved, buy) == (Decimal("20"), Decimal("20"))
    assert (bought, short) == (Decimal("20"), Decimal("0"))


def test_confirming_a_project_bin_line_then_a_line_at_the_pool_takes_what_was_proposed():
    """One order, 12 on hand, 5 at a project bin and 10 at the pool, one date."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=12, product=product)
        own = _project_bin(db, pool)
        order, _line, core_so, _core = _seed_line(
            db, company_id, project, product, own, qty_ordered="5",
            required_date=_far(10), line_no=10,
        )
        second = _core_line(db, core_so, product, pool, qty_ordered="10", required_date=_far(10))
        _project_line(db, order, line_no=20, product=product, core_line=second)
        db.commit()
        reserved, buy, bought, short = _confirm_the_proposal(db, order, actor)

    assert short == Decimal("0")
    assert bought == buy
    assert reserved + buy == Decimal("15")


def test_a_confirmation_cannot_reserve_more_than_the_pool_holds():
    """The add-back is arithmetic, not stock. 10 at this pool and 100 at another, two lines of
    one order ask for 10 each here: only 10 exist, so the second is short by 10."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        _dealer_pool(db, on_hand=100, product=product)
        order, line, core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
            required_date=_far(10), line_no=10,
        )
        second_core = _core_line(
            db, core_so, product, pool, qty_ordered="10", required_date=_far(17),
        )
        second = _project_line(db, order, line_no=20, product=product, core_line=second_core)
        db.commit()
        service = ProjectSupplyService(db)
        ask = [{"warehouse_id": str(pool.id), "qty": Decimal("10")}]
        service.confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(project_line_id=str(line.id), reserve=ask),
                    ConfirmLine(project_line_id=str(second.id), reserve=ask),
                ]
            ),
            actor_user_id=actor,
        )
        short = sum(
            (entry["short"] for entries in service._stock_short.values() for entry in entries),
            Decimal("0"),
        )

    assert short == Decimal("10")


def test_a_project_line_in_the_same_confirmation_reads_the_true_net():
    """12 on hand, 10 owed at the pool: a true net of 2. The line at the pool takes 6, paid for
    by its own add-back, so the 2 are still there. A project line of ANOTHER pool's group, which
    reads this pool as one of its others and has no own reading to correct it, gets those 2."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=12, product=product)
        own = _project_bin(db, _dealer_pool(db, on_hand=0, product=product))
        order, line, core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
            required_date=_far(10), line_no=10,
        )
        bin_core = _core_line(db, core_so, product, own, qty_ordered="5", required_date=_far(17))
        bin_line = _project_line(db, order, line_no=20, product=product, core_line=bin_core)
        db.commit()
        service = ProjectSupplyService(db)
        service.confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=str(line.id),
                        reserve=[{"warehouse_id": str(pool.id), "qty": Decimal("6")}],
                        buy_qty=Decimal("4"),
                    ),
                    ConfirmLine(
                        project_line_id=str(bin_line.id),
                        reserve=[{"warehouse_id": str(pool.id), "qty": Decimal("5")}],
                    ),
                ]
            ),
            actor_user_id=actor,
        )
        short = sum(
            (entry["short"] for entries in service._stock_short.values() for entry in entries),
            Decimal("0"),
        )

    assert short == Decimal("3")


def _confirm_reserve(db, order, line, pool, actor, qty, *, buy="0", reason=None):
    """One press, one line: Reserve at the pool and Buy the rest. Returns what came up short."""
    service = ProjectSupplyService(db)
    service.confirm(
        order,
        ConfirmSupplyBody(
            lines=[
                ConfirmLine(
                    project_line_id=str(line.id),
                    reserve=[{"warehouse_id": str(pool.id), "qty": Decimal(qty)}],
                    buy_qty=Decimal(buy),
                    **({"amend_reason": reason} if reason else {}),
                )
            ]
        ),
        actor_user_id=actor,
    )
    db.commit()
    return sum(
        (entry["short"] for entries in service._stock_short.values() for entry in entries),
        Decimal("0"),
    )


def test_confirming_a_proposal_that_draws_two_pools_takes_what_was_proposed():
    """10 here, 40 at another pool, nobody else, a line of 30 here. The own pool's draw is paid
    for by the add-back, so it must not use up the net the other pool's draw is measured by."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        _dealer_pool(db, on_hand=40, product=product)
        order, _line, _core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="30", required_date=_far(10),
        )
        reserved, buy, bought, short = _confirm_the_proposal(db, order, actor)

    assert (reserved, buy) == (Decimal("25"), Decimal("5"))
    assert (bought, short) == (Decimal("5"), Decimal("0"))


def test_a_line_cannot_reserve_stock_the_book_already_holds_for_another_order():
    """10 on hand, all 10 owed to another order: the proposal is Buy. Asking for the shelf anyway
    is short by all of it, as it is at any other location."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        _seed_line(db, company_id, project, product, pool, qty_ordered="50", line_no=30)
        order, line, _core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        short = _confirm_reserve(db, order, line, pool, actor, "10")

    assert short == Decimal("10")


def test_a_line_cannot_reserve_what_the_book_has_reserved():
    """10 on hand, 8 of it already reserved: 2 are free, however much the line owes."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0, product=product)
        _stock(db, product, pool, on_hand=10, reserved=8)
        db.commit()
        order, line, _core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        short = _confirm_reserve(db, order, line, pool, actor, "10")

    assert short == Decimal("8")


def test_another_pool_gives_a_line_at_the_pool_only_the_true_net():
    """Nothing here, 40 at another pool, a line of 30 here: a true net of 10. The add-back is
    what the line stands on, and it stands on nothing at the other pool."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0, product=product)
        other = _dealer_pool(db, on_hand=40, product=product)
        order, line, _core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="30",
        )
        short = _confirm_reserve(db, order, line, other, actor, "30")

    assert short == Decimal("20")


def test_two_orders_pressed_separately_cannot_reserve_the_same_stock():
    """10 on hand, two orders of 10. The second press must not take what the first holds."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        order_x, line_x, _so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10", line_no=10,
        )
        order_y, line_y, _so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10", line_no=20,
        )
        first = _confirm_reserve(db, order_x, line_x, pool, actor, "10")
        second = _confirm_reserve(db, order_y, line_y, pool, actor, "10")

    assert first + second >= Decimal("10"), (first, second)


def test_a_units_add_back_is_spent_once():
    """30 on hand, 15 owed to another order, one unit of 10 and 10: a true net of -5, so the
    unit can have 15 of its 20. The second line reads what the first left of the add-back."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=30, product=product)
        _seed_line(db, company_id, project, product, pool, qty_ordered="15", line_no=30)
        order, line, core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10", line_no=10,
        )
        second_core = _core_line(
            db, core_so, product, pool, qty_ordered="10", required_date=REQUIRED_DATE,
        )
        second = _project_line(db, order, line_no=20, product=product, core_line=second_core)
        db.commit()
        ask = [{"warehouse_id": str(pool.id), "qty": Decimal("10")}]
        service = ProjectSupplyService(db)
        service.confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(project_line_id=str(line.id), reserve=ask),
                    ConfirmLine(project_line_id=str(second.id), reserve=ask),
                ]
            ),
            actor_user_id=actor,
        )
        short = sum(
            (entry["short"] for entries in service._stock_short.values() for entry in entries),
            Decimal("0"),
        )

    assert short == Decimal("5")


def test_the_confirm_preview_of_a_line_at_the_pool_raises_its_order_row():
    """AC-7 on the path the board's preview calls. Nothing is refused, and the Buy is listed."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        order, line, _core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        entry = SimpleNamespace(
            pso_id=str(order.id),
            only_line_ids=None,
            lines=[
                ConfirmLine(
                    project_line_id=str(line.id),
                    reserve=[{"warehouse_id": str(pool.id), "qty": Decimal("5")}],
                    buy_qty=Decimal("5"),
                )
            ],
            as_of=None,
            model_dump=lambda **_kwargs: {},
        )
        results = ProjectSupplyService(db).confirm_many(
            [entry], actor_user_id=actor, assert_can_act=lambda *_args: None, preview=True,
        )

    assert [result.get("ok") for result in results] == [True], results
    assert not results[0].get("failing_lines"), results


# --------------------------------------------------------------------------- the share
#
# What a line's add-back is worth is the spare of what it stands on. Net-bound figures make that
# difference larger as the pools get shorter, which took the dealers' half on a short book.


def _three_lines_at_the_pool(*, owed_elsewhere):
    """160 on hand, three orders of 40, and a pool holding nothing that owes `owed_elsewhere`."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=160, product=product)
        short = _dealer_pool(db, on_hand=0, product=product)
        if owed_elsewhere:
            _seed_line(
                db, company_id, project, product, short, qty_ordered=str(owed_elsewhere),
                line_no=90,
            )
        cores = [
            _seed_line(
                db, company_id, project, product, pool, qty_ordered="40",
                required_date=_far(10 + number), line_no=number,
            )[2]
            for number in (1, 2, 3)
        ]
        board = _board(db, *cores)
        rows = [_sources(_board_row(board, core)) for core in cores]
    return sum((row.get("reserve", Decimal("0")) for row in rows), Decimal("0"))


def test_the_dealers_half_holds_on_a_healthy_book():
    assert _three_lines_at_the_pool(owed_elsewhere=0) == Decimal("80")


def test_reserve_does_not_rise_as_the_pools_get_shorter():
    """It read 80, then 118 at 39 owed elsewhere, 117 at 41 and 60 at 60."""
    totals = [_three_lines_at_the_pool(owed_elsewhere=owed) for owed in (0, 39, 41, 60)]
    assert totals == sorted(totals, reverse=True), totals
    assert totals[0] == Decimal("80")
