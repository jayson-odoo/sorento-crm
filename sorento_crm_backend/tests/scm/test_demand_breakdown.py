"""Which orders a planned buy is actually for.

> "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh"

Pooled netting is the answer, and it is invisible from the row. This lists the orders the
quantity was built from, including the ones that named no location.
"""
from __future__ import annotations

import uuid
from datetime import date

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
        customer_id=None, debtor_code=None, unit_price=None, required_date=None):
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
        "qty_ordered, qty_required, qty_delivered, unit_price, required_date, line_status, "
        "purchasing_status, created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, :q, :q, 0, :up, :rd, 'open', 'needs_purchase', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid, "q": qty, "up": unit_price,
        "rd": required_date})


def _customer(db, code, name, company_id=None):
    cid = str(uuid.uuid4())
    if company_id is None:
        db.execute(text(
            "INSERT INTO customers (id, customer_code, customer_name, is_active, "
            "created_at, updated_at) VALUES (:i, :c, :n, true, now(), now())"
        ), {"i": cid, "c": code, "n": name})
    else:
        db.execute(text(
            "INSERT INTO customers (id, customer_code, customer_name, is_active, "
            "company_id, created_at, updated_at) "
            "VALUES (:i, :c, :n, true, :co, now(), now())"
        ), {"i": cid, "c": code, "n": name, "co": company_id})
    return cid


def _company(db, name):
    """Another company, so a cross-company `customer_id` can be built at all."""
    coid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO companies (id, name, code, is_active, created_at) "
        "VALUES (:i, :n, :c, true, now())"
    ), {"i": coid, "n": name, "c": f"ZZTCO-{coid[:8]}"})
    return coid


def _run(db, codes):
    created = svc.create_run(db, codes, enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    return created["run_id"]


def _rec_row(db, run_id, pid, wid=None):
    """The recommendation for this product, optionally pinned to ONE location.

    Pinned wherever the scope is what is under test: a pool emits a row per member, and
    "whichever row came back first" is exactly the ambiguity these tests exist to remove.
    """
    sql = ("SELECT id::text AS id, warehouse_id::text AS warehouse_id, rec_type, inputs "
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


def _three_bin_pool(db, tag):
    """Three locations in one pool, one product, open demand at each.

    Returned in the order the run is asked to plan them, so a test can plan two and leave
    the third out of the run entirely.
    """
    root = _mk_warehouse(db, f"ZZTW-{tag}-R")
    bin_ = _mk_warehouse(db, f"ZZTW-{tag}-B")
    spare = _mk_warehouse(db, f"ZZTW-{tag}-X")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id IN (:b, :x)"),
               {"r": root, "b": bin_, "x": spare})
    pid = _mk_product(db, f"ZZTP-{tag}-{uuid.uuid4().hex[:6]}")
    for wid in (root, bin_, spare):
        _mk_stock(db, pid, wid, 0)
        _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, root, 40, number=f"ZZTSO-{tag}-R")
    _so(db, pid, bin_, 60, number=f"ZZTSO-{tag}-B")
    _so(db, pid, spare, 25, number=f"ZZTSO-{tag}-X")
    _link(db, pid, _mk_supplier(db, f"ZZT {tag} Supplier"), moq=None, mult=None)
    db.flush()
    return root, bin_, spare, pid


def test_the_pool_listed_is_the_part_of_it_the_run_actually_planned(scm_app):
    """AC-1.2: the members are the ones the ENGINE netted, not every sibling on the site.

    The engine groups the rows it planned; a run scoped to two bins nets those two. Reading
    the pool off `warehouses` instead adds a location the run never looked at, so the total
    under the header exceeds the demand the buy was sized against - the same "why so many"
    the popover exists to answer, reintroduced by the explanation itself.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    root, bin_, _spare, pid = _three_bin_pool(db, "SCOPE4")

    run_id = _run(db, ["ZZTW-SCOPE4-R", "ZZTW-SCOPE4-B"])
    rec = _rec_row(db, run_id, pid)
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "pool"
    assert sorted(l["so_number"] for l in out["lines"]) == [
        "ZZTSO-SCOPE4-B", "ZZTSO-SCOPE4-R",
    ], "the bin the run never planned is not part of this row's demand"
    assert out["locations"] == ["ZZTW-SCOPE4-B", "ZZTW-SCOPE4-R"]
    planned_committed = db.execute(text(
        "SELECT COALESCE(SUM((inputs->>'committed')::numeric), 0) "
        "FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": run_id, "p": pid}).scalar()
    assert out["committed_total"] == float(planned_committed) == 100.0


def test_one_planned_bin_in_a_pool_is_scoped_as_the_warehouse_it_is(scm_app):
    """The engine's own `len(members) == 1` branch: a pool of one is not a pool.

    With a single planned location there is nothing to net against, so calling the scope
    "pool" would claim a netting decision that never happened and would list a sibling's
    orders under a row that was sized without them.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    _root, bin_, _spare, pid = _three_bin_pool(db, "SCOPE5")

    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE5-B"]), pid, wid=bin_)
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "warehouse"
    assert out["pool_code"] is None
    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-SCOPE5-B"]
    assert out["committed_total"] == float(rec["inputs"]["committed"]) == 60.0


