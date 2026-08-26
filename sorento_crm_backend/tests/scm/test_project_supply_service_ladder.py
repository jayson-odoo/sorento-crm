"""The source ladder, as the captain last ruled it: v3, 25 August 2026
(`documentation/plans/scm/PLAN-scm-cs-planning-uat.md` section 1b, and 1c for the borrow a
person picks). The file was `..._ladder_v2.py`; the version is out of the name because the
ladder has now been renumbered twice and a name that dates itself goes stale on the next
ruling rather than on the next rewrite.

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


def test_the_own_location_is_a_group_source_again_under_ladder_v3():
    """Section 1b rung 2, the captain 25 August 2026: "consider the group location first
    (only available quantity)". The line's own location is a location of its group, so a
    line standing on free stock reserves it rather than buying it - which is what v2's rule
    7 exclusion made impossible."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, own, on_hand=999)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert len(components) == 1
    assert components[0]["kind"] == "reserve"
    assert components[0]["rung"] == "group_take"
    assert components[0]["source_location"] == own.warehouse_code
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


def test_a_line_beyond_the_window_buys_the_whole_line_however_much_sits_beside_it():
    """AC-L1: "if delivery date exceed lead time, directly buy". v2 still walked the two
    surplus rungs for such a line; v3 walks nothing. A pool holding exactly what the line
    owes is left alone, because a line 300 days out has months for a purchase order and the
    stock is kept for the orders that do not."""
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
    assert components[0]["kind"] == "buy"
    assert components[0]["qty"] == "358"
    assert "beyond the lead time window" in components[0]["reason"]


def test_a_line_inside_the_window_is_offered_the_donor_the_far_line_is_not():
    """The near line still SEES the donor; the far line does not. Neither has it proposed:
    borrowing another sales order's committed quantity is a person's pick (AC-L3), so the
    near line reads Buy with the donor beside it, waiting in Amend."""
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

        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)
        candidates = proposal["lines"][0]["borrow_candidates"]

    assert [c["kind"] for c in components] == ["buy"]
    assert any(c.get("donor_so_number") == "SO371334" for c in candidates)


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


# ------------------------------------------ group borrow: offered, never a rung (AC-L3)


def test_group_borrow_is_offered_not_proposed_and_a_manual_pick_raises_the_order_back():
    """AC-L3 + AC-L6, ruled 25 August 2026: the engine never composes a group borrow, so a
    line the group and the pool cannot cover reads Buy - with the donor offered beside it.
    Picking that donor in Amend and confirming still raises the order-back on the donor's
    own line, at the donor's own date, exactly as it always did."""
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
        assert [c["kind"] for c in components] == ["buy"]
        candidates = proposal["lines"][0]["borrow_candidates"]
        donor_candidate = next(
            c for c in candidates if c.get("donor_so_number") == "SO371334"
        )
        assert donor_candidate["rung"] == "group_borrow"
        assert donor_candidate["donor_line_no"] == 2
        # B4: urgency = the DONOR's own required date, so the order-back the manual pick
        # raises is dated by the order it is taken from, not by the one taking it.
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
                                "reason": "Authorised by agent CYNDI: urgent site delivery.",
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


def test_a_higher_ranked_donor_of_ANOTHER_agent_is_not_offered_at_all():
    """AC-L6 (section 1c): "a donor sharing the line's sales agent is offered at ANY rank
    ... another agent's order only when ranked below".

    The offer list used to carry every donor in the group. A higher-ranked order belonging
    to somebody else is not this planner's to take - offering it puts a row on the screen
    whose only honest use is to phone another agent and ask, which is not what the dialog
    says it is for.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        mine = _agent(db, f"CYNDI{_uid()[:4]}", location_group=_group)
        theirs = _agent(db, f"JEREMY{_uid()[:4]}", location_group=_group)
        db.commit()

        # Ranked ABOVE this line (due sooner), and somebody else's.
        _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE - timedelta(days=30), line_no=2,
            so_number="SO910001", sales_agent_id=theirs.id,
        )
        # Ranked BELOW this line, and also somebody else's: that one IS offered.
        _seed_line(
            db, company_id, project, product, own, qty_ordered="70",
            required_date=REQUIRED_DATE + timedelta(days=30), line_no=3,
            so_number="SO910002", sales_agent_id=theirs.id,
        )
        order, _line_obj, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO910003",
            sales_agent_id=mine.id,
        )
        db.commit()

        candidates = ProjectSupplyService(db).proposal_for(order)["lines"][0][
            "borrow_candidates"
        ]

    offered = {
        c["donor_so_number"] for c in candidates if c.get("rung") == "group_borrow"
    }
    assert offered == {"SO910002"}


# --------------------------------------------------------------------- rung 4: cross-group


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
        # Offered, never proposed (AC-L3): the planner picks it in Amend.
        assert any(
            c.get("donor_so_number") == "SO500001"
            and c["warehouse_code"] == sibling.warehouse_code
            for c in proposal["lines"][0]["borrow_candidates"]
        )

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
                                "reason": "Authorised by agent CYNDI: urgent site delivery.",
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
    """Nit: within one location, `_group_borrow_donors` must OFFER the LOWEST-ranked
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
        candidates = [
            c
            for c in proposal["lines"][0]["borrow_candidates"]
            if c.get("rung") == "group_borrow"
        ]

    # The order is what matters, not a composition: nothing is auto-composed any more
    # (AC-L3), so "safest first" is a statement about the list a person reads.
    assert candidates
    assert candidates[0]["donor_core_line_id"] == str(far_cline.id)


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


