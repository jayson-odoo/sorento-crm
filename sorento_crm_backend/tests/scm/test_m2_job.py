"""SCM M2 - analytics job observability, backfill, explain endpoint, auth
(AC-M2.11/2.12/2.13/2.14).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import analytics_service as svc
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

_GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "golden_m2.json")))
_AS_OF = date.fromisoformat(_GOLDEN["as_of"])


def _pid(db, code):
    return db.execute(text("SELECT id FROM products WHERE product_code = :c"), {"c": code}).scalar()


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def test_run_writes_analytics_run_log_with_counts_and_coverage(scm_app):
    """AC-M2.12: one scm_analytics_run row records status/window/counts + channel
    coverage %; stage counts are human-readable."""
    _, db, _, _ = scm_app
    pid = _pid(db, _GOLDEN["demand"][0]["product_code"])
    result = svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})

    row = db.execute(text(
        "SELECT status, window_days, counts, config_ref, started_at, finished_at "
        "FROM scm.scm_analytics_run WHERE id = :id"
    ), {"id": result["run_id"]}).fetchone()
    assert row.status == "completed"
    assert row.window_days == 90
    assert row.finished_at is not None and row.started_at is not None
    assert row.config_ref == _AS_OF.isoformat()
    counts = row.counts
    assert counts["demand_stat"] >= 1
    assert counts["item_classification"] >= 1
    assert "planning_skus" in counts
    assert "channel_coverage_pct" in counts  # logged even if partial
    assert "duration_ms" in counts


def test_first_run_backfills_all_planning_skus(scm_app):
    """AC-M2.14: every planning SKUxwarehouse in scope gets a demand_stat + a
    classification row on the first run - including keys with no outflow."""
    _, db, _, _ = scm_app
    # pick a product that spans several warehouses in the planning grid
    pid = db.execute(text(
        "SELECT product_id FROM scm.net_position_v GROUP BY product_id "
        "HAVING count(*) >= 2 LIMIT 1"
    )).scalar()
    planning_keys = db.execute(text(
        "SELECT product_id, warehouse_id FROM scm.net_position_v WHERE product_id = :p"
    ), {"p": pid}).fetchall()
    assert planning_keys

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    for k in planning_keys:
        ds = db.execute(text(
            "SELECT 1 FROM scm.demand_stat WHERE product_id = :p AND warehouse_id IS NOT DISTINCT FROM :w"
        ), {"p": k.product_id, "w": k.warehouse_id}).first()
        ic = db.execute(text(
            "SELECT 1 FROM scm.item_classification WHERE product_id = :p AND warehouse_id IS NOT DISTINCT FROM :w"
        ), {"p": k.product_id, "w": k.warehouse_id}).first()
        assert ds is not None, f"backfill missed demand_stat for {k.product_id}/{k.warehouse_id}"
        assert ic is not None, f"backfill missed classification for {k.product_id}/{k.warehouse_id}"


def test_rerun_is_idempotent_no_duplicates(scm_app):
    """AC-M2.8/latest-only: a second run overwrites, never duplicates."""
    _, db, _, _ = scm_app
    pid = _pid(db, _GOLDEN["demand"][0]["product_code"])
    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    dup = db.execute(text(
        "SELECT product_id, warehouse_id, count(*) c FROM scm.demand_stat "
        "WHERE product_id = :p GROUP BY product_id, warehouse_id HAVING count(*) > 1"
    ), {"p": pid}).fetchall()
    assert dup == []


def test_null_warehouse_key_upsert_is_idempotent(scm_app):
    """S2: warehouse_id is nullable and Postgres treats NULLs as DISTINCT, so an
    ON CONFLICT (product_id, warehouse_id) never dedupes a network-level (warehouse_id
    IS NULL) row - it duplicated every run and multiplied the dashboard LEFT JOIN. The
    delete-then-insert upsert must yield exactly ONE demand_stat + ONE classification
    row across re-runs for a null-warehouse key."""
    _, db, _, _ = scm_app
    pid = _pid(db, _GOLDEN["demand"][0]["product_code"])
    now = datetime.utcnow()
    key = (str(pid), None)  # network-level key: warehouse_id NULL
    payload = svc._demand_stat_payload(None, svc._abc_xyz_policy(db))
    svc._upsert_demand_stat(db, key, payload, now)
    svc._upsert_demand_stat(db, key, payload, now)  # re-run
    svc._upsert_classification(db, key, "A", "X", 100.0, 0.1, now)
    svc._upsert_classification(db, key, "A", "X", 100.0, 0.1, now)  # re-run
    db.flush()
    ds = db.execute(text(
        "SELECT count(*) FROM scm.demand_stat WHERE product_id = :p AND warehouse_id IS NULL"
    ), {"p": pid}).scalar()
    ic = db.execute(text(
        "SELECT count(*) FROM scm.item_classification WHERE product_id = :p AND warehouse_id IS NULL"
    ), {"p": pid}).scalar()
    assert ds == 1
    assert ic == 1


def test_explain_endpoint(scm_app):
    app, db = _client(scm_app, "purchasing")
    g = _GOLDEN["demand"][0]
    pid = _pid(db, g["product_code"])
    wid = db.execute(text("SELECT id FROM warehouses WHERE warehouse_code = :c"),
                     {"c": g["warehouse_code"]}).scalar()
    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": _AS_OF})
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/analytics/explain/demand",
                    params={"product_id": pid, "warehouse_id": wid, "as_of": _AS_OF.isoformat()})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["window_days"] == 90
    assert body["method"] == g["method"]
    assert abs(body["avg_daily_demand"] - g["avg_daily_demand"]) < 0.01


def test_run_requires_reorder_run_permission(scm_app):
    """Auth: triggering a run needs scm.reorder.run; a bare user is denied."""
    app, db = _client(scm_app, None)  # bare user
    pid = str(_pid(db, _GOLDEN["demand"][0]["product_code"]))
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/analytics/run", json={"scope": {"product_ids": [pid]}})
    assert res.status_code == 403


def test_run_and_read_log_via_api(scm_app):
    app, db = _client(scm_app, "purchasing")
    pid = str(_pid(db, _GOLDEN["demand"][0]["product_code"]))
    with TestClient(app) as c:
        run = c.post("/api/v1/scm/analytics/run",
                     json={"scope": {"product_ids": [pid]}, "config": {"as_of": _AS_OF.isoformat()}})
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "completed"
        runs = c.get("/api/v1/scm/analytics/runs")
    assert runs.status_code == 200
    assert any(r["status"] == "completed" for r in runs.json()["data"])