# --- the scope is the RUN's, so a later policy edit cannot move it ----------------

def test_a_pooled_row_keeps_its_pool_after_pooled_netting_is_turned_off(scm_app):
    """The row was planned under pooled netting, and a config change is not retroactive.

    Reading `pool_netting` at popover time described this row by a rule it was never
    planned under: the same recommendation reported a pool one day and a single bin the
    next, while its own frozen numbers had not moved. The run says what it netted, so the
    run is what is read.

    The header total stays the pool's, which is the quantity the buy was sized against;
    each pooled row's own `committed` is its share of it (`_emit_pool` copies the member's
    figure onto the member's row).
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    _root, _bin, pid = _two_bin_pool(db, "SCOPE6")
    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE6-R", "ZZTW-SCOPE6-B"]), pid)

    # The buyer turns pooled netting off the day after the run.
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "pool"
    assert out["pool_code"] == "ZZTW-SCOPE6-R"
    assert sorted(l["so_number"] for l in out["lines"]) == [
        "ZZTSO-SCOPE6-B", "ZZTSO-SCOPE6-R",
    ]
    assert out["committed_total"] == 100.0


def test_a_per_warehouse_row_keeps_its_own_bin_after_pooled_netting_is_turned_on(scm_app):
    """The mirror: a row netted per location does not acquire its siblings' orders.

    This is the direction that bites, because pooled netting is off by default and almost
    every warehouse carries a pool pointer - turning the switch on would otherwise have
    re-described every past row as a pool and printed a total larger than the SO figure on
    the row itself.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    root, _bin, pid = _two_bin_pool(db, "SCOPE7")
    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE7-R", "ZZTW-SCOPE7-B"]), pid, wid=root)

    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "warehouse"
    assert out["pool_code"] is None
    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-SCOPE7-R"]
    assert out["committed_total"] == float(rec["inputs"]["committed"]) == 40.0


def test_a_pooled_covered_row_lists_the_pool_its_own_figure_came_from(scm_app):
    """The pool's stock covers its demand, so the pool gets ONE row and no buy split.

    `_emit_pool` writes an allocation only when it buys, so this row names its siblings
    nowhere - and it sits on the pool root carrying the POOL's committed. Reading the
    scope off the row's own frozen `committed` is what keeps the two agreeing: without it
    the row printed 100 committed above a list of 40, which is the popover contradicting
    the row it hangs on.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    root = _mk_warehouse(db, "ZZTW-SCOPE8-R")
    bin_ = _mk_warehouse(db, "ZZTW-SCOPE8-B")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
               {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-SCOPE8-{uuid.uuid4().hex[:6]}")
    # Held at the root, ordered for both: the pool covers itself, so nothing is bought.
    _mk_stock(db, pid, root, 500)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _so(db, pid, root, 40, number="ZZTSO-SCOPE8-R")
    _so(db, pid, bin_, 60, number="ZZTSO-SCOPE8-B")
    _link(db, pid, _mk_supplier(db, "ZZT Scope8 Supplier"), moq=None, mult=None)
    db.flush()

    rec = _rec_row(db, _run(db, ["ZZTW-SCOPE8-R", "ZZTW-SCOPE8-B"]), pid)
    assert rec["rec_type"] == "covered", "the pool covered its own demand"
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "pool"
    assert out["pool_code"] == "ZZTW-SCOPE8-R"
    assert sorted(l["so_number"] for l in out["lines"]) == [
        "ZZTSO-SCOPE8-B", "ZZTSO-SCOPE8-R",
    ]
    assert out["committed_total"] == float(rec["inputs"]["committed"]) == 100.0


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


def test_every_line_carries_the_core_sos_own_id_for_the_record_link(scm_app):
    """21 Aug follow-up: "SO numbers in both views become hyperlinks to the sales
    order's own record" - `so_id` is the CORE `sales_orders.id`, the same id
    `/scm/sales-orders/{id}` (and `SalesOrdersList`'s own row link) already keys on -
    never the recommendation id, the product id, or any other uuid on the row."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-SOID")
    pid = _mk_product(db, f"ZZTP-SOID-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 5, number="ZZTSO-SOID-SHEET")
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=8)
    _link(db, pid, _mk_supplier(db, "ZZT Soid Supplier"), moq=None, mult=None)
    db.flush()

    real_so_id = db.execute(text(
        "SELECT id FROM sales_orders WHERE so_number = 'ZZTSO-SOID-SHEET'"
    )).scalar()
    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-SOID"], pid))

    by_number = {l["so_number"]: l for l in out["lines"]}
    assert by_number["ZZTSO-SOID-SHEET"]["so_id"] == str(real_so_id)
    confirmed = [l for l in out["lines"] if l["source"] == "order_inquiry_confirmed"][0]
    assert confirmed["so_id"] is not None
    assert confirmed["so_id"] != confirmed.get("so_number")