# --------------------------------------------------------- the donor ranking's tie-breaks


def _donor_row(**over):
    """A `_ranked` row with every key the sort reads, so a case states only what it varies."""
    row = {
        "source": "other_location",
        "warehouse_code": "BRW-IB",
        "warehouse_id": "wh-ib",
        "free_qty": "100",
        "available_after_need": "60",
        "available_qty": "80",
        "rank_index": None,
    }
    row.update(over)
    return row


def test_the_queue_position_breaks_a_tie_between_two_donor_lines_at_one_pile():
    """Two donor LINES at one pile agree about the pile, because availability is a fact
    about the pile and not about the line. The safest to take from is the one furthest DOWN
    the ranked queue - not the one holding the most, which is usually the nearest-dated."""
    ranked = ProjectSupplyService._ranked(
        [
            _donor_row(
                warehouse_code="MWH-BB", rung="group_borrow", donor_so_number="SO-NEAR",
                free_qty="90", rank_index=1,
            ),
            _donor_row(
                warehouse_code="MWH-BB", rung="group_borrow", donor_so_number="SO-FAR",
                free_qty="10", rank_index=7,
            ),
        ]
    )

    assert [row["donor_so_number"] for row in ranked] == ["SO-FAR", "SO-NEAR"]
    assert ranked[0]["recommended"] is True


def test_a_donor_lines_queue_position_never_pushes_free_stock_down_the_list():
    """The tie-break is between two ROWS THAT BOTH CARRY ONE. Free stock at a location has
    no queue position - there is no donor line to rank - and a sentinel standing in for the
    absence sorted it behind every group-borrow donor it tied with, which recommended
    somebody else's committed quantity over stock nobody had claimed."""
    ranked = ProjectSupplyService._ranked(
        [
            _donor_row(
                warehouse_code="MWH-BB", rung="group_borrow", donor_so_number="SO-DONOR",
                rank_index=7,
            ),
            _donor_row(warehouse_code="BRW-IB", source="other_location"),
        ]
    )

    assert [row["warehouse_code"] for row in ranked] == ["BRW-IB", "MWH-BB"]
    assert ranked[0]["recommended"] is True
    assert ranked[1]["recommended"] is False


def test_a_donor_project_hold_is_not_pushed_behind_a_donor_line_either():
    """The same absence, the other shape: a hold another PROJECT carries names no
    sales-order line, so it carries no queue position."""
    ranked = ProjectSupplyService._ranked(
        [
            _donor_row(
                warehouse_code="MWH-BB", rung="group_borrow", donor_so_number="SO-DONOR",
                rank_index=7,
            ),
            _donor_row(
                warehouse_code="JB", source="other_project",
                donor_project_ref="PRJ-0052 Seri Emas Phase 2",
            ),
        ]
    )

    assert [row["warehouse_code"] for row in ranked] == ["JB", "MWH-BB"]
    assert ranked[0]["recommended"] is True


def test_availability_still_outranks_the_queue_position():
    """The tie-break is a TIE-break: a donor that keeps more once this line is met still
    wins, whatever either row's queue position says."""
    ranked = ProjectSupplyService._ranked(
        [
            _donor_row(
                warehouse_code="MWH-BB", rung="group_borrow", donor_so_number="SO-DEEP",
                available_after_need="10", rank_index=9,
            ),
            _donor_row(
                warehouse_code="DC1-BB", rung="group_borrow", donor_so_number="SO-ROOMY",
                available_after_need="500", rank_index=2,
            ),
        ]
    )

    assert [row["donor_so_number"] for row in ranked] == ["SO-ROOMY", "SO-DEEP"]


# ------------------------------------ authorising a same-agent borrow (section 1c, AC-L6)


