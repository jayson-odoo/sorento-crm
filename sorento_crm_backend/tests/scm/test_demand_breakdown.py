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


def _so(db, pid, wid, qty, *, order_type="project", number=None,
        customer_id=None, debtor_code=None, unit_price=None):
    soid = str(uuid.uuid4())
    # S13b: a project-class order is committed demand only when the Order Inquiry
    # created or named it (`is_plan_demand_order()` / `scm.committed_v`). This test is
    # about which orders a buy is built from, not the project/retail split, so stamp
    # the origin whenever the demand_class is "project" or the row never counts.
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_type, demand_class, "
        "demand_origin, customer_id, debtor_code, created_at, updated_at) "
        "VALUES (:i, :n, 'open', :t, :t, :o, :c, :d, now(), now())"
    ), {"i": soid, "n": number or f"ZZTSO-{soid[:8]}", "t": order_type,
        "o": "scm_order_inquiry" if order_type == "project" else None,
        "c": customer_id, "d": debtor_code})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, unit_price, line_status, "
        "purchasing_status, created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, :q, :q, 0, :up, 'open', 'needs_purchase', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid, "q": qty, "up": unit_price})


def _customer(db, code, name):
    cid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO customers (id, customer_code, customer_name, is_active, "
        "created_at, updated_at) VALUES (:i, :c, :n, true, now(), now())"
    ), {"i": cid, "c": code, "n": name})
    return cid


def _run(db, codes):
    created = svc.create_run(db, codes, enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    return created["run_id"]


def _rec_row(db, run_id, pid, wid=None):
    """The recommendation for this product, optionally pinned to ONE location.

    Pinned wherever the scope is what is under test: a pool emits a row per member, and
    "whichever row came back first" is exactly the ambiguity these tests exist to remove.
    """
    sql = ("SELECT id::text AS id, warehouse_id::text AS warehouse_id, inputs "
           "FROM scm.reorder_recommendation "
           "WHERE run_id = :r AND product_id = :p AND rec_type IN ('buy','covered')")
    params = {"r": run_id, "p": pid}
    if wid is not None:
        sql += " AND warehouse_id = :w"
        params["w"] = wid
    row = db.execute(text(sql + " LIMIT 1"), params).mappings().first()
    assert row is not None
    return row


def _rec(db, codes, pid):
    return str(_rec_row(db, _run(db, codes), pid)["id"])


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


# --- the popover is scoped like the row (AC-1) ------------------------------------

def _two_bin_pool(db, tag):
    """Two locations in one pool, one product, open demand at each."""
    root = _mk_warehouse(db, f"ZZTW-{tag}-R")
    bin_ = _mk_warehouse(db, f"ZZTW-{tag}-B")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
               {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-{tag}-{uuid.uuid4().hex[:6]}")
    for wid in (root, bin_):
        _mk_stock(db, pid, wid, 0)
        _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, root, 40, number=f"ZZTSO-{tag}-R")
    _so(db, pid, bin_, 60, number=f"ZZTSO-{tag}-B")
    _link(db, pid, _mk_supplier(db, f"ZZT {tag} Supplier"), moq=None, mult=None)
    db.flush()
    return root, bin_, pid


def test_with_pooled_netting_off_the_popover_is_the_rows_own_warehouse(scm_app):
    """AC-1.1: the row is a product AT a location, and so is the list behind it.

    The plan netted each bin on its own, so a list that also names the sibling's orders
    describes a quantity this row was never sized against - and the total under the
    header would not be the SO figure printed on the row.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    root, bin_, pid = _two_bin_pool(db, "SCOPE1")

    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE1-R", "ZZTW-SCOPE1-B"]), pid, wid=root)
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "warehouse"
    assert out["pool_code"] is None
    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-SCOPE1-R"]
    assert out["committed_total"] == float(rec["inputs"]["committed"]) == 40.0


def test_with_pooled_netting_on_the_popover_names_the_pool_it_was_netted_over(scm_app):
    """AC-1.2: when the plan DID net the pool, the pool is what is listed, and said."""
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    root, bin_, pid = _two_bin_pool(db, "SCOPE2")

    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE2-R", "ZZTW-SCOPE2-B"]), pid)
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "pool"
    assert out["pool_code"] == "ZZTW-SCOPE2-R", "the pool root, which is what was netted"
    assert sorted(l["so_number"] for l in out["lines"]) == [
        "ZZTSO-SCOPE2-B", "ZZTSO-SCOPE2-R",
    ]
    assert out["committed_total"] == 100.0


def test_the_row_carrying_unlocated_demand_still_lists_it(scm_app):
    """AC-1.1: narrowing the scope must not drop the demand nobody located.

    It was attributed to exactly this row by the engine, so it belongs in this list -
    and the total has to keep matching the row's own committed figure.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    wid = _mk_warehouse(db, "ZZTW-SCOPE3")
    pid = _mk_product(db, f"ZZTP-SCOPE3-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 10, number="ZZTSO-SCOPE3-LOC")
    _so(db, pid, None, 90, number="ZZTSO-SCOPE3-NOLOC")
    _link(db, pid, _mk_supplier(db, "ZZT Scope3 Supplier"), moq=None, mult=None)
    db.flush()

    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE3"]), pid, wid=wid)
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "warehouse"
    assert out["committed_total"] == float(rec["inputs"]["committed"]) == 100.0
    assert [l["is_unlocated"] for l in out["lines"] if l["so_number"].endswith("NOLOC")] \
        == [True]


# --- who ordered it, and at what price (AC-1.4 / AC-4.2) --------------------------

def test_every_line_names_who_ordered_it_however_little_the_order_says(scm_app):
    """AC-4.3: customer name, then the debtor code, then the honest absence.

    "Unnamed customer" told the buyer nothing and was wrong twice over: an order with a
    debtor code IS attributable, and an order with neither is a fact about the order.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    wid = _mk_warehouse(db, "ZZTW-WHO")
    pid = _mk_product(db, f"ZZTP-WHO-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    cid = _customer(db, "ZZT-C001", "Vivo Homes Sdn Bhd")
    _so(db, pid, wid, 5, number="ZZTSO-WHO-NAMED", customer_id=cid,
        debtor_code="ZZT-C001", unit_price=94.5)
    _so(db, pid, wid, 6, number="ZZTSO-WHO-DEBTOR", debtor_code="300-R009")
    _so(db, pid, wid, 7, number="ZZTSO-WHO-NOBODY")
    _link(db, pid, _mk_supplier(db, "ZZT Who Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-WHO"], pid))
    label = {l["so_number"]: l["customer_label"] for l in out["lines"]}
    price = {l["so_number"]: l["unit_price"] for l in out["lines"]}

    assert label["ZZTSO-WHO-NAMED"] == "Vivo Homes Sdn Bhd"
    assert label["ZZTSO-WHO-DEBTOR"] == "Debtor 300-R009"
    assert label["ZZTSO-WHO-NOBODY"] == "No customer on order"
    assert price["ZZTSO-WHO-NAMED"] == 94.5
    assert price["ZZTSO-WHO-DEBTOR"] is None, "a line with no price says nothing, not 0"
