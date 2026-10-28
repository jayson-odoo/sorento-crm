"""FILTER-MULTISELECT PR5: Purchase orders Status, Proforma invoices (Supplier, Packing list placement),
Loading plans Status (the "active" group stays a pseudo-value that ORs with real statuses), the SCM
dashboard (Category, Supplier, Value ABC, Demand XYZ; Warehouses is the already-multi guard) and a
reorder run's recommendations Type take several values (OR within a filter, AND across). Comma-joined,
repeated and single all read. Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.procurement import ProductSupplier, PurchaseOrder, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import (
    ItemClassification,
    LoadingPlan,
    ProformaInvoice,
    ReorderRecommendation,
    ReorderRun,
)
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, pg_session, unique_code

SCM = "/api/v1/scm"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _supplier(db, key):
    s = Supplier(id=_uid(), supplier_code=unique_code(key, alpha=True), supplier_name=f"ZZT {key} {uuid.uuid4().hex[:4]}")
    db.add(s)
    db.flush()
    return s


# ---- Purchase orders: Status -----------------------------------------------------------------------------

@pytest.fixture
def pos(db):
    tag = unique_code("PO", alpha=True)
    rows = {}
    for key, status in (("a", "draft"), ("b", "active"), ("c", "closed"), ("d", "active")):
        po = PurchaseOrder(id=_uid(), po_number=f"{tag}-{key}", status=status)
        db.add(po)
        db.flush()
        rows[key] = po
    return rows


def _pos(client, pairs):
    resp = get(client, f"{SCM}/purchase-orders", [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


def test_po_status_single_union_repeated(client, pos):
    s = pos
    assert _pos(client, [("status", "active")]) == {s["b"].id, s["d"].id}
    assert _pos(client, [("status", "draft,closed")]) == {s["a"].id, s["c"].id}
    assert _pos(client, [("status", "draft"), ("status", "active")]) == {s["a"].id, s["b"].id, s["d"].id}


# ---- Proforma invoices: Supplier and Packing list placement ----------------------------------------------

@pytest.fixture
def pis(db):
    sups = [_supplier(db, f"pis{i}") for i in range(3)]
    rows = {}
    for key, si in (("a", 0), ("b", 1), ("c", 2), ("d", 0)):
        pi = ProformaInvoice(id=_uid(), pi_number=unique_code(f"PI{key}"), supplier_id=sups[si].id)
        db.add(pi)
        db.flush()
        rows[key] = pi
    return dict(sups=sups, **rows)


def _pis(client, pairs):
    resp = get(client, f"{SCM}/proforma-invoices", [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


def test_pi_supplier_single_union_repeated(client, pis):
    s = pis
    s0, s1, s2 = (x.id for x in s["sups"])
    assert _pis(client, [("supplier_id", s0)]) == {s["a"].id, s["d"].id}
    assert _pis(client, [("supplier_id", f"{s1},{s2}")]) == {s["b"].id, s["c"].id}
    assert _pis(client, [("supplier_id", s1), ("supplier_id", s2)]) == {s["b"].id, s["c"].id}


def test_pi_supplier_malformed_id_refused(client, pis):
    assert get(client, f"{SCM}/proforma-invoices", [("supplier_id", f"{_uid()},not-a-uuid")]).status_code == 422


def test_pi_placement_union(client, pis):
    # a PI with no lines has nothing placed: not_converted
    s = pis
    everything = {s[k].id for k in "abcd"}
    assert _pis(client, [("placement", "not_converted")]) == everything
    assert _pis(client, [("placement", "converted")]) == set()
    assert _pis(client, [("placement", "not_converted,converted")]) == everything
    assert _pis(client, [("placement", "converted,split")]) == set()
    assert _pis(client, [("placement", "converted"), ("placement", "not_converted")]) == everything


def test_pi_placement_unknown_refused(client, pis):
    assert get(client, f"{SCM}/proforma-invoices", [("placement", "converted,sideways")]).status_code == 422


def test_pi_supplier_and_placement_are_and_ed(client, pis):
    s = pis
    s0, s1, _s2 = (x.id for x in s["sups"])
    got = _pis(client, [("supplier_id", f"{s0},{s1}"), ("placement", "not_converted,split")])
    assert got == {s["a"].id, s["b"].id, s["d"].id}
    assert _pis(client, [("supplier_id", f"{s0},{s1}"), ("placement", "converted,split")]) == set()


# ---- Loading plans: Status (the "active" group is a pseudo-value) ----------------------------------------

@pytest.fixture
def plans(db):
    sup = _supplier(db, "lp")
    rows = {}
    for key, status in (("a", "planning"), ("b", "sent"), ("c", "cancelled"), ("d", "planning")):
        lp = LoadingPlan(id=_uid(), supplier_id=sup.id, status=status)
        db.add(lp)
        db.flush()
        rows[key] = lp
    return rows


def _plans(client, pairs):
    resp = get(client, f"{SCM}/loading-plans", [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


def test_plans_status_single_and_default_group(client, plans):
    s = plans
    assert _plans(client, [("status", "cancelled")]) == {s["c"].id}
    assert _plans(client, []) == {s["a"].id, s["b"].id, s["d"].id}
    assert _plans(client, [("status", "active")]) == {s["a"].id, s["b"].id, s["d"].id}


def test_plans_status_union(client, plans):
    s = plans
    assert _plans(client, [("status", "sent,cancelled")]) == {s["b"].id, s["c"].id}
    assert _plans(client, [("status", "planning"), ("status", "cancelled")]) == {s["a"].id, s["c"].id, s["d"].id}


def test_plans_active_group_ors_with_a_real_status(client, plans):
    s = plans
    assert _plans(client, [("status", "active,cancelled")]) == {s[k].id for k in "abcd"}
    assert _plans(client, [("status", "cancelled"), ("status", "active")]) == {s[k].id for k in "abcd"}


# ---- SCM dashboard: Category, Supplier, Value (ABC), Demand (XYZ), Warehouses guard ---------------------

@pytest.fixture
def dash_db():
    # The dashboard reads `scm.net_position_v`, a view over the REAL `stock` table, so the blank
    # schema cannot show seeded rows: this group seeds inside a rolled-back transaction on the real
    # schema and narrows every read with `query=<unique tag>`.
    with pg_session() as session:
        yield session


@pytest.fixture
def dash_client(dash_db, monkeypatch):
    with open_client(dash_db, monkeypatch) as (c, _actor):
        yield c


@pytest.fixture
def dash(dash_db):
    db = dash_db
    tag = unique_code("DSH", alpha=True)
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("u"), uom_name="ZZT uom")
    cats = [ProductCategory(id=_uid(), category_code=unique_code(f"c{i}", alpha=True), category_name=f"ZZT cat {i}") for i in range(3)]
    sups = [_supplier(db, f"ds{i}") for i in range(3)]
    whs = [Warehouse(id=_uid(), warehouse_code=unique_code(f"w{i}", alpha=True), warehouse_name=f"ZZT w{i}", is_active=True) for i in range(2)]
    db.add(uom)
    db.add_all(cats + whs)
    db.flush()
    # key: (category, supplier, abc, xyz, warehouse)
    spec = {
        "a": (0, 0, "A", "X", 0),
        "b": (1, 1, "B", "Y", 0),
        "c": (2, 2, "C", "Z", 0),
        "d": (0, 1, "A", "Z", 0),
        "e": (0, 0, None, None, 0),
        "f": (1, 2, "B", "X", 1),
    }
    codes = {}
    for key, (ci, si, abc, xyz, wi) in spec.items():
        p = Product(id=_uid(), product_code=f"{tag}-{key}", product_name=f"{tag} {key}", category_id=cats[ci].id,
                    base_uom_id=uom.id, list_price=Decimal("1.00"))
        db.add(p)
        db.flush()
        db.add(ProductSupplier(id=_uid(), product_id=p.id, supplier_id=sups[si].id))
        db.add(Stock(id=_uid(), product_id=p.id, warehouse_id=whs[wi].id, quantity_on_hand=5))
        if abc or xyz:
            db.add(ItemClassification(id=_uid(), product_id=p.id, warehouse_id=whs[wi].id, abc_class=abc, xyz_class=xyz))
        db.flush()
        codes[key] = p.product_code
    return dict(tag=tag, codes=codes, cats=cats, sups=sups, whs=whs)


def _dash(client, s, pairs):
    resp = get(client, f"{SCM}/dashboard/net-position", [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    back = {v: k for k, v in s["codes"].items()}
    return {back[r["sku"]] for r in rows}


def test_dash_seed_is_visible(dash_client, dash):
    assert _dash(dash_client, dash, []) == set("abcdef")


def test_dash_category_single_union_repeated(dash_client, dash):
    s = dash
    c0, c1, c2 = (c.id for c in s["cats"])
    assert _dash(dash_client, s, [("category_id", c2)]) == {"c"}
    assert _dash(dash_client, s, [("category_id", f"{c1},{c2}")]) == {"b", "c", "f"}
    assert _dash(dash_client, s, [("category_id", c1), ("category_id", c2)]) == {"b", "c", "f"}


def test_dash_category_malformed_id_refused(dash_client, dash):
    resp = get(dash_client, f"{SCM}/dashboard/net-position", [("category_id", f"{_uid()},not-a-uuid")])
    assert resp.status_code == 422, resp.text


def test_dash_supplier_single_union_repeated(dash_client, dash):
    s = dash
    c0, c1, c2 = (x.supplier_code for x in s["sups"])
    assert _dash(dash_client, s, [("supplier", c2)]) == {"c", "f"}
    assert _dash(dash_client, s, [("supplier", f"{c1},{c2}")]) == {"b", "c", "d", "f"}
    assert _dash(dash_client, s, [("supplier", c1), ("supplier", c2)]) == {"b", "c", "d", "f"}


def test_dash_abc_single_union_repeated_and_unknown(dash_client, dash):
    s = dash
    assert _dash(dash_client, s, [("abc", "C")]) == {"c"}
    assert _dash(dash_client, s, [("abc", "A,B")]) == {"a", "b", "d", "f"}
    assert _dash(dash_client, s, [("abc", "A"), ("abc", "C")]) == {"a", "c", "d"}
    assert _dash(dash_client, s, [("abc", "unknown,C")]) == {"c", "e"}


def test_dash_xyz_single_union_repeated_and_unknown(dash_client, dash):
    s = dash
    assert _dash(dash_client, s, [("xyz", "X")]) == {"a", "f"}
    assert _dash(dash_client, s, [("xyz", "X,Y")]) == {"a", "b", "f"}
    assert _dash(dash_client, s, [("xyz", "Y"), ("xyz", "Z")]) == {"b", "c", "d"}
    assert _dash(dash_client, s, [("xyz", "unknown,Y")]) == {"b", "e"}


def test_dash_filters_and_across(dash_client, dash):
    s = dash
    c0, c1, _c2 = (c.id for c in s["cats"])
    s0, s1, _s2 = (x.supplier_code for x in s["sups"])
    assert _dash(dash_client, s, [("abc", "A,B"), ("xyz", "Y,Z")]) == {"b", "d"}
    assert _dash(dash_client, s, [("category_id", f"{c0},{c1}"), ("supplier", f"{s0},{s1}"), ("abc", "A,B")]) == {"a", "b", "d"}


def test_dash_warehouses_guard_list_forms(dash_client, dash):
    s = dash
    w0, w1 = (w.warehouse_code for w in s["whs"])
    assert _dash(dash_client, s, [("warehouses", f"{w0},{w1}")]) == set("abcdef")
    assert _dash(dash_client, s, [("warehouses", w1)]) == {"f"}
    assert _dash(dash_client, s, [("warehouses", w0), ("warehouses", w1)]) == set("abcdef")


# ---- Reorder run recommendations: Type -------------------------------------------------------------------

@pytest.fixture
def recs(dash_db):
    db = dash_db
    tag = unique_code("REC", alpha=True)
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("u"), uom_name="ZZT uom")
    cat = ProductCategory(id=_uid(), category_code=unique_code("c", alpha=True), category_name="ZZT cat")
    db.add_all([uom, cat])
    db.flush()
    run = ReorderRun(id=_uid())
    db.add(run)
    db.flush()
    rows = {}
    for key, rtype in (("a", "buy"), ("b", "covered"), ("c", "disposition"), ("d", "buy")):
        p = Product(id=_uid(), product_code=f"{tag}-{key}", product_name=f"{tag} {key}", category_id=cat.id,
                    base_uom_id=uom.id, list_price=Decimal("1.00"))
        db.add(p)
        db.flush()
        r = ReorderRecommendation(id=_uid(), run_id=run.id, product_id=p.id, rec_type=rtype)
        db.add(r)
        db.flush()
        rows[key] = r
    return dict(run=run, **rows)


def _recs(client, s, pairs):
    resp = get(client, f"{SCM}/reorder-runs/{s['run'].id}/recommendations", [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


def test_recs_type_single_union_repeated(dash_client, recs):
    s = recs
    assert _recs(dash_client, s, [("type", "buy")]) == {s["a"].id, s["d"].id}
    assert _recs(dash_client, s, [("type", "covered,disposition")]) == {s["b"].id, s["c"].id}
    assert _recs(dash_client, s, [("type", "buy"), ("type", "covered")]) == {s["a"].id, s["b"].id, s["d"].id}
