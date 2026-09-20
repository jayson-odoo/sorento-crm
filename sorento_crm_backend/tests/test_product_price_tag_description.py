"""AC-S4-2 (PLAN-price-tag-r10.md S4): `products.price_tag_description` reaches
the product responses and can be written through the master-data PUT.

`response_model` silently drops any field it was not told about (LESSONS-
LEARNT), so the column existing on the model proves nothing on its own - this
pins it through the actual `ProductResponse` the master-data routes declare,
on both the detail GET and the list GET, and through the PUT that edits it.
Mirrors `tests/test_product_barcode_route.py`, the precedent for exactly this
shape of gap.

Written test-FIRST: `products.price_tag_description` does not exist on the
model yet, so every write below is red on `TypeError` (an unknown ORM kwarg)
and every read is red on a missing/None response key.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
    get_external_api_user,
)
from app.main import app
from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope

from ._pg_fixture import blank_session, unique_code

SORENTO_ID = DEFAULT_COMPANY_ID
STEM = "ZZTPTD"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


@pytest.fixture
def world(db):
    uom_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C")[:50], category_name="C"))
    db.flush()

    def product(code: str, *, price_tag_description: str | None = None) -> str:
        pid = str(uuid.uuid4())
        db.add(
            Product(
                id=pid,
                product_code=code,
                product_name=code,
                category_id=cat_id,
                base_uom_id=uom_id,
                list_price=Decimal("10.00"),
                is_active=True,
                price_tag_description=price_tag_description,
                company_id=SORENTO_ID,
            )
        )
        db.flush()
        return pid

    db.commit()
    return {"uom_id": uom_id, "cat_id": cat_id, "product": product}


@pytest.fixture
def api(db):
    def _override_get_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-ptd@test.com"}

    async def _override_scope():
        scope = frozenset({SORENTO_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[get_external_api_user] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_detail_response_carries_the_price_tag_description(api, world, db):
    pid = world["product"](f"{STEM}-DETAIL", price_tag_description="Solid brass, matte black finish")
    db.commit()

    res = api.get(f"/api/v1/master-data/products/{pid}")
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] == "Solid brass, matte black finish"


def test_detail_response_carries_null_when_unset(api, world, db):
    pid = world["product"](f"{STEM}-NULL")
    db.commit()

    res = api.get(f"/api/v1/master-data/products/{pid}")
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] is None


def test_list_response_carries_the_price_tag_description(api, world, db):
    world["product"](f"{STEM}-LIST", price_tag_description="Two-line tag copy")
    db.commit()

    res = api.get("/api/v1/master-data/products/", params={"query": f"{STEM}-LIST"})
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["price_tag_description"] == "Two-line tag copy"


def test_put_sets_the_price_tag_description(api, world, db):
    pid = world["product"](f"{STEM}-PUT")
    db.commit()

    res = api.put(
        f"/api/v1/master-data/products/{pid}",
        json={"price_tag_description": "Made in Malaysia\nStainless steel"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] == "Made in Malaysia\nStainless steel"

    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json()["price_tag_description"] == "Made in Malaysia\nStainless steel"


def test_put_without_the_field_leaves_it_untouched(api, world, db):
    pid = world["product"](f"{STEM}-KEEP", price_tag_description="Original copy")
    db.commit()

    res = api.put(f"/api/v1/master-data/products/{pid}", json={"product_name": f"{STEM}-KEEP renamed"})
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] == "Original copy"
