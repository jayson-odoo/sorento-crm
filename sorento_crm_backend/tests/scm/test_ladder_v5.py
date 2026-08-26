"""Ladder v5: four questions, and SPO is not one of them (`PLAN-scm-cs-planning-uat.md` 1e).

The engine half. `tests/test_ladder_v5_trail.py` is the board half (the proof rows, the
other-group block, staleness); `tests/scm/test_front_planning_golden.py` still owns the
golden numbers.

What v5 changes, and so what is pinned here:

* **AC-V2** incoming is NOT a rung. An SPO is inside the ownership group's net already
  (AutoCount's Available counts it), so a line whose group nets positive only because of an
  SPO is served from the GROUP - question 1 - and the composition carries no `timely_spo`
  component at all. Under v4 the same line was covered by rung 1 and the group rung was
  told the SPO had spent its offer.
* **AC-V7** the pool is walked before another group's stock, and a line that both could
  cover comes off the pool.
* **AC-V6** dealer hot-selling refuses the WHOLE pile, not the line's own site's share of
  it.

Postgres via `blank_session`, every chain seeded here (CI's database has no data).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import priority

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _product,
    _project_line,
    _project_so,
    _sorento,
    _stock,
    _uid,
    _user,
    _warehouse,
)
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _components,
    _group_sites,
    _seed_line,
    _spo_line,
    _world,
)


def _cap(db, name: str, *, max_qty=50, max_pct=10.0):
    priority.create_revision(
        db, name=name, factors={}, demand_class_weights={},
        reorder_coverage_until=None,
        cross_group_borrow_max_qty=max_qty, cross_group_borrow_max_pct=max_pct,
    )
    db.commit()


# --------------------------------------------------------------------------- AC-V2


def test_an_spo_covers_its_line_through_the_group_net_not_through_a_rung_of_its_own():
    """AC-V2. The SPO of 40 at the line's own group location makes the IB group net 0 with
    this line's own 40 netted out, so the group offers the whole 40 - and the answer is
    question 1, `group_take`, not a rung called Incoming.

    Under v4 this same fixture proposed `timely_spo 40`. The quantity is identical; what
    changed is which question answers it, and that is the whole of 1e's first bullet.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _spo_line(db, product, own, qty=40, arrives=REQUIRED_DATE - timedelta(days=5))
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["reserve"], (
        "the SPO is inside the group's net, so the group answers the line"
    )
    assert [c["rung"] for c in components] == ["group_take"]
    assert components[0]["qty"] == "40"
    assert components[0]["source_location"] == own.warehouse_code
    assert "group" in components[0]["reason"]


def test_no_composition_the_engine_writes_carries_an_incoming_component():
    """AC-V2, the general form: whatever the facts, `timely_spo` is a kind the v5 engine
    never proposes. It survives only on frozen snapshots taken under an older ladder."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=5)
        _spo_line(db, product, own, qty=100, arrives=REQUIRED_DATE - timedelta(days=5))
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert "timely_spo" not in [c["kind"] for c in components]


def test_a_line_beyond_the_window_buys_whole_even_when_an_spo_would_cover_it():
    """AC-V2 at rung 0. Incoming was the one rung that ran beyond the lead-time window; with
    no such rung, a far line is a whole-line Buy and purchasing links the SPO on its order
    inquiry row instead."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        far = REQUIRED_DATE + timedelta(days=900)
        _spo_line(db, product, own, qty=40, arrives=far - timedelta(days=5))
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40", required_date=far,
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["buy"]
    assert components[0]["qty"] == "40"


# --------------------------------------------------------------------------- AC-V7


def test_the_pool_is_walked_before_another_group_and_takes_the_whole_line():
    """AC-V7, the captain's own case: 24 needed, the site pools free 268, another group
    holding 100 within the cap. The proposal is Pool 24, never Borrow 24."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=268)
        # Another ownership group at the same site, holding 100 free and within the cap.
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=100)
        _cap(db, f"zzt-v5-order-{_uid()[:6]}")

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="24",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [(c["kind"], c["rung"], c["qty"]) for c in components] == [
        ("reserve", "pool", "24"),
    ]
    assert components[0]["source_location"] == pool.warehouse_code


# --------------------------------------------------------------------------- AC-V6


def test_dealer_hot_selling_refuses_the_whole_pile_not_only_this_site_s_pool():
    """AC-V6. The product is hot-selling at the line's own location; DC1 and MWH pool stock
    is not offered either, because the five pools are one pile and the gate refuses the
    pile."""
    from app.models.scm import ItemClassification

    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, own_pool = sites["BRW"]
        _, dc1_pool = sites["DC1"]
        _, mwh_pool = sites["MWH"]
        _stock(db, product, own_pool, on_hand=0)
        _stock(db, product, dc1_pool, on_hand=500)
        _stock(db, product, mwh_pool, on_hand=500)
        db.add(
            ItemClassification(
                id=_uid(), product_id=product.id, warehouse_id=own.id,
                abc_class_retail="A",
            )
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["buy"], (
        "1000 sits in the pile at DC1 and MWH and none of it is offered"
    )
