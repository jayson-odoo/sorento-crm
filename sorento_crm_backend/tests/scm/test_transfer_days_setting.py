"""`transfer_days` becomes a fulfilment-priority setting, default 0 (31 Aug ruling, R-B).

`documentation/plans/scm/PLAN-scm-planning-feedback-31aug.md` S2,
`scm-planning-feedback-31aug-acceptance-criteria.md` AC-2.1..2.4. Written BEFORE the fix, as
PRINCIPLES step 4 requires.

`front_planning_engine.TRANSFER_DAYS` was a literal `= 2`, charged on any option whose
stock is not already at the asking line's own bin - the captain's "02/09-for-a-31/08-plan"
row (pool bin BRW vs own bin BRW-IB) with no way to turn it off. The setting lives beside
`tba_date_from` / `reorder_coverage_until` on `scm.priority_policy` (migration 451):

* AC-2.1/2.2 are engine-level, `blank_session` (Postgres schema-translated scratch, every
  chain seeded here) - the same substrate `test_ladder_v7_borrow.py` uses.
* AC-2.3 is the `PUT/GET /scm/policies/fulfilment-priority` route, the real Postgres
  savepoint fixture `test_fulfilment_priority_policy.py` already uses - helpers imported
  from there so the two files cannot come to disagree about what a write body looks like.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

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
from .conftest import requires_pg
from .test_fulfilment_priority_policy import BASE, _active_row, _client, _write
from .test_ladder_v7_borrow import LEAD_DAYS, _options
from .test_project_supply_service_ladder import (
    _group_sites,
    _lead_time,
    _seed_line,
    _world,
)


def _pool_option(proposal):
    return next(option for option in _options(proposal) if option["step"] == "pool")


def _use_option(proposal):
    return next(option for option in _options(proposal) if option["step"] == "use")


# --------------------------------------------------------------------------- AC-2.1


def test_no_policy_row_charges_no_transfer_between_bins():
    """AC-2.1, first half: with no policy row at all, `transfer_days` reads 0 and a
    pool-take option's fulfilled date equals `as_of` - the same as an own-location take."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=15)
        _lead_time(db, product, LEAD_DAYS)
        # No `priority.create_revision` call at all - a policy-less database.

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="15",
            required_date=date.today(),
        )
        proposal = ProjectSupplyService(db).proposal_for(order)

    pool_option = _pool_option(proposal)
    assert pool_option["whole"] is True
    assert pool_option["fulfil_date"] == date.today().isoformat()
    assert pool_option["days_late"] == 0


def test_a_policy_row_with_no_transfer_days_set_also_charges_nothing():
    """AC-2.1, second half: a policy row that predates the migration (created here with no
    `transfer_days` argument, so it takes the column's own default) reads the same 0."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=15)
        _lead_time(db, product, LEAD_DAYS)
        priority.create_revision(
            db, name=f"zzt-transfer-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="15",
            required_date=date.today(),
        )
        proposal = ProjectSupplyService(db).proposal_for(order)

    pool_option = _pool_option(proposal)
    assert pool_option["fulfil_date"] == date.today().isoformat()
    assert pool_option["days_late"] == 0


# --------------------------------------------------------------------------- AC-2.2


def test_a_configured_transfer_charge_moves_the_non_own_location_option_out():
    """AC-2.2, first half: `transfer_days=2` saved on the policy pushes a non-own-location
    option's fulfilled date to `as_of + 2`, and `days_late` follows it."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=15)
        _lead_time(db, product, LEAD_DAYS)
        priority.create_revision(
            db, name=f"zzt-transfer-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None, transfer_days=2,
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="15",
            required_date=date.today(),
        )
        proposal = ProjectSupplyService(db).proposal_for(order)

    pool_option = _pool_option(proposal)
    expected = date.today() + timedelta(days=2)
    assert pool_option["whole"] is True
    assert pool_option["fulfil_date"] == expected.isoformat()
    assert pool_option["days_late"] == 2


