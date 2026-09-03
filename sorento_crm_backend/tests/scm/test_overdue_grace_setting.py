"""`overdue_grace_days` / `overdue_dead_days` become fulfilment-priority settings.

S4 of `PLAN-scm-pool-chain-first.md`, ruling R-O (#586); AC-O.5 in
`documentation/plans/scm/scm-pool-chain-first-acceptance-criteria.md`. Written BEFORE the
wiring, as PRINCIPLES step 4 requires.

The two numbers join `scm.priority_policy` beside `immediate_window_days` (migration 460) -
the SAME row `app.services.scm.priority` already reads for `tba_date_from` /
`reorder_coverage_until` / `transfer_days`, no new table:

* `overdue_grace_days` (int, 0-365, default 14) - a document whose arrival has passed with
  nothing received counts as supply landing `today + this`.
* `overdue_dead_days` (int, 0-365, default 90) - past this much lateness it counts as
  nothing at all, which is R31 kept for the dead.

The same shape and the same real-Postgres savepoint fixture
`test_fulfilment_immediate_share_setting.py` uses, because it is the same contract one
ruling later.
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


# --------------------------------------------------------------------------- AC-O.5 (unit)


def test_fulfilment_settings_defaults_with_no_policy_row():
    """A database that has never activated a policy reads the documented defaults - 14 /
    90 - never a guessed number."""
    settings = priority.fulfilment_settings(None)
    assert settings["overdue_grace_days"] == 14
    assert settings["overdue_dead_days"] == 90


def test_fulfilment_settings_defaults_on_a_policy_created_with_neither_argument():
    """A policy row created the way a pre-R-O caller of `create_revision` would create it
    takes the column's own default - 14 / 90, never None."""
    with blank_session() as db:
        row = priority.create_revision(
            db, name=f"zzt-grace-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
        )
        db.commit()
        settings = priority.fulfilment_settings(row)
    assert settings["overdue_grace_days"] == 14
    assert settings["overdue_dead_days"] == 90


def test_fulfilment_settings_reads_a_configured_policy_row():
    with blank_session() as db:
        row = priority.create_revision(
            db, name=f"zzt-grace-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
            overdue_grace_days=21, overdue_dead_days=60,
        )
        db.commit()
        settings = priority.fulfilment_settings(row)
    assert settings["overdue_grace_days"] == 21
    assert settings["overdue_dead_days"] == 60


def test_create_revision_writes_both_columns_on_the_row():
    with blank_session() as db:
        row = priority.create_revision(
            db, name=f"zzt-grace-{_uid()[:6]}", factors={},
            demand_class_weights={}, reorder_coverage_until=None,
            overdue_grace_days=0, overdue_dead_days=0,
        )
        db.commit()
        db.expire(row)
        # Through the ORM, so `blank_session`'s schema translation applies - a raw text()
        # naming `scm.priority_policy` would read the real (empty) schema.
        reloaded = db.get(type(row), row.id)
    # 0 is valid for both: no grace at all, and every late document dead on the day.
    assert reloaded.overdue_grace_days == 0
    assert reloaded.overdue_dead_days == 0


# --------------------------------------------------------------------------- AC-O.5 (route)


@requires_pg
def test_the_two_grace_fields_round_trip_through_the_settings_route(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(BASE, json=_write(overdue_grace_days=21, overdue_dead_days=60))
        assert put.status_code == 200, put.text
        assert put.json()["overdue_grace_days"] == 21
        assert put.json()["overdue_dead_days"] == 60

        got = c.get(BASE)
    assert got.json()["overdue_grace_days"] == 21
    assert got.json()["overdue_dead_days"] == 60
    active_id = _active_row(db)["id"]
    row = db.execute(
        text(
            "SELECT overdue_grace_days, overdue_dead_days FROM scm.priority_policy "
            "WHERE id = :id"
        ),
        {"id": active_id},
    ).mappings().first()
    assert row["overdue_grace_days"] == 21, "the active row's own column, not just the response"
    assert row["overdue_dead_days"] == 60


@requires_pg
def test_get_states_both_fields_even_when_the_write_body_omits_them(scm_app):
    """`response_model` silently drops an undeclared field, so both are asserted present
    on a bare GET and not only right after a PUT that named them."""
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        got = c.get(BASE)
    assert got.status_code == 200, got.text
    assert "overdue_grace_days" in got.json()
    assert "overdue_dead_days" in got.json()
    assert isinstance(got.json()["overdue_grace_days"], int)
    assert isinstance(got.json()["overdue_dead_days"], int)


@requires_pg
def test_a_put_that_omits_the_grace_fields_keeps_the_active_values(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        c.put(BASE, json=_write(overdue_grace_days=21, overdue_dead_days=60))

        body = _write()
        body.pop("overdue_grace_days", None)
        body.pop("overdue_dead_days", None)
        put = c.put(BASE, json=body)
        assert put.status_code == 200, put.text
        assert put.json()["overdue_grace_days"] == 21
        assert put.json()["overdue_dead_days"] == 60

        got = c.get(BASE)
    assert got.json()["overdue_grace_days"] == 21
    assert got.json()["overdue_dead_days"] == 60


@requires_pg
def test_overdue_grace_days_above_365_is_refused_with_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()

    with TestClient(app) as c:
        res = c.put(BASE, json=_write(overdue_grace_days=366))
    assert res.status_code == 422, res.text
    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count, "nothing was written on a refused out-of-range value"


@requires_pg
def test_overdue_dead_days_negative_is_refused_with_422(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.put(BASE, json=_write(overdue_dead_days=-1))
    assert res.status_code == 422, res.text
