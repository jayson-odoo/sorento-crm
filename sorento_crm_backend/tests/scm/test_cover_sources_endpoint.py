"""What the plan screen is told about cover, and about the pool each row sits in (AC-3.3).

The cover endpoint is keyed by PRODUCT because the free pool is shared: two rows of the same
product draw on the same units, and duplicating the pool per row would let the screen promise
the same stock twice. That keying is exactly why the scope filter cannot be applied once,
server-side, for the whole map: two rows of the same product can sit in DIFFERENT pools. So
the response carries the facts the per-row filter needs - each source's own pool, and the
run's `cover_scope` - and the recommendation row carries its own pool beside its warehouse.

Everything runs inside the rolled-back savepoint the `scm_app` fixture provides.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZCSEP"


def _client(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _mk_product(db, code):
    cat, uom = db.execute(text(
        "SELECT category_id, base_uom_id FROM products WHERE category_id IS NOT NULL LIMIT 1"
    )).fetchone()
    pid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, cost_price, is_active, is_discontinued, currency, created_at, updated_at) "
        "VALUES (:id, :code, :name, :cat, :uom, 100, 60, true, false, 'MYR', now(), now())"
    ), {"id": pid, "code": code, "name": f"{MARKER} {code}", "cat": cat, "uom": uom})
    return pid


def _mk_warehouse(db, code, pool_of=None):
    wid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, segment, pool_warehouse_id, created_at, updated_at) "
        "VALUES (:id, :code, :name, true, true, 'project', :pool, now(), now())"
    ), {"id": wid, "code": code, "name": f"{MARKER} {code}", "pool": pool_of})
    return wid


def _world(db):
    """A product with free stock at B (in A's pool) and C (its own site), and a plan row at A."""
    pid = _mk_product(db, f"{MARKER}-P-{uuid.uuid4().hex[:6]}")
    a = _mk_warehouse(db, f"{MARKER}-A-{uuid.uuid4().hex[:4]}")
    b = _mk_warehouse(db, f"{MARKER}-B-{uuid.uuid4().hex[:4]}", pool_of=a)
    c = _mk_warehouse(db, f"{MARKER}-C-{uuid.uuid4().hex[:4]}")
    for wid, qty in ((b, 5), (c, 50)):
        db.execute(text(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel, created_at, updated_at) "
            "VALUES (:id, :p, :w, :q, false, now(), now())"
        ), {"id": str(uuid.uuid4()), "p": pid, "w": wid, "q": qty})

    # The run needs the caller's company or `assert_run_visible` 404s every route below -
    # a plan that belongs to nobody is exactly what company isolation exists to prevent.
    run_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now())"),
        {"id": run_id, "co": SORENTO_COMPANY_ID})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, recommended_qty, "
        " status, company_id, inputs) "
        "VALUES (:id, :run, :p, :w, 'buy', 60, 60, 'proposed', :co, CAST(:inputs AS jsonb))"
    ), {"id": str(uuid.uuid4()), "run": run_id, "p": pid, "w": a, "co": SORENTO_COMPANY_ID,
        "inputs": '{"committed": 60, "on_hand": 0}'})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "a": a, "b": b, "c": c}


def test_each_source_names_the_pool_it_belongs_to(scm_app):
    app, db = _client(scm_app)
    w = _world(db)
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/cover-sources")
    assert res.status_code == 200, res.text
    sources = res.json()["sources"][w["product_id"]]
    by_id = {s["warehouse_id"]: s for s in sources}
    # B shares A's pool; C is its own pool (COALESCE(pool_warehouse_id, id)).
    assert by_id[w["b"]]["pool_warehouse_id"] == w["a"]
    assert by_id[w["c"]]["pool_warehouse_id"] == w["c"]


def test_the_response_carries_the_runs_cover_scope(scm_app):
    from app.services.scm.reorder_policy import upsert_global_policy

    app, db = _client(scm_app)
    w = _world(db)
    upsert_global_policy(db, cover_scope="all_locations")
    db.flush()
    with TestClient(app) as c:
        assert c.get(
            f"/api/v1/scm/reorder-runs/{w['run_id']}/cover-sources"
        ).json()["cover_scope"] == "all_locations"

    upsert_global_policy(db, cover_scope="own_pool")
    db.flush()
    with TestClient(app) as c:
        assert c.get(
            f"/api/v1/scm/reorder-runs/{w['run_id']}/cover-sources"
        ).json()["cover_scope"] == "own_pool"


def test_the_pool_map_is_not_pre_filtered_by_scope(scm_app):
    """Keyed by product, so it must stay whole: filtering it here would answer for one row
    and lie to every other row of the same product sitting in another pool."""
    from app.services.scm.reorder_policy import upsert_global_policy

    app, db = _client(scm_app)
    w = _world(db)
    upsert_global_policy(db, cover_scope="own_pool")
    db.flush()
    with TestClient(app) as c:
        sources = c.get(
            f"/api/v1/scm/reorder-runs/{w['run_id']}/cover-sources"
        ).json()["sources"][w["product_id"]]
    assert {s["warehouse_id"] for s in sources} == {w["b"], w["c"]}


def test_a_recommendation_row_carries_its_own_pool(scm_app):
    app, db = _client(scm_app)
    w = _world(db)
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/recommendations",
                    params={"page": 1, "limit": 50})
    assert res.status_code == 200, res.text
    row = next(r for r in res.json()["data"] if r["warehouse_id"] == w["a"])
    # A has no pool of its own, so it IS its own pool - the same COALESCE the sources use.
    assert row["pool_warehouse_id"] == w["a"]


def test_a_row_in_a_pool_reports_the_pool_root_not_itself(scm_app):
    app, db = _client(scm_app)
    w = _world(db)
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, recommended_qty, "
        " status, company_id, inputs) "
        "VALUES (:id, :run, :p, :w, 'buy', 3, 3, 'proposed', :co, CAST(:inputs AS jsonb))"
    ), {"id": str(uuid.uuid4()), "run": w["run_id"], "p": w["product_id"], "w": w["b"],
        "co": SORENTO_COMPANY_ID, "inputs": '{"committed": 3, "on_hand": 0}'})
    db.flush()
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/recommendations",
                    params={"page": 1, "limit": 50})
    assert res.status_code == 200, res.text
    row = next(r for r in res.json()["data"] if r["warehouse_id"] == w["b"])
    assert row["pool_warehouse_id"] == w["a"]


def test_cover_sources_rbac_denied_without_view(scm_app):
    app, db = _client(scm_app, None)  # bare user, no scm.dashboard.view
    w = _world(db)
    with TestClient(app) as c:
        assert c.get(
            f"/api/v1/scm/reorder-runs/{w['run_id']}/cover-sources"
        ).status_code == 403