def test_a_customer_row_of_another_company_never_names_this_order(scm_app):
    """The label join is a raw `LEFT JOIN customers`, so it crosses the company boundary
    unless the join says otherwise - and naming another company's buyer on this company's
    order is a disclosure, not a display bug. The honest answer is the code the document
    printed."""
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    wid = _mk_warehouse(db, "ZZTW-XCO")
    pid = _mk_product(db, f"ZZTP-XCO-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    foreign = _customer(db, "ZZT-XCO1", "Other Company Sdn Bhd",
                        company_id=_company(db, "ZZT Other Co"))
    _so(db, pid, wid, 5, number="ZZTSO-XCO", customer_id=foreign,
        debtor_code="ZZT-XCO1")
    _so(db, pid, wid, 6, number="ZZTSO-XCO-BARE", customer_id=foreign)
    _link(db, pid, _mk_supplier(db, "ZZT Xco Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-XCO"], pid))
    label = {l["so_number"]: l["customer_label"] for l in out["lines"]}

    assert label["ZZTSO-XCO"] == "Debtor ZZT-XCO1"
    assert label["ZZTSO-XCO-BARE"] == "No customer on order"


# --- provenance: which feed a line came off, and the top-level channel totals -----
# (20 Aug live ask - "for project is order inquiry, for retail is sales order directly")

def test_a_sheet_leg_line_is_tagged_order_inquiry(scm_app):
    """`demand_origin='scm_order_inquiry'` on the order is what makes a project-class
    line count at all (S13b) - and it is also what earns it the `order_inquiry` tag."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-SRC1")
    pid = _mk_product(db, f"ZZTP-SRC1-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 12, order_type="project", number="ZZTSO-SRC1")
    _link(db, pid, _mk_supplier(db, "ZZT Src1 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-SRC1"], pid))

    assert len(out["lines"]) == 1
    assert out["lines"][0]["source"] == "order_inquiry"


def test_a_direct_so_line_is_tagged_sales_order(scm_app):
    """"for dealer side is exactly based on the sales order" - a retail-class line off the
    ordinary book, no sheet involved, is tagged `sales_order`."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-SRC2")
    pid = _mk_product(db, f"ZZTP-SRC2-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 9, order_type="retail", number="ZZTSO-SRC2")
    _link(db, pid, _mk_supplier(db, "ZZT Src2 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-SRC2"], pid))

    assert len(out["lines"]) == 1
    assert out["lines"][0]["source"] == "sales_order"


def test_a_confirmed_oi_leg_line_appears_exactly_once_tagged_confirmed(scm_app):
    """Front planning section 4 / `scm.committed_v`'s own two-leg split, mirrored here: a
    confirmed decision's Buy residual is the ONLY reading of that line - the sheet leg the
    core order might otherwise have produced never shows beside it (would double-count)."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-SRC3")
    pid = _mk_product(db, f"ZZTP-SRC3-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=8)
    _link(db, pid, _mk_supplier(db, "ZZT Src3 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-SRC3"], pid))

    confirmed = [l for l in out["lines"] if l["source"] == "order_inquiry_confirmed"]
    assert len(confirmed) == 1
    assert confirmed[0]["qty"] == 8
    assert confirmed[0]["demand_class"] == "project"
    # The sheet leg for the SAME core order does not also appear - once, not twice.
    assert len(out["lines"]) == 1


def test_the_top_level_totals_sum_the_lines_by_channel(scm_app):
    """`project_total` / `retail_total` / `unclassified_total` are drawn off the SAME
    lines the popover lists, over every source - sheet, direct SO, and confirmed OI."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-SRC4")
    pid = _mk_product(db, f"ZZTP-SRC4-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 7, order_type="retail", number="ZZTSO-SRC4-R")
    _so(db, pid, wid, 3, order_type=None, number="ZZTSO-SRC4-U")
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=8)
    _link(db, pid, _mk_supplier(db, "ZZT Src4 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-SRC4"], pid))

    assert out["project_total"] == 8.0
    assert out["retail_total"] == 7.0
    assert out["unclassified_total"] == 3.0
    assert out["project_total"] + out["retail_total"] + out["unclassified_total"] == sum(
        l["qty"] for l in out["lines"]
    )


# --- SF-1 / SF-2: totals stay uncapped past `limit`, on BOTH legs -----------------

