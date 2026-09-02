"""AC-S7-1: `products.barcode` reaches the product responses.

`response_model` silently drops any field it was not told about (see
LESSONS-LEARNT.md), so the column existing on the model proves nothing on its
own - this pins it through the actual `ProductResponse` the master-data routes
declare, on both the detail GET and the list GET, and through the PUT that
edits it.
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
STEM = "ZZTBARCODE"


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

    def product(code: str, *, barcode: str | None = None) -> str:
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
                barcode=barcode,
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

    principal = {"id": str(uuid.uuid4()), "email": "zzt-barcode@test.com"}

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


def test_detail_response_carries_the_barcode(api, world, db):
    pid = world["product"](f"{STEM}-DETAIL", barcode="1234567890123")
    db.commit()

    res = api.get(f"/api/v1/master-data/products/{pid}")
    assert res.status_code == 200, res.text
    assert res.json()["barcode"] == "1234567890123"


def test_detail_response_carries_null_when_unset(api, world, db):
    pid = world["product"](f"{STEM}-NULL")
    db.commit()

    res = api.get(f"/api/v1/master-data/products/{pid}")
    assert res.status_code == 200, res.text
    assert res.json()["barcode"] is None


def test_list_response_carries_the_barcode(api, world, db):
    world["product"](f"{STEM}-LIST", barcode="9998887776665")
    db.commit()

    res = api.get("/api/v1/master-data/products/", params={"query": f"{STEM}-LIST"})
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["barcode"] == "9998887776665"


def test_put_sets_the_barcode(api, world, db):
    pid = world["product"](f"{STEM}-PUT")
    db.commit()

    res = api.put(f"/api/v1/master-data/products/{pid}", json={"barcode": "5551112223334"})
    assert res.status_code == 200, res.text
    assert res.json()["barcode"] == "5551112223334"

    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json()["barcode"] == "5551112223334"


def test_put_with_empty_string_clears_the_barcode(api, world, db):
    """An explicit "" is a clear, not a stored empty string - `ProductUpdate`
    normalizes it to None the same way `normalize_currency` treats blank."""
    pid = world["product"](f"{STEM}-CLEAR", barcode="1112223334445")
    db.commit()

    res = api.put(f"/api/v1/master-data/products/{pid}", json={"barcode": ""})
    assert res.status_code == 200, res.text
    assert res.json()["barcode"] is None

    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json()["barcode"] is None


def test_put_without_barcode_leaves_it_untouched(api, world, db):
    """`exclude_unset` on the update: omitting the field is not the same as
    clearing it - the same rule the rest of ProductUpdate follows."""
    pid = world["product"](f"{STEM}-KEEP", barcode="1112223334445")
    db.commit()

    res = api.put(f"/api/v1/master-data/products/{pid}", json={"product_name": "Renamed"})
    assert res.status_code == 200, res.text
    assert res.json()["barcode"] == "1112223334445"