def _same_agent_world(db):
    """This line and a donor line of the SAME agent, the donor ranked ABOVE it.

    Ranked above is the whole point: a donor BELOW this line in the queue is ordinary
    group borrow and needs no special permission. A donor above it is only reachable
    because the agent who owns both orders can say so.
    """
    company_id, eling, project, product = _world(db)
    _group, sites = _group_sites(db)
    own, _pool = sites["BRW"]
    agent = _agent(db, f"CYNDI{_uid()[:4]}", location_group=_group)
    db.commit()

    _donor_order, _dl, _dcso, donor_cline = _seed_line(
        db, company_id, project, product, own, qty_ordered="90",
        required_date=REQUIRED_DATE - timedelta(days=30), line_no=2,
        so_number="SO920001", sales_agent_id=agent.id,
    )
    order, line, _cso, _cline = _seed_line(
        db, company_id, project, product, own, qty_ordered="90",
        required_date=REQUIRED_DATE, line_no=1, so_number="SO920002",
        sales_agent_id=agent.id,
    )
    db.commit()
    return company_id, eling, order, line, donor_cline, own


def _borrow_body(line, warehouse, donor_cline, reason):
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    return ConfirmSupplyBody(
        lines=[
            ConfirmLine(
                project_line_id=line.id,
                borrow=[
                    {
                        "source": "other_location",
                        "warehouse_id": str(warehouse.id),
                        "qty": "90",
                        "reason": reason,
                        "donor_core_line_id": str(donor_cline.id),
                        "donor_so_number": "SO920001",
                        "donor_line_no": 2,
                    }
                ],
            )
        ]
    )


def test_a_same_agent_donor_ranked_above_this_line_is_refused_without_an_authorisation():
    """AC-L6: the donor is offered at any rank BECAUSE the agent can authorise moving stock
    between her own orders - so confirming it has to say she did.

    Judged on the SERVER's own donor list, never on the payload's `same_agent` flag: that
    flag is a client claim, and the rule it gates is a permission.
    """
    with blank_session() as db:
        company_id, eling, order, line, donor_cline, own = _same_agent_world(db)

        with pytest.raises(AppException) as refused:
            ProjectSupplyService(db).confirm(
                order,
                _borrow_body(line, own, donor_cline, "The site is waiting."),
                actor_user_id=eling,
            )

    failing = refused.value.detail["failing_lines"]
    assert len(failing) == 1
    assert failing[0]["reason"] == (
        "SO920001 line 2 shares this line's sales agent and is ranked ahead of it, so it "
        "can only be borrowed with that agent's authorisation. Say who authorised it in "
        "the reason."
    )


def test_the_same_borrow_confirms_once_the_reason_names_who_authorised_it():
    with blank_session() as db:
        company_id, eling, order, line, donor_cline, own = _same_agent_world(db)

        result = ProjectSupplyService(db).confirm(
            order,
            _borrow_body(
                line, own, donor_cline,
                "Authorised by agent CYNDI: agreed on the phone. The site is waiting.",
            ),
            actor_user_id=eling,
        )
        assert result["revision_no"] == 1

        # And it is stored where AC-L6 says: beside the quantity it justifies.
        from app.models.project_so import SOLineAllocation

        rows = (
            db.query(SOLineAllocation)
            .filter(SOLineAllocation.so_line_id == line.id)
            .all()
        )
        assert [r.reason for r in rows] == [
            "Authorised by agent CYNDI: agreed on the phone. The site is waiting."
        ]


def test_another_agents_donor_ranked_below_needs_no_authorisation():
    """The rule is narrow on purpose. A donor BELOW this line in the queue is ordinary
    group borrow - the ladder would have taken it automatically under v2 - so demanding an
    authorisation for it would make a mandatory field a rubber stamp."""
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        mine = _agent(db, f"CYNDI{_uid()[:4]}", location_group=_group)
        theirs = _agent(db, f"JEREMY{_uid()[:4]}", location_group=_group)
        db.commit()

        _donor_order, _dl, _dcso, donor_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=30), line_no=2,
            so_number="SO920001", sales_agent_id=theirs.id,
        )
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO920002",
            sales_agent_id=mine.id,
        )
        db.commit()

        result = ProjectSupplyService(db).confirm(
            order,
            _borrow_body(line, own, donor_cline, "Their hand-over is in December."),
            actor_user_id=eling,
        )
        assert result["revision_no"] == 1


def test_a_same_agent_donor_ranked_BELOW_this_line_needs_no_authorisation_either():
    """Same agent, but the donor is behind this line in the queue: no permission is being
    exercised, so none is demanded."""
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        agent = _agent(db, f"CYNDI{_uid()[:4]}", location_group=_group)
        db.commit()

        _donor_order, _dl, _dcso, donor_cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE + timedelta(days=30), line_no=2,
            so_number="SO920001", sales_agent_id=agent.id,
        )
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="90",
            required_date=REQUIRED_DATE, line_no=1, so_number="SO920002",
            sales_agent_id=agent.id,
        )
        db.commit()

        result = ProjectSupplyService(db).confirm(
            order,
            _borrow_body(line, own, donor_cline, "Her later order can wait a week."),
            actor_user_id=eling,
        )
        assert result["revision_no"] == 1