def test_sf1_shown_and_total_respect_the_cap_on_both_legs(scm_app):
    """SF-1: the confirmed OI leg had NO `LIMIT` at all while the sheet leg capped at
    `limit` - so past the cap `total`/`shown` disagreed with what was actually returned.
    `limit=2` against 3 rows on EACH leg pins that both legs are now capped the same way,
    and that `total` still counts every row that exists, not just the ones shown."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-CAP1")
    pid = _mk_product(db, f"ZZTP-CAP1-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 5, order_type="retail", number="ZZTSO-CAP1-R1")
    _so(db, pid, wid, 6, order_type="retail", number="ZZTSO-CAP1-R2")
    _so(db, pid, wid, 4, order_type=None, number="ZZTSO-CAP1-R3")
    for _ in range(3):
        _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=3)
    _link(db, pid, _mk_supplier(db, "ZZT Cap1 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-CAP1"], pid), limit=2)

    sheet_shown = [l for l in out["lines"] if l["source"] != "order_inquiry_confirmed"]
    confirmed_shown = [l for l in out["lines"] if l["source"] == "order_inquiry_confirmed"]
    assert len(sheet_shown) == 2, "sheet leg still capped at limit"
    assert len(confirmed_shown) == 2, "confirmed leg is now capped at limit too"
    assert out["shown"] == 4 == len(out["lines"])
    assert out["total"] == 6, "3 sheet rows + 3 confirmed rows, uncapped"


def test_sf2_channel_totals_are_read_off_the_uncapped_set(scm_app):
    """SF-2: `project_total`/`retail_total`/`unclassified_total`/`committed_total` were
    summed off the CAPPED line list - past `limit` they undercounted. `limit=2` against
    more lines than that on each channel (and on the confirmed leg) pins that the totals
    still reflect every line that exists."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-CAP2")
    pid = _mk_product(db, f"ZZTP-CAP2-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 5, order_type="retail", number="ZZTSO-CAP2-R1")
    _so(db, pid, wid, 6, order_type="retail", number="ZZTSO-CAP2-R2")
    _so(db, pid, wid, 4, order_type=None, number="ZZTSO-CAP2-U1")
    for _ in range(3):
        _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=3)
    _link(db, pid, _mk_supplier(db, "ZZT Cap2 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-CAP2"], pid), limit=2)

    assert out["shown"] == 4, "the sanity check: this is deliberately less than the totals"
    assert out["retail_total"] == 11.0, "5 + 6, both retail lines, though only 2 are shown"
    assert out["unclassified_total"] == 4.0
    assert out["project_total"] == 9.0, "3 confirmed rows x 3, though only 2 are shown"
    assert out["committed_total"] == 24.0, "15 sheet + 9 confirmed, all uncapped"
    assert (
        out["project_total"] + out["retail_total"] + out["unclassified_total"]
        == out["committed_total"]
    )


# =============================================================================
# S1 (review fix) - the drill speaks the SAME horizon the run itself was sized against
# =============================================================================

