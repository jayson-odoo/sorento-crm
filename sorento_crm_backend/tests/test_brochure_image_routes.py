"""Route-level tests for the brochure image endpoints (S7.0).

``test_brochure_image_service.py`` owns the rules: one chosen image per product,
images only, nothing chosen automatically. What is under test HERE is the three
things a service test structurally cannot reach.

1. **The static paths win over the parametric ones.** ``/brochure-images`` sits
   on a router that already declares ``GET /{product_attachment_id}``, so a
   declaration in the wrong order makes FastAPI read "brochure-images" as an id
   and answer 400/404 forever. The same shape bit the SLA router
   (``/integration/escalate``), which is why it is asserted rather than assumed.
2. **The wire shape.** The frontend reads ``productId`` / ``chosenAttachmentId``
   / ``candidates[].attachmentId``; a snake_case response is a blank screen, not
   an error.
3. **Refusal.** A caller without ``master_data.product_attachments.view`` gets
   403, and an attachment belonging to another product gets 404 rather than 403,
   because a 403 confirms the row exists.

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

_EDITOR_ID = "4b17c8e2-6d59-5a30-9f84-1c2e7b0d3a65"
_EDITOR_ROLE = "0a5d3f92-7c81-5e46-b2d0-8f1a6c4e9b73"
_NOPERM_ID = "9c6e2a41-3f70-5b28-8d15-7a4b0e9c2f36"
_SORENTO = "00000000-0000-0000-0000-000000000001"

_BASE = "/api/v1/master-data/product-attachments/brochure-images"


def _seed(db: Session) -> None:
    """One role holding view+edit, and one user holding nothing at all."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_EDITOR_ROLE,
            slug="zzt_brochure_editor",
            name="ZZT Brochure Editor",
            description="Chooses product photographs",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(id=_EDITOR_ID, email="zzt-brochure-editor@test.com", name="Editor", status="ACTIVE")
    )
    db.add(
        User(id=_NOPERM_ID, email="zzt-brochure-outsider@test.com", name="Outsider", status="ACTIVE")
    )
    db.flush()

    db.add(UserRoleAssignment(user_id=_EDITOR_ID, role_id=_EDITOR_ROLE))

    # blank_session builds an empty schema, so the permission rows a real
    # database already holds have to be created here. These slugs exist in
    # production: the feature deliberately does not invent a new one.
    for slug in (
        "master_data.product_attachments.view",
        "master_data.product_attachments.edit",
    ):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=_EDITOR_ROLE, permission_id=perm_id
            )
        )
    db.commit()


def _product(db: Session, code: str | None = None):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = f"ZZTBI{uuid.uuid4().hex[:6]}"
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem[:20], uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        product_code=code or stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("250.00"),
        company_id=_SORENTO,
    )
    db.add(product)
    db.flush()
    return product


def _attach(db: Session, product, filename: str, mime: str = "image/jpeg"):
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment

    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"product/{filename}",
        mime_type=mime,
        company_id=_SORENTO,
    )
    db.add(attachment)
    db.flush()
    link = ProductAttachment(
        id=str(uuid.uuid4()),
        product_id=product.id,
        attachment_id=attachment.id,
        company_id=_SORENTO,
    )
    db.add(link)
    db.flush()
    return link


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

        # The real resolver reads the bearer token these tests do not send. Left
        # alone it returns UNSET and every owned SELECT is empty before any route
        # logic runs, so pin it to the incumbent company.
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


def _row(body: dict, product_id: str) -> dict:
    return next(item for item in body["items"] if item["productId"] == product_id)


