"""SCM M1 — dashboard endpoint tests (Postgres-backed, rolled back).

Covers, against the seeded demo:
  * shape of every dashboard endpoint,
  * a known SKU's computed net / valuation / status (WESERP10B),
  * the health filter narrows net-position,
  * RBAC deny (403 without scm.dashboard.view),
  * the module guard blocks when scm is disabled.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

# WESERP10B aggregated across all 8 warehouses in the demo seed.
WES_ON_HAND = 7182.0
WES_ON_ORDER = 500.0
WES_COMMITTED = 100.0
WES_NET = 7582.0
WES_VALUATION = 933660.0  # 7182 × 130.00


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _wes_row(client, **params):
    params.setdefault("query", "WESERP10B")
    res = client.get("/api/v1/scm/dashboard/net-position", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def test_net_position_shape_and_known_sku(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        body = _wes_row(c)
    assert set(body) == {"data", "empty", "pagination"}
    assert set(body["pagination"]) == {"total", "page"}
    assert body["pagination"]["total"] == 1
    row = body["data"][0]
    assert row["sku"] == "WESERP10B"
    assert row["on_hand"] == WES_ON_HAND
    assert row["on_order"] == WES_ON_ORDER
    assert row["committed"] == WES_COMMITTED
    assert row["net_position"] == WES_NET
    assert row["stock_valuation"] == WES_VALUATION
    assert row["status"] == "incoming"  # stock + open PO, recent movement
    assert row["imbalance"] is True     # stocked-out in some wh, surplus in others
    # M2 analytics fields are present (real once the analytics job has run;
    # avg_daily_demand/days_of_cover are non-negative or null when no demand).
    assert {"avg_daily_demand", "days_of_cover", "abc_class", "xyz_class"} <= set(row)
    assert row["avg_daily_demand"] is None or row["avg_daily_demand"] >= 0
    # Reorder point stays deferred to M3.
    assert row["reorder_point"] is None
    # per-warehouse breakdown present.
    assert len(row["warehouses"]) == 8
    assert {"warehouse_code", "on_hand", "net_position", "status"} <= set(row["warehouses"][0])


def test_net_position_health_filter(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        incoming = _wes_row(c, health="incoming")
        dead = _wes_row(c, health="dead")
    assert incoming["pagination"]["total"] == 1  # WESERP10B is incoming
    assert dead["pagination"]["total"] == 0       # …so absent from the dead filter
    assert dead["empty"] is True


def test_rollups_shape(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/dashboard/rollups")
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {
        "total_stock_valuation", "dead_stock_valuation", "stockout_count",
        "incoming_po_count", "incoming_po_next_eta", "valuation_missing_cost_count",
        "below_rop_count", "overstock_valuation", "overstock_count",
    }
    # exactly one placed PO (PO-2026/07-0029, active) contributes incoming supply.
    assert body["incoming_po_count"] == 1
    assert body["incoming_po_next_eta"] == "2026-08-04"
    # Below-reorder-point is now populated (M8-B) from the latest completed run's
    # engine ROP — a non-negative int (0 when no run has completed); overstock is M2-real.
    assert body["below_rop_count"] is not None and body["below_rop_count"] >= 0
    assert body["overstock_valuation"] is not None and body["overstock_valuation"] >= 0
    assert body["overstock_count"] is not None and body["overstock_count"] >= 0
    assert body["total_stock_valuation"] > 0
    assert body["stockout_count"] > 0


def test_warehouses_shape(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/dashboard/warehouses")
    assert res.status_code == 200, res.text
    tiles = res.json()["data"]
    assert tiles, "expected warehouse tiles"
    t = tiles[0]
    assert {"warehouse_code", "warehouse_name", "worst_state", "stock_valuation",
            "sku_count", "composition"} <= set(t)
    # M8-B7: low (below reorder point) is now a real per-warehouse count; overstock is M2-real.
    assert t["composition"]["low"] is not None and t["composition"]["low"] >= 0
    assert t["composition"]["overstock"] is not None and t["composition"]["overstock"] >= 0


def test_suppliers_shape(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/dashboard/suppliers", params={"supplier": "SCM-SEED-001"})
    assert res.status_code == 200, res.text
    groups = res.json()["data"]
    assert len(groups) == 1
    g = groups[0]
    assert g["supplier_code"] == "SCM-SEED-001"
    assert g["declared_lead_time_days"] == 45
    assert g["incoming_po_count"] == 1
    assert g["skus"], "supplier should carry its SKUs"
    assert {"sku", "net_position", "status"} <= set(g["skus"][0])


def test_products_drilldown(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get(
            "/api/v1/scm/dashboard/products",
            params={"q": "WESERP10B", "status": "stockout"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    # Paginated envelope now carries total + page.
    assert set(body) == {"data", "total", "page"}
    assert body["page"] == 1
    rows = body["data"]
    # WESERP10B is stocked out in exactly the zero-on-hand warehouses.
    assert rows and all(r["status"] == "stockout" for r in rows)
    assert all(r["sku"] == "WESERP10B" for r in rows)
    assert body["total"] == len(rows)
    # Enriched metric columns are all present per row.
    assert {
        "sku", "product_name", "warehouse_code", "warehouse_name",
        "on_hand", "on_order", "committed", "net_position", "stock_valuation",
        "status", "stockout_with_committed",
    } <= set(rows[0])
    # Stocked out ⇒ on_hand 0; WESERP10B carries committed demand somewhere.
    assert all(r["on_hand"] == 0 for r in rows)


def test_products_drilldown_pagination(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        page1 = c.get(
            "/api/v1/scm/dashboard/products",
            params={"status": "stockout", "page": 1, "limit": 5},
        ).json()
        page2 = c.get(
            "/api/v1/scm/dashboard/products",
            params={"status": "stockout", "page": 2, "limit": 5},
        ).json()
    assert page1["total"] == page2["total"]
    if page1["total"] > 5:
        assert len(page1["data"]) == 5
        # different pages return different rows
        assert page1["data"][0] != page2["data"][0]


def test_products_drilldown_sort(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        asc = c.get(
            "/api/v1/scm/dashboard/products",
            params={"status": "stockout", "sort": "net_position", "dir": "asc", "limit": 200},
        ).json()["data"]
        desc = c.get(
            "/api/v1/scm/dashboard/products",
            params={"status": "stockout", "sort": "net_position", "dir": "desc", "limit": 200},
        ).json()["data"]
    asc_nets = [r["net_position"] for r in asc]
    desc_nets = [r["net_position"] for r in desc]
    assert asc_nets == sorted(asc_nets)
    assert desc_nets == sorted(desc_nets, reverse=True)


def test_products_drilldown_search(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get(
            "/api/v1/scm/dashboard/products",
            params={"q": "WESERP10B", "limit": 200},
        ).json()
    assert res["total"] > 0
    assert all(r["sku"] == "WESERP10B" for r in res["data"])


def test_net_position_bad_sort_key_does_not_500(scm_app):
    """A non-scalar / unknown sort key (e.g. the list-valued ``warehouses``
    breakdown) must fall back to the attention default, not raise a 500."""
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        # 'warehouses' is a list[dict] per row — previously TypeError → 500.
        bad = c.get("/api/v1/scm/dashboard/net-position", params={"sort": "warehouses"})
        assert bad.status_code == 200, bad.text
        nonsense = c.get("/api/v1/scm/dashboard/net-position", params={"sort": "not_a_column"})
        assert nonsense.status_code == 200, nonsense.text
        # falls back to the same default ordering as no sort at all
        default = c.get("/api/v1/scm/dashboard/net-position")
        assert default.status_code == 200, default.text
        assert [r["sku"] for r in bad.json()["data"]] == [
            r["sku"] for r in default.json()["data"]
        ]


def test_net_position_sort_by_net_position(scm_app):
    """An allow-listed scalar column still sorts correctly."""
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        asc = c.get(
            "/api/v1/scm/dashboard/net-position",
            params={"sort": "net_position", "dir": "asc", "limit": 200},
        ).json()["data"]
        desc = c.get(
            "/api/v1/scm/dashboard/net-position",
            params={"sort": "net_position", "dir": "desc", "limit": 200},
        ).json()["data"]
    asc_nets = [r["net_position"] for r in asc]
    desc_nets = [r["net_position"] for r in desc]
    assert asc_nets == sorted(asc_nets)
    assert desc_nets == sorted(desc_nets, reverse=True)


def test_rbac_denial_without_slug(scm_app):
    # A bare user (no role → no scm.dashboard.view) is denied.
    app, _ = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/dashboard/rollups")
    assert res.status_code == 403, res.text


def test_module_guard_blocks_when_disabled(scm_app, monkeypatch):
    app, _ = _client(scm_app, "purchasing")  # has perm; only the module gate fails
    from app.config import settings
    import app.modules.runtime.guards as guards

    monkeypatch.setattr(settings, "module_guard_strict", True, raising=False)
    monkeypatch.setattr(guards, "is_module_enabled", lambda *a, **k: False)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/dashboard/rollups")
    assert res.status_code == 403, res.text
    assert "not enabled" in res.text.lower()
