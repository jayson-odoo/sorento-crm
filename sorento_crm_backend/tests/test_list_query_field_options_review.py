"""FILTER-MULTISELECT PR7 review round. Options DISTINCT (a shared status appears once, `pagination.total` counts
distinct values); the options search escapes LIKE wildcards (`query=%` is not "everything"); `line_product_id`
labels read "CODE - Name"; more than 200 filter values is a 422, never a 500, on purchase requests, campaigns and
GRN. Postgres only; seeded here.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.order import Order, OrderLine, OrderStatus
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._multi_filter_client import get
from tests._pg_fixture import unique_code
from tests.test_list_query_field_options import (  # noqa: F401  (fixtures and helpers)
    _field,
    _opts,
    _uid,
    allow,
    client,
    db,
    orders,
)

SORENTO = DEFAULT_COMPANY_ID


# ---- 2. DISTINCT ---------------------------------------------------------------------------------------------

def test_a_status_shared_by_two_orders_appears_once(client, orders):
    body = _opts(client, "orders", "order_status_id").json()
    values = [o["value"] for o in body["data"]]
    assert len(values) == len(set(values))
    assert body["pagination"]["total"] == len(set(values)) == 2
    assert orders["st"]["a"].id in values


# ---- 4. LIKE wildcards are literal ---------------------------------------------------------------------------

@pytest.mark.parametrize("wild", ["%", "_", "ZZT-TYPE-_"])
def test_wildcards_in_the_search_are_literal(client, orders, wild):
    resp = _opts(client, "orders", "order_type", query=wild)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


# ---- 5. line_product_id labels read "CODE - Name" ---------------------------------------------------------------

def test_line_product_labels_lead_with_the_product_code(db, client):
    _field(db, "orders", "line_product_id", "order_line.product_id")
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("U")[:20], uom_name="Unit")
    cat = ProductCategory(id=_uid(), category_code=unique_code("C")[:50], category_name="ZZT cat", company_id=SORENTO)
    wh = Warehouse(id=_uid(), company_id=SORENTO, warehouse_code=unique_code("W")[:50], warehouse_name="ZZT wh", is_active=True)
    db.add_all([uom, cat, wh])
    db.flush()
    codes = []
    expected = []
    # (name, label rule): a name -> "CODE - Name"; a blank name or one equal to the code -> just "CODE".
    for i, name in enumerate(("ZZT Same Name", "ZZT Same Name", "", None)):
        code = unique_code(f"PC{i}")[:40]
        codes.append(code)
        if name is None:
            name = code
            expected.append(code)
        elif name == "":
            expected.append(code)
        else:
            expected.append(f"{code} - {name}")
        product = Product(id=_uid(), company_id=SORENTO, product_code=code, product_name=name, category_id=cat.id,
                          base_uom_id=uom.id, list_price=Decimal("1.00"))
        db.add(product)
        db.flush()
        order = Order(id=_uid(), company_id=SORENTO, order_number=unique_code(f"SO{i}")[:50])
        db.add(order)
        db.flush()
        db.add(OrderLine(id=_uid(), order_id=order.id, product_id=product.id, warehouse_id=wh.id, quantity=Decimal("1"), company_id=SORENTO))
    db.commit()
    labels = [o["label"] for o in _opts(client, "orders", "line_product_id").json()["data"]]
    assert sorted(labels) == sorted(expected)


# ---- 3. over the value cap: 422, not 500 -----------------------------------------------------------------------

def _many(n=201):
    return [f"v{i}" for i in range(n)]


@pytest.mark.parametrize("url,param", [
    ("/api/v1/procurement/purchase-requests/", "approval_status"),
    ("/api/v1/marketing/campaigns/", "status"),
    ("/api/v1/procurement/grn/", "picking_status"),
])
def test_more_than_200_filter_values_is_422_not_500(client, url, param):
    resp = get(client, url, [(param, v) for v in _many()])
    assert resp.status_code == 422, resp.text
