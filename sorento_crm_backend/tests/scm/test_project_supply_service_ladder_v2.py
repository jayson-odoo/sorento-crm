"""Ladder v2 - the source ladder as the captain answered it, 19 August 2026 evening
(`documentation/plans/scm/PLAN-demo-followups-19aug-ladder-v2.md` section E).

Service-level (`ProjectSupplyService.proposal_for` / `.confirm`), not HTTP: every scenario
here is about the COMPOSITION and the write path, not the route layer, which
`tests/test_so_supply_confirmation.py` already covers end to end. Warehouse and world
helpers are imported from that suite so the two files cannot come to disagree about what a
Project SO looks like (the same convention `tests/test_supply_partial_confirmation.py`
already follows).

Postgres via `tests/_pg_fixture.py::blank_session`, every test seeding its own chain, per
PRINCIPLES.md and this repo's CI-is-empty lesson.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.models.project_so import SO_STATUS_PUBLISHED
from app.services import project_seed_service
from app.services.error_handler import AppException
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import priority

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _product,
    _project_line,
    _project_so,
    _second_company,  # noqa: F401
    _sorento,
    _stock,
    _uid,
    _user,
    _warehouse,
)

#: The delivery date every scenario here plans against.
#:
#: RELATIVE to today, and inside the ATP reserve window on purpose (see
#: `front_planning_engine.reserve_window_end`): the borrow rungs this file exists to pin are
#: not offered to a line due beyond `today + lead time + buffer`, so a fixed far-future date
#: would test the window rule instead of the rungs. The window's own behaviour is asserted in
#: `test_front_planning_engine.py` and in this file's own reserve-window scenarios.
REQUIRED_DATE = date.today() + timedelta(days=30)


def _world(db):
    """Company, project, product - the minimum every scenario below builds on."""
    from app.models.base import company_scope
    from app.services.project_service import register_project

    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    eling = _user(db, "zzt-ladder-v2 Eling")
    project = register_project(
        db, company_id=company_id, actor_user_id=eling, developer_party_id=None,
        title="zzt-ladder-v2 Tuju Residences",
    )
    from tests.test_so_supply_confirmation import _product

    product = _product(db)
    return company_id, eling, project, product


def _group_sites(db):
    """Three sites, one ownership group: `ZZT<SITE>-<GROUP>` at BRW/MWH/DC1, each with its
    own site pool `ZZT<SITE><suffix>` (no hyphen - the plain pool code)."""
    group = f"BB{_uid()[:4]}"
    sites = {}
    for site in ("BRW", "MWH", "DC1"):
        pool = _warehouse(db, f"ZZT{site}{_uid()[:4]}")
        own = _warehouse(db, f"ZZT{site}-{group}")
        own.pool_warehouse_id = pool.id
        db.flush()
        sites[site] = (own, pool)
    return group, sites


def _seed_line(db, company_id, project, product, warehouse, *, qty_ordered, required_date=REQUIRED_DATE,
          line_no=10, so_number=None, sales_agent_id=None):
    from app.models.order import SalesOrder

    core_so = _core_so(db, company_id)
    if so_number is not None:
        core_so.so_number = so_number
    if sales_agent_id is not None:
        core_so.sales_agent_id = sales_agent_id
    db.flush()
    core_line = _core_line(
        db, core_so, product, warehouse, qty_ordered=qty_ordered, required_date=required_date,
    )
    order = _project_so(db, project, status=SO_STATUS_PUBLISHED)
    line = _project_line(db, order, line_no=line_no, product=product, core_line=core_line)
    db.commit()
    return order, line, core_so, core_line


def _agent(db, code: str, *, location_group=None):
    from app.models.sales_agent import SalesAgent

    row = SalesAgent(id=_uid(), sales_agent=code, source="manual", is_active=True,
                      location_group=location_group)
    db.add(row)
    db.flush()
    return row


def _components(proposal):
    return proposal["lines"][0]["components"]


# --------------------------------------------------------------------------- rung 0


def test_a_line_beyond_the_coverage_date_proposes_buy_all_only():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=999)
        priority.create_revision(
            db, name="zzt-coverage", factors={}, demand_class_weights={},
            reorder_coverage_until=date(2026, 10, 31),
            cross_group_borrow_max_qty=50, cross_group_borrow_max_pct=10.0,
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
            required_date=date(2029, 1, 1),
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert len(components) == 1
    assert components[0]["kind"] == "buy"
    assert components[0]["qty"] == "40"
    assert "coverage" in components[0]["reason"]


def test_a_line_on_or_before_the_coverage_date_runs_the_ladder_normally():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=40)
        priority.create_revision(
            db, name="zzt-coverage-2", factors={}, demand_class_weights={},
            reorder_coverage_until=date(2026, 10, 31),
            cross_group_borrow_max_qty=50, cross_group_borrow_max_pct=10.0,
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
            required_date=date(2026, 10, 31),
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert len(components) == 1
    assert components[0]["kind"] == "reserve"
    assert components[0]["qty"] == "40"


# --------------------------------------------------------------------------- own location


def test_the_own_location_is_never_a_source_only_the_pool_and_group_locations_are():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        # Free stock sits at the line's OWN location - the ladder must not touch it.
        _stock(db, product, own, on_hand=999)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert not any(c.get("source_location") == own.warehouse_code for c in components)
    assert len(components) == 1
    assert components[0]["kind"] == "buy"
    assert components[0]["qty"] == "40"


# --------------------------------------------------------------------------- rung 2: pool


def test_pool_reserve_draws_the_own_site_pool_before_other_site_pools():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _other_own, other_pool = sites["MWH"]
        _stock(db, product, pool, on_hand=15)
        _stock(db, product, other_pool, on_hand=100)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    reserves = {c["source_location"]: c for c in components if c["kind"] == "reserve"}
    assert set(reserves) == {pool.warehouse_code, other_pool.warehouse_code}
    assert reserves[pool.warehouse_code]["qty"] == "15"
    assert reserves[other_pool.warehouse_code]["qty"] == "25"
    assert sum(Decimal(c["qty"]) for c in components) == Decimal("40")


def test_a_pool_with_negative_available_offers_nothing_not_a_floor_of_zero_read_as_some():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=50)
        # The pool's own book already owes 80 there, ranked ahead of nobody in particular -
        # its SIGNED availability (on hand - SO qty) is -30.
        theirs_so, _theirs = _core_so(db, company_id), None
        _core_line(db, theirs_so, product, pool, qty_ordered="80")
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert not any(c["kind"] == "reserve" for c in components)
    assert len(components) == 1
    assert components[0]["kind"] == "buy"
    assert components[0]["qty"] == "10"


# --------------------------------------------------------------------------- rung 3: group take


def test_group_take_covers_the_line_from_a_sibling_location_mwh_bb():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        _stock(db, product, sibling, on_hand=50)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="50",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert len(components) == 1
    assert components[0]["kind"] == "reserve"
    assert components[0]["rung"] == "group_take"
    assert components[0]["source_location"] == sibling.warehouse_code
    assert components[0]["qty"] == "50"


# --------------------------------------------------------------------------- rung 6: whole-line


def test_whole_line_rule_a_partial_cover_becomes_a_single_buy_for_the_whole_line():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=213)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="358",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert len(components) == 1
    assert components[0]["kind"] == "buy"
    assert components[0]["qty"] == "358"
    assert "213" in components[0]["reason"] and "358" in components[0]["reason"]


def test_whole_line_rule_a_full_cover_keeps_its_composition():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=358)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="358",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert len(components) == 1
    assert components[0]["kind"] == "reserve"
    assert components[0]["qty"] == "358"


# ------------------------------------------------------------- rung 0b: the reserve window


def _lead_time(db, product, supplier_days: int) -> None:
    """State a supplier agreement for the product, which is where the lead time comes from."""
    import uuid as _uuid

    from app.models.procurement import ProductSupplier, Supplier

    supplier = Supplier(
        id=str(_uuid.uuid4()),
        supplier_code=f"ZZT-SUP-{_uuid.uuid4().hex[:8]}".upper(),
        supplier_name="ZZT lead-time supplier",
    )
    db.add(supplier)
    db.flush()
    db.add(
        ProductSupplier(
            id=str(_uuid.uuid4()),
            product_id=product.id,
            supplier_id=supplier.id,
            standard_lead_time_days=supplier_days,
        )
    )
    db.commit()


def test_a_line_beyond_the_reserve_window_buys_rather_than_borrowing_a_nearer_orders_stock():
    """The rule, end to end: a line due long after purchasing could simply buy for it does
    not take stock a nearer-dated order is holding. Its whole quantity is a Buy, and the
    reason names the window rather than the arithmetic."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _lead_time(db, product, 30)

        # A donor at the same location, due later still - the rung-4 candidate this line
        # would take from if it were inside its window.
        _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=date.today() + timedelta(days=400), line_no=2,
            so_number="SO371334",
        )
        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            # 30 days of lead time + 14 of buffer = a window of 44 days; this is well beyond.
            required_date=date.today() + timedelta(days=300), line_no=1,
            so_number="SO331506",
        )

        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert len(components) == 1
    assert components[0]["kind"] == "buy"
    assert components[0]["qty"] == "145"
    assert "beyond the lead time window" in components[0]["reason"]


