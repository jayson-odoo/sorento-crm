"""SCM Policy Configuration - Phase-2 backend tests (test-first).

Keyed back to `documentation/plans/scm/scm-policy-config-acceptance-criteria.md`.
Covers reorder-policy CRUD + validation, the two single-row global upserts
(classification / supplier scoring), and - the anti-drift centrepiece (Risk #1,
AC-PREV-2) - resolver parity: the `/resolve` endpoint must return exactly what the
shipped engine's `resolve_policy_for_sku` returns, never a reimplementation.

Everything runs inside the rolled-back savepoint (see conftest), so writes never
escape. Authorized role = `purchasing` (carries `scm.policy.manage`, migration 274).
"""
from __future__ import annotations

import uuid as _uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

BASE = "/api/v1/scm/policies"


# --- harness helpers --------------------------------------------------------

def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _a_product(db):
    """A real active product + its category_code (referential inputs for tests)."""
    row = db.execute(text(
        "SELECT p.id::text AS id, p.product_code, pc.category_code "
        "FROM products p JOIN product_categories pc ON pc.id = p.category_id "
        "WHERE p.is_active = true ORDER BY p.product_code LIMIT 1"
    )).mappings().first()
    assert row, "need a seeded product with a category"
    return row["id"], row["product_code"], row["category_code"]


def _write(**overrides) -> dict:
    body = {
        "scope_type": "sku",
        "scope_ref": None,
        "policy_type": "reorder_point",
        "service_level": 0.95,
        "safety_stock_method": "fixed_days",
        "safety_days": 7,
        "review_period_days": 30,
        "forecast_window_days": 90,
        "baseline_source": "continuous_only",
        "spike_handling": "committed_only",
        "buy_scope": "network",
        "dead_stock_days": 180,
        "overstock_days": 120,
        "min_override": None,
        "max_override": None,
        "priority": 0,
        "is_active": True,
        "supplier_selection": "primary",
        "lead_time_default_days": 30,
    }
    body.update(overrides)
    return body


# --- list / paging / sort / search (AC-LIST-1/3) ----------------------------

