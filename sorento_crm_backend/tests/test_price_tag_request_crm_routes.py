"""The CRM price tag routes, on the wire.

``test_price_tag_request.py`` covers the service. This file covers what a
service test structurally cannot: FastAPI's ``response_model`` drops any field
the schema does not declare, silently, so the listing and the detail page drew
blanks for the line count, the salesperson, the promotion and the assignee while
every service call underneath was answering correctly.

Auth-override pattern from ``test_dealer_kit_tag_data_routes.py``.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
_BASE = "/api/v1/dealer-kit/price-tag-requests"

_MARKETER_ID = "2d6f8a41-5c93-5e27-b108-7a4d3f9c6e15"
_MARKETER_ROLE = "7b3e5d20-8f41-5a96-c274-1e6b9d4a8f30"
_MARKETER_NAME = "ZZT Marketing Mei"


def _seed_principals(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_MARKETER_ROLE,
            slug="zzt_price_tag_marketer",
            name="ZZT Price Tag Marketer",
            description="Designs price tags",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_MARKETER_ID,
            email="zzt-price-tag-marketer@test.com",
            name=_MARKETER_NAME,
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_MARKETER_ID, role_id=_MARKETER_ROLE))

    for slug in (
        "dealer_kit.price_tag_requests.view",
        "dealer_kit.price_tag_requests.process",
    ):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=_MARKETER_ROLE, permission_id=perm_id
            )
        )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_principals(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _MARKETER_ID, "email": "zzt-price-tag-marketer@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        with TestClient(app) as client:
            yield client, db

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _contact(db, name: str):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=name,
    )
    db.add(contact)
    db.flush()
    return contact


def _promotion(db, description: str) -> str:
    from app.models.marketing import Promotion

    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        is_active=True,
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    return promotion.id


def _product(db):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("PTR")
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=stem, category_name=f"ZZT cat {stem}"
    )
    brand = Brand(id=str(uuid.uuid4()), brand_code=stem[:50], brand_name=f"ZZT {stem}")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=1599.00,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _submitted_request(db, *, lines: int = 2, promotion_id: str | None = None):
    """A request the salesperson has SENT: no ``portal_draft_at``."""
    contact = _contact(db, unique_code("ZZT Sales Sam"))
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "promotion_id": promotion_id,
            "lines": [
                {"line_type": "product", "product_id": _product(db).id}
                for _ in range(lines)
            ],
        },
    )
    request.portal_draft_at = None
    db.commit()
    return request, contact


# ---------------------------------------------------------------------------
# What the screens draw
# ---------------------------------------------------------------------------


class TestTheDetailNamesWhoClaimedIt:
    def test_a_claim_records_the_claimer_and_the_detail_names_them(self, api):
        """"Assigned to" read "Unclaimed" forever after a successful claim.

        The claim wrote the user id into ``created_by``, which nothing reads
        back, and neither the column the page reads nor the name beside it was
        declared on the response - so the request moved to ``designing`` with no
        sign of who was designing it.
        """
        client, db = api
        request, _contact = _submitted_request(db)

        claimed = client.post(f"{_BASE}/{request.id}/claim")
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["assigned_to_id"] == _MARKETER_ID
        assert claimed.json()["assigned_to_name"] == _MARKETER_NAME

        detail = client.get(f"{_BASE}/{request.id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["assigned_to_id"] == _MARKETER_ID
        assert body["assigned_to_name"] == _MARKETER_NAME
        assert body["status"] == "designing"

    def test_the_creator_is_not_overwritten_by_a_claim(self, api):
        """``created_by`` says who made the row; it is not the assignee field."""
        client, db = api
        request, _contact = _submitted_request(db)
        assert request.created_by is None

        client.post(f"{_BASE}/{request.id}/claim")

        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        row = db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).first()
        assert row.created_by is None
        assert row.assigned_to_id == _MARKETER_ID

    def test_the_detail_names_the_salesperson_and_the_promotion(self, api):
        client, db = api
        promotion_id = _promotion(db, "ZZT August Promo")
        request, contact = _submitted_request(db, promotion_id=promotion_id)

        body = client.get(f"{_BASE}/{request.id}").json()

        assert body["contact_name"] == contact.name
        assert body["promotion_name"] == "ZZT August Promo"

    def test_an_unclaimed_request_says_so_rather_than_guessing(self, api):
        client, db = api
        request, _contact = _submitted_request(db)

        body = client.get(f"{_BASE}/{request.id}").json()

        assert body["assigned_to_id"] is None
        assert body["assigned_to_name"] is None


class TestTheListingCarriesWhatItDraws:
    def test_the_row_carries_the_line_count_and_the_names(self, api):
        client, db = api
        promotion_id = _promotion(db, "ZZT Listing Promo")
        request, contact = _submitted_request(db, lines=3, promotion_id=promotion_id)

        listed = client.get(_BASE, params={"q": request.doc_number})
        assert listed.status_code == 200, listed.text
        rows = listed.json()
        row = next(r for r in _rows_of(rows) if r["id"] == request.id)

        assert row["line_count"] == 3
        assert row["contact_name"] == contact.name
        assert row["promotion_name"] == "ZZT Listing Promo"
        assert row["assigned_to_name"] is None

    def test_a_claimed_row_shows_the_claimer_in_the_listing(self, api):
        client, db = api
        request, _contact = _submitted_request(db)
        client.post(f"{_BASE}/{request.id}/claim")

        listed = client.get(_BASE, params={"q": request.doc_number})
        row = next(r for r in _rows_of(listed.json()) if r["id"] == request.id)

        assert row["assigned_to_id"] == _MARKETER_ID
        assert row["assigned_to_name"] == _MARKETER_NAME


def _rows_of(body):
    """The listing rows, whether the body is a bare list or a paged envelope."""
    return body["data"] if isinstance(body, dict) else body
