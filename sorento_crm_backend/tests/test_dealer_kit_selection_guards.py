"""Guards for the Selection routes, from a self-review of the S4 code.

Each test here was written because reading the route raised a doubt, not because
something visibly broke. They are the cases a happy-path suite structurally
cannot reach.

Auth-override pattern from test_dealer_kit_selection_routes.py.
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

_OWNER_ID = "4a7e2c91-6b38-5d40-9e15-3f8b1d6c2a07"
_ROLE_ID = "2d9f5b71-8c46-5a13-b028-7e4c1f3a9b65"
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
    db.add(User(id=_OWNER_ID, email="zzt-guard@test.com", name="Guard", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_OWNER_ID, role_id=_ROLE_ID))
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

    code = f"ZZTG{uuid.uuid4().hex[:6]}"
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("120.00"),
        invoice_price=Decimal("84.00"),
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


def _contact(db: Session):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"6017{uuid.uuid4().hex[:7]}",
        name="ZZT guard contact",
    )
    db.add(contact)
    db.flush()
    return contact


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

        def _as(principal: dict):
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, _as

        app.dependency_overrides.clear()


def test_a_contact_owned_selection_is_not_reachable_through_the_user_route(api):
    """A contact's basket must not answer to a CRM principal.

    The ownership check compared `selection.user_id != caller`. A contact-owned
    selection has `user_id IS NULL`, so any principal whose id resolved to None
    matched it - None == None - and read somebody else's design.
    """
    db, _as = api
    from app.services.dealer_kit import selection_service

    contact = _contact(db)
    selection = selection_service.create_selection(db, contact_id=contact.id)
    db.commit()

    _as({"email": "no-id@test.com"})  # a principal with no resolvable id
    client = TestClient(app)

    assert client.get(f"/api/v1/dealer-kit/selections/{selection.id}").status_code == 404
    assert client.delete(f"/api/v1/dealer-kit/selections/{selection.id}").status_code == 404


def test_a_signed_in_user_is_not_handed_the_invoice_price(api):
    """A selection carries no document toggle, so there is nothing turning the
    internal price ON - and both gates must agree before it is sent (AC-G6).

    The route asserted `show_invoice_price=True` for every caller. The design
    has DEALERS signed in as CRM users, so that shipped the figure the invoice
    will be raised at to the person negotiating against it.
    """
    db, _as = api
    _as({"id": _OWNER_ID, "email": "zzt-guard@test.com"})
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    body = client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 1},
    ).json()

    assert body["lines"][0]["price"] == "120.00"
    assert body["lines"][0]["invoicePrice"] is None


def test_an_unknown_product_is_refused_rather_than_crashing(api):
    """A bad product id hit the foreign key and surfaced as a 500."""
    db, _as = api
    _as({"id": _OWNER_ID, "email": "zzt-guard@test.com"})
    client = TestClient(app)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    response = client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": str(uuid.uuid4()), "quantity": 1},
    )

    assert response.status_code == 404, response.text


def test_a_discontinued_product_can_still_be_removed(api):
    """Removing is the one edit that must keep working on a dead line.

    Otherwise a customer whose product was discontinued is stuck with it in
    their design and no way to take it out.
    """
    db, _as = api
    _as({"id": _OWNER_ID, "email": "zzt-guard@test.com"})
    client = TestClient(app)
    product = _product(db)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 2},
    )

    product.is_discontinued = True
    db.flush()

    cleared = client.post(
        f"/api/v1/dealer-kit/selections/{selection_id}/lines",
        json={"productId": product.id, "quantity": 0},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["lines"] == []


def test_a_room_with_a_malformed_outline_does_not_crash_the_read(api):
    """The room is stored as given. A client sending nonsense must not make the
    selection unreadable ever after - area simply has no answer."""
    db, _as = api
    _as({"id": _OWNER_ID, "email": "zzt-guard@test.com"})
    client = TestClient(app)

    selection_id = client.post("/api/v1/dealer-kit/selections", json={}).json()["id"]
    saved = client.put(
        f"/api/v1/dealer-kit/selections/{selection_id}/room",
        json={"outline": [{"x": "left", "y": None}, {"x": 1}], "placements": []},
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["roomAreaSqm"] is None
    assert client.get(f"/api/v1/dealer-kit/selections/{selection_id}").status_code == 200