# --------------------------------------------------------------------------- rung 1


def _shipment(db, *, eta, arrived=None):
    """A booked container. Once one exists the arrival is TRACKED, which is what takes the
    row out of the staleness rule (`spo_supply`)."""
    from app.models.procurement import InboundShipment

    row = InboundShipment(
        id=_uid(),
        shipment_number=f"ZZT-SHIP-{_uid()[:8]}",
        shipment_date=date.today(),
        estimated_arrival_date=eta,
        actual_arrival_date=arrived,
        shipment_status="in_transit",
    )
    db.add(row)
    db.flush()
    return row


def _spo_line(db, product, warehouse, *, qty, arrives, spo_number=None, line_no=1,
              shipment=None):
    """One open SPO line: a shipping order with no container booked, which is what every
    SPO document is until somebody books one (section K, migration 420)."""
    from app.models.procurement import SPOAllocation

    row = SPOAllocation(
        id=_uid(),
        spo_number=spo_number or f"SPO-2026/08-{_uid()[:4]}",
        spo_line_number=line_no,
        product_id=product.id,
        warehouse_id=warehouse.id,
        inbound_shipment_id=shipment.id if shipment is not None else None,
        allocated_quantity=qty,
        quantity_received=0,
        receipt_status="pending",
        line_status="open",
        source_system="scm_spo_history",
        expected_date=arrives,
    )
    db.add(row)
    db.flush()
    return row


def test_an_spo_arriving_before_the_required_date_is_proposed_on_rung_1():
    """AC-K4. The SPO has no shipment and no ETA of its own beyond the line's
    `expected_date`, which is the only date an imported shipping order carries - and the
    thing that made rung 1 unfireable while SPO documents sat in `purchase_orders`."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        spo_number = _spo_line(
            db, product, own, qty=40, arrives=REQUIRED_DATE - timedelta(days=5)
        ).spo_number
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)

    assert [c["kind"] for c in components] == ["timely_spo"]
    assert components[0]["qty"] == "40"
    assert components[0]["rung"] == "incoming"
    assert spo_number in components[0]["reason"]


def test_an_spo_arriving_after_the_required_date_is_not_timely():
    """The other half of the same rule: incoming that lands too late is not cover, and the
    line falls through the ladder to a Buy rather than promising a date it cannot keep."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _spo_line(db, product, own, qty=40, arrives=REQUIRED_DATE + timedelta(days=5))
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["buy"]


def test_a_past_dated_promise_still_fires_rung_1_and_says_it_is_overdue():
    """TRUST THE BOOK (captain, 26 August 2026). The goods are owed until a re-uploaded PO
    and SPO book says they arrived, so an overdue promise is still incoming supply - and it
    is NAMED as overdue, because the buyer reading the trail is the person who can chase it.

    Dropping these rows instead would have told the planner to buy 39,110 units a second
    time: every open SPO line on the captain's book carries a past date today.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        spo_number = _spo_line(
            db, product, own, qty=40, arrives=date.today() - timedelta(days=25)
        ).spo_number
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["timely_spo"]
    assert components[0]["qty"] == "40"
    assert components[0]["rung"] == "incoming"
    assert spo_number in components[0]["reason"]
    assert "(overdue 25 days)" in components[0]["reason"]


def test_a_promise_dated_today_is_not_overdue():
    """The boundary, said out loud on both rules: a row dated today arrives today, so it is
    not overdue, and an arrival on the required date itself is timely. An exclusive
    comparison on either would look like a rounding detail and cost a whole day."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _spo_line(db, product, own, qty=40, arrives=date.today())
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
            required_date=date.today(),
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["timely_spo"]
    assert "overdue" not in components[0]["reason"]


def test_a_fully_received_line_is_not_supply_however_open_its_date_looks():
    """The other half of the rule. What makes a row supply is what is still TO COME on it,
    and a line the book states as received has nothing: it is out, and no date changes
    that."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        row = _spo_line(db, product, own, qty=40, arrives=REQUIRED_DATE - timedelta(days=5))
        row.quantity_received = 40
        row.receipt_status = "fully_received"
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["buy"]


def test_a_shipment_backed_row_reads_its_container_date():
    """Once a container is booked the arrival is tracked, so the ladder reads the
    shipment's date rather than the line's promise."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        shipment = _shipment(db, eta=REQUIRED_DATE - timedelta(days=5))
        _spo_line(db, product, own, qty=40, arrives=date.today() - timedelta(days=400),
                  shipment=shipment)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["timely_spo"]
    assert "overdue" not in components[0]["reason"]
