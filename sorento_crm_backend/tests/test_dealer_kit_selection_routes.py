"""Route-level tests for /api/v1/dealer-kit/selections.

The service tests own the pricing and availability rules. What is under test
HERE is the thing a service test structurally cannot reach: that a Selection is
private to the person who made it.

There is no permission slug for this - a Selection is one person's basket, not
shared administrative data - so ownership IS the authorisation, and it is
checked on every route. The assertion that matters is that another signed-in
user, holding every dealer-kit permission there is, gets 404 rather than 403 or
the row. 403 would confirm the id exists, which turns a guess into an
enumeration of other people's designs.

Auth-override pattern from test_dealer_kit_routes.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_OWNER_ID = "7c3d9f21-4b85-5e60-9a12-6f4b8d2e0c37"
_OTHER_ID = "1e8a4b57-3d92-5c04-8f61-2b7c9e5a1d84"
_ROLE_ID = "9f2c6d18-7a43-5b95-8c20-4e1d3f7b6a52"
_SORENTO = "00000000-0000-0000-0000-000000000001"


def _seed(db: Session) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(User(id=_OWNER_ID, email="zzt-sel-owner@test.com", name="Owner", status="ACTIVE"))
    db.add(User(id=_OTHER_ID, email="zzt-sel-other@test.com", name="Other", status="ACTIVE"))
    db.flush()

    # BOTH users are superadmins. If the private-selection rule were expressed
    # as a permission, this test could not tell the difference.
    db.add(UserRoleAssignment(user_id=_OWNER_ID, role_id=_ROLE_ID))
    db.add(UserRoleAssignment(user_id=_OTHER_ID, role_id=_ROLE_ID))

    for slug in ("dealer_kit.page.view", "dealer_kit.page.edit"):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=perm_id)
        )
    db.commit()


def _product(db: Session, **overrides):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = f"ZZTSR{uuid.uuid4().hex[:6]}"
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("250.00"),
        invoice_price=Decimal("175.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
        company_id=_SORENTO,
    )
    fields.update(overrides)
    product = Product(**fields)
    db.add(product)
    db.flush()
    return product


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, _as

        app.dependency_overrides.clear()


def test_a_selection_round_trips_with_lines_and_a_room(api):
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)
    product = _product(db)

    created = client.post("/api/v1/dealer-kit/selections", json={"name": "ZZT kitchen"})
    assert created.status_code == 201, created.text
    selection_id = created.json()["id"]

    added = client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 2},
    )
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["lines"][0]["quantity"] == 2
    # Asserted against the SERVER response, never the DOM (AC-T3).
    assert body["total"] == "500.00"

    saved = client.put(
        f"/api/v1/dealer-kit/selections/{selection_id}/room",
        json={
            "outline": [
                {"x": 0, "y": 0},
                {"x": 4000, "y": 0},
                {"x": 4000, "y": 3000},
                {"x": 0, "y": 3000},
            ],
            "placements": [{"lineId": "x", "x": 100, "y": 100, "rotation": 90}],
        },
    )
    assert saved.status_code == 200, saved.text
    # Derived from the polygon on every read, never stored (AC-R5).
    assert saved.json()["roomAreaSqm"] == 12.0

    reopened = client.get(f"/api/v1/dealer-kit/selections/{selection_id}")
    assert reopened.status_code == 200
    assert len(reopened.json()["room"]["outline"]) == 4
    assert reopened.json()["room"]["placements"][0]["rotation"] == 90


def test_a_ceiling_height_round_trips(api):
    """The one vertical number the room has.

    Without it the 3D view is a floor plan floating in space, and every design
    silently assumes the same ceiling. It is optional on purpose: a design saved
    before this existed must still load rather than 422.
    """
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)

    created = client.post("/api/v1/dealer-kit/selections", json={"name": "ZZT ceiling"})
    selection_id = created.json()["id"]
    square = [
        {"x": 0, "y": 0},
        {"x": 3000, "y": 0},
        {"x": 3000, "y": 3000},
        {"x": 0, "y": 3000},
    ]

    saved = client.put(
        f"/api/v1/dealer-kit/selections/{selection_id}/room",
        json={"outline": square, "placements": [], "ceilingHeightMm": 2700},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["room"]["ceilingHeightMm"] == 2700

    reopened = client.get(f"/api/v1/dealer-kit/selections/{selection_id}")
    assert reopened.json()["room"]["ceilingHeightMm"] == 2700

    # Omitted entirely: still a valid save, and the height simply is not set.
    without = client.put(
        f"/api/v1/dealer-kit/selections/{selection_id}/room",
        json={"outline": square, "placements": []},
    )
    assert without.status_code == 200, without.text
    assert without.json()["room"]["ceilingHeightMm"] is None


def test_another_user_cannot_read_or_change_someone_elses_selection(api):
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post(
        "/api/v1/dealer-kit/selections", json={"name": "ZZT private"}
    ).json()["id"]

    _as(_OTHER_ID)
    assert client.get(f"/api/v1/dealer-kit/selections/{selection_id}").status_code == 404
    assert (
        client.post(
            f"/api/v1/dealer-kit/selections/{selection_id}/lines",
            json={"productId": product.id, "quantity": 1},
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/dealer-kit/selections/{selection_id}/room",
            json={"outline": [], "placements": []},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/dealer-kit/selections/{selection_id}").status_code == 404


def test_setting_a_line_to_zero_removes_it(api):
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 3},
    )

    cleared = client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 0},
    )
    assert cleared.status_code == 200
    assert cleared.json()["lines"] == []
    assert cleared.json()["total"] == "0.00"


def test_a_repeated_line_write_does_not_double_the_quantity(api):
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    payload = {"productId": product.id, "quantity": 2}
    client.post(f"/api/v1/dealer-kit/selections/{selection_id}/lines", json=payload)
    repeated = client.post(f"/api/v1/dealer-kit/selections/{selection_id}/lines", json=payload)

    # The write is absolute, so a retry is not an order for four.
    assert repeated.json()["lines"][0]["quantity"] == 2


def test_a_negative_quantity_is_refused(api):
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    response = client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": -1},
    )
    assert response.status_code == 422


def test_deleting_a_selection_leaves_the_product_alone(api):
    db, _as = api
    _as(_OWNER_ID)
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 1},
    )

    assert client.delete(f"/api/v1/dealer-kit/selections/{selection_id}").status_code == 204
    assert client.get(f"/api/v1/dealer-kit/selections/{selection_id}").status_code == 404

    from app.models.product import Product

    assert db.query(Product).filter(Product.id == product.id).first() is not None