def test_the_listing_answers_in_the_documented_shape(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    product = _product(db)
    link = _attach(db, product, "front.jpg")

    response = client.get(_BASE, params={"only_unset": "false", "query": product.product_code})
    assert response.status_code == 200, response.text
    body = response.json()

    assert {"items", "total", "remaining", "shown"} <= set(body)
    row = _row(body, product.id)
    assert row["productCode"] == product.product_code
    assert row["productName"] == product.product_name
    assert row["chosenAttachmentId"] is None
    candidate = row["candidates"][0]
    assert candidate["attachmentId"] == link.attachment_id
    # The filename is the ONLY thing telling two thumbnails apart when one of
    # them is a different product entirely.
    assert candidate["filename"] == "front.jpg"
    assert "url" in candidate
    assert "accessLevels" in candidate


def test_only_unset_hides_the_products_already_done(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    stem = f"ZZTPAIR{uuid.uuid4().hex[:6]}"
    chosen = _product(db, code=f"{stem}-A")
    pending = _product(db, code=f"{stem}-B")
    link = _attach(db, chosen, "a.jpg")
    _attach(db, pending, "b.jpg")

    assert (
        client.put(f"{_BASE}/{chosen.id}", json={"attachment_id": link.attachment_id}).status_code
        == 200
    )

    everything = client.get(_BASE, params={"only_unset": "false", "query": stem}).json()
    assert {item["productId"] for item in everything["items"]} == {chosen.id, pending.id}
    assert everything["total"] == 2
    assert everything["remaining"] == 1

    outstanding = client.get(_BASE, params={"only_unset": "true", "query": stem}).json()
    assert [item["productId"] for item in outstanding["items"]] == [pending.id]


def test_the_search_narrows_to_one_product(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    wanted = _product(db, code=f"ZZTWANTED{uuid.uuid4().hex[:6]}")
    other = _product(db, code=f"ZZTOTHER{uuid.uuid4().hex[:6]}")
    _attach(db, wanted, "a.jpg")
    _attach(db, other, "b.jpg")

    body = client.get(
        _BASE, params={"only_unset": "false", "query": wanted.product_code}
    ).json()

    assert [item["productId"] for item in body["items"]] == [wanted.id]


def test_choosing_an_image_is_named_back_and_read_back(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    product = _product(db)
    first = _attach(db, product, "a.jpg")
    second = _attach(db, product, "b.jpg")

    response = client.put(f"{_BASE}/{product.id}", json={"attachment_id": second.attachment_id})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "productId": product.id,
        "chosenAttachmentId": second.attachment_id,
    }

    listed = client.get(
        _BASE, params={"only_unset": "false", "query": product.product_code}
    ).json()
    assert _row(listed, product.id)["chosenAttachmentId"] == second.attachment_id
    assert first.attachment_id != second.attachment_id


def test_an_attachment_of_another_product_is_not_found(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    product = _product(db)
    elsewhere = _attach(db, _product(db), "b.jpg")

    response = client.put(
        f"{_BASE}/{product.id}", json={"attachment_id": elsewhere.attachment_id}
    )

    # 404, never 403: a 403 would confirm the row exists.
    assert response.status_code == 404, response.text
    # The message is asserted because an absent route is ALSO a 404. Without
    # this the test passes against a router that never had these paths.
    assert response.json()["message"] == "That file is not attached to this product"


def test_a_spec_sheet_cannot_be_the_brochure_image(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    product = _product(db)
    spec = _attach(db, product, "spec.pdf", mime="application/pdf")

    response = client.put(f"{_BASE}/{product.id}", json={"attachment_id": spec.attachment_id})

    assert response.status_code == 400, response.text


def test_an_unknown_product_is_not_found(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)

    response = client.put(
        f"{_BASE}/{uuid.uuid4()}", json={"attachment_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404, response.text
    # As above: an absent route answers 404 too, so the refusal has to be named.
    assert response.json()["message"] == "Product not found"


def test_clearing_leaves_the_product_with_no_chosen_image(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    product = _product(db)
    link = _attach(db, product, "a.jpg")
    client.put(f"{_BASE}/{product.id}", json={"attachment_id": link.attachment_id})

    cleared = client.delete(f"{_BASE}/{product.id}")
    assert cleared.status_code == 200, cleared.text

    listed = client.get(
        _BASE, params={"only_unset": "false", "query": product.product_code}
    ).json()
    assert _row(listed, product.id)["chosenAttachmentId"] is None


def test_a_caller_without_the_permission_is_refused(api):
    db, _as = api
    _as(_EDITOR_ID)
    client = TestClient(app)
    product = _product(db)
    link = _attach(db, product, "a.jpg")

    _as(_NOPERM_ID)
    assert client.get(_BASE).status_code == 403
    assert (
        client.put(f"{_BASE}/{product.id}", json={"attachment_id": link.attachment_id}).status_code
        == 403
    )
    assert client.delete(f"{_BASE}/{product.id}").status_code == 403
