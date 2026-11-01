"""DEALER-PLANNING PR 1: a line at a dealer-segment bin can be planned (UAC AC-1 to AC-6).

Dealer sales orders sit at a site pool such as BRW: segment dealer, `fulfilment_planning` off.
The flag verdict refused every one of them, and ticking the flag is not the way out, because it
would add the pool to the planning, netting and Stock Debt reads of every project line. So the
VERDICT moves and the flag does not. These tests hold both halves.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService, SupplyLinesRefused
from app.services.scm.planning_predicate import (
    OUTSIDE_FULFILMENT_PLANNING,
    in_fulfilment_planning,
    outside_fulfilment_planning,
)

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import _stock, _uid, _warehouse
from .test_consign_plan import _consign_world
from .test_project_supply_service_ladder import _components, _seed_line, _world


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


def test_lifting_the_verdict_does_not_put_the_bin_in_planning():
    """AC-6: `in_fulfilment_planning` is what the planning reads use, and it does not move."""
    assert in_fulfilment_planning(_bin(segment="dealer")) is False


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
        company_id, _eling, project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        order, _line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        fact = next(iter(service._facts_for(order, service.lines_of(str(order.id))).values()))
        components = _components(service.proposal_for(order))

    assert fact.unplannable_reason is None
    assert components, "the ladder must propose something for a line it can now plan"


def test_a_line_at_a_dealer_pool_draws_on_that_pool_before_buying():
    """AC-7: 100 on hand at the line's own pool, 40 wanted. Nothing needs to be bought."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
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
        company_id, eling, project, product = _world(db)
        pool = _dealer_pool(db, on_hand=0)
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, pool, qty_ordered="40",
        )
        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=str(line.id), buy_qty=Decimal("40"))]
            ),
            actor_user_id=eling,
        )


def test_confirming_a_line_at_a_flagged_off_project_bin_is_still_refused():
    """AC-3."""
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
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
                actor_user_id=eling,
            )
        reasons = [row["reason"] for row in excinfo.value.detail["failing_lines"]]

    assert OUTSIDE_FULFILMENT_PLANNING in reasons


def test_the_dealer_pool_stays_out_of_the_planning_reads():
    """AC-6: a project line's netting and proposal do not start reading the pool."""
    with blank_session() as db:
        _company_id, _eling, _project, product = _world(db)
        pool = _dealer_pool(db, product=product)
        planning = ProjectSupplyService(db)._planning_warehouses()
        pool_id = str(pool.id)
        flag = pool.fulfilment_planning

    assert pool_id not in planning
    assert flag is False


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
