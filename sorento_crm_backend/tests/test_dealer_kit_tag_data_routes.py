"""Route-level tests for the tag editor's data endpoints (S3b, AC-L.2 / L.4 / L.8).

``test_dealer_kit_tag_data.py`` covers the service. This file covers what a
service test structurally cannot:

* **The permission gate.** These endpoints read the product master and resolved
  prices, so they sit behind ``dealer_kit.tag_templates.view`` like the rest of
  the editor. A user without it must be refused.
* **What survives ``response_model``.** FastAPI drops any field a response model
  does not declare, silently, and a tag with no spec lines looks exactly like a
  product that has none. Every field is asserted ON THE WIRE.

Auth-override pattern from test_dealer_kit_routes.py.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"

_DESIGNER_ID = "9f2c4b18-6d35-5e70-a91c-3b8e0d5f7a26"
_DESIGNER_ROLE = "4a8d6e02-7c19-5b43-8f26-1d9c5a3e0b74"
_OUTSIDER_ID = "1c7e3a95-4b28-5d61-9e03-6f2a8c4d5b19"


class _SigningBackend:
    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://cdn.test.invalid/{key}?Signature=stub"


@pytest.fixture(autouse=True)
def _signing_works(monkeypatch):
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _SigningBackend())


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
            id=_DESIGNER_ROLE,
            slug="zzt_tag_designer",
            name="ZZT Tag Designer",
            description="Designs price tags",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_DESIGNER_ID,
            email="zzt-tag-designer@test.com",
            name="Tag Designer",
            status="ACTIVE",
        )
    )
    db.add(
        User(
            id=_OUTSIDER_ID,
            email="zzt-tag-outsider@test.com",
            name="Outsider",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_DESIGNER_ID, role_id=_DESIGNER_ROLE))

    granted = ("dealer_kit.tag_templates.view", "dealer_kit.price_tag_requests.view")
    for slug in granted:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=_DESIGNER_ROLE, permission_id=perm_id
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

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        _as(_DESIGNER_ID)
        yield db, _as

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _product(db, *, list_price="1599.00", barcode=None):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTR")
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
        description="One line\nAnother line",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
        currency="MYR",
        dimensions_length=Decimal("800"),
        dimensions_width=Decimal("500"),
        dimensions_height=Decimal("220"),
        is_active=True,
        is_discontinued=False,
        barcode=barcode,
    )
    db.add(product)
    db.flush()
    return product


def _image(db, product):
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment

    name = unique_code("zztimg")
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{name}.jpg",
        stored_filename=f"{name}.jpg",
        file_path=f"https://cdn.example.test/products/{name}.jpg",
        mime_type="image/jpeg",
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    db.add(
        ProductAttachment(
            id=str(uuid.uuid4()),
            product_id=product.id,
            attachment_id=attachment.id,
            is_primary=True,
            sort_order=0,
            access_levels=["dealer", "end_user"],
            company_id=SORENTO,
        )
    )
    db.flush()
    return attachment


def _promotion(db, product, *, promo_price="599.00"):
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=unique_code("ZZT promo"),
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
        access_levels=["dealer", "end_user"],
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    # `promotion_group_id` is NOT NULL: every promotion line belongs to a group
    # (a headline group, a bundle group), so the seed builds one.
    group = PromotionGroup(
        promotion_id=promotion.id, group_name="ZZT group", sort_order=0
    )
    db.add(group)
    db.flush()

    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion.id,
            promotion_group_id=str(group.id),
            product_id=product.id,
            promo_selling_price=Decimal(promo_price),
            company_id=SORENTO,
        )
    )
    db.flush()
    return promotion


def _product_set(db, members):
    from app.models.product_set import ProductSet, ProductSetMember

    product_set = ProductSet(
        id=str(uuid.uuid4()),
        set_code=unique_code("ZZTSET"),
        name="ZZT set",
        company_id=SORENTO,
    )
    db.add(product_set)
    db.flush()
    for index, product in enumerate(members):
        db.add(
            ProductSetMember(
                id=str(uuid.uuid4()),
                product_set_id=product_set.id,
                product_id=product.id,
                quantity=Decimal("1"),
                contributes_to_price=True,
                sort_order=index,
            )
        )
    db.flush()
    return product_set


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_product_search_returns_id_code_and_name(api):
    db, _as = api
    product = _product(db)

    with TestClient(app) as client:
        res = client.get(
            "/api/v1/dealer-kit/products/search",
            params={"q": product.product_code, "limit": 10},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body == [
        {
            "id": product.id,
            "product_code": product.product_code,
            "product_name": product.product_name,
        }
    ]


def test_product_search_is_refused_without_the_view_permission(api):
    db, _as = api
    _product(db)
    _as(_OUTSIDER_ID)

    with TestClient(app) as client:
        res = client.get("/api/v1/dealer-kit/products/search", params={"q": "ZZT"})

    assert res.status_code == 403, res.text


def test_product_set_search_returns_id_code_and_name(api):
    db, _as = api
    product_set = _product_set(db, [_product(db)])

    with TestClient(app) as client:
        res = client.get(
            "/api/v1/dealer-kit/product-sets/search",
            params={"q": product_set.set_code},
        )

    assert res.status_code == 200, res.text
    assert res.json() == [
        {
            "id": product_set.id,
            "set_code": product_set.set_code,
            "name": product_set.name,
        }
    ]


# ---------------------------------------------------------------------------
# Tag data on the wire
# ---------------------------------------------------------------------------


def test_product_tag_data_keeps_every_field(api):
    """`response_model` drops what it does not declare. Assert the whole shape."""
    db, _as = api
    product = _product(db, barcode="1234567890123")
    attachment = _image(db, product)
    promotion = _promotion(db, product)

    with TestClient(app) as client:
        res = client.get(
            f"/api/v1/dealer-kit/products/{product.id}/tag-data",
            params={"promotion_id": promotion.id},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {
        "id",
        "code",
        "name",
        "dimensions",
        "spec_lines",
        "specs",
        "images",
        "list_price",
        "offer_price",
        "promotion_id",
        "barcode",
    }
    assert body["code"] == product.product_code
    assert body["name"] == product.product_name
    assert body["dimensions"] == "800 x 500 x 220 mm"
    assert body["spec_lines"] == ["One line", "Another line"]
    assert body["images"] == [
        {
            "attachment_id": attachment.id,
            "url": body["images"][0]["url"],
            "is_primary": True,
        }
    ]
    assert body["images"][0]["url"].startswith("https://")
    assert body["list_price"] == 1599.0
    assert body["offer_price"] == 599.0
    assert body["promotion_id"] == promotion.id
    assert body["barcode"] == "1234567890123"


def test_unknown_product_is_404(api):
    _db, _as = api

    with TestClient(app) as client:
        res = client.get(f"/api/v1/dealer-kit/products/{uuid.uuid4()}/tag-data")

    assert res.status_code == 404, res.text


def test_product_set_tag_data_keeps_every_field(api):
    db, _as = api
    first = _product(db, list_price="1000.00")
    second = _product(db, list_price="200.00")
    product_set = _product_set(db, [first, second])

    with TestClient(app) as client:
        res = client.get(
            f"/api/v1/dealer-kit/product-sets/{product_set.id}/tag-data"
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {
        "id",
        "set_code",
        "name",
        "members",
        "list_price",
        "offer_price",
        "promotion_id",
    }
    assert set(body["members"][0]) == {
        "product_id",
        "code",
        "name",
        "dimensions",
        "quantity",
    }
    assert [m["code"] for m in body["members"]] == [
        first.product_code,
        second.product_code,
    ]
    assert body["list_price"] == 1200.0


# ---------------------------------------------------------------------------
# Preview resolution (AC-L.8)
# ---------------------------------------------------------------------------


def test_resolve_preview_answers_with_product_tag_data(api):
    db, _as = api
    product = _product(db)
    promotion = _promotion(db, product)

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/dealer-kit/tag-templates/resolve-preview",
            json={"product_id": product.id, "promotion_id": promotion.id},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["product"]["code"] == product.product_code
    assert body["product"]["offer_price"] == 599.0
    assert body["product_set"] is None


def test_resolve_preview_answers_with_set_tag_data(api):
    db, _as = api
    product_set = _product_set(db, [_product(db, list_price="300.00")])

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/dealer-kit/tag-templates/resolve-preview",
            json={"product_set_id": product_set.id},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["product"] is None
    assert body["product_set"]["set_code"] == product_set.set_code
    assert body["product_set"]["list_price"] == 300.0


def test_resolve_preview_needs_something_to_resolve(api):
    _db, _as = api

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/dealer-kit/tag-templates/resolve-preview", json={}
        )

    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# Request line prices (AC-L.8) - the Phase 1 mock is gone
# ---------------------------------------------------------------------------


def test_resolve_prices_for_lines_returns_engine_prices(api):
    db, _as = api
    from app.models.access import RespondContact
    from app.services.price_tag_request_service import PriceTagRequestService

    product = _product(db, barcode="4567891234567")
    promotion = _promotion(db, product)

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "promotion_id": promotion.id,
            "lines": [
                {
                    "line_type": "product",
                    "product_id": product.id,
                    "show_promo_price": True,
                    "quantity": 1,
                }
            ],
        },
    )
    db.commit()
    line_id = request.lines[0].id

    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/dealer-kit/price-tag-requests/{request.id}/resolve-prices",
            json=[line_id],
        )

    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["line_id"] == line_id
    assert row["code"] == product.product_code
    assert row["name"] == product.product_name
    assert row["list_price"] == 1599.0
    assert row["sell_price"] == 599.0
    assert row["dimensions"] == "800 x 500 x 220 mm"
    assert row["spec_lines"] == "One line\nAnother line"
    assert row["barcode"] == "4567891234567"


# ---------------------------------------------------------------------------
# Request DETAIL lines carry what the detail page draws
# ---------------------------------------------------------------------------


def test_request_detail_lines_carry_code_name_and_prices(api):
    """The CRM detail page draws `line.code`, `line.name` and both prices.

    None of the four is a column on ``price_tag_request_lines`` - a line stores
    a product id and nothing else - so a response model that declares only the
    columns hands the page four blanks and the grid reads as a request with no
    products in it. Asserted ON THE WIRE because ``response_model`` drops an
    undeclared field silently.
    """
    db, _as = api
    from app.models.access import RespondContact
    from app.services.price_tag_request_service import PriceTagRequestService

    product = _product(db)
    promotion = _promotion(db, product)

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "promotion_id": promotion.id,
            "lines": [
                {
                    "line_type": "product",
                    "product_id": product.id,
                    "show_promo_price": True,
                    "quantity": 1,
                }
            ],
        },
    )
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}")

    assert res.status_code == 200, res.text
    line = res.json()["lines"][0]
    assert line["code"] == product.product_code
    assert line["name"] == product.product_name
    assert line["list_price"] == 1599.0
    assert line["sell_price"] == 599.0


def test_request_detail_line_for_a_set_carries_the_set_code_and_name(api):
    """A set line names the SET, not one of its members."""
    db, _as = api
    from app.models.access import RespondContact
    from app.services.price_tag_request_service import PriceTagRequestService

    product_set = _product_set(db, [_product(db, list_price="300.00")])

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {
                    "line_type": "product_set",
                    "product_set_id": product_set.id,
                    "quantity": 1,
                }
            ],
        },
    )
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}")

    assert res.status_code == 200, res.text
    line = res.json()["lines"][0]
    assert line["code"] == product_set.set_code
    assert line["name"] == product_set.name
    assert line["list_price"] == 300.0
    assert line["sell_price"] is None


def test_request_detail_line_survives_a_product_that_is_gone(api):
    """A line the resolver cannot answer for still appears, with blank text.

    The resolver SKIPS a line whose product has disappeared. Dropping the line
    from the detail response too would make a request look shorter than it is,
    so the line is returned with what the row itself knows.
    """
    db, _as = api
    from app.models.access import RespondContact
    from app.services.price_tag_request_service import PriceTagRequestService

    product = _product(db)
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {"line_type": "product", "product_id": product.id, "quantity": 1}
            ],
        },
    )
    db.commit()

    from app.models.product import Product

    db.query(Product).filter(Product.id == product.id).update({"is_active": False})
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/dealer-kit/price-tag-requests/{request.id}")

    assert res.status_code == 200, res.text
    lines = res.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["product_id"] == product.id


# ---------------------------------------------------------------------------
# The print payload carries each line's photos (D42)
# ---------------------------------------------------------------------------


def test_print_payload_lines_carry_their_photos(api):
    """A photo slot with no pinned attachment follows the product's PRIMARY
    photo (D42). The page can only pick it if the payload sends the line's
    images, and the payload is a plain dict, so this is the test that keeps
    the key from quietly disappearing."""
    db, _as = api
    from app.models.access import RespondContact
    from app.models.dealer_kit import ExportRequest, Page, PageVersion
    from app.models.download import DownloadStatus, UserDownload
    from app.services.dealer_kit.tag_sheet_export_service import (
        resolve_tag_sheet_print_payload,
    )
    from app.services.price_tag_request_service import PriceTagRequestService

    product = _product(db)
    photo = _image(db, product)

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {
                    "line_type": "product",
                    "product_id": product.id,
                    "show_promo_price": False,
                    "quantity": 1,
                }
            ],
        },
    )
    db.flush()
    line_id = request.lines[0].id

    stem = unique_code("zzttag").lower()
    page = Page(
        name=f"ZZT tags {stem}",
        slug=f"zzt-tags-{stem}",
        kind="tag_sheet",
        company_id=SORENTO,
    )
    db.add(page)
    db.flush()
    version = PageVersion(
        page_id=page.id,
        version=1,
        doc={"kind": "tag_sheet", "imposition": {}, "sheets": []},
    )
    db.add(version)
    db.flush()
    request.page_id = page.id

    download = UserDownload(
        user_id=_DESIGNER_ID,
        kind="dealer_kit_tag_sheet_pdf",
        source_entity_type="price_tag_request",
        source_entity_id=request.id,
        status=DownloadStatus.PENDING.value,
        filename="zzt-tags.pdf",
    )
    db.add(download)
    db.flush()
    db.add(
        ExportRequest(
            download_id=download.id,
            page_id=page.id,
            page_version_id=version.id,
            audience="staff",
            show_invoice_price=False,
            requested_by=_DESIGNER_ID,
        )
    )
    db.commit()

    payload = resolve_tag_sheet_print_payload(db, download.id)

    row = payload["resolvedData"][line_id]
    assert [img["attachment_id"] for img in row["images"]] == [photo.id]
    assert row["images"][0]["is_primary"] is True
    assert row["images"][0]["url"].startswith("https://")
    # And the same photo is in the signed map the page preloads.
    assert photo.id in payload["images"]


# ---------------------------------------------------------------------------
# Merge fields: the specs on the wire, and the key catalogue (D58, AC-M.24)
# ---------------------------------------------------------------------------


def _registry_key(db, spec_key, label, *, unit=None, is_active=True):
    from app.models.product_spec import ProductSpecRegistry

    row = ProductSpecRegistry(
        id=str(uuid.uuid4()),
        spec_key=spec_key,
        label=label,
        data_type="enum",
        unit=unit,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _spec_values(db, product, values):
    from app.models.product_spec import ProductSpecifications

    db.add(
        ProductSpecifications(
            id=str(uuid.uuid4()),
            product_id=product.id,
            values=values,
            provenance={},
            rendered_text="ZZT rendered",
        )
    )
    db.flush()


def test_product_tag_data_carries_specs_on_the_wire(api):
    """``response_model`` drops what it does not declare, and a product with no
    specs looks exactly like one whose specs were dropped. Asserted on the
    wire for that reason."""
    db, _as = api

    stem = unique_code("zztw").lower()
    _registry_key(db, f"{stem}_diameter", "Diameter", unit="mm")
    product = _product(db)
    _spec_values(db, product, {f"{stem}_diameter": {"value": 407}})
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/dealer-kit/products/{product.id}/tag-data")

    assert res.status_code == 200, res.text
    specs = res.json()["specs"]
    assert {
        "key": f"{stem}_diameter",
        "label": "Diameter",
        "value": "407",
        "unit": "mm",
    } in specs


def test_spec_keys_are_listed_for_the_merge_field_catalogue(api):
    """The Insert field dialog's spec group. Behind the editor's own
    permission, not the master-data one, so a marketing role that may design a
    tag can read it."""
    db, _as = api

    stem = unique_code("zztc").lower()
    _registry_key(db, f"{stem}_material", "Material")
    _registry_key(db, f"{stem}_retired", "Retired", is_active=False)
    db.commit()

    with TestClient(app) as client:
        res = client.get("/api/v1/dealer-kit/spec-keys")

    assert res.status_code == 200, res.text
    keys = {row["key"]: row for row in res.json()}
    assert keys[f"{stem}_material"]["label"] == "Material"
    assert f"{stem}_retired" not in keys


def test_spec_keys_refuse_a_user_without_the_editor_permission(api):
    db, _as = api
    db.commit()
    _as(_OUTSIDER_ID)

    with TestClient(app) as client:
        res = client.get("/api/v1/dealer-kit/spec-keys")

    assert res.status_code == 403, res.text


def test_print_payload_lines_carry_their_specs(api):
    """A ``{{spec.<key>}}`` in a saved tag has to resolve in the PDF too, and
    the payload is a plain dict with no schema to keep the key alive."""
    db, _as = api
    from app.models.access import RespondContact
    from app.models.dealer_kit import ExportRequest, Page, PageVersion
    from app.models.download import DownloadStatus, UserDownload
    from app.services.dealer_kit.tag_sheet_export_service import (
        resolve_tag_sheet_print_payload,
    )
    from app.services.price_tag_request_service import PriceTagRequestService

    stem = unique_code("zztp").lower()
    _registry_key(db, f"{stem}_material", "Material")
    product = _product(db)
    _spec_values(db, product, {f"{stem}_material": {"value": "ceramic"}})

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": [
                {"line_type": "product", "product_id": product.id, "quantity": 1}
            ],
        },
    )
    db.flush()
    line_id = request.lines[0].id

    slug = unique_code("zztspec").lower()
    page = Page(
        name=f"ZZT tags {slug}",
        slug=f"zzt-tags-{slug}",
        kind="tag_sheet",
        company_id=SORENTO,
    )
    db.add(page)
    db.flush()
    version = PageVersion(
        page_id=page.id,
        version=1,
        doc={"kind": "tag_sheet", "imposition": {}, "sheets": []},
    )
    db.add(version)
    db.flush()
    request.page_id = page.id

    download = UserDownload(
        user_id=_DESIGNER_ID,
        kind="dealer_kit_tag_sheet_pdf",
        source_entity_type="price_tag_request",
        source_entity_id=request.id,
        status=DownloadStatus.PENDING.value,
        filename="zzt-tags.pdf",
    )
    db.add(download)
    db.flush()
    db.add(
        ExportRequest(
            download_id=download.id,
            page_id=page.id,
            page_version_id=version.id,
            audience="staff",
            show_invoice_price=False,
            requested_by=_DESIGNER_ID,
        )
    )
    db.commit()

    payload = resolve_tag_sheet_print_payload(db, download.id)

    assert {
        "key": f"{stem}_material",
        "label": "Material",
        "value": "ceramic",
        "unit": None,
    } in payload["resolvedData"][line_id]["specs"]