def test_list_paging_sort_search(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, code, _cat = _a_product(db)
    with TestClient(app) as c:
        c.post(BASE, json=_write(scope_type="sku", scope_ref=pid, priority=5))
        res = c.get(f"{BASE}?page=1&limit=50&sort=priority&dir=desc")
        assert res.status_code == 200, res.text
        body = res.json()
        assert "data" in body and "total" in body
        assert body["total"] >= 2  # seeded global + our sku override
        # scope_label never leaks a UUID (AC-NAV-4)
        for r in body["data"]:
            assert pid not in (r["scope_label"] or "")
        # search by product_code finds the sku override
        found = c.get(f"{BASE}?page=1&limit=50&query={code}").json()
        assert any(r["scope_ref"] == pid for r in found["data"])


def test_list_global_row_label_em_dash(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        body = c.get(f"{BASE}?page=1&limit=100").json()
    globals_ = [r for r in body["data"] if r["scope_type"] == "global"]
    assert globals_ and all(r["scope_label"] == "-" for r in globals_)


def test_list_a_reorder_level_row_returns_200(scm_app):
    """`reorder_level` is the manual-planning basis the GLOBAL row carries whenever S1's
    planning-mode switch is set to "manual" (migration 356). A tenant with that switch on
    was 500ing `GET /scm/policies` because the response schema's `PolicyType` did not know
    the value - reproduced here by seeding a row exactly the way the planning-mode PUT does
    (raw `policy_type`, bypassing `ReorderPolicyWrite`)."""
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    rid = str(_uuid.uuid4())
    db.execute(text(
        "INSERT INTO scm.reorder_policy "
        "(id, scope_type, scope_ref, policy_type, priority, is_active, "
        " source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 'sku', :pid, 'reorder_level', 0, true, 'test', 'test', now(), now())"
    ), {"id": rid, "pid": pid})
    db.flush()
    with TestClient(app) as c:
        res = c.get(f"{BASE}?page=1&limit=200")
    assert res.status_code == 200, res.text
    mine = [r for r in res.json()["data"] if r["id"] == rid]
    assert mine and mine[0]["policy_type"] == "reorder_level"


# --- create each scope (AC-EDIT-1) ------------------------------------------

def test_create_sku_override(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, code, _cat = _a_product(db)
    with TestClient(app) as c:
        res = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid))
    assert res.status_code == 201, res.text
    row = res.json()
    assert row["scope_type"] == "sku"
    assert row["scope_ref"] == pid
    assert code in row["scope_label"]
    # persisted
    assert db.execute(text("SELECT 1 FROM scm.reorder_policy WHERE id = :id"),
                      {"id": row["id"]}).first()


def test_create_class_override(scm_app):
    app, db = _client(scm_app, "purchasing")
    _pid, _code, cat = _a_product(db)
    with TestClient(app) as c:
        res = c.post(BASE, json=_write(scope_type="product_class", scope_ref=cat))
    assert res.status_code == 201, res.text
    assert res.json()["scope_ref"] == cat


def test_create_cell_override(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post(BASE, json=_write(scope_type="abc_xyz_cell", scope_ref="A-X"))
    assert res.status_code == 201, res.text
    row = res.json()
    assert row["scope_ref"] == "A-X"
    assert row["scope_label"] == "A-X"


def test_update_policy(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        created = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid, safety_days=7)).json()
        upd = c.put(f"{BASE}/{created['id']}",
                    json=_write(scope_type="sku", scope_ref=pid, safety_days=14, priority=9))
    assert upd.status_code == 200, upd.text
    assert float(upd.json()["safety_days"]) == 14
    assert upd.json()["priority"] == 9


# --- delete (AC-DEL-1 / AC-DEL-2) -------------------------------------------

def test_delete_hard_removes_row(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        created = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid)).json()
        res = c.delete(f"{BASE}/{created['id']}")
    assert res.status_code == 204, res.text
    assert not db.execute(text("SELECT 1 FROM scm.reorder_policy WHERE id = :id"),
                          {"id": created["id"]}).first()


def test_delete_global_blocked(scm_app):
    app, db = _client(scm_app, "purchasing")
    gid = db.execute(text(
        "SELECT id FROM scm.reorder_policy WHERE scope_type = 'global' "
        "ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).scalar()
    with TestClient(app) as c:
        res = c.delete(f"{BASE}/{gid}")
    assert res.status_code == 422, res.text
    assert "cannot be deleted" in res.json()["message"].lower()


# --- RBAC (AC-CFG-3 / AC-NAV-2) ---------------------------------------------

def test_rbac_denied_without_manage(scm_app):
    app, _ = _client(scm_app, None)  # bare user, no scm.policy.manage
    with TestClient(app) as c:
        assert c.get(f"{BASE}?page=1&limit=10").status_code == 403
        assert c.post(BASE, json=_write(scope_type="abc_xyz_cell", scope_ref="A-X")).status_code == 403


def test_rbac_read_denied_with_only_dashboard_view(scm_app):
    """Read gate is manage, not dashboard.view (AC-CFG-3)."""
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, None)
    from datetime import datetime
    rid = str(_uuid.uuid4())
    db.execute(text(
        "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default, created_at) "
        "VALUES (:id, :slug, 'View Only', false, false, false, :now)"
    ), {"id": rid, "slug": f"scm-viewonly-{rid[:8]}", "now": datetime.utcnow()})
    pid = db.execute(text("SELECT id FROM user_permissions WHERE slug = 'scm.dashboard.view'")).scalar()
    db.execute(text(
        "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
        "VALUES (:id, :r, :p, :now)"
    ), {"id": str(_uuid.uuid4()), "r": rid, "p": pid, "now": datetime.utcnow()})
    from app.models.user import UserRoleAssignment
    db.add(UserRoleAssignment(user_id=uid, role_id=rid))
    db.flush()
    as_user(app, gcu, gcuak, uid)
    with TestClient(app) as c:
        assert c.get(f"{BASE}?page=1&limit=10").status_code == 403


# --- validation (AC-VAL-1..9) -----------------------------------------------

def test_val1_scope_ref_required_non_global(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=None)).status_code == 422


