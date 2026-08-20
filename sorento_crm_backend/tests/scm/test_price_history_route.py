"""The price-history ROUTE, not just the service (fix-cluster 2026-08-20).

`price_history_service.price_history_for_run` carries two codes the endpoint's own
serializer used to hand-whitelist away: `other_supplier_price` (we never bought this
from the run's chosen supplier, but we paid someone else) and `history_without_price`
(the structured PO/SPO extract names the document, date and quantity but no price). The
service-level tests in `test_price_history.py` already prove the SERVICE returns these
facts; this file proves they actually reach the HTTP response, since a hand-listed key
whitelist in the route drops anything not named regardless of what the service returns.

Everything runs inside the rolled-back savepoint the `scm_app` fixture provides.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZPHRT"


def _client(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _mk_product(db, code):
    """Seed the whole chain (category -> uom -> product), never borrowed with LIMIT 1."""
    cat_id, uom_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO product_categories (id, category_code, category_name) "
        "VALUES (:id, :c, :c)"
    ), {"id": cat_id, "c": f"{MARKER}-CAT-{cat_id[:8]}"})
    db.execute(text(
        "INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:id, :c, :c)"
    ), {"id": uom_id, "c": f"{MARKER}U{uom_id[:8]}"})
    pid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, cost_price, is_active, is_discontinued, currency, created_at, updated_at) "
        "VALUES (:id, :code, :name, :cat, :uom, 100, 60, true, false, 'MYR', now(), now())"
    ), {"id": pid, "code": code, "name": f"{MARKER} {code}", "cat": cat_id, "uom": uom_id})
    return pid


def _mk_supplier(db, code):
    sid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO suppliers (id, supplier_code, supplier_name) VALUES (:id, :c, :c)"
    ), {"id": sid, "c": f"{MARKER} {code}"})
    return sid


def _mk_warehouse(db, code):
    wid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, created_at, updated_at) "
        "VALUES (:id, :c, :c, true, true, now(), now())"
    ), {"id": wid, "c": f"{MARKER}-{code}-{uuid.uuid4().hex[:6]}"})
    return wid


def _add_po_line(db, supplier_id, product_id, warehouse_id, number, day, cost):
    pid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, supplier_id, issue_date, status, "
        "currency, source_system) VALUES (:id, :n, :s, :d, 'closed', 'USD', :src)"
    ), {"id": pid, "n": f"{MARKER}-{number}", "s": supplier_id, "d": day, "src": "scm_po_history"})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
        "VALUES (:id, :po, :p, :w, 40, 0, :c, 'USD', 'open')"
    ), {"id": str(uuid.uuid4()), "po": pid, "p": product_id, "w": warehouse_id, "c": cost})


def _mk_recommendation(db, run_id, product_id, warehouse_id, supplier_id):
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, supplier_id, rec_type, rounded_qty, "
        " recommended_qty, status, company_id, inputs) "
        "VALUES (:id, :r, :p, :w, :s, 'buy', 10, 10, 'proposed', :co, CAST(:inputs AS jsonb))"
    ), {"id": str(uuid.uuid4()), "r": run_id, "p": product_id, "w": warehouse_id,
        "s": supplier_id, "co": SORENTO_COMPANY_ID, "inputs": '{"committed": 10, "on_hand": 0}'})


def _world(db):
    """Two products, each recommended against a supplier with NO purchase of its own:

    - ``other_key``: another supplier HAS a priced purchase of the product -> `other_supplier_price`.
    - ``no_price_key``: the only purchase on record for the product carries no price
      (a 0.00 line, the structured-extract shape) -> `history_without_price`.
    """
    run_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now())"),
        {"id": run_id, "co": SORENTO_COMPANY_ID})

    wh = _mk_warehouse(db, "WH")

    other_product = _mk_product(db, f"{MARKER}-OTHER-{uuid.uuid4().hex[:6]}")
    other_chosen = _mk_supplier(db, "CHOSEN1")
    other_known = _mk_supplier(db, "KNOWN1")
    _mk_recommendation(db, run_id, other_product, wh, other_chosen)
    _add_po_line(db, other_known, other_product, wh, "OTHER", "2021-05-01", 15.5)

    nop_product = _mk_product(db, f"{MARKER}-NOPRICE-{uuid.uuid4().hex[:6]}")
    nop_chosen = _mk_supplier(db, "CHOSEN2")
    nop_seller = _mk_supplier(db, "SELLER2")
    _mk_recommendation(db, run_id, nop_product, wh, nop_chosen)
    _add_po_line(db, nop_seller, nop_product, wh, "NOPRICE", "2021-06-01", 0.0)

    db.flush()

    from app.models.procurement import Supplier

    known_supplier = db.query(Supplier).filter(Supplier.id == other_known).one()
    chosen1 = db.query(Supplier).filter(Supplier.id == other_chosen).one()
    chosen2 = db.query(Supplier).filter(Supplier.id == nop_chosen).one()

    return {
        "run_id": run_id,
        "other_key": f"{other_product}:{chosen1.supplier_code}",
        "known_supplier": known_supplier,
        "no_price_key": f"{nop_product}:{chosen2.supplier_code}",
    }


def test_other_supplier_price_fields_reach_the_response(scm_app):
    """The 4 `other_supplier_price` facts (S13e fix-cluster 2026-08-20) must survive the
    route's own serializer, not just the service `price_history_for_run` returns."""
    app, db = _client(scm_app)
    w = _world(db)
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/price-history")
    assert res.status_code == 200, res.text

    entry = res.json()["prices"][w["other_key"]]
    assert entry["advice"] == "other_supplier_price"
    assert entry["last"]["unit_cost"] == 15.5
    assert entry["other_supplier_code"] == w["known_supplier"].supplier_code
    assert entry["other_supplier_name"] == w["known_supplier"].supplier_name


def test_history_without_price_fields_reach_the_response(scm_app):
    """The 4 `history_without_price` facts must also survive the route serializer."""
    app, db = _client(scm_app)
    w = _world(db)
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/price-history")
    assert res.status_code == 200, res.text

    entry = res.json()["prices"][w["no_price_key"]]
    assert entry["advice"] == "history_without_price"
    assert entry["history_last_date"] == "2021-06-01"
    assert entry["history_doc_number"] == f"{MARKER}-NOPRICE"
    assert entry["history_po_count"] == 1
    assert entry["history_total_qty"] == 40.0


def test_price_history_rbac_denied_without_view(scm_app):
    app, db = _client(scm_app, None)  # bare user, no scm.dashboard.view
    w = _world(db)
    with TestClient(app) as c:
        assert c.get(
            f"/api/v1/scm/reorder-runs/{w['run_id']}/price-history"
        ).status_code == 403