def test_drill_matches_the_frozen_row_under_a_horizon(scm_app):
    """Before threading the run's `plan_horizon_date` through, the drill compared a LIVE
    UNHORIZONED total against the FROZEN, HORIZONED `inputs.committed` the run actually
    sized the row against. A line dated well past the horizon inflated the live sum past
    the frozen figure, so `committed_total` (and the lines list) stopped summing to the
    row - the exact drift the scope test exists to prevent."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-HZN1")
    pid = _mk_product(db, f"ZZTP-HZN1-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 40, order_type="retail", number="ZZTSO-HZN-NEAR",
        required_date=date(2026, 6, 1))
    # Horizoned OUT of the run's own committed figure - must be horizoned out of the
    # drill too, or the drill disagrees with the row that opened it.
    _so(db, pid, wid, 900, order_type="retail", number="ZZTSO-HZN-FAR",
        required_date=date(2030, 1, 1))
    _link(db, pid, _mk_supplier(db, "ZZT Hzn1 Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-HZN1"], enqueue=False,
                             plan_horizon_date=date(2026, 12, 31))
    svc.run_reorder(created["run_id"], db=db)
    rec = _rec_row(db, created["run_id"], pid, wid)
    assert float((rec["inputs"] or {}).get("committed")) == 40.0, (
        "the run's own frozen committed figure must already exclude the 2030 line"
    )

    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "warehouse", "a single unpooled location - never mislabelled pool"
    assert out["committed_total"] == 40.0, "must match the run's own horizoned figure"
    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-HZN-NEAR"], (
        "the far-dated line must not appear in the drill either"
    )


def test_drill_keeps_a_horizoned_pool_row_from_reading_as_a_sibling_pool(scm_app):
    """S1's own example: a pooled row, sized by the run under a horizon. Without the
    fix, a beyond-horizon line at the row's OWN location inflates `total_for([wid])`
    past the frozen `committed`, and the scope test falls through toward the pool
    reading - the row's popover would then list a SIBLING warehouse's orders."""
    _, db, _, _ = scm_app
    root = _mk_warehouse(db, "ZZTW-HZNROOT")
    bin_ = _mk_warehouse(db, "ZZTW-HZNBIN")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
              {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-HZNPOOL-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 0)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _so(db, pid, bin_, 40, number="ZZTSO-HZNBIN-NEAR", required_date=date(2026, 6, 1))
    _so(db, pid, bin_, 900, number="ZZTSO-HZNBIN-FAR", required_date=date(2030, 1, 1))
    _link(db, pid, _mk_supplier(db, "ZZT HznPool Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-HZNROOT", "ZZTW-HZNBIN"], enqueue=False,
                             plan_horizon_date=date(2026, 12, 31))
    svc.run_reorder(created["run_id"], db=db)
    rec = _rec_row(db, created["run_id"], pid, bin_)

    out = dbs.demand_for_recommendation(db, str(rec["id"]))

    assert out["scope"] == "warehouse", (
        "the row's own location reproduces the frozen figure once horizoned; it must "
        "never be mislabelled pool and list the root's unrelated orders"
    )
    assert out["locations"] == ["ZZTW-HZNBIN"]
    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-HZNBIN-NEAR"]


# =============================================================================
# 20 Aug live diagnosis - defect A: a `channel` trigger opens ONLY that channel
# =============================================================================
#
# "i think it would be easier if we can just put the icon at project and retail
# separately then we don't need the open SOs" (captain's own preferred fix). Before this,
# ONE popover hung off the Project cell and listed every channel - a Retail-chipped SO
# under the Project number read as retail counted as project, though both figures were
# always correct (committed_v's own split).

def _committed_v_split(db, pid, wid):
    row = db.execute(text(
        "SELECT COALESCE(project_committed, 0) AS project_committed, "
        "       COALESCE(retail_committed, 0) AS retail_committed, "
        "       COALESCE(unclassified_committed, 0) AS unclassified_committed "
        "FROM scm.committed_v WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).mappings().first()
    if row is None:
        return {"project_committed": 0.0, "retail_committed": 0.0,
                "unclassified_committed": 0.0}
    return {k: float(v or 0) for k, v in row.items()}


def test_channel_filter_returns_only_that_channels_lines_and_matches_committed_v(scm_app):
    """A channel trigger's list must contain ONLY that channel's lines, and its total must
    be the SAME figure `scm.committed_v` (and the row's own `project_committed` etc.)
    already report - never a mix, and never a different number from the row it hangs on."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-CHFLT")
    pid = _mk_product(db, f"ZZTP-CHFLT-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 5, order_type="project", number="ZZTSO-CHFLT-PRJ")
    _so(db, pid, wid, 7, order_type="retail", number="ZZTSO-CHFLT-RTL")
    _so(db, pid, wid, 3, order_type=None, number="ZZTSO-CHFLT-UNC")
    _link(db, pid, _mk_supplier(db, "ZZT Chflt Supplier"), moq=None, mult=None)
    db.flush()
    rec_id = _rec(db, ["ZZTW-CHFLT"], pid)

    project = dbs.demand_for_recommendation(db, rec_id, channel="project")
    retail = dbs.demand_for_recommendation(db, rec_id, channel="retail")
    unclassified = dbs.demand_for_recommendation(db, rec_id, channel="unclassified")

    assert [l["so_number"] for l in project["lines"]] == ["ZZTSO-CHFLT-PRJ"]
    assert {l["demand_class"] for l in project["lines"]} == {"project"}
    assert [l["so_number"] for l in retail["lines"]] == ["ZZTSO-CHFLT-RTL"]
    assert {l["demand_class"] for l in retail["lines"]} == {"retail"}
    assert [l["so_number"] for l in unclassified["lines"]] == ["ZZTSO-CHFLT-UNC"]
    assert unclassified["lines"][0]["demand_class"] is None

    assert project["channel"] == "project"
    assert retail["channel"] == "retail"
    assert unclassified["channel"] == "unclassified"

    split = _committed_v_split(db, pid, wid)
    assert project["committed_total"] == split["project_committed"] == 5.0
    assert retail["committed_total"] == split["retail_committed"] == 7.0
    assert unclassified["committed_total"] == split["unclassified_committed"] == 3.0


def test_an_unrecognised_channel_is_unfiltered(scm_app):
    """Contract: unfiltered is the DEFAULT, not an error - so a caller that predates the
    field, or a bad value, sees exactly what an omitted `channel` always has."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-CHFLT2")
    pid = _mk_product(db, f"ZZTP-CHFLT2-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 5, order_type="project", number="ZZTSO-CHFLT2-PRJ")
    _so(db, pid, wid, 7, order_type="retail", number="ZZTSO-CHFLT2-RTL")
    _link(db, pid, _mk_supplier(db, "ZZT Chflt2 Supplier"), moq=None, mult=None)
    db.flush()
    rec_id = _rec(db, ["ZZTW-CHFLT2"], pid)

    unfiltered = dbs.demand_for_recommendation(db, rec_id)
    bogus = dbs.demand_for_recommendation(db, rec_id, channel="dealer")

    assert unfiltered["channel"] is None
    assert bogus["channel"] is None
    assert sorted(l["so_number"] for l in bogus["lines"]) == sorted(
        l["so_number"] for l in unfiltered["lines"]
    )
    assert bogus["committed_total"] == unfiltered["committed_total"] == 12.0


def test_a_channel_filter_on_a_pooled_row_keeps_the_pool_scope(scm_app):
    """The scope decision (warehouse vs pool) must be resolved off the UNFILTERED total -
    a channel is a display slice of an already-scoped row, never a second opinion on which
    locations it was netted over. Filtering to retail (a channel with only ONE line, at
    ONE of the two pool members) must not make a pooled row read as its own warehouse."""
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    root, bin_, pid = _two_bin_pool(db, "CHFLT3")
    # `_two_bin_pool` already raises project-class orders at both members; add one
    # retail-class line at a SINGLE member so the retail channel has exactly one line.
    _so(db, pid, bin_, 15, order_type="retail", number="ZZTSO-CHFLT3-RTL")
    db.flush()

    rec = _rec_row(db, _run(db, ["ZZTW-CHFLT3-R", "ZZTW-CHFLT3-B"]), pid)
    retail = dbs.demand_for_recommendation(db, str(rec["id"]), channel="retail")

    assert retail["scope"] == "pool", (
        "the row was netted over the pool; a channel filter must not relabel that"
    )
    assert retail["pool_code"] == "ZZTW-CHFLT3-R"
    assert [l["so_number"] for l in retail["lines"]] == ["ZZTSO-CHFLT3-RTL"]


def test_a_retail_channel_filter_excludes_the_confirmed_oi_leg(scm_app):
    """The confirmed leg is entirely project-class by construction (S13b) - a retail or
    unclassified channel must come back with none of it, not an empty-but-still-queried
    leg."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-CHFLT4")
    pid = _mk_product(db, f"ZZTP-CHFLT4-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 6, order_type="retail", number="ZZTSO-CHFLT4-RTL")
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=8)
    _link(db, pid, _mk_supplier(db, "ZZT Chflt4 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-CHFLT4"], pid), channel="retail")

    assert [l["source"] for l in out["lines"]] == ["sales_order"]
    assert out["committed_total"] == 6.0


