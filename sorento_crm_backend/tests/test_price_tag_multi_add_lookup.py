"""PRICETAG-MULTI-ADD: the Item lookup's discontinued flag (AC-9) and its 50 per kind default (AC-10).

Postgres only, through the repo's blank-schema fixture; every test seeds its own chain.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves the circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402
from tests._pg_fixture import blank_session, unique_code
from tests.test_portal_price_tag_routes import _seed_contact_who_can_see_the_form

_LOOKUP = "/api/v1/public/portal/lookups/price-tag-items"
_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def _seed_products(db, codes: list[str], *, discontinued: set[str] | None = None) -> dict[str, str]:
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("cat"),
        category_name=unique_code("Category"),
        class_label="Kitchen Sink",
    )
    brand = Brand(id=str(uuid.uuid4()), brand_code=unique_code("br"), brand_name=unique_code("Brand"))
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("uom"), uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    ids: dict[str, str] = {}
    for code in codes:
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=f"Name {code}",
            category_id=category.id,
            brand_id=brand.id,
            base_uom_id=uom.id,
            list_price=100.00,
            is_discontinued=code in (discontinued or set()),
        )
        db.add(product)
        ids[code] = product.id
    db.flush()
    return ids


def _seed_set(db, code: str) -> str:
    from app.models.product_set import ProductSet

    row = ProductSet(
        id=str(uuid.uuid4()),
        set_code=code,
        name=f"Set {code}",
        company_id=_SORENTO_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row.id


@pytest.fixture
def client():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    with blank_session() as db:
        contact_id = _seed_contact_who_can_see_the_form(db)

        def _override_get_db():
            yield db

        def _override_portal_token():
            return PortalToken(id=str(uuid.uuid4()), contact_id=contact_id, space_id="zzt-space")

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = _override_portal_token
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


def test_ac9_service_rows_carry_is_discontinued():
    from app.services.price_tag_request_service import PriceTagRequestService

    with blank_session() as db:
        prefix = unique_code("MAD").upper()
        live, dead = f"{prefix}-LIVE", f"{prefix}-DEAD"
        _seed_products(db, [live, dead], discontinued={dead})
        _seed_set(db, f"{prefix}-SET")

        rows = PriceTagRequestService.lookup_tag_items(db, prefix)

    by_code = {r["code"]: r for r in rows}
    assert by_code[dead]["is_discontinued"] is True
    assert by_code[live]["is_discontinued"] is False
    assert by_code[f"{prefix}-SET"]["is_discontinued"] is False


def test_ac9_route_returns_is_discontinued(client):
    c, db = client
    prefix = unique_code("MAD").upper()
    dead = f"{prefix}-DEAD"
    _seed_products(db, [dead], discontinued={dead})

    res = c.get(_LOOKUP, params={"q": prefix})

    assert res.status_code == 200, res.text
    rows = {r["code"]: r for r in res.json()}
    assert rows[dead]["is_discontinued"] is True


def test_ac10_service_default_limit_is_50_per_kind():
    from app.services.price_tag_request_service import PriceTagRequestService

    with blank_session() as db:
        prefix = unique_code("MAD").upper()
        _seed_products(db, [f"{prefix}-P{i:03d}" for i in range(60)])
        for i in range(60):
            _seed_set(db, f"{prefix}-S{i:03d}")

        rows = PriceTagRequestService.lookup_tag_items(db, prefix)

    assert len([r for r in rows if r["kind"] == "product"]) == 50
    assert len([r for r in rows if r["kind"] == "product_set"]) == 50


def test_ac10_route_without_limit_returns_more_than_20_per_kind(client):
    c, db = client
    prefix = unique_code("MAD").upper()
    _seed_products(db, [f"{prefix}-P{i:03d}" for i in range(60)])

    res = c.get(_LOOKUP, params={"q": prefix})

    assert res.status_code == 200, res.text
    products = [r for r in res.json() if r["kind"] == "product"]
    assert len(products) == 50


def test_ac10_route_still_refuses_a_limit_over_50(client):
    c, _db = client
    res = c.get(_LOOKUP, params={"limit": 51})
    assert res.status_code == 422