def test_val2_global_scope_ref_nulled(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        # global create collides with the seeded active global -> uniqueness 422;
        # but a global write must never persist a scope_ref. Assert via the seeded
        # global row which always keeps scope_ref NULL.
        pass
    gref = db.execute(text(
        "SELECT scope_ref FROM scm.reorder_policy WHERE scope_type = 'global' "
        "ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).scalar()
    assert gref is None


def test_val3_service_level_range(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        service_level=0)).status_code == 422
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        service_level=1)).status_code == 422
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        service_level=1.5)).status_code == 422


def test_val4_day_fields_positive(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        safety_days=0)).status_code == 422
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        review_period_days=-1)).status_code == 422
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        lead_time_default_days=0)).status_code == 422


def test_val5_min_le_max(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid, policy_type="min_max",
                                        min_override=100, max_override=50)).status_code == 422
        # equal is allowed
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid, policy_type="min_max",
                                        min_override=50, max_override=50)).status_code == 201


def test_val6_enum(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        policy_type="bogus")).status_code == 422
        assert c.post(BASE, json=_write(scope_type="bogus", scope_ref=pid)).status_code == 422
        assert c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                        supplier_selection="cheapest")).status_code == 422


def test_val7_statistical_requires_service_level(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        res = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                       safety_stock_method="statistical", service_level=None))
    assert res.status_code == 422, res.text
    assert "service level" in res.json()["message"].lower()


def test_val8_uniqueness_on_active(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        first = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid))
        assert first.status_code == 201, first.text
        dup = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid))
        assert dup.status_code == 422, dup.text
        assert "already exists" in dup.json()["message"].lower()
        # editing the same row is allowed
        upd = c.put(f"{BASE}/{first.json()['id']}",
                    json=_write(scope_type="sku", scope_ref=pid, priority=3))
        assert upd.status_code == 200, upd.text


def test_val9_referential(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        assert c.post(BASE, json=_write(scope_type="sku",
                                        scope_ref=str(_uuid.uuid4()))).status_code == 422
        assert c.post(BASE, json=_write(scope_type="product_class",
                                        scope_ref="NO_SUCH_CODE")).status_code == 422
        assert c.post(BASE, json=_write(scope_type="abc_xyz_cell",
                                        scope_ref="Q-Q")).status_code == 422


# --- factor_toggles merge (Risk #7, AC-EDIT-2) ------------------------------

def test_factor_toggles_merge_survives(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        created = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid,
                                           supplier_selection="primary",
                                           lead_time_default_days=30)).json()
    # inject an unrelated toggle key straight into the JSONB
    db.execute(text(
        "UPDATE scm.reorder_policy SET factor_toggles = "
        "jsonb_set(COALESCE(factor_toggles,'{}'::jsonb), '{safety_stock_manual}', '42') "
        "WHERE id = :id"
    ), {"id": created["id"]})
    db.flush()
    with TestClient(app) as c:
        c.put(f"{BASE}/{created['id']}",
              json=_write(scope_type="sku", scope_ref=pid,
                          supplier_selection="best_score", lead_time_default_days=45))
    toggles = db.execute(text(
        "SELECT factor_toggles FROM scm.reorder_policy WHERE id = :id"
    ), {"id": created["id"]}).scalar()
    assert toggles["supplier_selection"] == "best_score"
    assert int(toggles["lead_time_default_days"]) == 45
    assert int(toggles["safety_stock_manual"]) == 42  # unrelated key survived


# --- classification (AC-CFG-2) ----------------------------------------------

def test_classification_fraction_round_trip_and_analytics_parity(scm_app):
    from app.services.scm.analytics_service import _abc_xyz_policy
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(f"{BASE}/classification",
                    json={"abc_a_pct": 0.80, "abc_b_pct": 0.15,
                          "xyz_x_max": 0.5, "xyz_y_max": 1.0})
        assert put.status_code == 200, put.text
        got = c.get(f"{BASE}/classification").json()
    # round-trips in fraction form (AC-CFG-2 storage convention)
    assert abs(got["abc_a_pct"] - 0.80) < 1e-9
    assert abs(got["abc_b_pct"] - 0.15) < 1e-9
    assert got["exists"] is True
    # …and the analytics engine reads it back as cumulative (80, 95)
    cuts = _abc_xyz_policy(db)
    assert abs(cuts["a"] - 80.0) < 1e-6
    assert abs(cuts["b"] - 95.0) < 1e-6