def test_a_line_beyond_the_reserve_window_is_offered_no_donor_to_borrow_from():
    """Not composed AND not offered. The sheet ranked a donor list beside the line anyway, so
    Amend still put the one move the rule forbids in front of the planner - the same defect
    the board showed on SO414341, on the other screen."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        outside = _warehouse(db, f"ZZTHP-{_uid()[:4]}")
        _stock(db, product, outside, on_hand=650)
        _lead_time(db, product, 90)

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="441",
            # 174 days out, against 90 of lead time plus the 14-day buffer.
            required_date=date.today() + timedelta(days=174),
        )
        line = ProjectSupplyService(db).proposal_for(order)["lines"][0]

    assert line["components"][0]["kind"] == "buy"
    assert line["borrow_candidates"] == []


def test_a_line_beyond_the_window_still_reserves_stock_that_is_genuinely_surplus():
    """The pool rung is capped at the location's SIGNED availability, so what it offers is
    what nothing else there is owed. Refusing a far line that would buy stock the business
    already holds and nobody needs."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=358)
        _lead_time(db, product, 30)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="358",
            required_date=date.today() + timedelta(days=300),
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert len(components) == 1
    assert components[0]["kind"] == "reserve"
    assert components[0]["qty"] == "358"


def test_a_line_inside_the_window_is_untouched_by_the_rule():
    """The near line keeps rung 4, exactly as it always had it."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _lead_time(db, product, 30)

        _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=date.today() + timedelta(days=40), line_no=2,
            so_number="SO371334",
        )
        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=date.today() + timedelta(days=10), line_no=1,
            so_number="SO331506",
        )

        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert components[0]["kind"] == "borrow"
    assert components[0]["rung"] == "group_borrow"


def test_a_product_nobody_states_a_lead_time_for_uses_the_documented_default():
    """No supplier agreement, no measured performance: 90 days (the median of the live book)
    plus the 14-day buffer, so a line 300 days out is still outside its window and a line 60
    days out is still inside it."""
    from app.services.scm.front_planning_engine import DEFAULT_LEAD_TIME_DAYS

    assert DEFAULT_LEAD_TIME_DAYS == 90

    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        # Deliberately no `_lead_time` call.

        _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=date.today() + timedelta(days=400), line_no=2,
            so_number="SO371334",
        )
        far, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=date.today() + timedelta(days=300), line_no=1,
            so_number="SO331506",
        )
        far_components = _components(ProjectSupplyService(db).proposal_for(far))

    assert far_components[0]["kind"] == "buy"
    assert "beyond the lead time window" in far_components[0]["reason"]


# --------------------------------------------------------------------------- rung 4: group borrow


def test_group_borrow_from_a_lower_ranked_so_is_auto_proposed_with_an_order_back():
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        # The donor: another sales order at the SAME location, due LATER (so it ranks
        # below on need_by_date, the default seeded weight).
        donor_order, _donor_line, donor_cso, donor_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=REQUIRED_DATE + timedelta(days=60), line_no=2,
            so_number="SO371334",
        )

        # This line, due SOONER - ranked ahead of the donor.
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="145",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO331506",
        )

        proposal = ProjectSupplyService(db).proposal_for(order)
        components = proposal["lines"][0]["components"]
        assert len(components) == 1
        borrow = components[0]
        assert borrow["kind"] == "borrow"
        assert borrow["rung"] == "group_borrow"
        assert borrow["qty"] == "145"
        assert borrow["donor_so_number"] == "SO371334"
        assert borrow["donor_line_no"] == 2
        assert borrow["order_back_qty"] == "145"
        # B4: urgency = the DONOR's own required date, carried by the engine itself -
        # not this line's, and not left for the confirm payload alone to state.
        assert borrow["donor_required_date"] == REQUIRED_DATE + timedelta(days=60)
        candidates = proposal["lines"][0]["borrow_candidates"]
        donor_candidate = next(
            c for c in candidates if c.get("donor_so_number") == "SO371334"
        )
        assert donor_candidate["donor_required_date"] == REQUIRED_DATE + timedelta(days=60)

        service = ProjectSupplyService(db)
        result = service.confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=line.id,
                        borrow=[
                            {
                                "source": "other_location",
                                "warehouse_id": str(own.id),
                                "qty": "145",
                                "reason": "Group borrow, auto-proposed.",
                                "donor_core_line_id": str(donor_cline.id),
                                "donor_so_number": "SO371334",
                                "donor_line_no": 2,
                                "donor_required_date": (
                                    REQUIRED_DATE + timedelta(days=60)
                                ).isoformat(),
                            }
                        ],
                    )
                ]
            ),
            actor_user_id=eling,
        )
        assert result["inquiry_rows_created"] == 1

        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert str(row.qty) in ("145", "145.0000")
        assert row.stock_location == own.warehouse_code
        assert "SO371334" in row.note
        assert "line 2" in row.note
        assert row.delivery_date == REQUIRED_DATE + timedelta(days=60)


def test_a_same_agent_donor_is_offered_even_when_ranked_above_but_never_auto_proposed():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        agent = _agent(db, f"JEREMY{_uid()[:4]}", location_group=_group)
        db.commit()

        # The donor is due SOONER (ranked ABOVE this line) but shares the same agent.
        _donor_order, _donor_line, donor_cso, _donor_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE - timedelta(days=30), line_no=2,
            so_number="SO900001", sales_agent_id=agent.id,
        )
        order, _line_obj, cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO900002",
            sales_agent_id=agent.id,
        )
        db.commit()

        proposal = ProjectSupplyService(db).proposal_for(order)
        components = proposal["lines"][0]["components"]
        # Not auto-proposed: a higher-ranked donor never composes, whole-line falls to Buy.
        assert len(components) == 1
        assert components[0]["kind"] == "buy"

        candidates = proposal["lines"][0]["borrow_candidates"]
        same_agent_rows = [c for c in candidates if c.get("same_agent")]
        assert same_agent_rows, "same-agent donor must still be OFFERED"
        assert same_agent_rows[0]["donor_so_number"] == "SO900001"
        assert same_agent_rows[0].get("lower_ranked") is False


# --------------------------------------------------------------------------- rung 5: cross-group


def test_cross_group_borrow_is_capped_by_the_small_quantity_limit():
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        outside = _warehouse(db, f"ZZTHP-{_uid()[:4]}")
        _stock(db, product, outside, on_hand=999)
        priority.create_revision(
            db, name="zzt-cap", factors={}, demand_class_weights={},
            reorder_coverage_until=None,
            cross_group_borrow_max_qty=20, cross_group_borrow_max_pct=0.0,
        )
        db.commit()

        # Two INDEPENDENT groups, so the small and the big line never compete for the
        # same group_borrow pile - each is judged on the cross-group cap alone.
        _group_1, sites_1 = _group_sites(db)
        own_small, _pool_1 = sites_1["BRW"]
        _group_2, sites_2 = _group_sites(db)
        own_big, _pool_2 = sites_2["BRW"]

        # Under the cap: 15 <= 20.
        order_small, _l1, _c1, _cl1 = _seed_line(
            db, company_id, project, product, own_small, qty_ordered="15", line_no=1,
        )
        proposal_small = ProjectSupplyService(db).proposal_for(order_small)
        small_components = proposal_small["lines"][0]["components"]

        # Over the cap: 25 > 20.
        order_big, _l2, _c2, _cl2 = _seed_line(
            db, company_id, project, product, own_big, qty_ordered="25", line_no=1,
        )
        proposal_big = ProjectSupplyService(db).proposal_for(order_big)
        big_components = proposal_big["lines"][0]["components"]

    assert len(small_components) == 1
    assert small_components[0]["kind"] == "borrow"
    assert small_components[0]["rung"] == "cross_group_borrow"
    assert small_components[0]["source_location"] == outside.warehouse_code

    assert len(big_components) == 1
    assert big_components[0]["kind"] == "buy"
    assert big_components[0]["qty"] == "25"


# --------------------------------------------------------------------------- review fixes (B3/S1/S2/S3/S8, nits)


def test_group_borrow_from_a_sibling_location_raises_the_order_back_only_once():
    """B3: a group borrow whose donor sits at a SIBLING location (not this line's own)
    used to be fed BOTH into the unconditional order-back AND the location-pile
    shortfall loop, so `donor_availability`'s own netting of the donor's `so_qty` looked
    like a second hole and raised a second `IV_BORROW_SHORTFALL` row for the same take."""
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]

        donor_order, _donor_line, _dcso, donor_cline = _seed_line(
            db, company_id, project, product, sibling, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=60), line_no=3,
            so_number="SO500001",
        )
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO500002",
        )

        proposal = ProjectSupplyService(db).proposal_for(order)
        components = proposal["lines"][0]["components"]
        assert len(components) == 1
        assert components[0]["kind"] == "borrow"
        assert components[0]["rung"] == "group_borrow"
        assert components[0]["source_location"] == sibling.warehouse_code

        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=line.id,
                        borrow=[
                            {
                                "source": "other_location",
                                "warehouse_id": str(sibling.id),
                                "qty": "90",
                                "reason": "Group borrow, auto-proposed.",
                                "donor_core_line_id": str(donor_cline.id),
                                "donor_so_number": "SO500001",
                                "donor_line_no": 3,
                            }
                        ],
                    )
                ]
            ),
            actor_user_id=eling,
        )

        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
            .all()
        )
        assert len(rows) == 1, "a sibling-location group borrow must raise exactly one order-back"


def test_borrow_shortfall_netting_consumes_an_actioned_row_once_not_per_entry():
    """B3: `_raise_borrow_shortfalls`'s `placed` pool is CONSUMED as each shortfall entry
    draws on it, not restated in full against every entry sharing its (item, location)
    key. Two lines of one confirmation each open their own hole at the SAME donor
    location; purchasing has only actioned 50 of the 90 total. Netting the WHOLE 50 off
    BOTH entries (the bug) makes the second entry's 40 look covered when only the first
    entry's 50 was; consuming the 50 once (the fix) still raises the 40 that is real.
    """
    from app.models.project_so import IV_BORROW_SHORTFALL, INQUIRY_ACTIONED, OrderInquiryRow
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]

        donor_a_order, _da, _dacso, donor_a_cline = _seed_line(
            db, company_id, project, product, sibling, qty_ordered="200",
            required_date=REQUIRED_DATE + timedelta(days=90), line_no=1,
            so_number="SO860001",
        )
        donor_b_order, _db_, _dbcso, donor_b_cline = _seed_line(
            db, company_id, project, product, sibling, qty_ordered="200",
            required_date=REQUIRED_DATE + timedelta(days=90), line_no=1,
            so_number="SO860002",
        )

        core_so = _core_so(db, company_id)
        core_so.so_number = "SO860003"
        db.flush()
        core_line_1 = _core_line(
            db, core_so, product, own, qty_ordered="50", required_date=REQUIRED_DATE,
        )
        core_line_2 = _core_line(
            db, core_so, product, own, qty_ordered="40", required_date=REQUIRED_DATE,
        )
        order = _project_so(db, project, status=SO_STATUS_PUBLISHED)
        line_1 = _project_line(db, order, line_no=1, product=product, core_line=core_line_1)
        line_2 = _project_line(db, order, line_no=2, product=product, core_line=core_line_2)
        db.commit()

        def borrow_payload():
            return [
                ConfirmLine(
                    project_line_id=line_1.id,
                    borrow=[
                        {
                            "source": "other_location",
                            "warehouse_id": str(sibling.id),
                            "qty": "50",
                            "reason": "Group borrow.",
                            "donor_core_line_id": str(donor_a_cline.id),
                            "donor_so_number": "SO860001",
                            "donor_line_no": 1,
                        }
                    ],
                ),
                ConfirmLine(
                    project_line_id=line_2.id,
                    borrow=[
                        {
                            "source": "other_location",
                            "warehouse_id": str(sibling.id),
                            "qty": "40",
                            "reason": "Group borrow.",
                            "donor_core_line_id": str(donor_b_cline.id),
                            "donor_so_number": "SO860002",
                            "donor_line_no": 1,
                        }
                    ],
                ),
            ]

        service = ProjectSupplyService(db)
        service.confirm(
            order, ConfirmSupplyBody(lines=borrow_payload()), actor_user_id=eling,
        )
        db.commit()

        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL, OrderInquiryRow.state == "raised")
            .all()
        )
        assert len(rows) == 2
        by_qty = {str(r.qty).split(".")[0]: r for r in rows}
        # Purchasing has only actioned the 50 - not the 40.
        by_qty["50"].state = INQUIRY_ACTIONED
        db.commit()

        service_2 = ProjectSupplyService(db)
        service_2.confirm(
            order, ConfirmSupplyBody(lines=borrow_payload()), actor_user_id=eling,
        )
        db.commit()

        still_raised = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL, OrderInquiryRow.state == "raised")
            .all()
        )
        # The 50 already placed nets out; the 40 that was NEVER placed is raised again.
        assert len(still_raised) == 1, still_raised
        assert str(still_raised[0].qty).split(".")[0] == "40"


def test_a_second_confirmation_cannot_borrow_what_an_earlier_one_already_holds():
    """S1: `_donor_line_ledger` only guarded two lines of the SAME confirmation. A
    second, separate confirmation re-read the donor's live open quantity fresh and could
    borrow the same units again - seeded now net of what an earlier confirmed decision
    already holds from that donor line (`_group_borrow_held_qty`)."""
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        donor_order, _donor_line, _dcso, donor_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=60), line_no=9,
            so_number="SO600001",
        )
        order_a, line_a, _cso_a, _cline_a = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO600002",
        )
        order_b, line_b, _cso_b, _cline_b = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO600003",
        )

        borrow_payload = [
            {
                "source": "other_location",
                "warehouse_id": str(own.id),
                "qty": "90",
                "reason": "Group borrow.",
                "donor_core_line_id": str(donor_cline.id),
                "donor_so_number": "SO600001",
                "donor_line_no": 9,
            }
        ]

        ProjectSupplyService(db).confirm(
            order_a,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=line_a.id, borrow=list(borrow_payload))]
            ),
            actor_user_id=eling,
        )
        db.commit()

        with pytest.raises(AppException):
            ProjectSupplyService(db).confirm(
                order_b,
                ConfirmSupplyBody(
                    lines=[
                        ConfirmLine(project_line_id=line_b.id, borrow=list(borrow_payload))
                    ]
                ),
                actor_user_id=eling,
            )


def test_a_sibling_line_of_the_same_sales_order_is_never_an_auto_donor():
    """S2: borrowing from another line of the SAME sales order and raising an
    order-back against it is a borrow "against itself" - never offered, auto or not."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        core_so = _core_so(db, company_id)
        core_so.so_number = "SO700001"
        db.flush()
        donor_core = _core_line(
            db, core_so, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=60),
        )
        asking_core = _core_line(
            db, core_so, product, own, qty_ordered="90", required_date=REQUIRED_DATE,
        )
        order = _project_so(db, project, status=SO_STATUS_PUBLISHED)
        _project_line(db, order, line_no=2, product=product, core_line=donor_core)
        asking_line = _project_line(db, order, line_no=1, product=product, core_line=asking_core)
        db.commit()

        proposal = ProjectSupplyService(db).proposal_for(order)
        by_id = {l["project_line_id"]: l for l in proposal["lines"]}
        asking = by_id[str(asking_line.id)]

    assert not any(c["kind"] == "borrow" for c in asking["components"])
    assert asking["components"][0]["kind"] == "buy"
    assert not any(
        c.get("donor_core_line_id") == str(donor_core.id)
        for c in asking["borrow_candidates"]
    ), "a sibling line of the SAME sales order must never be offered as a donor"


