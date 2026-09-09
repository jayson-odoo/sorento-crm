"""S4 (PLAN-reorder-feedback-9sep.md) - the sales-order window gains a START date.

`plan_horizon_date` ("Plan until") has always been end-only; this adds
`plan_horizon_start` beside it on `CreateReorderRunRequest`/`ReplanReorderRunRequest`/
`ReorderRun`, applied on every leg `horizon_committed_select_sql` already horizons
(AC-S4.1/S4.2/S4.3/S4.6). G2 (9 Sep ruling): undated demand always stays in, the same
reading the end date already gives it.

Harness copied from `tests/scm/test_m3_run.py` (`scm_app`, `_client`, the raw-SQL
builders) and `tests/scm/test_plan_horizon_review_fixes.py` (the horizon-only fixture
shape) - both already exercise `plan_horizon_date`. Postgres only, every row
marker-prefixed and seeded fresh; nothing borrowed off the shared prod-copy DB.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

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


def _so(db, pid, wid, qty, *, number, required_date=None, order_type="retail"):
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_type, demand_class, "
        "created_at, updated_at) VALUES (:i, :n, 'open', :t, :t, now(), now())"
    ), {"i": soid, "n": number, "t": order_type})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, required_date, line_status, "
        "purchasing_status, created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, :q, :q, 0, :rd, 'open', 'needs_purchase', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid, "q": qty, "rd": required_date})
    return soid


def _committed_for(db, run_id, pid) -> float:
    row = db.execute(text(
        "SELECT inputs FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type IN ('buy', 'covered') LIMIT 1"
    ), {"r": run_id, "p": pid}).mappings().first()
    assert row is not None, "expected a recommendation row for the product"
    return float((row["inputs"] or {}).get("committed") or 0)


# --- AC-S4.1: start must not be after end ------------------------------------------

def test_start_after_end_is_refused_with_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, "ZZTHW-VAL")
    pid = _mk_product(db, "ZZTHP-VAL")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, "ZZT Horizon Val Supplier"))
    db.flush()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": ["ZZTHW-VAL"],
            "plan_horizon_start": "2026-06-01",
            "plan_horizon_date": "2026-01-01",
        })

    assert resp.status_code == 422, resp.text


# --- AC-S4.2/S4.6: a run created with a START date excludes an earlier-dated line --

def test_run_with_start_only_excludes_an_earlier_dated_line_but_keeps_a_later_one(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTHW-START")
    pid = _mk_product(db, "ZZTHP-START")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 40, number="ZZTHSO-BEFORE", required_date=date(2025, 12, 1))
    _so(db, pid, wid, 25, number="ZZTHSO-AFTER", required_date=date(2026, 6, 1))
    _link(db, pid, _mk_supplier(db, "ZZT Horizon Start Supplier"))
    db.flush()

    created = svc.create_run(
        db, ["ZZTHW-START"], enqueue=False, plan_horizon_start=date(2026, 1, 1),
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], pid) == 25.0, (
        "the 2025 line must be excluded by the start; the June line stays in"
    )


def test_a_line_with_no_required_date_stays_in_under_a_start(scm_app):
    """G2, 9 Sep ruling: undated demand is never dropped by a start date."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTHW-UNDATED")
    pid = _mk_product(db, "ZZTHP-UNDATED")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 15, number="ZZTHSO-UNDATED", required_date=None)
    _link(db, pid, _mk_supplier(db, "ZZT Horizon Undated Supplier"))
    db.flush()

    created = svc.create_run(
        db, ["ZZTHW-UNDATED"], enqueue=False, plan_horizon_start=date(2026, 1, 1),
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], pid) == 15.0


def test_run_with_both_start_and_end_narrows_to_the_window(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTHW-BOTH")
    pid = _mk_product(db, "ZZTHP-BOTH")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 10, number="ZZTHSO-EARLY", required_date=date(2025, 1, 1))
    _so(db, pid, wid, 20, number="ZZTHSO-INSIDE", required_date=date(2026, 6, 1))
    _so(db, pid, wid, 900, number="ZZTHSO-LATE", required_date=date(2030, 1, 1))
    _link(db, pid, _mk_supplier(db, "ZZT Horizon Both Supplier"))
    db.flush()

    created = svc.create_run(
        db, ["ZZTHW-BOTH"], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], pid) == 20.0


# --- AC-S4.1: ReorderRunStatusResponse ("ReorderRunOut") carries plan_horizon_start -

def test_run_status_response_carries_plan_horizon_start(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, "ZZTHW-OUT")
    pid = _mk_product(db, "ZZTHP-OUT")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, "ZZT Horizon Out Supplier"))
    db.flush()

    with TestClient(app) as c:
        launch = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": ["ZZTHW-OUT"],
            "plan_horizon_start": "2026-01-01",
        })
        assert launch.status_code == 202, launch.text
        run_id = launch.json()["run_id"]

        status = c.get(f"/api/v1/scm/reorder-runs/{run_id}")
        assert status.status_code == 200, status.text
        body = status.json()

    assert body.get("plan_horizon_start") == "2026-01-01"


# --- AC-S4.3: Re-plan carries a changed start ----------------------------------------

def test_replan_carries_a_changed_start_onto_the_new_run(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTHW-REPLAN")
    pid = _mk_product(db, "ZZTHP-REPLAN")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, "ZZT Horizon Replan Supplier"))
    db.flush()

    old = svc.create_run(db, ["ZZTHW-REPLAN"], enqueue=False)
    svc.run_reorder(old["run_id"], db=db)

    new = svc.replan_run(
        db, old["run_id"], warehouse_codes=["ZZTHW-REPLAN"], product_codes=[],
        plan_horizon_date=None, plan_horizon_start=date(2026, 3, 1), actor="tester",
    )

    stamped = db.execute(text(
        "SELECT plan_horizon_start FROM scm.reorder_run WHERE id = :r"
    ), {"r": new["run_id"]}).scalar()
    assert stamped == date(2026, 3, 1)
