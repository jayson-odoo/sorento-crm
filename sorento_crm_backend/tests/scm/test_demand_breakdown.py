"""Which orders a planned buy is actually for.

> "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh"

Pooled netting is the answer, and it is invisible from the row. This lists the orders the
quantity was built from, including the ones that named no location.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.scm import demand_breakdown_service as dbs
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link, _mk_demand, _mk_product, _mk_stock, _mk_supplier, _mk_warehouse,
)

pytestmark = requires_pg


def _so(db, pid, wid, qty, *, order_type="project", number=None):
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_type, demand_class, "
        "created_at, updated_at) VALUES (:i, :n, 'open', :t, :t, now(), now())"
    ), {"i": soid, "n": number or f"ZZTSO-{soid[:8]}", "t": order_type})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, :q, :q, 0, 'open', 'needs_purchase', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid, "q": qty})


def _rec(db, codes, pid):
    created = svc.create_run(db, codes, enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    row = db.execute(text(
        "SELECT id::text AS id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type IN ('buy','covered') LIMIT 1"
    ), {"r": created["run_id"], "p": pid}).mappings().first()
    assert row is not None
    return str(row["id"])


def test_a_pooled_buy_names_the_bin_the_order_was_actually_for(scm_app):
    _, db, _, _ = scm_app
    root = _mk_warehouse(db, "ZZTW-ROOT2")
    bin_ = _mk_warehouse(db, "ZZTW-BIN2")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
               {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-BRK-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 0)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _so(db, pid, bin_, 40, number="ZZTSO-BIN")
    _link(db, pid, _mk_supplier(db, "ZZT Brk Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-ROOT2", "ZZTW-BIN2"], pid))

    assert out["committed_total"] == 40.0
    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-BIN"]
    assert out["locations"] == ["ZZTW-BIN2"], "the bin the order named, not the pool root"


def test_it_says_which_orders_named_no_location(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-BRK3")
    pid = _mk_product(db, f"ZZTP-BRK3-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 10, number="ZZTSO-LOC")
    _so(db, pid, None, 90, number="ZZTSO-NOLOC")
    _link(db, pid, _mk_supplier(db, "ZZT Brk3 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-BRK3"], pid))

    assert out["committed_total"] == 100.0
    assert out["unlocated_total"] == 90.0
    assert any(l["is_unlocated"] for l in out["lines"])
    assert "No location" in out["locations"]


def test_it_reports_the_order_class_so_project_and_retail_are_distinguishable(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-BRK4")
    pid = _mk_product(db, f"ZZTP-BRK4-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 5, order_type="project", number="ZZTSO-PRJ")
    _so(db, pid, wid, 7, order_type="retail", number="ZZTSO-RTL")
    _link(db, pid, _mk_supplier(db, "ZZT Brk4 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-BRK4"], pid))

    assert {l["order_type"] for l in out["lines"]} == {"project", "retail"}


def test_an_unknown_recommendation_reports_nothing_rather_than_failing(scm_app):
    _, db, _, _ = scm_app
    out = dbs.demand_for_recommendation(db, str(uuid.uuid4()))
    assert out["lines"] == [] and out["committed_total"] == 0.0