def test_a_line_covered_by_another_active_decision_is_not_offered_as_a_donor():
    """S2, parity with `_pile_book`'s own `_decided_elsewhere` exclusion: a line already
    covered by another active decision is not a stable donor for a different one."""
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        donor_order, donor_line, _dcso, donor_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=60), line_no=5,
            so_number="SO800001",
        )
        ProjectSupplyService(db).confirm(
            donor_order,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=donor_line.id, buy_qty="90")]
            ),
            actor_user_id=eling,
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO800002",
        )

        proposal = ProjectSupplyService(db).proposal_for(order)
        components = proposal["lines"][0]["components"]

    assert not any(c["kind"] == "borrow" for c in components)
    assert components[0]["kind"] == "buy"
    assert not any(
        c.get("donor_core_line_id") == str(donor_cline.id)
        for c in proposal["lines"][0]["borrow_candidates"]
    )


def test_group_borrow_donors_at_one_location_prefer_the_lowest_ranked_over_the_biggest():
    """Nit: within one location, `_group_borrow_donors` must take the LOWEST-ranked
    donor first (the safest one to draw from), not the one holding the most."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        # donor_far ranks BELOW donor_near (a much later required date) at the SAME
        # location, despite holding less - it is the safer donor to draw from first.
        _far_order, _far_line, _far_cso, far_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=REQUIRED_DATE + timedelta(days=120), line_no=2,
            so_number="SO840001",
        )
        _near_order, _near_line, _near_cso, _near_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=10), line_no=3,
            so_number="SO840002",
        )
        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO840003",
        )

        proposal = ProjectSupplyService(db).proposal_for(order)
        components = proposal["lines"][0]["components"]

    assert len(components) == 1
    assert components[0]["kind"] == "borrow"
    assert components[0]["rung"] == "group_borrow"
    assert components[0]["donor_core_line_id"] == str(far_cline.id)


def test_group_borrow_refuses_a_donor_line_of_a_different_product():
    """S8: the donor line named has to hold the SAME product this line is asking for."""
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        other_product = _product(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        core_so = _core_so(db, company_id)
        core_so.so_number = "SO810001"
        db.flush()
        donor_core = _core_line(db, core_so, other_product, own, qty_ordered="90")
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90", line_no=1,
        )

        with pytest.raises(AppException):
            ProjectSupplyService(db).confirm(
                order,
                ConfirmSupplyBody(
                    lines=[
                        ConfirmLine(
                            project_line_id=line.id,
                            borrow=[
                                {
                                    "source": "other_location",
                                    "warehouse_id": str(own.id),
                                    "qty": "90",
                                    "reason": "Group borrow.",
                                    "donor_core_line_id": str(donor_core.id),
                                }
                            ],
                        )
                    ]
                ),
                actor_user_id=eling,
            )


def test_group_borrow_refuses_a_donor_line_outside_the_ownership_group():
    """S8: the donor's own location has to be inside THIS line's ownership group - a
    bare site pool (no group suffix) is not a group-borrow donor."""
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]

        core_so = _core_so(db, company_id)
        core_so.so_number = "SO820001"
        db.flush()
        donor_core = _core_line(db, core_so, product, pool, qty_ordered="90")
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90", line_no=1,
        )

        with pytest.raises(AppException):
            ProjectSupplyService(db).confirm(
                order,
                ConfirmSupplyBody(
                    lines=[
                        ConfirmLine(
                            project_line_id=line.id,
                            borrow=[
                                {
                                    "source": "other_location",
                                    "warehouse_id": str(pool.id),
                                    "qty": "90",
                                    "reason": "Group borrow.",
                                    "donor_core_line_id": str(donor_core.id),
                                }
                            ],
                        )
                    ]
                ),
                actor_user_id=eling,
            )


def test_group_borrow_refuses_a_donor_line_that_is_no_longer_open_demand():
    """S8: a donor line already fully delivered is no longer open demand and cannot be
    borrowed from, reusing `is_open_demand()`."""
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        core_so = _core_so(db, company_id)
        core_so.so_number = "SO830001"
        db.flush()
        donor_core = _core_line(
            db, core_so, product, own, qty_ordered="90", qty_delivered="90",
        )
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90", line_no=1,
        )

        with pytest.raises(AppException):
            ProjectSupplyService(db).confirm(
                order,
                ConfirmSupplyBody(
                    lines=[
                        ConfirmLine(
                            project_line_id=line.id,
                            borrow=[
                                {
                                    "source": "other_location",
                                    "warehouse_id": str(own.id),
                                    "qty": "90",
                                    "reason": "Group borrow.",
                                    "donor_core_line_id": str(donor_core.id),
                                }
                            ],
                        )
                    ]
                ),
                actor_user_id=eling,
            )


def test_group_pile_runs_o1_queries_for_a_board_of_n_lines_of_one_product_group():
    """S3: `_group_pile_members` is cached per (product, group), not per line - a board
    of N lines sharing one product/group must run its own query ONCE, not N times.

    Counted by the ONE query in this whole call graph that joins `sales_agents`
    (`_group_pile_members`'s own read) - a query-count assertion via a real
    `before_cursor_execute` listener, not an inference from timing.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        # A donor, so the group pile is a real read with more than one row to rank.
        _donor_order, _donor_line, _dcso, _dcline = _seed_line(
            db, company_id, project, product, own, qty_ordered="500",
            required_date=REQUIRED_DATE + timedelta(days=120), line_no=99,
            so_number="SO850000",
        )

        # N lines of ONE order, same product/location - one group pile.
        core_so = _core_so(db, company_id)
        core_so.so_number = "SO850001"
        db.flush()
        order = _project_so(db, project, status=SO_STATUS_PUBLISHED)
        n = 8
        for i in range(1, n + 1):
            core_line = _core_line(
                db, core_so, product, own, qty_ordered="10",
                required_date=REQUIRED_DATE + timedelta(days=i),
            )
            _project_line(db, order, line_no=i, product=product, core_line=core_line)
        db.commit()

        calls = {"group_pile": 0}

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "sales_agents" in statement:
                calls["group_pile"] += 1

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", _count)
        try:
            proposal = ProjectSupplyService(db).proposal_for(order)
        finally:
            event.remove(connection, "before_cursor_execute", _count)

    assert proposal["lines_total"] == n
    assert calls["group_pile"] == 1, calls
