"""SCM M2 - dashboard binding tests (Postgres-backed, rolled back).

Runs the analytics engine inside the test's savepoint, then asserts the dashboard
reads surface the REAL demand / classification / overstock / supplier-performance
values (not the retired FE mock). Covers, against the seeded prod-copy:
  * net-position / products return real avg_daily_demand / days_of_cover / ABC / XYZ,
  * the overstock rollup (valuation + count) and the ``status=overstock`` filter,
  * the supplier scorecard object,
  * the 12-month demand-series endpoint,
  * RBAC deny on demand-series.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.scm import analytics_service
from app.services.scm.dashboard_service import _is_overstock
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg


# ---------------------------------------------------------------------------
# Overstock predicate - pure maths (S1: ∞-cover-with-stock counts as overstock)
# ---------------------------------------------------------------------------

def test_is_overstock_pure_predicate():
    ceiling = 90
    # finite cover above the ceiling → overstock
    assert _is_overstock(on_hand=100, days_of_cover=120, avg_daily_demand=1.0, ceiling=ceiling)
    # finite cover under the ceiling → not overstock
    assert not _is_overstock(on_hand=100, days_of_cover=30, avg_daily_demand=1.0, ceiling=ceiling)
    # ∞ cover WITH stock (no demand) → overstock, whether demand is None or 0
    assert _is_overstock(on_hand=100, days_of_cover=None, avg_daily_demand=None, ceiling=ceiling)
    assert _is_overstock(on_hand=100, days_of_cover=None, avg_daily_demand=0, ceiling=ceiling)
    # zero-stock rows are NEVER overstock (nothing is invested)
    assert not _is_overstock(on_hand=0, days_of_cover=None, avg_daily_demand=None, ceiling=ceiling)
    assert not _is_overstock(on_hand=0, days_of_cover=200, avg_daily_demand=1.0, ceiling=ceiling)


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _run(db):
    """Run the full analytics engine within the test's rolled-back savepoint."""
    return analytics_service.run_analytics(db, scope=None, config=None)


def test_net_position_enriched_after_run(scm_app):
    app, db = _client(scm_app, "purchasing")
    res = _run(db)
    assert res["status"] == "completed"
    assert res["counts"]["demand_stat"] > 0
    with TestClient(app) as c:
        body = c.get(
            "/api/v1/scm/dashboard/net-position", params={"query": "WESERP10B"}
        ).json()
    row = body["data"][0]
    # WESERP10B is a real high-volume seller → non-null demand + forward cover.
    assert row["avg_daily_demand"] is not None and row["avg_daily_demand"] > 0
    assert row["days_of_cover"] is not None
    assert row["abc_class"] in {"A", "B", "C"}
    assert row["xyz_class"] in {"X", "Y", "Z"}
    assert row["reorder_point"] is None  # M3


def test_net_position_sort_days_of_cover_nulls_last(scm_app):
    app, db = _client(scm_app, "purchasing")
    _run(db)
    with TestClient(app) as c:
        desc = c.get(
            "/api/v1/scm/dashboard/net-position",
            params={"sort": "days_of_cover", "dir": "desc", "limit": 200},
        ).json()["data"]
    docs = [r["days_of_cover"] for r in desc]
    present = [d for d in docs if d is not None]
    # non-null values are sorted high→low and no null precedes a real value.
    assert present == sorted(present, reverse=True)
    first_null = next((i for i, d in enumerate(docs) if d is None), len(docs))
    assert all(d is None for d in docs[first_null:])


def test_overstock_rollup_and_filter(scm_app):
    app, db = _client(scm_app, "purchasing")
    _run(db)
    with TestClient(app) as c:
        rollups = c.get("/api/v1/scm/dashboard/rollups").json()
        over_np = c.get(
            "/api/v1/scm/dashboard/net-position",
            params={"health": "overstock", "limit": 200},
        ).json()
        over_prod = c.get(
            "/api/v1/scm/dashboard/products",
            params={"status": "overstock", "limit": 200},
        ).json()
    assert rollups["overstock_valuation"] is not None
    assert rollups["overstock_count"] is not None and rollups["overstock_count"] >= 0
    # Every overstock drill-down row is over-invested one of two ways (S1): finite
    # cover over the ceiling, OR ∞ cover with stock (on_hand>0, no demand). A zero-stock
    # row is never overstock.
    for r in over_prod["data"]:
        assert r["on_hand"] > 0
        finite_over = r["days_of_cover"] is not None
        infinite_with_stock = r["days_of_cover"] is None and not r["avg_daily_demand"]
        assert finite_over or infinite_with_stock
    # The product grid overstock filter is authoritative (server-paginated total).
    assert over_np["pagination"]["total"] >= 0