# =============================================================================
# 20 Aug live diagnosis - defect B: the "OI" chip must not promise an empty worklist
# =============================================================================
#
# `source == "order_inquiry"` is a permanent stamp on the ORDER (`demand_origin`), made at
# creation and never cleared once CS works through every inquiry row off it. `has_inquiry_row`
# is the fact that actually says whether the Order Inquiry worklist has something to open for
# THIS line right now (measured live: 605 core orders carry the stamp, 7 still have a row).

def test_a_sheet_leg_line_with_no_inquiry_row_says_so(scm_app):
    """The common case (598 of 605, measured): the order was created by the OI import, but
    every row off it is long gone. The chip's underlying fact must read false, not assume
    true from the stamp alone."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-OIROW1")
    pid = _mk_product(db, f"ZZTP-OIROW1-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wid, 12, order_type="project", number="ZZTSO-OIROW1")
    _link(db, pid, _mk_supplier(db, "ZZT Oirow1 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-OIROW1"], pid))

    assert len(out["lines"]) == 1
    assert out["lines"][0]["source"] == "order_inquiry"
    assert out["lines"][0]["has_inquiry_row"] is False


def test_a_sheet_leg_line_with_a_live_inquiry_row_says_so(scm_app):
    """The rare case (7 of 605): a row genuinely exists for this line, and has not (yet)
    been confirmed - only an ACTIVE decision's Buy pulls a line out of the sheet leg
    (`PLAN_DEMAND_LINE_SQL`), so a `superseded` decision leaves the sheet-leg line in
    place, sitting beside the row that is its real evidence."""
    from app.models.order import SalesOrder, SalesOrderLine
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-OIROW2")
    pid = _mk_product(db, f"ZZTP-OIROW2-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    so = SalesOrder(id=str(uuid.uuid4()), so_number="ZZTSO-OIROW2", status="open",
                    demand_class="project", demand_origin="scm_order_inquiry")
    db.add(so)
    db.flush()
    core_line = SalesOrderLine(id=str(uuid.uuid4()), sales_order_id=so.id, product_id=pid,
                               warehouse_id=wid, qty_ordered=20, qty_delivered=0,
                               line_status="open")
    db.add(core_line)
    db.flush()
    # A decision that is NOT active leaves the sheet-leg line alone, while the helper
    # still writes the `projects.order_inquiry_rows` row - exactly the "row exists, but
    # not (yet) confirmed" case the chip has to tell apart from "no row at all".
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=20,
                   decision_state="superseded", core_line=core_line)
    _link(db, pid, _mk_supplier(db, "ZZT Oirow2 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-OIROW2"], pid))

    assert len(out["lines"]) == 1
    assert out["lines"][0]["source"] == "order_inquiry"
    assert out["lines"][0]["has_inquiry_row"] is True


# =============================================================================
# 21 Aug live diagnosis - defect C: who sold it, and the top product-grain row's own drill
# =============================================================================
#
# "for project, what's the sales order for the past year, who is the customer and agent...
# and of course the price" - the agent is the `sales_agents` master
# (`sales_orders.sales_agent_id`), never invented when the order carries none.

def _agent(db, code, person_label=None):
    from app.models.sales_agent import SalesAgent

    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, person_label=person_label)
    db.add(row)
    db.flush()
    return row.id


def test_a_line_names_the_agent_who_sold_it_when_the_order_carries_one(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-AGT1")
    pid = _mk_product(db, f"ZZTP-AGT1-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    aid = _agent(db, f"ZZT-AGT-{uuid.uuid4().hex[:6]}", person_label="ZZT Jeremy")
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_type, demand_class, "
        "demand_origin, sales_agent_id, created_at, updated_at) "
        "VALUES (:i, :n, 'open', 'retail', 'retail', NULL, :a, now(), now())"
    ), {"i": str(uuid.uuid4()), "n": "ZZTSO-AGT1-NAMED", "a": aid})
    so_id = db.execute(text(
        "SELECT id FROM sales_orders WHERE so_number = 'ZZTSO-AGT1-NAMED'"
    )).scalar()
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, 5, 5, 0, 'open', 'needs_purchase', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": so_id, "p": pid, "w": wid})
    _so(db, pid, wid, 6, order_type="retail", number="ZZTSO-AGT1-BARE")
    _link(db, pid, _mk_supplier(db, "ZZT Agt1 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-AGT1"], pid))
    agent = {l["so_number"]: l["agent_label"] for l in out["lines"]}

    assert agent["ZZTSO-AGT1-NAMED"] == "ZZT Jeremy", "person_label wins when a human set it"
    assert agent["ZZTSO-AGT1-BARE"] is None, "an order with no agent is honestly absent"


def test_a_confirmed_leg_line_also_names_its_agent_and_price(scm_app):
    """The confirmed leg reads the SAME agent/price columns off the core order the sheet
    leg does - `so.sales_agent_id` and `sol`/`psl.unit_price` - so the drill answers "who
    sold it, at what price" the same way on both legs."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-AGT2")
    pid = _mk_product(db, f"ZZTP-AGT2-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    aid = _agent(db, f"ZZT-AGT2-{uuid.uuid4().hex[:6]}")
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=8,
                   sales_agent_id=aid, unit_price="12.50")
    _link(db, pid, _mk_supplier(db, "ZZT Agt2 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-AGT2"], pid))

    confirmed = [l for l in out["lines"] if l["source"] == "order_inquiry_confirmed"]
    assert len(confirmed) == 1
    assert confirmed[0]["agent_label"] is not None, "the code itself, absent a person_label"
    assert confirmed[0]["unit_price"] == 12.5