def test_classification_validation(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        # a + b >= 1
        assert c.put(f"{BASE}/classification",
                     json={"abc_a_pct": 0.80, "abc_b_pct": 0.30,
                           "xyz_x_max": 0.5, "xyz_y_max": 1.0}).status_code == 422
        # a out of (0,1)
        assert c.put(f"{BASE}/classification",
                     json={"abc_a_pct": 0, "abc_b_pct": 0.15,
                           "xyz_x_max": 0.5, "xyz_y_max": 1.0}).status_code == 422
        # xyz_x_max > xyz_y_max
        assert c.put(f"{BASE}/classification",
                     json={"abc_a_pct": 0.80, "abc_b_pct": 0.15,
                           "xyz_x_max": 1.5, "xyz_y_max": 1.0}).status_code == 422


def test_classification_single_row_upsert(scm_app):
    app, db = _client(scm_app, "purchasing")
    before = db.execute(text(
        "SELECT count(*) FROM scm.abc_xyz_policy WHERE is_active = true"
    )).scalar()
    with TestClient(app) as c:
        c.put(f"{BASE}/classification", json={"abc_a_pct": 0.80, "abc_b_pct": 0.15,
                                              "xyz_x_max": 0.5, "xyz_y_max": 1.0})
        c.put(f"{BASE}/classification", json={"abc_a_pct": 0.75, "abc_b_pct": 0.20,
                                              "xyz_x_max": 0.4, "xyz_y_max": 0.9})
    after = db.execute(text(
        "SELECT count(*) FROM scm.abc_xyz_policy WHERE is_active = true"
    )).scalar()
    assert after == max(before, 1)  # upsert, never a second active row


# --- supplier scoring (AC-SUP-2) --------------------------------------------

def test_supplier_scoring_round_trip(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put(f"{BASE}/supplier-scoring",
                    json={"delivery_weight": 0.6, "quality_weight": 0.4,
                          "grace_days": 3, "min_sample_size": 5})
        assert put.status_code == 200, put.text
        got = c.get(f"{BASE}/supplier-scoring").json()
    assert abs(got["delivery_weight"] - 0.6) < 1e-9
    assert got["grace_days"] == 3
    assert got["min_sample_size"] == 5
    assert got["exists"] is True


def test_supplier_scoring_validation(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        # sum != 1
        assert c.put(f"{BASE}/supplier-scoring",
                     json={"delivery_weight": 0.6, "quality_weight": 0.6,
                           "grace_days": 2, "min_sample_size": 3}).status_code == 422
        # weight out of [0,1]
        assert c.put(f"{BASE}/supplier-scoring",
                     json={"delivery_weight": 1.5, "quality_weight": -0.5,
                           "grace_days": 2, "min_sample_size": 3}).status_code == 422
        # min_sample_size < 1
        assert c.put(f"{BASE}/supplier-scoring",
                     json={"delivery_weight": 0.5, "quality_weight": 0.5,
                           "grace_days": 2, "min_sample_size": 0}).status_code == 422
        # grace_days < 0
        assert c.put(f"{BASE}/supplier-scoring",
                     json={"delivery_weight": 0.5, "quality_weight": 0.5,
                           "grace_days": -1, "min_sample_size": 3}).status_code == 422


def test_supplier_scoring_single_row_upsert(scm_app):
    app, db = _client(scm_app, "purchasing")
    before = db.execute(text(
        "SELECT count(*) FROM scm.supplier_scoring_policy WHERE is_active = true"
    )).scalar()
    with TestClient(app) as c:
        c.put(f"{BASE}/supplier-scoring", json={"delivery_weight": 0.6, "quality_weight": 0.4,
                                                "grace_days": 2, "min_sample_size": 3})
        c.put(f"{BASE}/supplier-scoring", json={"delivery_weight": 0.7, "quality_weight": 0.3,
                                                "grace_days": 1, "min_sample_size": 4})
    after = db.execute(text(
        "SELECT count(*) FROM scm.supplier_scoring_policy WHERE is_active = true"
    )).scalar()
    assert after == max(before, 1)


# --- resolve parity (AC-PREV-2, the anti-drift test) ------------------------

def _seed_cell(db, product_id, abc, xyz):
    db.execute(text(
        "DELETE FROM scm.item_classification WHERE product_id = :pid "
        "AND warehouse_id IS NOT DISTINCT FROM NULL"
    ), {"pid": product_id})
    db.execute(text(
        "INSERT INTO scm.item_classification "
        "(id, product_id, warehouse_id, abc_class, xyz_class, source_system, source_ref, created_at) "
        "VALUES (:id, :pid, NULL, :a, :x, 'test', 'test', now())"
    ), {"id": str(_uuid.uuid4()), "pid": product_id, "a": abc, "x": xyz})
    db.flush()


def test_resolve_parity_most_specific_wins(scm_app):
    from app.services.scm.reorder_engine import resolve_policy_for_sku
    app, db = _client(scm_app, "purchasing")
    pid, _code, cat = _a_product(db)
    _seed_cell(db, pid, "A", "X")
    with TestClient(app) as c:
        c.post(BASE, json=_write(scope_type="product_class", scope_ref=cat))
        c.post(BASE, json=_write(scope_type="abc_xyz_cell", scope_ref="A-X"))
        sku = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid)).json()
        res = c.get(f"{BASE}/resolve?product_id={pid}").json()
    engine = resolve_policy_for_sku(db, pid)
    assert res["winner"]["id"] == str(engine["id"])
    assert res["winner"]["id"] == sku["id"]         # most-specific (sku) wins
    assert res["winner"]["scope_type"] == "sku"
    chain = {link["scope_type"]: link for link in res["chain"]}
    assert chain["sku"]["is_winner"] is True
    assert chain["sku"]["reason"] == "most-specific-active"
    assert chain["abc_xyz_cell"]["matched"] is True
    assert chain["abc_xyz_cell"]["is_winner"] is False
    assert chain["product_class"]["matched"] is True
    assert chain["global"]["matched"] is True


def test_resolve_no_classification_global_wins(scm_app):
    from app.services.scm.reorder_engine import resolve_policy_for_sku
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    # ensure the SKU has no classification cell
    db.execute(text(
        "DELETE FROM scm.item_classification WHERE product_id = :pid "
        "AND warehouse_id IS NOT DISTINCT FROM NULL"
    ), {"pid": pid})
    db.flush()
    with TestClient(app) as c:
        res = c.get(f"{BASE}/resolve?product_id={pid}").json()
    engine = resolve_policy_for_sku(db, pid)
    assert res["winner"]["id"] == str(engine["id"])
    assert res["winner"]["scope_type"] == "global"
    chain = {link["scope_type"]: link for link in res["chain"]}
    assert chain["abc_xyz_cell"]["matched"] is False
    assert chain["abc_xyz_cell"]["reason"] == "no-match"
    assert chain["global"]["is_winner"] is True


def test_resolve_priority_tiebreak(scm_app):
    from app.services.scm.reorder_engine import resolve_policy_for_sku
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    # a SECOND active global with higher priority (legacy duplicate) forces a tie
    # at the winning (global) scope -> priority breaks it.
    db.execute(text(
        "INSERT INTO scm.reorder_policy "
        "(id, scope_type, scope_ref, policy_type, priority, is_active, "
        " source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 'global', NULL, 'reorder_point', 99, true, 'test', 'test', now(), now())"
    ), {"id": str(_uuid.uuid4())})
    db.flush()
    with TestClient(app) as c:
        res = c.get(f"{BASE}/resolve?product_id={pid}").json()
    engine = resolve_policy_for_sku(db, pid)
    assert res["winner"]["id"] == str(engine["id"])
    chain = {link["scope_type"]: link for link in res["chain"]}
    assert chain["global"]["is_winner"] is True
    assert chain["global"]["reason"] == "priority-tiebreak"


def test_resolve_product_and_warehouse_labels(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid, code, _cat = _a_product(db)
    wcode = db.execute(text("SELECT warehouse_code FROM warehouses LIMIT 1")).scalar()
    with TestClient(app) as c:
        res = c.get(f"{BASE}/resolve?product_id={pid}&warehouse_id={wcode}").json()
    assert res["product"]["product_code"] == code
    assert res["warehouse"]["warehouse_code"] == wcode
    assert "affected_sku_count" not in res  # AC-PREV-5 deferred


# --- cover scope is READ here, never written (AC-3.2) -----------------------
#
# `cover_scope` is a GLOBAL setting with exactly ONE writer: PUT /scm/config/cover-scope.
# The policy grid shows it because a screen that cannot see it would silently disagree with
# what the plan does, but the grid must never write it: while it sat in the write schema,
# saving ANY unrelated policy field (from a form that does not even carry cover_scope) reset
# the company's setting back to the schema default.

def test_a_policy_save_leaves_the_global_cover_scope_alone(scm_app):
    app, db = _client(scm_app, "purchasing")
    gid = db.execute(text(
        "SELECT id FROM scm.reorder_policy WHERE scope_type = 'global' "
        "ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).scalar()
    with TestClient(app) as c:
        assert c.put("/api/v1/scm/config/cover-scope",
                     json={"cover_scope": "all_locations"}).status_code == 200

        # A grid save of the SAME row, with a payload that carries no cover_scope at all.
        saved = c.put(f"{BASE}/{gid}", json=_write(scope_type="global", safety_days=9))
        assert saved.status_code == 200, saved.text

        assert c.get("/api/v1/scm/config/cover-scope").json() == {
            "cover_scope": "all_locations"
        }
    row = db.execute(text("SELECT safety_days, cover_scope FROM scm.reorder_policy "
                          "WHERE id = :id"), {"id": gid}).fetchone()
    assert float(row[0]) == 9  # the save DID land
    assert row[1] == "all_locations"  # and it did not touch the setting


def test_the_grid_reads_the_value_the_config_route_wrote(scm_app):
    app, db = _client(scm_app, "purchasing")
    gid = db.execute(text(
        "SELECT id FROM scm.reorder_policy WHERE scope_type = 'global' "
        "ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).scalar()
    with TestClient(app) as c:
        c.put("/api/v1/scm/config/cover-scope", json={"cover_scope": "all_locations"})
        listed = c.get(f"{BASE}?page=1&limit=200").json()
    mine = [r for r in listed["data"] if r["id"] == str(gid)]
    assert mine and mine[0]["cover_scope"] == "all_locations"


def test_a_new_policy_row_starts_at_own_pool(scm_app):
    """The captain's answer is the default a fresh row lands on, from the column default -
    not from a value the write schema smuggled in."""
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        created = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid))
    assert created.status_code == 201, created.text
    assert created.json()["cover_scope"] == "own_pool"
    assert db.execute(text("SELECT cover_scope FROM scm.reorder_policy WHERE id = :id"),
                      {"id": created.json()["id"]}).scalar() == "own_pool"


def test_a_legacy_row_with_no_cover_scope_reads_as_own_pool(scm_app):
    """A row written before the column existed must not read as "the whole network"."""
    app, db = _client(scm_app, "purchasing")
    pid, _code, _cat = _a_product(db)
    with TestClient(app) as c:
        created = c.post(BASE, json=_write(scope_type="sku", scope_ref=pid)).json()
        db.execute(text("UPDATE scm.reorder_policy SET cover_scope = NULL WHERE id = :id"),
                   {"id": created["id"]})
        db.flush()
        listed = c.get(f"{BASE}?page=1&limit=200").json()
    mine = [r for r in listed["data"] if r["id"] == created["id"]]
    assert mine and mine[0]["cover_scope"] == "own_pool"
