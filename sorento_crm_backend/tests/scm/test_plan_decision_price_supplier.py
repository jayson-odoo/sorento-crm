"""AC-R13 / AC-R14 - the price and the supplier are the buyer's to change.

> "on the plan row the Suggested price pill becomes a switch (Use last price / Ask new
>  price), the Suggested supplier a select over the product's suppliers"

Both ride on the row's own decision (`scm.plan_row_decision.price_mode` /
`supplier_id` / `unit_cost`) and both flow into the draft PO the plan confirms.
Switching the supplier re-reads THAT supplier's last price and lead time off the
recommendation's frozen alternatives.

No UUID crosses the wire: the decision is recorded against a supplier CODE, the same
way a stock take names a warehouse code.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.inventory import Stock
from app.services.error_handler import AppException
from app.services.scm import decision_service as dsvc
from app.services.scm import reorder_run_service as run_svc
from tests.scm.conftest import requires_pg, set_plan_grain
from tests.scm.test_m4_cash import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


def _mk_stock(db, pid, wid, qty):
    db.add(Stock(id=str(uuid.uuid4()), product_id=pid, warehouse_id=wid,
                 quantity_on_hand=qty))
    db.flush()


def _supplier_code(db, sid: str) -> str:
    return db.execute(text("SELECT supplier_code FROM suppliers WHERE id = :s"),
                      {"s": sid}).scalar()


def _two_supplier_buy(db, wid_code, product_code):
    """A buy row whose product has TWO linked suppliers: a cheap primary and a dearer
    one with a longer lead. The engine proposes the primary; the buyer may not agree."""
    wid = _mk_warehouse(db, wid_code)
    pid = _mk_product(db, product_code)
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    primary = _mk_supplier(db, f"R13 Primary {product_code}")
    other = _mk_supplier(db, f"R13 Other {product_code}")
    _link(db, pid, primary, cost=60, lead=30, primary=True)
    _link(db, pid, other, cost=85, lead=45, primary=False)
    db.flush()

    set_plan_grain(db, "location")
    # G1/G10 (`PLAN-scm-reorder-oi-feedback-1sep.md`): the daily run plans committed
    # demand only; `product_codes` names the SKU (G10) - this fixture builds a plain
    # stock-shortage buy off `demand_stat`, not a committed order.
    created = run_svc.create_run(db, [wid_code], "warehouse",
                                 product_codes=[product_code], enqueue=False)
    assert run_svc.run_reorder(created["run_id"], db=db)["status"] == "completed"
    rec = db.execute(text(
        "SELECT id::text AS id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": created["run_id"], "p": pid}).mappings().first()
    assert rec is not None, "fixture must produce a buy row"
    return {
        "run_id": created["run_id"], "rec_id": rec["id"], "product_id": pid,
        "primary_id": primary, "other_id": other,
        "primary_code": _supplier_code(db, primary),
        "other_code": _supplier_code(db, other),
    }


def _decision_row(db, rec_id):
    return db.execute(text(
        "SELECT kind, buy_qty, price_mode, supplier_id::text AS supplier_id, unit_cost "
        "FROM scm.plan_row_decision WHERE recommendation_id = :r"
    ), {"r": rec_id}).mappings().first()


def _draft_line(db, rec_id):
    return db.execute(text(
        "SELECT pol.qty_ordered, pol.unit_cost, po.supplier_id::text AS supplier_id "
        "FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE pol.source_ref = :r"), {"r": rec_id}).mappings().first()


# ===========================================================================
# AC-R13 - the price switch
# ===========================================================================

def test_ask_new_price_records_the_mode_and_leaves_the_line_unpriced(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R13W-ASK", "R13P-ASK")

    out = dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        price_mode="ask_new",
    )
    assert out["price_mode"] == "ask_new"
    assert out["unit_cost"] is None

    dsvc.confirm_decisions(db, w["run_id"], ids=None, actor="tester")
    line = _draft_line(db, w["rec_id"])
    assert line is not None
    assert line["unit_cost"] is None, "a price still to be asked is not a price"


def test_use_last_price_costs_the_row_and_the_draft_po_line(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R13W-USE", "R13P-USE")

    dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        price_mode="ask_new",
    )
    out = dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        price_mode="use_last",
    )

    assert out["price_mode"] == "use_last"
    assert out["unit_cost"] == 60.0
    row = _decision_row(db, w["rec_id"])
    assert row["price_mode"] == "use_last"
    assert float(row["unit_cost"]) == 60.0

    dsvc.confirm_decisions(db, w["run_id"], ids=None, actor="tester")
    line = _draft_line(db, w["rec_id"])
    assert float(line["unit_cost"]) == 60.0


def test_a_decision_defaults_to_the_last_price(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R13W-DEF", "R13P-DEF")

    out = dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 10, [], None, [], None, "tester")

    assert out["price_mode"] == "use_last"
    assert out["unit_cost"] == 60.0


def test_an_unknown_price_mode_is_refused(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R13W-BAD", "R13P-BAD")

    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(
            db, w["rec_id"], "buy", 10, [], None, [], None, "tester",
            price_mode="haggle")


# ===========================================================================
# AC-R14 - the supplier select
# ===========================================================================

def test_switching_the_supplier_rereads_its_price_and_lead_time(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R14W-SWAP", "R14P-SWAP")

    out = dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        supplier_code=w["other_code"],
    )

    assert out["supplier_code"] == w["other_code"]
    assert out["unit_cost"] == 85.0
    assert out["lead_time_days"] == 45.0
    row = _decision_row(db, w["rec_id"])
    assert row["supplier_id"] == w["other_id"]


def test_the_draft_po_goes_to_the_chosen_supplier(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R14W-PO", "R14P-PO")

    dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        supplier_code=w["other_code"],
    )
    dsvc.confirm_decisions(db, w["run_id"], ids=None, actor="tester")

    line = _draft_line(db, w["rec_id"])
    assert line["supplier_id"] == w["other_id"]
    assert float(line["unit_cost"]) == 85.0


def test_leaving_the_supplier_alone_keeps_the_engines_choice(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R14W-KEEP", "R14P-KEEP")

    dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester")
    dsvc.confirm_decisions(db, w["run_id"], ids=None, actor="tester")

    line = _draft_line(db, w["rec_id"])
    assert line["supplier_id"] == w["primary_id"]


def test_a_supplier_switch_survives_a_reconfirm(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R14W-RECON", "R14P-RECON")

    dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        supplier_code=w["other_code"])
    dsvc.confirm_decisions(db, w["run_id"], ids=None, actor="tester")
    dsvc.confirm_decisions(db, w["run_id"], ids=None, actor="tester")

    lines = db.execute(text(
        "SELECT COUNT(*) FROM purchase_order_lines WHERE source_ref = :r"),
        {"r": w["rec_id"]}).scalar()
    assert lines == 1, "reconfirming reconciles the line, it never duplicates it"
    assert _draft_line(db, w["rec_id"])["supplier_id"] == w["other_id"]


def test_the_run_list_carries_the_price_mode_and_supplier(scm_app):
    _, db, _, _ = scm_app
    w = _two_supplier_buy(db, "R14W-LIST", "R14P-LIST")

    dsvc.record_plan_row_decision(
        db, w["rec_id"], "buy", 120, [], None, [], None, "tester",
        price_mode="ask_new", supplier_code=w["other_code"])

    listed = dsvc.list_plan_row_decisions(db, w["run_id"])
    entry = next(d for d in listed["data"] if d["recommendation_id"] == w["rec_id"])

    assert entry["price_mode"] == "ask_new"
    assert entry["supplier_code"] == w["other_code"]
    assert entry["unit_cost"] is None


# ===========================================================================
# the route forwards what the buyer chose (found in the browser, 27 Aug: the POST
# carried price_mode / supplier_code and returned 200, the row kept the defaults)
# ===========================================================================

def test_the_route_forwards_price_mode_supplier_and_unit_cost(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_plan_row_decision import _client

    app, db = _client(scm_app, "purchasing")
    w = _two_supplier_buy(db, "R14W-ROUTE", "R14P-ROUTE")
    db.commit()

    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{w['rec_id']}/decision",
            json={
                "kind": "buy",
                "buy_qty": 120,
                "price_mode": "ask_new",
                "supplier_code": w["other_code"],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["price_mode"] == "ask_new"
        assert body["supplier_code"] == w["other_code"]

    db.expire_all()
    row = _decision_row(db, w["rec_id"])
    assert row["price_mode"] == "ask_new"
    assert row["supplier_id"] == w["other_id"]