# --- the product-grain top row's own drill (scope="product") ----------------------
#
# "put the same per-channel drill trigger... on the TOP row's three channel cells,
# product grain and location grain alike" - a grouped product row sums every
# recommendation the run wrote for the product; its own drill has to union the same set.

def test_scope_product_unions_every_recommendation_of_the_product_in_the_run(scm_app):
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    wa = _mk_warehouse(db, "ZZTW-PWIDE-A")
    wb = _mk_warehouse(db, "ZZTW-PWIDE-B")
    pid = _mk_product(db, f"ZZTP-PWIDE-{uuid.uuid4().hex[:6]}")
    for wid in (wa, wb):
        _mk_stock(db, pid, wid, 0)
        _mk_demand(db, pid, wid, 0.0)
    _so(db, pid, wa, 5, order_type="project", number="ZZTSO-PWIDE-A")
    _so(db, pid, wb, 7, order_type="retail", number="ZZTSO-PWIDE-B")
    _link(db, pid, _mk_supplier(db, "ZZT Pwide Supplier"), moq=None, mult=None)
    db.flush()

    run_id = _run(db, ["ZZTW-PWIDE-A", "ZZTW-PWIDE-B"])
    rec_a = _rec_row(db, run_id, pid, wid=wa)

    row_scope = dbs.demand_for_recommendation(db, str(rec_a["id"]))
    product_scope = dbs.demand_for_recommendation(db, str(rec_a["id"]), scope="product")

    assert [l["so_number"] for l in row_scope["lines"]] == ["ZZTSO-PWIDE-A"], (
        "the row's own scope is unaffected by the new parameter's default"
    )
    assert sorted(l["so_number"] for l in product_scope["lines"]) == [
        "ZZTSO-PWIDE-A", "ZZTSO-PWIDE-B",
    ]
    assert product_scope["scope"] == "product"
    assert product_scope["pool_code"] is None
    assert product_scope["committed_total"] == 12.0
    assert sorted(product_scope["locations"]) == ["ZZTW-PWIDE-A", "ZZTW-PWIDE-B"]


def test_scope_product_still_gives_each_sibling_its_own_pool(scm_app):
    """A sibling that was ITSELF pooled contributes its whole pool, not just its own
    cell - the union is of NETTED SETS, not of bare warehouse ids."""
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    root, bin_, pid = _two_bin_pool(db, "PWIDE2")
    lone = _mk_warehouse(db, "ZZTW-PWIDE2-LONE")
    _mk_stock(db, pid, lone, 0)
    _mk_demand(db, pid, lone, 0.0)
    _so(db, pid, lone, 15, order_type="retail", number="ZZTSO-PWIDE2-LONE")
    db.flush()

    run_id = _run(db, ["ZZTW-PWIDE2-R", "ZZTW-PWIDE2-B", "ZZTW-PWIDE2-LONE"])
    rec_pool = _rec_row(db, run_id, pid)
    rec_lone = _rec_row(db, run_id, pid, wid=lone)

    out = dbs.demand_for_recommendation(db, str(rec_pool["id"]), scope="product")

    assert sorted(l["so_number"] for l in out["lines"]) == [
        "ZZTSO-PWIDE2-B", "ZZTSO-PWIDE2-LONE", "ZZTSO-PWIDE2-R",
    ]
    assert sorted(out["locations"]) == [
        "ZZTW-PWIDE2-B", "ZZTW-PWIDE2-LONE", "ZZTW-PWIDE2-R",
    ]
    assert str(rec_lone["id"]) != str(rec_pool["id"])


# --- the trailing-window order-history section (AC point 3) -----------------------
#
# "for project, what's the sales order for the past year... for retail, past 3 months...
# including delivered ones" - fed by the same window `demand_context_for_product`
# already computes the 12m/3m totals from, as a second section alongside the open-demand
# lines rather than folded into them.

