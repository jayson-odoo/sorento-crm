"""F1-7 (PRICETAG-MULTI-ADD round 5): ``line_pricing`` answers a SET line from
``tag_data_service.product_set_tag_data``, and the portal lookup route accepts
``product_set_id`` instead of dropping it. Written test-FIRST."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves the circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402
from app.services.dealer_kit.pricing import line_pricing
from app.services.dealer_kit.viewer import ViewerContext
from tests._pg_fixture import blank_session, unique_code
from tests.test_portal_price_tag_routes import _seed_contact_who_can_see_the_form
from tests.test_price_tag_line_pricing import _product

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ROUTE = "/api/v1/public/portal/lookups/line-pricing"


def _viewer() -> ViewerContext:
    return ViewerContext(is_staff=True, is_internal_copy=True)


def _set(db, members: list[tuple], *, override: str | None = None) -> str:
    """``members`` is a list of (product, quantity)."""
    from app.models.product_set import ProductSet, ProductSetMember

    row = ProductSet(
        id=str(uuid.uuid4()),
        set_code=unique_code("ZZTSET"),
        name="ZZT Set",
        company_id=_SORENTO,
        list_price_override=Decimal(override) if override is not None else None,
    )
    db.add(row)
    db.flush()
    for order, (product, quantity) in enumerate(members):
        db.add(
            ProductSetMember(
                id=str(uuid.uuid4()),
                product_set_id=row.id,
                product_id=product.id,
                quantity=Decimal(str(quantity)),
                contributes_to_price=True,
                sort_order=order,
            )
        )
    db.flush()
    return row.id


def _price(db, set_id: str) -> dict:
    return line_pricing(db, [{"key": "k", "product_set_id": set_id}], _viewer())[0]


def test_set_list_price_is_the_members_times_quantity_and_sell_equals_list():
    with blank_session() as db:
        a = _product(db, list_price="100.00")
        b = _product(db, list_price="250.00")
        row = _price(db, _set(db, [(a, 2), (b, 1)]))

        assert float(row["list_price"]) == 450.0
        assert float(row["sell_price"]) == 450.0
        assert row["sell_price_basis"] == "list"
        assert row["promotion_options"] == []


def test_set_override_wins_over_the_members():
    with blank_session() as db:
        a = _product(db, list_price="100.00")
        b = _product(db, list_price="250.00")
        row = _price(db, _set(db, [(a, 2), (b, 1)], override="400.00"))

        assert float(row["list_price"]) == 400.0
        assert float(row["sell_price"]) == 400.0


def test_set_with_no_members_has_no_list_price():
    with blank_session() as db:
        row = _price(db, _set(db, []))

        assert row["list_price"] is None


@pytest.fixture
def portal_client():
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


def test_portal_line_pricing_route_accepts_product_set_id(portal_client):
    c, db = portal_client
    a = _product(db, list_price="100.00")
    b = _product(db, list_price="250.00")
    set_id = _set(db, [(a, 2), (b, 1)])

    res = c.post(_ROUTE, json={"lines": [{"key": "k", "product_set_id": set_id}]})

    assert res.status_code == 200, res.text
    assert float(res.json()[0]["list_price"]) == 450.0
