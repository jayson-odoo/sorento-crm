"""HTTP-level coverage for `POST /reorder-runs/{run_id}/replan` (S5, review S7).

`test_reorder_replan.py` proves the SERVICE contract (`replan_run` / `carry_replan_decisions`)
directly; this file proves the ROUTE wraps it correctly - the 202 envelope shape, the
`scm.reorder.run` permission gate, the cross-company 404 (`assert_run_visible`'s own contract,
same as every other run-scoped endpoint), and that `superseded_by_run_id` / `needs_recheck`
actually reach the wire on `GET /reorder-runs/{id}` and `GET .../recommendations`.

Same controlled-fixture / synchronous-`run_reorder` harness as `test_m3_run.py`.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _client,
    _link,
    _mk_committed,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


def _seed(db, code: str):
    wid = _mk_warehouse(db, f"RPR-{code}")
    pid = _mk_product(db, f"RPRP-{code}")
    _mk_stock(db, pid, wid, 10)
    _mk_demand(db, pid, wid, 10.0)
    _mk_committed(db, pid, wid, qty=1)
    _link(db, pid, _mk_supplier(db, f"Replan Route Supplier {code}"))
    db.flush()
    return {"warehouse_id": wid, "warehouse_code": f"RPR-{code}",
            "product_id": pid, "product_code": f"RPRP-{code}"}


def test_replan_returns_202_with_the_accepted_envelope(scm_app):
    """202 shape: run_id, status='running', buy_scope, stage, and `supersedes_run_id`
    naming the run this one replaces (the FE navigates on this response, same as Start
    Plan's own 202)."""
    app, db = _client(scm_app, "purchasing")
    p = _seed(db, "A1")
    with TestClient(app) as c:
        launch = c.post("/api/v1/scm/reorder-runs", json={"warehouse_codes": [p["warehouse_code"]]})
        assert launch.status_code == 202, launch.text
        old_id = launch.json()["run_id"]
        svc.run_reorder(old_id, db=db)

        res = c.post(f"/api/v1/scm/reorder-runs/{old_id}/replan", json={
            "warehouse_codes": [p["warehouse_code"]], "product_codes": [], "plan_horizon_date": None,
        })
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["status"] == "running"
        assert body["run_id"] and body["run_id"] != old_id
        assert body["supersedes_run_id"] == old_id
        assert set(body) >= {"run_id", "status", "buy_scope", "stage", "supersedes_run_id"}


def test_replan_denied_without_reorder_run_permission(scm_app):
    """Auth: re-planning needs scm.reorder.run, same gate as launching a run - a bare
    user (no role) is denied."""
    app, db = _client(scm_app, "purchasing")
    p = _seed(db, "B1")
    with TestClient(app) as c:
        launch = c.post("/api/v1/scm/reorder-runs", json={"warehouse_codes": [p["warehouse_code"]]})
        old_id = launch.json()["run_id"]
        svc.run_reorder(old_id, db=db)

    app2, _ = _client(scm_app, None)
    with TestClient(app2) as c2:
        res = c2.post(f"/api/v1/scm/reorder-runs/{old_id}/replan", json={
            "warehouse_codes": [], "product_codes": [], "plan_horizon_date": None,
        })
    assert res.status_code == 403


def test_replan_404s_a_run_in_another_company(scm_app):
    """`assert_run_visible`'s own contract: a run stamped to a DIFFERENT company reads as
    not-found, never as a 403/other-company hint - the same rule every other run-scoped
    route already gets."""
    app, db = _client(scm_app, "purchasing")
    p = _seed(db, "C1")
    with TestClient(app) as c:
        launch = c.post("/api/v1/scm/reorder-runs", json={"warehouse_codes": [p["warehouse_code"]]})
        old_id = launch.json()["run_id"]
        svc.run_reorder(old_id, db=db)

        from app.models.company import Company
        other = Company(id=str(uuid.uuid4()), code=f"RPRB1-{uuid.uuid4().hex[:8]}".upper(),
                        name="RPR route-test other company")
        db.add(other)
        db.flush()
        db.execute(text("UPDATE scm.reorder_run SET company_id = :cid WHERE id = :id"),
                   {"cid": other.id, "id": old_id})
        db.flush()

        res = c.post(f"/api/v1/scm/reorder-runs/{old_id}/replan", json={
            "warehouse_codes": [], "product_codes": [], "plan_horizon_date": None,
        })
    assert res.status_code == 404


def test_superseded_by_run_id_and_needs_recheck_reach_the_wire(scm_app):
    """The two facts the Header tab and the Lines tab respectively read off the run over
    HTTP: `superseded_by_run_id` on the OLD run's `GET`, and `needs_recheck` on the
    changed-suggestion row of the NEW run's recommendations."""
    app, db = _client(scm_app, "purchasing")
    p = _seed(db, "D1")
    with TestClient(app) as c:
        launch = c.post("/api/v1/scm/reorder-runs", json={"warehouse_codes": [p["warehouse_code"]]})
        old_id = launch.json()["run_id"]
        svc.run_reorder(old_id, db=db)

        old_rec = c.get(f"/api/v1/scm/reorder-runs/{old_id}/recommendations",
                        params={"page": 1, "limit": 50, "type": "buy"}).json()["data"][0]
        decided = c.post(f"/api/v1/scm/recommendations/{old_rec['id']}/decision", json={
            "kind": "buy", "buy_qty": old_rec["order_qty"],
        })
        assert decided.status_code == 200, decided.text

        # Raise committed demand so the next run's suggestion genuinely changes.
        from app.models.order import SalesOrder, SalesOrderLine
        so = SalesOrder(id=str(uuid.uuid4()), so_number=f"RPRTESTSO-{uuid.uuid4().hex[:8]}",
                        status="open", demand_class="retail")
        db.add(so)
        db.flush()
        db.add(SalesOrderLine(
            id=str(uuid.uuid4()), sales_order_id=so.id, product_id=p["product_id"],
            warehouse_id=p["warehouse_id"], qty_ordered=500, qty_delivered=0, line_status="open",
        ))
        db.flush()

        replan = c.post(f"/api/v1/scm/reorder-runs/{old_id}/replan", json={
            "warehouse_codes": [p["warehouse_code"]], "product_codes": [], "plan_horizon_date": None,
        })
        new_id = replan.json()["run_id"]
        svc.run_reorder(new_id, db=db)

        old_status = c.get(f"/api/v1/scm/reorder-runs/{old_id}")
        assert old_status.json()["superseded_by_run_id"] == new_id

        new_recs = c.get(f"/api/v1/scm/reorder-runs/{new_id}/recommendations",
                         params={"page": 1, "limit": 50, "type": "buy"}).json()["data"]
        row = next(r for r in new_recs if r["sku"] == p["product_code"])
        assert row["needs_recheck"] is True