def test_an_own_location_option_is_never_charged_a_transfer():
    """AC-2.2, second half: the SAME `transfer_days=2` policy leaves an own-location option
    at `as_of` - the charge is about the BIN, not a blanket delay on every option."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _stock(db, product, own, on_hand=15)
        _lead_time(db, product, LEAD_DAYS)
        priority.create_revision(
            db, name=f"zzt-transfer-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None, transfer_days=2,
        )
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="15",
            required_date=date.today(),
        )
        proposal = ProjectSupplyService(db).proposal_for(order)

    use_option = _use_option(proposal)
    assert use_option["whole"] is True
    assert use_option["fulfil_date"] == date.today().isoformat()
    assert use_option["days_late"] == 0


# --------------------------------------------------------------------------- AC-2.4


def test_changing_the_setting_after_a_confirm_does_not_touch_the_stored_decision():
    """AC-2.4: a settings change only ever reaches the NEXT walk. A line confirmed while
    `transfer_days` was 0 keeps the exact component it was confirmed with once the policy
    is changed to 2 - the frozen decision is not re-derived."""
    with blank_session() as db:
        from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=15)
        _lead_time(db, product, LEAD_DAYS)
        priority.create_revision(
            db, name=f"zzt-transfer-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None, transfer_days=0,
        )
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="15",
            required_date=date.today(),
        )
        service = ProjectSupplyService(db)
        service.confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=str(line.id),
                        reserve=[{"warehouse_id": str(pool.id), "qty": "15"}],
                    )
                ]
            ),
            actor_user_id=eling,
        )
        db.commit()
        before = service.active_decision(str(order.id))
        before_snapshot = list(before.line_snapshots or [])

        # The setting changes AFTER the confirm.
        priority.create_revision(
            db, name=f"zzt-transfer-changed-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None, transfer_days=2,
        )
        db.commit()

        after = ProjectSupplyService(db).active_decision(str(order.id))
        after_snapshot = list(after.line_snapshots or [])

    assert after.id == before.id, "no new decision was written by the setting change alone"
    assert after_snapshot == before_snapshot, (
        "the frozen decision is untouched - only the NEXT walk sees the new setting"
    )


# --------------------------------------------------------------------------- AC-2.3


@requires_pg
def test_transfer_days_round_trips_through_the_settings_route(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(BASE, json=_write(transfer_days=3))
        assert put.status_code == 200, put.text
        assert put.json()["transfer_days"] == 3

        got = c.get(BASE)
    assert got.json()["transfer_days"] == 3
    active_id = _active_row(db)["id"]
    on_the_row = db.execute(
        text("SELECT transfer_days FROM scm.priority_policy WHERE id = :id"),
        {"id": active_id},
    ).scalar()
    assert on_the_row == 3, "the active row's own column, not just the response"


@requires_pg
def test_get_states_transfer_days_even_when_the_write_body_omits_it(scm_app):
    """`response_model` silently drops an undeclared field - the field is asserted present
    on a bare GET, not only right after a PUT that named it."""
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        got = c.get(BASE)
    assert got.status_code == 200, got.text
    assert "transfer_days" in got.json()
    assert isinstance(got.json()["transfer_days"], int)


@requires_pg
def test_a_put_that_omits_transfer_days_keeps_the_active_value(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        c.put(BASE, json=_write(transfer_days=4))

        body = _write()
        body.pop("transfer_days", None)
        put = c.put(BASE, json=body)
        assert put.status_code == 200, put.text
        assert put.json()["transfer_days"] == 4

        got = c.get(BASE)
    assert got.json()["transfer_days"] == 4


@requires_pg
def test_negative_transfer_days_is_refused_with_the_coded_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()

    with TestClient(app) as c:
        res = c.put(BASE, json=_write(transfer_days=-1))
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "transfer_days_negative"
    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count, "nothing was written on a refused negative value"
