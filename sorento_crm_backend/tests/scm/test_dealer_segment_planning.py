"""DEALER-PLANNING PR 1: a line at a dealer-segment bin can be planned (UAC AC-1 to AC-7).

Dealer sales orders sit at a site pool such as BRW: segment dealer, `fulfilment_planning` off.
The flag verdict refused every one of them, and ticking the flag is not the way out, because it
would add the pool to the planning, netting and Stock Debt reads of every project line. So the
VERDICT moves and the flag does not. The walk and confirm do not change, so a line at a pool
reads the pool as any project line does, its own demand included. PR 2 changes that part.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.project_so import OrderInquiryRow
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService, SupplyLinesRefused
from app.services.scm.planning_predicate import (
    OUTSIDE_FULFILMENT_PLANNING,
    outside_fulfilment_planning,
)

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import _stock, _uid, _warehouse
from .test_consign_plan import _board_world, _build, _consign_world, _contributions
from .test_project_supply_service_ladder import _components, _seed_line, _world


def _bin(*, segment, active=True, flag=False):
    return SimpleNamespace(is_active=active, fulfilment_planning=flag, segment=segment)


def _dealer_pool(db, on_hand=0, product=None):
    pool = _warehouse(
        db, f"ZZD{_uid()[:6]}", segment="dealer", fulfilment_planning=False,
    )
    db.flush()
    pool.pool_warehouse_id = pool.id
    if product is not None and on_hand:
        _stock(db, product, pool, on_hand=on_hand)
    db.commit()
    return pool


def _totals(components):
    return {
        kind: sum(Decimal(str(c["qty"])) for c in components if c["kind"] == kind)
        for kind in {c["kind"] for c in components}
    }


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


def test_a_line_at_a_dealer_pool_is_plannable_and_reserves_with_its_own_demand_back():
    """AC-1: no verdict, and the ladder is walked. 100 on hand, 40 owed here and all of it this
    line's, so Available is 100 and the dealers' half leaves 50: Reserve 40 (R7)."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=100, product=product)
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        fact = next(iter(service._facts_for(order, service.lines_of(str(order.id))).values()))
        got = _totals(_components(service.proposal_for(order)))

    assert fact.unplannable_reason is None
    assert got == {"reserve": Decimal("40")}


def test_a_project_line_on_just_enough_stock_keeps_the_dealer_share():
    """10 on hand, 10 ordered, nobody else, a project-class line: its own demand no longer nets
    the pool to zero (R7), and the dealers' half is still held back from it (R9)."""
    with blank_session() as db:
        company_id, _actor, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=10, product=product)
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        got = _totals(_components(ProjectSupplyService(db).proposal_for(order)))

    assert got == {"reserve": Decimal("5"), "buy": Decimal("5")}


def test_confirming_a_buy_at_a_dealer_pool_raises_its_order_row():
    """AC-7: the refusal a flagged-off project bin earns does not reach a dealer one, and the Buy
    reaches purchasing at the line's own location."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=str(line.id), buy_qty=Decimal("10"))]
            ),
            actor_user_id=actor,
        )
        db.commit()
        rows = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).all()
        got = [(row.verb, Decimal(str(row.qty)), row.stock_location) for row in rows]
        code = pool.warehouse_code

    assert got == [("ORDER", Decimal("10"), code)]


def test_the_confirm_preview_of_a_line_at_the_pool_is_not_refused():
    """AC-7 on the path the board's preview calls."""
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        order, line, _core_so, _core = _seed_line(
            db, company_id, project, product, pool, qty_ordered="10",
        )
        entry = SimpleNamespace(
            pso_id=str(order.id),
            only_line_ids=None,
            lines=[ConfirmLine(project_line_id=str(line.id), buy_qty=Decimal("10"))],
            as_of=None,
            model_dump=lambda **_kwargs: {},
        )
        results = ProjectSupplyService(db).confirm_many(
            [entry], actor_user_id=actor, assert_can_act=lambda *_args: None, preview=True,
        )

    assert [result.get("ok") for result in results] == [True], results
    assert not results[0].get("failing_lines"), results


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
    """AC-6: lifting the verdict does not put the pool in the set planning and netting read."""
    with blank_session() as db:
        _company_id, _actor, _project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        planning = ProjectSupplyService(db)._planning_warehouses()
        pool_id = str(pool.id)

    assert pool_id not in planning


def test_a_project_bin_line_drawing_the_pool_reads_it_as_before():
    """AC-6: 10 at the pool lends 5."""
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
        got = _totals(_components(ProjectSupplyService(db).proposal_for(order)))

    assert got == {"reserve": Decimal("5"), "buy": Decimal("5")}


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


def test_the_board_plans_a_line_at_a_dealer_pool_as_the_sheet_does():
    """AC-1 on the screen's own read."""
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

    assert row["unplannable"] is False
    assert [(s["kind"], Decimal(s["qty"])) for s in row["sources"]] == [("buy", Decimal("10"))]
