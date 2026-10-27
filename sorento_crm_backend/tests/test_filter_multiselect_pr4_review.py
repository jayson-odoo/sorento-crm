"""FILTER-MULTISELECT PR4 review round. Spec registry "Seen in products": the Value options are counted before
the value filter (picking one value leaves the others on offer), and a value that itself contains a comma
(a multi-value key reads back like `["Gold", "Matt Black"]`) filters exactly when sent as a repeated param.
Exports: stock balance export (status, warehouse_ids) and the products list-query export (several categories,
several brands) take the same several values the lists do. Red first for the registry; the export tests are
GUARDS that may already pass. Postgres only; every row seeded here.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.inventory import Stock
from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import SORENTO, get, open_client
from tests._pg_fixture import blank_session, unique_code
from tests.test_inventory_multi_filters import (  # noqa: F401  (`balance` is a pytest fixture)
    _bucket_products,
    balance,
)
from tests.test_spec_registry_pr2_routes import (  # noqa: F401  (`api` is a pytest fixture)
    _BASE,
    _MERCHANDISER,
    _key,
    _product,
    _spec,
    api,
)

COMMA_LIST = ["Gold", "Matt Black"]


# ---- Seen in products: Value options and comma values ---------------------------------------------------------

@pytest.fixture
def finish(api):
    db, as_user = api
    as_user(_MERCHANDISER)
    _key(db, "zzt_finish")
    prov = {"zzt_finish": {"source": "derived"}}
    chrome, brushed, commaed = _product(db), _product(db), _product(db)
    _spec(db, chrome, {"zzt_finish": {"value": "Chrome"}, "class": {"value": "ZZT Sink"}}, prov)
    _spec(db, brushed, {"zzt_finish": {"value": "Brushed"}, "class": {"value": "ZZT Sink"}}, prov)
    _spec(db, commaed, {"zzt_finish": {"value": COMMA_LIST}, "class": {"value": "ZZT Sink"}}, prov)
    db.commit()
    return TestClient(app), dict(chrome=chrome, brushed=brushed, commaed=commaed)


def _read(client, *pairs):
    resp = get(client, f"{_BASE}/zzt_finish/products", list(pairs))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_value_options_still_list_every_value_after_one_is_picked(finish):
    client, p = finish
    everything = {row["value"] for row in _read(client)["by_value"]}
    assert len(everything) == 3
    body = _read(client, ("value", "Chrome"))
    assert {r["product_code"] for r in body["products"]} == {p["chrome"].product_code}
    assert {row["value"] for row in body["by_value"]} == everything


def test_a_value_containing_a_comma_filters_exactly_when_repeated(finish):
    client, p = finish
    comma_value = next(row["value"] for row in _read(client)["by_value"] if "Matt Black" in str(row["value"]))
    assert "," in comma_value
    body = _read(client, ("value", comma_value))
    assert {r["product_code"] for r in body["products"]} == {p["commaed"].product_code}
    both = _read(client, ("value", comma_value), ("value", "Chrome"))
    assert {r["product_code"] for r in both["products"]} == {p["commaed"].product_code, p["chrome"].product_code}


def test_plain_values_union_as_repeated_params(finish):
    client, p = finish
    want = {p["chrome"].product_code, p["brushed"].product_code}
    # Text values ride repeated params only (plan section 1): a comma inside one is part of the value.
    assert {r["product_code"] for r in _read(client, ("value", "Chrome"), ("value", "Brushed"))["products"]} == want


# ---- Exports (guards) -----------------------------------------------------------------------------------------

@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def test_stock_balance_export_status_union_guard(client, balance):
    s = balance
    resp = get(client, "/api/v1/inventory/stock/balance/export", [("status", "critical,low")])
    assert resp.status_code == 200, resp.text
    pids = {row["product_id"] for row in resp.json()["data"]}
    got = {k for k, v in s["buckets"].items() if v in pids}
    assert got == {"critical", "low"}
    resp = get(client, "/api/v1/inventory/stock/balance/export", [("status", "critical"), ("status", "overstock")])
    pids = {row["product_id"] for row in resp.json()["data"]}
    assert {k for k, v in s["buckets"].items() if v in pids} == {"critical", "overstock"}


def test_stock_balance_export_warehouse_ids_union_guard(client, balance):
    s = balance
    w1, w2, w3 = (w.id for w in s["w"])
    resp = get(client, "/api/v1/inventory/stock/balance/export", [("warehouse_ids", f"{w2},{w3}"), ("product_ids", s["p"].id)])
    assert resp.status_code == 200, resp.text
    assert {row["warehouse_id"] for row in resp.json()["data"]} == {w2, w3}


def test_products_export_two_categories_and_two_brands_guard(db, client):
    resource = ListQueryResource(id=str(uuid.uuid4()), resource_key="products", display_name="products", is_active=True)
    db.add(resource)
    db.flush()
    db.add(ListQueryField(id=str(uuid.uuid4()), resource_id=resource.id, field_key="product_code", label="Code",
                          data_type="string", compile_key="product.product_code", allowed_operators=["eq"],
                          filterable=True, exportable=True))
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("U")[:20], uom_name="Unit")
    cats = [ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("C")[:50], category_name=f"ZZT cat {i}", company_id=SORENTO) for i in range(3)]
    brands = [Brand(id=str(uuid.uuid4()), brand_code=unique_code("B")[:50], brand_name=f"ZZT brand {i}", company_id=SORENTO) for i in range(3)]
    db.add_all([uom, *cats, *brands])
    db.flush()
    tag = unique_code("XP", alpha=True)
    for i in range(3):
        db.add(Product(id=str(uuid.uuid4()), company_id=SORENTO, product_code=f"{tag}-{i}", product_name=f"{tag} {i}",
                       category_id=cats[i].id, brand_id=brands[i].id, base_uom_id=uom.id, list_price=Decimal("1.00")))
    db.flush()

    def export(**filters):
        body = {"resource": "products", "fields": [{"field_key": "product_code"}], "quick_search": tag, **filters}
        resp = client.post("/api/v1/list-query/export", json=body)
        assert resp.status_code == 200, resp.text
        return {r["product_code"] for r in resp.json()["data"]}

    assert export(category_id=f"{cats[0].id},{cats[2].id}") == {f"{tag}-0", f"{tag}-2"}
    assert export(brand_id=f"{brands[1].id},{brands[2].id}") == {f"{tag}-1", f"{tag}-2"}
    assert export(category_id=f"{cats[0].id},{cats[1].id}", brand_id=f"{brands[1].id},{brands[2].id}") == {f"{tag}-1"}
