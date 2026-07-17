"""SCM M8 Slice D — daily scheduled reorder run + /today first-view fallback + drop buy_scope.

Covers:
  * D8 — ``_handler_scm_reorder_run`` creates a run over ALL warehouses (warehouse_codes
    empty), market insight OFF, and the full-budget path funds every costed buy (M8-D1/D6),
    plus the seeded ``scheduled_tasks`` row (days/1 + 06:00-KL anchor + metadata).
  * D9 — the create-run REQUEST no longer carries ``buy_scope`` (defaults to network
    internally); ``GET /reorder-runs/today`` returns today's snapshot, and falls back to
    the latest completed run when none started today.

Reuses the ``scm_app`` savepoint fixture + the controlled fixture builders from
``test_m3_run`` (a stock row makes a SKU×warehouse appear in ``scm.net_position_v``; a
demand_stat row sets its rate). ``run_reorder`` / the handler run SYNCHRONOUSLY.
"""
from __future__ import annotations

import types
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.scheduler.task_scheduler import _handler_scm_reorder_run
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _client,
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


# ===========================================================================
# D8 — daily scheduled reorder run handler
# ===========================================================================

def test_scheduled_handler_runs_all_warehouses_market_off_full_budget(scm_app, monkeypatch):
    """M8-D1/D6/D8: the scheduled handler creates a NETWORK run with market OFF over all
    warehouses (empty warehouse_codes) and the full-budget path funds every costed buy.

    The catalog is shrunk to one controlled warehouse (monkeypatching the all-warehouses
    resolver) so the run is fast + isolated; the patch also asserts the handler asked for
    ALL warehouses (empty codes)."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "M8DW-ALL")
    pid = _mk_product(db, "M8DP-ALL")
    _mk_stock(db, pid, wid, 8)            # low stock → triggers a buy
    _mk_demand(db, pid, wid, 11.0)        # demand·lead ≫ net
    _link(db, pid, _mk_supplier(db, "M8D All Supplier"))
    db.flush()

    seen: dict = {}

    def _fake_resolve(_db, codes):
        seen["codes"] = codes           # handler must pass all-warehouses (empty)
        return [wid]

    monkeypatch.setattr(svc, "_resolve_warehouse_ids", _fake_resolve)

    task = types.SimpleNamespace(metadata_={"budget": None, "include_market": False})
    result = _handler_scm_reorder_run(db, task)

    assert not seen["codes"], "scheduled run must target ALL warehouses (empty codes)"
    assert result["include_market"] is False
    assert result["funded_count"] >= 1
    assert result["deferred_count"] == 0        # full budget defers nothing (M8-D6)

    run = db.execute(text(
        "SELECT status, buy_scope, include_market, budget_amount "
        "FROM scm.reorder_run WHERE id = :id"
    ), {"id": result["run_id"]}).mappings().first()
    assert run["status"] == "completed"
    assert run["buy_scope"] == "network"
    assert run["include_market"] is False
    assert run["budget_amount"] is None          # full budget stamps a null cap

    buys = db.execute(text(
        "SELECT funding_status, cash_impact FROM scm.reorder_recommendation "
        "WHERE run_id = :id AND rec_type = 'buy' AND product_id = :p"
    ), {"id": result["run_id"], "p": pid}).mappings().all()
    assert buys, "expected at least one buy for the controlled SKU"
    assert all(b["funding_status"] == "funded" for b in buys)
    assert all(b["cash_impact"] is not None for b in buys)


def test_scheduled_handler_seed_row_exists_days_1_at_0600_kl(scm_app):
    """M8-D2/D8: the seeded ``scheduled_tasks`` row is daily (days/1), anchored to 06:00
    Malaysia local, and carries the {budget:null, include_market:false} metadata."""
    _, db, _, _ = scm_app
    row = db.execute(text("""
        SELECT interval_unit, interval_value, enabled, metadata,
               EXTRACT(hour FROM ((start_at AT TIME ZONE 'utc')
                       AT TIME ZONE 'Asia/Kuala_Lumpur'))::int AS kl_hour
        FROM scheduled_tasks WHERE key = 'scm_reorder_run'
    """)).mappings().first()
    assert row is not None, "scm_reorder_run scheduled task must be seeded (run migrations)"
    assert row["interval_unit"] == "days"
    assert row["interval_value"] == 1
    assert row["enabled"] is True
    assert row["kl_hour"] == 6, "scheduled run must anchor to 06:00 Malaysia local"
    meta = row["metadata"] or {}
    assert meta.get("include_market") is False
    assert "budget" in meta and meta["budget"] is None


# ===========================================================================
# D9 — drop buy_scope from the create-run request
# ===========================================================================

def test_create_run_request_without_buy_scope_defaults_network(scm_app):
    """M8-D5: the create-run REQUEST no longer takes ``buy_scope``; the run defaults to
    network. A stray ``buy_scope`` in the body is ignored (schema dropped it)."""
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        # no buy_scope in the body → network default
        res = c.post("/api/v1/scm/reorder-runs", json={"warehouse_codes": []})
        assert res.status_code == 202, res.text
        assert res.json()["buy_scope"] == "network"

        # a stray buy_scope is ignored (not honoured) → still network
        res2 = c.post("/api/v1/scm/reorder-runs",
                      json={"warehouse_codes": [], "buy_scope": "warehouse"})
        assert res2.status_code == 202, res2.text
        assert res2.json()["buy_scope"] == "network"


# ===========================================================================
# D9 — GET /reorder-runs/today (first-view fallback)
# ===========================================================================

def test_today_returns_todays_completed_snapshot(scm_app):
    """M8-D3: GET /reorder-runs/today returns today's most-recent snapshot (is_today True)
    with the run-log summary, so the FE opens the plan without knowing an id."""
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, "M8DW-TODAY")
    pid = _mk_product(db, "M8DP-TODAY")
    _mk_stock(db, pid, wid, 8)
    _mk_demand(db, pid, wid, 11.0)
    _link(db, pid, _mk_supplier(db, "M8D Today Supplier"))
    db.flush()

    created = svc.create_run(db, ["M8DW-TODAY"], enqueue=False)  # network default
    svc.run_reorder(created["run_id"], db=db)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/reorder-runs/today")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body is not None
        assert body["run_id"] == created["run_id"]
        assert body["is_today"] is True
        assert body["status"] == "completed"
        assert body["buy_scope"] == "network"
        assert body["summary"]["recommendation_count"] >= 1


def test_today_falls_back_to_latest_completed_when_none_today(scm_app):
    """M8-D4: when no run started today, the picker returns the most-recent COMPLETED run
    (the last available snapshot) with is_today False rather than nothing. Forced by
    asking for a future calendar date so today's window is empty."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "M8DW-FALL")
    pid = _mk_product(db, "M8DP-FALL")
    _mk_stock(db, pid, wid, 8)
    _mk_demand(db, pid, wid, 11.0)
    _link(db, pid, _mk_supplier(db, "M8D Fall Supplier"))
    db.flush()

    created = svc.create_run(db, ["M8DW-FALL"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    future = date.today() + timedelta(days=5)
    picked = svc.today_or_latest_run(db, today=future)
    assert picked is not None, "expected a completed-run fallback"
    assert picked["is_today"] is False
    assert picked["row"]["status"] == "completed"


def test_today_auth_denied_without_dashboard_view(scm_app):
    """Auth: the first-view endpoint needs scm.dashboard.view; a bare user is denied."""
    app, _ = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/reorder-runs/today")
    assert res.status_code == 403
