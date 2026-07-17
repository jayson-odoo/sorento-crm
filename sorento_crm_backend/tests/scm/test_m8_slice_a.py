"""SCM M8 Slice A — explain drills on calculated numbers (read-only, no numeric write).

Three drills keyed to the M8 UAC:

  * M8-A1 — the Net drill lists the OPEN sales-order lines behind ``committed`` (SO
    number, qty, customer, order date), summing to the committed figure, and the four
    components satisfy ``on_hand + on_order - committed == net``. Endpoint
    ``GET /reorder-runs recommendations/{rec_id}/explain-net``.
  * M8-A2 — ``GET /analytics/explain/demand`` also carries ``demand_dos``: the delivery
    orders that drove the outflow in the window, as a navigable list; cancelled DOs are
    excluded and DOs outside the window are ignored.
  * M8-A3 — the recommendations grid row carries the FROZEN order-qty inputs
    (reorder_point / order_up_to / safety_stock / recommended_qty / rounded_qty) —
    already produced server-side; this pins the contract (NO backend change was needed).

DB-backed; reuse the ``scm_app`` savepoint fixture + the M4 seed helpers. Runs are
driven synchronously (``enqueue=False``). Everything is rolled back on teardown.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_m4_cash import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


# ===========================================================================
# controlled DB fixture builders (inside the savepoint)
# ===========================================================================

def _mk_customer(db, name: str) -> str:
    cid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO customers (id, customer_code, customer_name, customer_type, "
        "is_active, created_at) "
        "VALUES (:id, :code, :name, 'company', true, now())"
    ), {"id": cid, "code": f"M8C-{cid[:8]}", "name": name})
    return cid


def _mk_open_so(db, pid, wid, *, so_number, customer_id, qty_ordered,
                qty_delivered=0, status="open", order_date="2026-07-01"):
    """One sales order + a single line for `pid`×`wid` (feeds committed_v / net)."""
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, customer_id, order_date, status, "
        "created_at, updated_at) "
        "VALUES (:id, :num, :cid, :od, :st, now(), now())"
    ), {"id": soid, "num": so_number, "cid": customer_id, "od": order_date, "st": status})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_delivered, line_status, created_at, updated_at) "
        "VALUES (:id, :so, :p, :w, :qo, :qd, 'open', now(), now())"
    ), {"id": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid,
        "qo": qty_ordered, "qd": qty_delivered})
    return soid


def _mk_do(db, pid, wid, *, order_number, qty, order_date, is_cancelled=False):
    """A delivery order (orders + one order_line) — the demand outflow source."""
    oid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
        "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
        "created_at, updated_at) "
        "VALUES (:id, :num, :od, :cancel, false, 0, 0, 0, 0, false, now(), now())"
    ), {"id": oid, "num": order_number, "od": order_date, "cancel": is_cancelled})
    db.execute(text(
        "INSERT INTO order_lines (id, line_sequence, order_id, product_id, warehouse_id, "
        "quantity, created_at, updated_at) "
        "VALUES (:id, 1, :o, :p, :w, :q, now(), now())"
    ), {"id": str(uuid.uuid4()), "o": oid, "p": pid, "w": wid, "q": qty})
    return oid


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_buy_with_committed(db):
    """A low-stock buy SKU with TWO open SO lines (committed) + an on-order PO-less
    supplier link. Returns (warehouse_id, product_id, [so_numbers])."""
    wid = _mk_warehouse(db, "M8W-A")
    pid = _mk_product(db, "M8P-COMMIT")
    _mk_stock(db, pid, wid, 40)          # on_hand 40
    _mk_demand(db, pid, wid, 10.0)       # drives a buy (net < ROP)
    _link(db, pid, _mk_supplier(db, "M8 Supplier A"))

    c1 = _mk_customer(db, "Alpha Retail")
    c2 = _mk_customer(db, "Beta Trading")
    _mk_open_so(db, pid, wid, so_number="SO-M8-001", customer_id=c1,
                qty_ordered=12, order_date="2026-07-02")
    # partially delivered line — only the remainder (5) counts toward committed
    _mk_open_so(db, pid, wid, so_number="SO-M8-002", customer_id=c2,
                qty_ordered=8, qty_delivered=3, order_date="2026-07-05")
    db.flush()
    return wid, pid, ["SO-M8-001", "SO-M8-002"]


# ===========================================================================
# M8-A1 — Net drill lists committed SOs + net arithmetic
# ===========================================================================

def test_explain_net_lists_committed_sos_and_arithmetic(scm_app):
    """The net drill returns the four components + the open SO lines behind committed;
    the listed line qtys sum to committed, and on_hand + on_order - committed == net."""
    app, db = _client(scm_app, "purchasing")
    _, pid, so_numbers = _seed_buy_with_committed(db)
    created = svc.create_run(db, ["M8W-A"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rec_id = db.execute(text(
        "SELECT id FROM scm.reorder_recommendation WHERE run_id = :r AND rec_type = 'buy'"
    ), {"r": created["run_id"]}).scalar()
    assert rec_id, "run should produce a buy rec for the committed SKU"

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/recommendations/{rec_id}/explain-net")
        assert res.status_code == 200, res.text
        body = res.json()

    assert set(body) == {"on_hand", "on_order", "committed", "net", "committed_sos"}
    # committed = 12 (SO-001) + (8-3) (SO-002) = 17
    assert body["committed"] == pytest.approx(17.0)
    assert body["on_hand"] == pytest.approx(40.0)
    # net arithmetic holds (M8-A1)
    assert body["on_hand"] + body["on_order"] - body["committed"] == pytest.approx(body["net"])

    lines = body["committed_sos"]
    assert {l["so_number"] for l in lines} == set(so_numbers)
    # listed line qtys sum to committed
    assert sum(l["qty"] for l in lines) == pytest.approx(body["committed"])
    by_so = {l["so_number"]: l for l in lines}
    assert by_so["SO-M8-001"]["qty"] == pytest.approx(12.0)
    assert by_so["SO-M8-002"]["qty"] == pytest.approx(5.0)     # remainder only
    # human-readable, no UUIDs (M8-A6)
    assert by_so["SO-M8-001"]["customer_name"] == "Alpha Retail"
    assert by_so["SO-M8-002"]["customer_name"] == "Beta Trading"
    assert by_so["SO-M8-001"]["order_date"] == "2026-07-02"


def test_explain_net_empty_when_no_open_sos(scm_app):
    """A SKU with no open SO lines returns committed_sos=[] and committed 0 (M8-A1)."""
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, "M8W-NOSO")
    pid = _mk_product(db, "M8P-NOSO")
    _mk_stock(db, pid, wid, 20)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, "M8 Supplier NoSO"))
    db.flush()
    created = svc.create_run(db, ["M8W-NOSO"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rec_id = db.execute(text(
        "SELECT id FROM scm.reorder_recommendation WHERE run_id = :r AND rec_type = 'buy'"
    ), {"r": created["run_id"]}).scalar()

    with TestClient(app) as c:
        body = c.get(f"/api/v1/scm/recommendations/{rec_id}/explain-net").json()
    assert body["committed_sos"] == []
    assert body["committed"] == pytest.approx(0.0)
    assert body["on_hand"] + body["on_order"] - body["committed"] == pytest.approx(body["net"])


def test_explain_net_404_for_unknown_rec(scm_app):
    """An unknown recommendation id 404s (not a 500)."""
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/recommendations/{uuid.uuid4()}/explain-net")
    assert res.status_code == 404


def test_explain_net_denied_without_view_permission(scm_app):
    """Auth: the net drill needs scm.dashboard.view; a bare user is denied (M8 X-cut)."""
    app, _ = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/recommendations/{uuid.uuid4()}/explain-net")
    assert res.status_code == 403


# ===========================================================================
# M8-A2 — days-cover demand as a navigable DO list
# ===========================================================================

def test_explain_demand_carries_navigable_dos(scm_app):
    """explain_demand adds demand_dos: the DOs behind the outflow in the window, newest
    first, each with order id + DO number + date + qty out. Cancelled DOs and DOs
    outside the 90-day window are excluded; qty sums plausibly."""
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, "M8W-DEM")
    pid = _mk_product(db, "M8P-DEM")
    as_of = "2026-07-17"
    # two in-window DOs (drive the outflow)
    _mk_do(db, pid, wid, order_number="DO-M8-A", qty=6, order_date="2026-07-10")
    _mk_do(db, pid, wid, order_number="DO-M8-B", qty=4, order_date="2026-06-20")
    # a cancelled DO — excluded (M8-A2)
    _mk_do(db, pid, wid, order_number="DO-M8-CANCEL", qty=99,
           order_date="2026-07-11", is_cancelled=True)
    # a DO before the 90-day window — excluded
    _mk_do(db, pid, wid, order_number="DO-M8-OLD", qty=50, order_date="2026-01-01")
    db.flush()

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/analytics/explain/demand",
                    params={"product_id": pid, "warehouse_id": wid, "as_of": as_of})
        assert res.status_code == 200, res.text
        body = res.json()

    assert "demand_dos" in body
    nums = [d["do_number"] for d in body["demand_dos"]]
    assert nums == ["DO-M8-A", "DO-M8-B"]            # newest first, in-window only
    assert "DO-M8-CANCEL" not in nums and "DO-M8-OLD" not in nums
    first = body["demand_dos"][0]
    assert set(first) == {"order_id", "do_number", "order_date", "qty_out"}
    assert first["qty_out"] == pytest.approx(6.0)
    assert first["order_date"].startswith("2026-07-10")
    # the two in-window DOs sum to the total outflow (10 units)
    assert sum(d["qty_out"] for d in body["demand_dos"]) == pytest.approx(10.0)
    # the historical fields are still present (unchanged contract)
    assert "avg_daily_demand" in body and "demand_cv" in body and "buckets" in body


def test_explain_demand_denied_without_view_permission(scm_app):
    """Auth: the demand drill needs scm.dashboard.view; a bare user is denied."""
    app, _ = _client(scm_app, None)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/analytics/explain/demand",
                    params={"product_id": str(uuid.uuid4())})
    assert res.status_code == 403


# ===========================================================================
# M8-A3 — recommendations row carries the frozen order-qty inputs (NO code change)
# ===========================================================================

def test_recommendations_row_carries_frozen_order_qty_inputs(scm_app):
    """AC pin: the recommendations grid row already surfaces the engine's frozen
    order-qty derivation (reorder_point / order_up_to / safety_stock / recommended_qty /
    rounded_qty). No backend change was needed for M8-A3 — this asserts the contract."""
    app, db = _client(scm_app, "purchasing")
    _seed_buy_with_committed(db)
    created = svc.create_run(db, ["M8W-A"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rid = created["run_id"]

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{rid}/recommendations",
                    params={"type": "buy", "limit": 100})
        assert res.status_code == 200, res.text
        buys = [r for r in res.json()["data"] if r["type"] == "buy"]
    assert buys, "expected at least one buy row"
    row = buys[0]
    for field in ("reorder_point", "order_up_to", "safety_stock",
                  "recommended_qty", "order_qty"):
        assert field in row, f"row missing frozen input {field}"
        assert row[field] is not None, f"frozen input {field} should be populated"
    # order_qty (rounded_qty) is the post-rounding buy qty; recommended_qty is pre-round
    assert row["order_qty"] is not None and row["recommended_qty"] is not None
