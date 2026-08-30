"""Fulfilment priority admin API - PLAN-demo-followups-19aug-ladder-v2.md C1/C2.

    GET /api/v1/scm/policies/fulfilment-priority
    PUT /api/v1/scm/policies/fulfilment-priority

Same fixture family as `test_policy_config.py` (real Postgres, rolled-back savepoint,
`purchasing` role which migration 274 grants `scm.policy.manage`). Three things pinned:

1. The GET answers the seeded ("fair") values migration 385 activated, factor-for-factor.
2. A PUT writes a NEW revision and activates it - the OLD row stays, `is_active=false`, and
   `priority.active_policy()` (what the board itself reads) sees the new weights immediately.
3. Negative weights, and a `tba_date_from` earlier than today, are refused with 422 and
   write nothing (AC-S1-2).
4. `priority.create_revision` turns the race two concurrent PUTs can hit - both trying to
   activate a new revision at once - into a 409 rather than an unhandled `IntegrityError`
   (500) off `uq_scm_priority_policy_one_active`.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.scm import PriorityPolicy
from app.services.error_handler import AppException
from app.services.scm import priority as priority_svc
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

BASE = "/api/v1/scm/policies/fulfilment-priority"


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _write(**overrides) -> dict:
    body = {
        "factors": {
            "po_document_sequence": 1.0,
            "demand_class": 3.0,
            "need_by_date": 3.0,
            "document_age": 1.0,
            "customer_credit": 1.0,
        },
        "demand_class_weights": {"project": 1.0, "retail": 0.4},
        "reorder_coverage_until": "2026-10-31",
        "tba_date_from": "2029-01-01",
    }
    body.update(overrides)
    return body


def _active_row(db) -> dict:
    row = db.execute(
        text(
            "SELECT id, name, is_active, factors, demand_class_weights, "
            "reorder_coverage_until, tba_date_from "
            "FROM scm.priority_policy WHERE is_active = true"
        )
    ).mappings().first()
    assert row, "no active priority_policy row - migration 385 must have run"
    return dict(row)


def test_get_returns_the_seeded_fair_policy(scm_app):
    app, db = _client(scm_app, "purchasing")
    seeded = _active_row(db)
    with TestClient(app) as c:
        got = c.get(BASE)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["exists"] is True
    assert body["name"] == seeded["name"]
    assert body["factors"] == seeded["factors"]
    assert body["demand_class_weights"] == seeded["demand_class_weights"]
    seeded_until = seeded["reorder_coverage_until"]
    assert body["reorder_coverage_until"] == (seeded_until.isoformat() if seeded_until else None)
    assert body["tba_date_from"] == seeded["tba_date_from"].isoformat()
    # The dropped cross-group caps (R5) are gone from the response, not merely ignored:
    # `response_model` would silently keep serving them if the schema still declared them.
    assert "cross_group_borrow_max_qty" not in body
    assert "cross_group_borrow_max_pct" not in body


def test_put_creates_a_revision_and_the_board_sees_it(scm_app):
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(
        text("SELECT count(*) FROM scm.priority_policy")
    ).scalar()

    new_weights = _write(
        factors={
            "po_document_sequence": 2.0,
            "demand_class": 4.0,
            "need_by_date": 5.0,
            "document_age": 0.5,
            "customer_credit": 0.5,
        },
        reorder_coverage_until="2026-11-15",
        tba_date_from="2030-06-30",
    )
    with TestClient(app) as c:
        put = c.put(BASE, json=new_weights)
        assert put.status_code == 200, put.text
        body = put.json()

    assert body["factors"]["need_by_date"] == 5.0
    assert body["reorder_coverage_until"] == "2026-11-15"

    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count + 1  # a NEW row, the old one kept

    active = _active_row(db)
    assert active["factors"]["need_by_date"] == 5.0
    assert active["reorder_coverage_until"] == date(2026, 11, 15)
    assert active["tba_date_from"] == date(2030, 6, 30)

    # The board's own read (`priority.active_policy`) resolves to the same row.
    board_policy = priority_svc.active_policy(db)
    assert str(board_policy.id) == str(active["id"])
    weights, _classes = priority_svc.policy_weights(board_policy)
    assert weights["need_by_date"] == 5.0


def test_put_never_mutates_the_row_it_replaces(scm_app):
    app, db = _client(scm_app, "purchasing")
    before = _active_row(db)

    with TestClient(app) as c:
        c.put(BASE, json=_write(reorder_coverage_until="2026-09-01"))

    old_row = db.execute(
        text(
            "SELECT is_active, reorder_coverage_until FROM scm.priority_policy WHERE id = :id"
        ),
        {"id": before["id"]},
    ).mappings().first()
    assert old_row["is_active"] is False
    # The row this test started with is untouched - the PUT deactivated it, not rewrote it.
    assert old_row["reorder_coverage_until"] == before["reorder_coverage_until"]


def test_negative_factor_weight_is_refused(scm_app):
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()

    with TestClient(app) as c:
        res = c.put(BASE, json=_write(factors={
            "po_document_sequence": 1.0,
            "demand_class": -1.0,
            "need_by_date": 3.0,
            "document_age": 1.0,
            "customer_credit": 1.0,
        }))
    assert res.status_code == 422, res.text
    assert db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar() == before_count


def test_negative_class_weight_is_refused(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.put(BASE, json=_write(demand_class_weights={"project": -0.1, "retail": 0.4}))
    assert res.status_code == 422, res.text


def test_reorder_coverage_until_round_trips_a_date(scm_app):
    """The captain's "purchasing reorders until October" is a calendar date, not a rolling
    day count - a PUT carrying one comes back unchanged on the very next GET."""
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(BASE, json=_write(reorder_coverage_until="2026-10-31"))
        assert put.status_code == 200, put.text
        assert put.json()["reorder_coverage_until"] == "2026-10-31"

        got = c.get(BASE)
    assert got.json()["reorder_coverage_until"] == "2026-10-31"
    active = _active_row(db)
    assert active["reorder_coverage_until"] == date(2026, 10, 31)


def test_reorder_coverage_until_null_clears_it(scm_app):
    """A PUT with no date at all is "no coverage limit", not "keep whatever was there"."""
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        c.put(BASE, json=_write(reorder_coverage_until="2026-10-31"))
        cleared = c.put(BASE, json=_write(reorder_coverage_until=None))
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["reorder_coverage_until"] is None

        got = c.get(BASE)
    assert got.json()["reorder_coverage_until"] is None
    active = _active_row(db)
    assert active["reorder_coverage_until"] is None


def test_tba_date_from_round_trips_and_reaches_the_row(scm_app):
    """AC-S1-2: the PUT accepts it, the GET answers it, and the active row holds it."""
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(BASE, json=_write(tba_date_from="2031-03-01"))
        assert put.status_code == 200, put.text
        assert put.json()["tba_date_from"] == "2031-03-01"

        got = c.get(BASE)
    assert got.json()["tba_date_from"] == "2031-03-01"
    assert _active_row(db)["tba_date_from"] == date(2031, 3, 1)


def test_a_tba_date_in_the_past_is_refused(scm_app):
    """A TBA line dated yesterday turns the WHOLE open book into placeholders - every line
    dated on or after it stops taking supply. Refused with 422, and nothing written."""
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with TestClient(app) as c:
        res = c.put(BASE, json=_write(tba_date_from=yesterday))
    assert res.status_code == 422, res.text
    assert db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar() == before_count


def test_todays_tba_date_is_accepted(scm_app):
    """"Today or later" - the boundary itself is allowed, so the panel's own mirror of the
    rule and the server agree on the day they are both looking at."""
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.put(BASE, json=_write(tba_date_from=date.today().isoformat()))
    assert res.status_code == 200, res.text


def test_a_weight_saves_over_a_stored_tba_date_that_has_since_passed(scm_app):
    """The freshness rule is about a CHANGE, not about the value (fixed 30 Aug).

    A TBA date is legal the day it is saved and historic a year later. Refusing every PUT
    that resubmits it locked the WHOLE panel: no weight, no coverage date, no class weight
    could be saved again until somebody also picked a new TBA date - and the panel sends the
    stored date back with every save, so the block was permanent and had nothing to do with
    the field being edited.
    """
    app, db = _client(scm_app, "purchasing")
    stale = date.today() - timedelta(days=400)
    db.execute(
        text("UPDATE scm.priority_policy SET tba_date_from = :d WHERE is_active = true"),
        {"d": stale},
    )
    db.flush()

    body = _write(tba_date_from=stale.isoformat())
    body["factors"] = {**body["factors"], next(iter(body["factors"])): 7.0}
    with TestClient(app) as c:
        put = c.put(BASE, json=body)
    assert put.status_code == 200, put.text
    assert put.json()["tba_date_from"] == stale.isoformat()
    assert _active_row(db)["tba_date_from"] == stale


def test_moving_the_tba_date_further_into_the_past_is_still_refused(scm_app):
    """The other half: a DIFFERENT past date is the move the rule exists to stop, whatever
    the stored one is."""
    app, db = _client(scm_app, "purchasing")
    stale = date.today() - timedelta(days=400)
    db.execute(
        text("UPDATE scm.priority_policy SET tba_date_from = :d WHERE is_active = true"),
        {"d": stale},
    )
    db.flush()

    with TestClient(app) as c:
        res = c.put(
            BASE,
            json=_write(tba_date_from=(date.today() - timedelta(days=1)).isoformat()),
        )
    assert res.status_code == 422, res.text
    assert _active_row(db)["tba_date_from"] == stale


def test_a_stored_tba_date_in_the_past_still_reads_200(scm_app):
    """The freshness rule belongs to the WRITE body, never to the response.

    A date that was legal the day it was saved is in the past a year later, and the row is
    still the active policy. `FulfilmentPriorityPolicy` inheriting the write validator made
    every GET 500 on its own stored value from the day the date passed - the screen went
    down without a single row changing.
    """
    app, db = _client(scm_app, "purchasing")
    # Written straight onto the row: the PUT itself would (correctly) refuse this date.
    db.execute(
        text(
            "UPDATE scm.priority_policy SET tba_date_from = :d WHERE is_active = true"
        ),
        {"d": date(2020, 1, 1)},
    )
    db.flush()

    with TestClient(app) as c:
        got = c.get(BASE)
        assert got.status_code == 200, got.text
        assert got.json()["tba_date_from"] == "2020-01-01"

        # And the panel can still save a fresh date over it.
        future = (date.today() + timedelta(days=30)).isoformat()
        put = c.put(BASE, json=_write(tba_date_from=future))
    assert put.status_code == 200, put.text
    assert put.json()["tba_date_from"] == future
    assert _active_row(db)["tba_date_from"] == date.today() + timedelta(days=30)


def test_a_put_that_omits_the_tba_date_keeps_the_active_value(scm_app):
    """An older bundle, a script or an n8n call that predates the field saves the weights
    it means to save and moves nothing else. Defaulting the body to 2029-01-01 instead let
    such a writer silently reset a configured TBA line while editing a weight."""
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        c.put(BASE, json=_write(tba_date_from="2031-03-01"))

        body = _write()
        body.pop("tba_date_from")
        put = c.put(BASE, json=body)
        assert put.status_code == 200, put.text
        assert put.json()["tba_date_from"] == "2031-03-01"

        got = c.get(BASE)
    assert got.json()["tba_date_from"] == "2031-03-01"
    assert _active_row(db)["tba_date_from"] == date(2031, 3, 1)


def test_rbac_denied_without_manage(scm_app):
    app, _db = _client(scm_app, None)  # bare user, no scm.policy.manage
    with TestClient(app) as c:
        assert c.get(BASE).status_code == 403
        assert c.put(BASE, json=_write()).status_code == 403


def test_a_uniqueness_conflict_on_activation_is_a_409_not_a_500(scm_app):
    """`create_revision` wraps its own INSERT in a savepoint precisely so a collision on
    `uq_scm_priority_policy_one_active` - what two concurrent PUTs racing past the FOR
    UPDATE lock would produce - surfaces as an AppException 409, not a bare
    `IntegrityError` bubbling up as a 500. Simulated by making the flush itself raise,
    the same shape a real unique-index refusal takes at that call site.
    """
    app, db = _client(scm_app, "purchasing")
    before_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()

    real_flush = db.flush

    def _boom_only_for_the_new_revision(*args, **kwargs):
        # `Session.begin_nested()` itself flushes (to take its snapshot) before
        # `create_revision` ever adds the new row, and that call must stay a real,
        # harmless no-op flush - only the flush that actually has the new
        # `PriorityPolicy` pending should look like the unique-index refusal.
        if any(isinstance(obj, PriorityPolicy) for obj in db.new):
            raise IntegrityError(
                "INSERT INTO scm.priority_policy ...",
                {},
                Exception(
                    'duplicate key value violates unique constraint '
                    '"uq_scm_priority_policy_one_active"'
                ),
            )
        return real_flush(*args, **kwargs)

    db.flush = _boom_only_for_the_new_revision
    try:
        with pytest.raises(AppException) as excinfo:
            priority_svc.create_revision(
                db,
                name="ZZT conflict test",
                factors={"po_document_sequence": 1.0},
                demand_class_weights={},
                reorder_coverage_until=None,
                tba_date_from=date(2029, 1, 1),
            )
    finally:
        db.flush = real_flush

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "scm_priority_policy_conflict"

    # No orphan row was inserted - the savepoint around the INSERT rolled that part
    # back, which is exactly what stops a 409 from also leaving a stray policy row
    # nobody activated.
    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count