def test_history_lines_include_delivered_orders_within_the_window(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-HIST1")
    pid = _mk_product(db, f"ZZTP-HIST1-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    aid = _agent(db, f"ZZT-HIST-{uuid.uuid4().hex[:6]}")
    # A fully DELIVERED project order, inside the trailing window - invisible to the
    # open-demand `lines` (line_status/qty_delivered exclude it) but must appear here.
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_type, demand_class, "
        "demand_origin, sales_agent_id, order_date, created_at, updated_at) "
        "VALUES (:i, :n, 'open', 'project', 'project', 'scm_order_inquiry', :a, "
        "CURRENT_DATE - INTERVAL '2 months', now(), now())"
    ), {"i": str(uuid.uuid4()), "n": "ZZTSO-HIST1-DELIVERED", "a": aid})
    so_id = db.execute(text(
        "SELECT id FROM sales_orders WHERE so_number = 'ZZTSO-HIST1-DELIVERED'"
    )).scalar()
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_delivered, unit_price, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, 20, 20, 45.0, 'closed', 'covered', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": so_id, "p": pid, "w": wid})
    # A separate, still-OPEN line so the run actually writes a recommendation for this
    # product - the delivered order above carries zero open demand on its own.
    _so(db, pid, wid, 1, order_type="project", number="ZZTSO-HIST1-OPEN")
    _link(db, pid, _mk_supplier(db, "ZZT Hist1 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-HIST1"], pid), channel="project")

    assert [l["so_number"] for l in out["lines"]] == ["ZZTSO-HIST1-OPEN"], (
        "the delivered order is not OPEN demand"
    )
    hist = {l["so_number"]: l for l in out["history_lines"]}
    assert "ZZTSO-HIST1-DELIVERED" in hist
    assert hist["ZZTSO-HIST1-DELIVERED"]["delivered"] is True
    assert hist["ZZTSO-HIST1-DELIVERED"]["qty"] == 20.0
    assert hist["ZZTSO-HIST1-DELIVERED"]["unit_price"] == 45.0
    assert hist["ZZTSO-HIST1-DELIVERED"]["agent_label"] is not None
    assert hist["ZZTSO-HIST1-DELIVERED"]["so_id"] == str(so_id)
    assert out["history_shown"] == len(out["history_lines"])
    assert out["history_total"] == out["history_shown"], "uncapped == capped, well under limit"


def test_history_lines_are_empty_off_the_window_and_off_unclassified(scm_app):
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-HIST2")
    pid = _mk_product(db, f"ZZTP-HIST2-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    # Outside even the 12-month project window.
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_type, demand_class, "
        "demand_origin, order_date, created_at, updated_at) "
        "VALUES (:i, :n, 'open', 'project', 'project', 'scm_order_inquiry', "
        "CURRENT_DATE - INTERVAL '3 years', now(), now())"
    ), {"i": str(uuid.uuid4()), "n": "ZZTSO-HIST2-OLD"})
    so_id = db.execute(text(
        "SELECT id FROM sales_orders WHERE so_number = 'ZZTSO-HIST2-OLD'"
    )).scalar()
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_delivered, line_status, purchasing_status, created_at, updated_at) "
        "VALUES (:i, :so, :p, :w, 20, 20, 'closed', 'covered', now(), now())"
    ), {"i": str(uuid.uuid4()), "so": so_id, "p": pid, "w": wid})
    # A separate, still-OPEN line so the run actually writes a recommendation for this
    # product - the 3-year-old order above carries zero open demand on its own.
    _so(db, pid, wid, 1, order_type="project", number="ZZTSO-HIST2-OPEN")
    _link(db, pid, _mk_supplier(db, "ZZT Hist2 Supplier"), moq=None, mult=None)
    db.flush()
    rec_id = _rec(db, ["ZZTW-HIST2"], pid)

    old_line = dbs.demand_for_recommendation(db, rec_id, channel="project")
    unfiltered = dbs.demand_for_recommendation(db, rec_id)
    unclassified = dbs.demand_for_recommendation(db, rec_id, channel="unclassified")

    assert old_line["history_lines"] == [], "outside the 12-month project window"
    assert unfiltered["history_lines"] == [], "no channel picked - no window to speak of"
    assert unclassified["history_lines"] == [], "unclassified has no configured window"


def test_a_confirmed_leg_line_always_has_an_inquiry_row(scm_app):
    """The confirmed leg is BUILT from a live row (S13b) - `has_inquiry_row` is trivially
    true, and the worklist link must never be gated off it for this source."""
    from tests.scm.test_channel_read_model import _confirmed_leg

    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-OIROW3")
    pid = _mk_product(db, f"ZZTP-OIROW3-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=8)
    _link(db, pid, _mk_supplier(db, "ZZT Oirow3 Supplier"), moq=None, mult=None)
    db.flush()

    out = dbs.demand_for_recommendation(db, _rec(db, ["ZZTW-OIROW3"], pid))

    confirmed = [l for l in out["lines"] if l["source"] == "order_inquiry_confirmed"]
    assert len(confirmed) == 1
    assert confirmed[0]["has_inquiry_row"] is True
