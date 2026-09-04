"""`immediate_window_days` / `pool_share_pct` become fulfilment-priority settings.

S1 of `PLAN-scm-fulfilment-feedback-2sep.md`, ruling R-B. `documentation/plans/scm/
scm-fulfilment-feedback-2sep-acceptance-criteria.md` AC-1.1, AC-1.2. Written BEFORE the
fix, as PRINCIPLES step 4 requires.

The two numbers join `scm.priority_policy` beside `transfer_days` (migration 452) - the
SAME row `app.services.scm.priority` already reads for `tba_date_from` /
`reorder_coverage_until` / `transfer_days`, no new table:

* `immediate_window_days` (int, 0-365, default 30) - how many days out a line counts as
  "immediate" for the pool's share step.
* `pool_share_pct` (int, 0-100, default 50) - percent of the site pool's free pile kept
  back for dealers before a project line may take a share.

S1 is settings storage only - the engine wiring (S2) reads these two through
`fulfilment_settings()` but does not exist yet, so this file pins the STORAGE contract:
`priority.fulfilment_settings()` defaults and round trip (unit, `blank_session`), and the
`GET/PUT /scm/policies/fulfilment-priority` route (AC-1.1 round trip, AC-1.2 out-of-range
422 and 0-is-valid), the same real-Postgres savepoint fixture
`test_fulfilment_priority_policy.py` already uses.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import priority

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import _uid
from .conftest import requires_pg
from .test_fulfilment_priority_policy import BASE, _active_row, _client, _write

pytestmark = requires_pg


# --------------------------------------------------------------------------- AC-1.1 (unit)


def test_fulfilment_settings_defaults_with_no_policy_row():
    """A database that has never activated a policy reads the documented defaults - 30 /
    50 - the same "no guessed number" contract `transfer_days` already has."""
    settings = priority.fulfilment_settings(None)
    assert settings["immediate_window_days"] == 30
    assert settings["pool_share_pct"] == 50


def test_fulfilment_settings_defaults_on_a_policy_created_with_neither_argument():
    """A policy row created with no `immediate_window_days` / `pool_share_pct` argument
    (the same shape a pre-S1 caller of `create_revision` would use) takes the column's own
    default - 30 / 50, never None and never a guess."""
    with blank_session() as db:
        row = priority.create_revision(
            db, name=f"zzt-share-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
        )
        db.commit()
        settings = priority.fulfilment_settings(row)
    assert settings["immediate_window_days"] == 30
    assert settings["pool_share_pct"] == 50


def test_fulfilment_settings_reads_a_configured_policy_row():
    with blank_session() as db:
        row = priority.create_revision(
            db, name=f"zzt-share-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
            immediate_window_days=45, pool_share_pct=40,
        )
        db.commit()
        settings = priority.fulfilment_settings(row)
    assert settings["immediate_window_days"] == 45
    assert settings["pool_share_pct"] == 40


def test_create_revision_writes_both_columns_on_the_row():
    with blank_session() as db:
        row = priority.create_revision(
            db, name=f"zzt-share-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
            immediate_window_days=0, pool_share_pct=0,
        )
        db.commit()
        db.expire(row)
        # `blank_session` schema-translates ORM/Table constructs, not a raw text() query
        # naming "scm.priority_policy" explicitly - that bypasses the translation and
        # would read the real (empty) scm schema, so the reload goes through the ORM.
        reloaded = db.get(type(row), row.id)
    # AC-1.2: 0 is valid for both - 0 % never gives a share, 0 days = nothing is immediate.
    assert reloaded.immediate_window_days == 0
    assert reloaded.pool_share_pct == 0


# --------------------------------------------------------------------------- AC-1.1 (route)


@requires_pg
def test_immediate_window_and_pool_share_round_trip_through_the_settings_route(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(BASE, json=_write(immediate_window_days=45, pool_share_pct=40))
        assert put.status_code == 200, put.text
        assert put.json()["immediate_window_days"] == 45
        assert put.json()["pool_share_pct"] == 40

        got = c.get(BASE)
    assert got.json()["immediate_window_days"] == 45
    assert got.json()["pool_share_pct"] == 40
    active_id = _active_row(db)["id"]
    row = db.execute(
        text(
            "SELECT immediate_window_days, pool_share_pct FROM scm.priority_policy "
            "WHERE id = :id"
        ),
        {"id": active_id},
    ).mappings().first()
    assert row["immediate_window_days"] == 45, "the active row's own column, not just the response"
    assert row["pool_share_pct"] == 40


@requires_pg
def test_get_states_both_fields_even_when_the_write_body_omits_them(scm_app):
    """`response_model` silently drops an undeclared field - both fields are asserted
    present on a bare GET, not only right after a PUT that named them."""
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        got = c.get(BASE)
    assert got.status_code == 200, got.text
    assert "immediate_window_days" in got.json()
    assert "pool_share_pct" in got.json()
    assert isinstance(got.json()["immediate_window_days"], int)
    assert isinstance(got.json()["pool_share_pct"], int)


@requires_pg
def test_a_put_that_omits_immediate_window_days_keeps_the_active_value(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        c.put(BASE, json=_write(immediate_window_days=45))

        body = _write()
        body.pop("immediate_window_days", None)
        put = c.put(BASE, json=body)
        assert put.status_code == 200, put.text
        assert put.json()["immediate_window_days"] == 45

        got = c.get(BASE)
    assert got.json()["immediate_window_days"] == 45


@requires_pg
def test_a_put_that_omits_pool_share_pct_keeps_the_active_value(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        c.put(BASE, json=_write(pool_share_pct=40))

        body = _write()
        body.pop("pool_share_pct", None)
        put = c.put(BASE, json=body)
        assert put.status_code == 200, put.text
        assert put.json()["pool_share_pct"] == 40

        got = c.get(BASE)
    assert got.json()["pool_share_pct"] == 40


@requires_pg
def test_zero_is_valid_for_both_fields(scm_app):
    """AC-1.2: 0 % = the pool never gives a share, 0 days = nothing is immediate - both
    are legal values, never refused as out of range."""
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(BASE, json=_write(immediate_window_days=0, pool_share_pct=0))
    assert put.status_code == 200, put.text
    assert put.json()["immediate_window_days"] == 0
    assert put.json()["pool_share_pct"] == 0
    active = _active_row(db)
    assert active is not None


# --------------------------------------------------------------------------- AC-1.2


@requires_pg
def test_immediate_window_days_above_365_is_refused_with_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()

    with TestClient(app) as c:
        res = c.put(BASE, json=_write(immediate_window_days=366))
    assert res.status_code == 422, res.text
    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count, "nothing was written on a refused out-of-range value"


@requires_pg
def test_immediate_window_days_negative_is_refused_with_422(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.put(BASE, json=_write(immediate_window_days=-1))
    assert res.status_code == 422, res.text


@requires_pg
def test_pool_share_pct_above_100_is_refused_with_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()

    with TestClient(app) as c:
        res = c.put(BASE, json=_write(pool_share_pct=101))
    assert res.status_code == 422, res.text
    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count, "nothing was written on a refused out-of-range value"


@requires_pg
def test_pool_share_pct_negative_is_refused_with_422(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.put(BASE, json=_write(pool_share_pct=-1))
    assert res.status_code == 422, res.text
