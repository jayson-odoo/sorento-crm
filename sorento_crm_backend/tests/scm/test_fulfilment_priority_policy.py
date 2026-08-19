"""Fulfilment priority admin API - PLAN-demo-followups-19aug-ladder-v2.md C1/C2.

    GET /api/v1/scm/policies/fulfilment-priority
    PUT /api/v1/scm/policies/fulfilment-priority

Same fixture family as `test_policy_config.py` (real Postgres, rolled-back savepoint,
`purchasing` role which migration 274 grants `scm.policy.manage`). Three things pinned:

1. The GET answers the seeded ("fair") values migration 385 activated, factor-for-factor.
2. A PUT writes a NEW revision and activates it - the OLD row stays, `is_active=false`, and
   `priority.active_policy()` (what the board itself reads) sees the new weights immediately.
3. Negative weights, and the ladder-v2 settings outside their bounds, are refused with 422 and
   write nothing.
4. `priority.create_revision` turns the race two concurrent PUTs can hit - both trying to
   activate a new revision at once - into a 409 rather than an unhandled `IntegrityError`
   (500) off `uq_scm_priority_policy_one_active`.
"""
from __future__ import annotations

from datetime import date

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
        "cross_group_borrow_max_qty": 50,
        "cross_group_borrow_max_pct": 10.0,
    }
    body.update(overrides)
    return body


def _active_row(db) -> dict:
    row = db.execute(
        text(
            "SELECT id, name, is_active, factors, demand_class_weights, "
            "reorder_coverage_until, cross_group_borrow_max_qty, cross_group_borrow_max_pct "
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
    assert body["cross_group_borrow_max_qty"] == seeded["cross_group_borrow_max_qty"]
    assert float(body["cross_group_borrow_max_pct"]) == float(
        seeded["cross_group_borrow_max_pct"]
    )


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
        cross_group_borrow_max_qty=25,
        cross_group_borrow_max_pct=5.0,
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
    assert active["cross_group_borrow_max_qty"] == 25

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


def test_cross_group_borrow_qty_must_not_be_negative(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        assert c.put(BASE, json=_write(cross_group_borrow_max_qty=-1)).status_code == 422


def test_cross_group_borrow_pct_must_be_in_0_100(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        assert c.put(BASE, json=_write(cross_group_borrow_max_pct=150)).status_code == 422
        assert c.put(BASE, json=_write(cross_group_borrow_max_pct=-1)).status_code == 422


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
                cross_group_borrow_max_qty=50,
                cross_group_borrow_max_pct=10.0,
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
