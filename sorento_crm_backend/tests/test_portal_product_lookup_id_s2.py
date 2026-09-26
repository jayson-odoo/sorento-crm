"""S2-16: the portal product lookup must carry `product_id` so an opportunity line can send
`{product_id, qty}` (lines need an id, not just the code).

Plan: documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md, section 16 ("Lines
(S2-16)"). UAC: sales-targets-opportunities-26sep-acceptance-criteria.md, S2-16.

Today `GET /api/v1/public/portal/lookups/products` (app/api/v1/public/portal.py,
`ProductLookupItem`) returns `product_code`, `product_name`, `category_*` but no id. This test
is expected to fail on the response body missing the `product_id` key (Pydantic's
`response_model` drops it even if a route author adds it to the dict without adding it to the
schema - LESSONS-LEARNT.md), not on a route/import error: the route itself already exists and is
mounted.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

BASE = "/api/v1/public/portal"


def _uid() -> str:
    return str(uuid.uuid4())


def _contact(db, *, name: str = "ZZT Lookup Contact"):
    from app.models.access import RespondContact

    contact = RespondContact(id=_uid(), phone_number=f"+60{_uid().replace('-', '')[:9]}", name=name)
    db.add(contact)
    db.flush()
    return contact


def _product(db, *, name: str = "ZZT Lookup Product"):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:6]}", category_name="ZZT Lookup Cat"
    )
    brand = Brand(id=_uid(), brand_code=f"ZZT-{_uid()[:6]}", brand_name="ZZT Lookup Brand")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT-{_uid()[:6]}", uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:6]}",
        product_name=name,
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal("50.00"),
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


@contextmanager
def _portal_client(db, contact_id: str):
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    def _override_get_db():
        yield db

    def _override_portal_token():
        return PortalToken(id=_uid(), contact_id=contact_id, space_id="zzt-space")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_portal_token] = _override_portal_token
    try:
        with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_product_lookup_item_carries_product_id_matching_the_product_row():
    with blank_session() as db:
        contact = _contact(db)
        product = _product(db, name="ZZT Findable Widget")

        with _portal_client(db, contact.id) as c:
            res = c.get(f"{BASE}/lookups/products", params={"q": "ZZT Findable Widget"})
            assert res.status_code == 200, res.text
            items = res.json()
            assert items, "expected the seeded product to be returned by the lookup"
            match = next(i for i in items if i["product_code"] == product.product_code)
            assert match["product_id"] == str(product.id)


def test_product_lookup_id_is_additive_existing_fields_still_present():
    with blank_session() as db:
        contact = _contact(db)
        product = _product(db, name="ZZT Additive Widget")

        with _portal_client(db, contact.id) as c:
            res = c.get(f"{BASE}/lookups/products", params={"q": "ZZT Additive Widget"})
            assert res.status_code == 200, res.text
            match = next(i for i in res.json() if i["product_code"] == product.product_code)
            assert match["product_name"] == "ZZT Additive Widget"
            assert "product_id" in match
