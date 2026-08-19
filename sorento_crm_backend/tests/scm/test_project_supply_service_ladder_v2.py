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

from app.models.project_so import SO_STATUS_PUBLISHED
from app.services import project_seed_service
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import priority

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _second_company,  # noqa: F401
    _sorento,
    _stock,
    _uid,
    _user,
    _warehouse,
)

REQUIRED_DATE = date(2027, 3, 1)


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
