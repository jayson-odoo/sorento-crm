"""FILTER-MULTISELECT PR7 security finding: the options route never leaks another company's values.
1. Suppliers `country`: a country used only by a Mocha supplier is not offered to a Sorento caller, and
   `pagination.total` equals the rows returned (red today: only `Country` is scoped, `Supplier` is not).
2. Orders `line_product_id` / `line_warehouse_id`: guards.
3. A caller without any list-query view permission asking an UNKNOWN resource gets 403, not 404.
4. `query` over 200 characters is 422.
Postgres only; two-company seeding as in tests/test_list_query_field_options.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.country import Country
from app.models.inventory import Warehouse
from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.models.order import Order, OrderLine
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import open_client
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
MOCHA = "00000000-0000-0000-0000-000000000002"
LQ = "/api/v1/list-query"


def _uid() -> str:
    return str(uuid.uuid4())


def _opts(client, resource, field, **params):
    return client.get(f"{LQ}/{resource}/fields/{field}/options", params=params)


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


@pytest.fixture
def allow():
    return {"view": True}


@pytest.fixture
def client(db, monkeypatch, allow):
    with open_client(db, monkeypatch, scope=frozenset({SORENTO})) as (c, _a):
        monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: allow["view"])
        yield c


def _field(db, resource, key, compile_key, dtype="uuid"):
    res = db.query(ListQueryResource).filter_by(resource_key=resource).first()
    if res is None:
        res = ListQueryResource(id=_uid(), resource_key=resource, display_name=resource)
        db.add(res)
        db.flush()
    db.add(ListQueryField(
        id=_uid(), resource_id=res.id, field_key=key, label=key, data_type=dtype, compile_key=compile_key,
        allowed_operators=["eq", "in"], filterable=True, exportable=True,
    ))
    db.flush()


# ---- 1. Suppliers country ----------------------------------------------------------------------------------

def test_a_country_used_only_by_another_companys_supplier_is_not_offered(db, client):
    _field(db, "suppliers", "country", "country.name", "string")
    shared = Country(id=_uid(), code="ZA", name="ZZT Sorento-land", company_id=SORENTO)
    leaky = Country(id=_uid(), code="ZB", name="ZZT Mocha-only-land", company_id=SORENTO)
    db.add_all([shared, leaky])
    db.flush()
    db.add(Supplier(id=_uid(), company_id=SORENTO, supplier_code=unique_code("S"), supplier_name="ZZT Sorento sup", country_id=shared.id))
    db.add(Supplier(id=_uid(), company_id=MOCHA, supplier_code=unique_code("S"), supplier_name="ZZT Mocha sup", country_id=leaky.id))
    db.commit()
    resp = _opts(client, "suppliers", "country")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {o["label"] for o in body["data"]}
    assert "ZZT Sorento-land" in names
    assert "ZZT Mocha-only-land" not in names
    assert body["pagination"]["total"] == len(body["data"])
    assert _opts(client, "suppliers", "country", query="Mocha-only").json()["data"] == []


# ---- 2. Orders line product / warehouse (guards) -----------------------------------------------------------

def test_a_product_and_warehouse_only_on_another_companys_order_are_not_offered(db, client):
    _field(db, "orders", "line_product_id", "order_line.product_id")
    _field(db, "orders", "line_warehouse_id", "order_line.warehouse_id")
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("U")[:20], uom_name="Unit")
    cat = ProductCategory(id=_uid(), category_code=unique_code("C")[:50], category_name="ZZT cat", company_id=SORENTO)
    db.add_all([uom, cat])
    db.flush()
    made = {}
    for key, company in (("sorento", SORENTO), ("mocha", MOCHA)):
        product = Product(id=_uid(), company_id=company, product_code=unique_code(f"P{key}"), product_name=f"ZZT prod {key}",
                          category_id=cat.id, base_uom_id=uom.id, list_price=Decimal("1.00"))
        warehouse = Warehouse(id=_uid(), company_id=company, warehouse_code=unique_code(f"W{key}")[:50], warehouse_name=f"ZZT wh {key}", is_active=True)
        db.add_all([product, warehouse])
        db.flush()
        order = Order(id=_uid(), company_id=company, order_number=unique_code(f"SO{key}")[:50])
        db.add(order)
        db.flush()
        db.add(OrderLine(id=_uid(), order_id=order.id, product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal("1"),
                         company_id=company))
        made[key] = (product, warehouse)
    db.commit()
    prods = {o["label"] for o in _opts(client, "orders", "line_product_id").json()["data"]}
    whs = {o["label"] for o in _opts(client, "orders", "line_warehouse_id").json()["data"]}
    # Labels follow code_with_name: "CODE - Name".
    assert any(p.endswith(" - ZZT prod sorento") for p in prods) and not any("ZZT prod mocha" in p for p in prods)
    assert "ZZT wh sorento" in whs and "ZZT wh mocha" not in whs


# ---- 3. No disclosure of which resources exist ------------------------------------------------------------------

def test_an_unknown_resource_without_any_view_permission_is_403_not_404(client, allow):
    allow["view"] = False
    assert _opts(client, "no_such_resource", "anything").status_code == 403


def test_with_the_permission_an_unknown_field_is_still_404(db, client):
    _field(db, "orders", "order_type", "order.order_type", "string")
    assert _opts(client, "orders", "no_such_field").status_code == 404


# ---- 4. query length --------------------------------------------------------------------------------------------

def test_a_query_over_200_characters_is_422(db, client):
    _field(db, "orders", "order_type", "order.order_type", "string")
    assert _opts(client, "orders", "order_type", query="x" * 201).status_code == 422
    assert _opts(client, "orders", "order_type", query="x" * 200).status_code == 200
