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
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

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
        "buy_all_horizon_days": 180,
        "cross_group_borrow_max_qty": 50,
        "cross_group_borrow_max_pct": 10.0,
    }
    body.update(overrides)
    return body


def _active_row(db) -> dict:
    row = db.execute(
        text(
            "SELECT id, name, is_active, factors, demand_class_weights, "
            "buy_all_horizon_days, cross_group_borrow_max_qty, cross_group_borrow_max_pct "
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
    assert body["buy_all_horizon_days"] == seeded["buy_all_horizon_days"]
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
        buy_all_horizon_days=90,
        cross_group_borrow_max_qty=25,
        cross_group_borrow_max_pct=5.0,
    )
    with TestClient(app) as c:
        put = c.put(BASE, json=new_weights)
        assert put.status_code == 200, put.text
        body = put.json()

    assert body["factors"]["need_by_date"] == 5.0
    assert body["buy_all_horizon_days"] == 90

    after_count = db.execute(text("SELECT count(*) FROM scm.priority_policy")).scalar()
    assert after_count == before_count + 1  # a NEW row, the old one kept

    active = _active_row(db)
    assert active["factors"]["need_by_date"] == 5.0
    assert active["buy_all_horizon_days"] == 90
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
        c.put(BASE, json=_write(buy_all_horizon_days=30))

    old_row = db.execute(
        text(
            "SELECT is_active, buy_all_horizon_days FROM scm.priority_policy WHERE id = :id"
        ),
        {"id": before["id"]},
    ).mappings().first()
    assert old_row["is_active"] is False
    # The row this test started with is untouched - the PUT deactivated it, not rewrote it.
    assert old_row["buy_all_horizon_days"] == before["buy_all_horizon_days"]


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


def test_horizon_must_be_positive(scm_app):
    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        assert c.put(BASE, json=_write(buy_all_horizon_days=0)).status_code == 422


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
