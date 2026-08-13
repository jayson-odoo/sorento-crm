"""Demand with no stated location nets, instead of nothing.

> "all SO line should have warehouse one, no warehouse we can just put it under net"

`scm.committed_v` groups an unlocated line under a NULL warehouse key, and
`scm.net_position_v` then joins that key to itself with `=`, which is never true for NULL.
So the quantity was netted against nothing anywhere and the product never reached a plan.
1,130,402 units on the customer's book.

It now lands on the location holding the most of that item - where the goods would actually
ship from - and is stamped on the row so the plan can say which part of a buy came from
demand nobody located.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


def _so_line(db, pid: str, wid: str | None, qty: float) -> None:
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, source_system, source_ref, "
        "created_at, updated_at) "
        "VALUES (:id, :num, 'open', 'scm_order_inquiry', 'order_inquiry', now(), now())"
    ), {"id": soid, "num": f"ZZTSO-{soid[:8]}"})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:id, :so, :p, :w, :q, :q, 0, 'open', 'needs_purchase', now(), now())"
    ), {"id": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid, "q": qty})


def _recs(db, run_id: str, pid: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT rec_type, warehouse_id, rounded_qty, inputs "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": pid}).mappings().all()]


def test_unlocated_demand_reaches_the_plan(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-UNLOC")
    pid = _mk_product(db, f"ZZTP-UNLOC-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 10)
    _mk_demand(db, pid, wid, 0.0)
    _so_line(db, pid, None, 400)          # no location at all
    _link(db, pid, _mk_supplier(db, "ZZT Unloc Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-UNLOC"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid)
    assert rows, "demand with no location must still produce a recommendation"
    buys = [r for r in rows if r["rec_type"] == "buy"]
    assert buys, "400 committed against 10 on hand is a shortage, so it is a buy"
    assert float(buys[0]["rounded_qty"]) >= 390


def test_the_plan_says_how_much_of_it_nobody_located(scm_app):
    # A buy part-built from demand nobody located is the part most likely to be wrong, so
    # the row carries the figure rather than presenting all of it as confirmed.
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-STAMP")
    pid = _mk_product(db, f"ZZTP-STAMP-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so_line(db, pid, None, 250)
    _link(db, pid, _mk_supplier(db, "ZZT Stamp Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-STAMP"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    row = _recs(db, created["run_id"], pid)[0]
    assert float(row["inputs"]["unlocated_demand"]) == 250.0


def test_it_lands_where_the_goods_are_not_spread_across_every_location(scm_app):
    # Netting it against every location would count the same 300 units several times over
    # and inflate the buy. It belongs to one place: the one holding the item.
    _, db, _, _ = scm_app
    big = _mk_warehouse(db, "ZZTW-BIG")
    small = _mk_warehouse(db, "ZZTW-SMALL")
    pid = _mk_product(db, f"ZZTP-LAND-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, big, 900)
    _mk_stock(db, pid, small, 5)
    _mk_demand(db, pid, big, 0.0)
    _mk_demand(db, pid, small, 0.0)
    _so_line(db, pid, None, 300)
    _link(db, pid, _mk_supplier(db, "ZZT Land Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-BIG", "ZZTW-SMALL"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    stamped = [r for r in _recs(db, created["run_id"], pid)
               if (r["inputs"] or {}).get("unlocated_demand")]
    assert len(stamped) == 1, "the demand lands once, not once per location"
    assert str(stamped[0]["warehouse_id"]) == big, "on the location holding the item"


def test_900_on_hand_against_300_unlocated_is_a_suggestion_not_a_purchase(scm_app):
    # The two rules meet here: the demand is now visible AND the stock covers it, so the
    # planner is shown the choice rather than either outcome being taken for them.
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-COVUN")
    pid = _mk_product(db, f"ZZTP-COVUN-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 900)
    _mk_demand(db, pid, wid, 0.0)
    _so_line(db, pid, None, 300)
    _link(db, pid, _mk_supplier(db, "ZZT Covun Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-COVUN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid)
    covered = [r for r in rows if r["rec_type"] == "covered"]
    assert covered, "visible demand that stock covers is a suggestion"
    assert float(covered[0]["inputs"]["covered_committed"]) == 300.0


def test_a_located_line_is_not_counted_twice(scm_app):
    # Only lines with no warehouse are moved. A line that already names one is netted where
    # it says, and adding it again would double the demand.
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-LOC")
    pid = _mk_product(db, f"ZZTP-LOC-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so_line(db, pid, wid, 60)            # located
    _link(db, pid, _mk_supplier(db, "ZZT Loc Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-LOC"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    row = _recs(db, created["run_id"], pid)[0]
    assert (row["inputs"] or {}).get("unlocated_demand") is None
    assert float(row["rounded_qty"] or 0) <= 60, "60 committed, never 120"