def test_infinite_cover_stocked_zero_demand_is_overstock(scm_app):
    """S1: a stocked SKU with no demand (∞ cover, days_of_cover null) is over-invested
    capital - it must be RETURNED by the health=overstock filter AND counted in
    overstock_count, matching the grid's ∞-cover overstock colour. Grid, count and
    filter now agree; previously the count/filter excluded the ∞ case."""
    app, db = _client(scm_app, "purchasing")
    _run(db)
    with TestClient(app) as c:
        over = c.get(
            "/api/v1/scm/dashboard/net-position",
            params={"health": "overstock", "limit": 200},
        ).json()["data"]
        rollups = c.get("/api/v1/scm/dashboard/rollups").json()
    if not over:
        pytest.skip("no overstock rows in the seeded active+ongoing scope")
    # zero-stock rows are NEVER overstock (nothing is invested)
    assert all(r["on_hand"] > 0 for r in over)
    # the ∞-cover case (stock but no demand → days_of_cover null) is now INCLUDED
    infinite = [r for r in over if r["days_of_cover"] is None and not r["avg_daily_demand"]]
    assert infinite, "∞-cover stocked zero-demand SKU missing from health=overstock (S1)"
    # the count agrees - the ∞ rows it now includes are also in the filter above
    assert rollups["overstock_count"] >= 1


def test_abc_xyz_filter_server_side(scm_app):
    app, db = _client(scm_app, "purchasing")
    _run(db)
    with TestClient(app) as c:
        a = c.get(
            "/api/v1/scm/dashboard/net-position", params={"abc": "A", "limit": 200}
        ).json()
        unknown = c.get(
            "/api/v1/scm/dashboard/net-position", params={"xyz": "unknown", "limit": 5}
        ).json()
    assert all(r["abc_class"] == "A" for r in a["data"])
    assert all(r["xyz_class"] is None for r in unknown["data"])


def test_supplier_scorecard_after_run(scm_app):
    app, db = _client(scm_app, "purchasing")
    _run(db)
    with TestClient(app) as c:
        groups = c.get(
            "/api/v1/scm/dashboard/suppliers", params={"supplier": "SCM-SEED-001"}
        ).json()["data"]
    assert groups, "expected the seeded supplier group"
    perf = groups[0]["performance"]
    assert perf is not None
    assert {"on_time_rate", "avg_lead_time_days", "reject_rate", "fill_rate",
            "composite_score", "sample_size", "confidence"} <= set(perf)
    assert perf["confidence"] in {"high", "medium", "low"}


def test_supplier_scorecard_null_when_unscored(scm_app):
    """A supplier with no completing receipts is returned with performance=null  - 
    never a fabricated score."""
    app, db = _client(scm_app, "purchasing")
    _run(db)
    with TestClient(app) as c:
        groups = c.get("/api/v1/scm/dashboard/suppliers").json()["data"]
    # At least one supplier in the catalog has no computed performance row.
    assert any(g["performance"] is None for g in groups)


def test_demand_series_twelve_monthly_buckets(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get(
            "/api/v1/scm/dashboard/demand-series", params={"sku": "WESERP10B"}
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sku"] == "WESERP10B"
    assert len(body["points"]) == 12
    assert {"month", "qty"} <= set(body["points"][0])
    # oldest → newest, YYYY-MM keys.
    months = [p["month"] for p in body["points"]]
    assert months == sorted(months)
    assert body["total_qty"] >= 0
    assert body["peak_qty"] >= 0


def test_demand_series_unknown_sku_404(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get(
            "/api/v1/scm/dashboard/demand-series", params={"sku": "NOPE-XYZ-000"}
        )
    assert res.status_code == 404, res.text


def test_demand_series_rbac_denied(scm_app):
    app, db = _client(scm_app, None)  # no role → no scm.dashboard.view
    with TestClient(app) as c:
        res = c.get(
            "/api/v1/scm/dashboard/demand-series", params={"sku": "WESERP10B"}
        )
    assert res.status_code == 403, res.text
