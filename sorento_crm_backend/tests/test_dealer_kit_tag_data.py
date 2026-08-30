"""The data layer behind a price tag: product search, tag data, set members, prices.

Written BEFORE the implementation (S3b, AC-L.2 / L.4 / L.8).

The canvas can already draw a tag. What it could not do was say WHAT the tag is
about: the editor had a mocked resolver and the tag sheet designer built its
display data out of the request line alone, so a tag showed a code and two empty
strings where the flyer shows a photo, a spec list and a price.

Three things these tests pin down, because getting any of them wrong is a wrong
price or a leaked image in front of a customer:

* **Prices come from ``resolve_prices``**, never from a second copy of the
  promotion rules. A promotion line priced below list resolves to
  ``offer_price``; anything else the pricing engine refuses (expired, inactive,
  wrong audience) has to be refused here too, because it is the same call.
* **Images go through the SAME gate as ``primary_image_urls``.** Trade imagery
  is tagged ``dealer`` and must be absent - not hidden - for a consumer.
* **Every field survives ``response_model``.** FastAPI silently drops what a
  response model does not declare, and a missing ``spec_lines`` looks exactly
  like a product with no specs.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


class _SigningBackend:
    """Signing that works without this machine holding a CloudFront key.

    Same stub as tests/test_dealer_kit_product_images.py, and for the same
    reason: image paths sign STRICTLY, so without it every URL would be absent
    and the access-control assertions below would pass for the wrong reason.
    """

    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://cdn.test.invalid/{key}?Signature=stub"


@pytest.fixture(autouse=True)
def _signing_works(monkeypatch):
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _SigningBackend())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _product(db, *, list_price="1599.00", description=None, code=None):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTD")
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=stem,
        category_name=f"ZZT cat {stem}",
    )
    brand = Brand(
        id=str(uuid.uuid4()), brand_code=stem[:50], brand_name=f"ZZT brand {stem}"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=code or stem,
        product_name=f"ZZT product {stem}",
        description=description,
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
    )
    db.add(product)
    db.flush()
    return product


def _image(db, product, *, access_levels, is_primary=False, sort_order=0):
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
            is_primary=is_primary,
            sort_order=sort_order,
            access_levels=access_levels,
            company_id=SORENTO,
        )
    )
    db.flush()
    return attachment


def _promotion(db, product, *, promo_price="599.00", access_levels=None):
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=unique_code("ZZT promo"),
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
        access_levels=access_levels or ["dealer", "end_user"],
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


def _spec(db, product, rendered_text):
    from app.models.product_spec import ProductSpecifications

    db.add(
        ProductSpecifications(
            id=str(uuid.uuid4()),
            product_id=product.id,
            values={},
            provenance={},
            rendered_text=rendered_text,
        )
    )
    db.flush()


def _product_set(db, members):
    from app.models.product_set import ProductSet, ProductSetMember

    product_set = ProductSet(
        id=str(uuid.uuid4()),
        set_code=unique_code("ZZTSET"),
        name="ZZT bathroom furniture set",
        company_id=SORENTO,
    )
    db.add(product_set)
    db.flush()

    for index, (product, quantity, contributes) in enumerate(members):
        db.add(
            ProductSetMember(
                id=str(uuid.uuid4()),
                product_set_id=product_set.id,
                product_id=product.id,
                quantity=Decimal(str(quantity)),
                contributes_to_price=contributes,
                sort_order=index,
            )
        )
    db.flush()
    db.refresh(product_set)
    return product_set


# ---------------------------------------------------------------------------
# Product search (AC-L.2)
# ---------------------------------------------------------------------------


class TestProductSearch:
    def test_matches_code_and_name(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)

        by_code = tag_data_service.search_products(db, product.product_code, limit=10)
        by_name = tag_data_service.search_products(db, product.product_name, limit=10)

        assert [p.id for p in by_code] == [product.id]
        assert product.id in [p.id for p in by_name]

    def test_inactive_products_are_not_offered(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        product.is_active = False
        db.flush()

        assert tag_data_service.search_products(db, product.product_code, limit=10) == []

    def test_limit_is_honoured(self, db):
        from app.services.dealer_kit import tag_data_service

        stem = unique_code("ZZTLIM")
        for index in range(3):
            _product(db, code=f"{stem}-{index}")

        assert len(tag_data_service.search_products(db, stem, limit=2)) == 2


# ---------------------------------------------------------------------------
# Product tag data (AC-L.2)
# ---------------------------------------------------------------------------


class TestProductTagData:
    def test_every_field_is_populated(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        _spec(db, product, "Stainless steel bowl.\nOverflow included.")
        _image(db, product, access_levels=["dealer", "end_user"], is_primary=True)

        data = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )

        assert data["id"] == product.id
        assert data["code"] == product.product_code
        assert data["name"] == product.product_name
        assert data["dimensions"] == "800 x 500 x 220 mm"
        assert data["spec_lines"] == [
            "Stainless steel bowl.",
            "Overflow included.",
        ]
        assert len(data["images"]) == 1
        assert data["images"][0]["is_primary"] is True
        assert data["images"][0]["url"].startswith("https://")
        assert data["list_price"] == Decimal("1599.00")
        assert data["offer_price"] is None
        assert data["promotion_id"] is None

    def test_spec_lines_fall_back_to_flyer_text_then_description(self, db):
        from app.models.product_spec import ProductFlyerText
        from app.services.dealer_kit import tag_data_service

        viewer = tag_data_service.staff_viewer()

        # 1. Nothing but a description.
        described = _product(db, description="Single bowl sink\nWith drainer")
        assert tag_data_service.product_tag_data(db, described, viewer)["spec_lines"] == [
            "Single bowl sink",
            "With drainer",
        ]

        # 2. Flyer text wins over the description.
        db.add(
            ProductFlyerText(
                id=str(uuid.uuid4()),
                product_code=described.product_code,
                source_label="ZZT A3 FLYER",
                lines=["Flyer line one", "Flyer line two"],
                text="Flyer line one\nFlyer line two",
            )
        )
        db.flush()
        assert tag_data_service.product_tag_data(db, described, viewer)["spec_lines"] == [
            "Flyer line one",
            "Flyer line two",
        ]

        # 3. Derived specs win over both.
        _spec(db, described, "Derived spec sentence")
        assert tag_data_service.product_tag_data(db, described, viewer)["spec_lines"] == [
            "Derived spec sentence"
        ]

    def test_dealer_only_photo_is_absent_for_a_consumer(self, db):
        from app.services.dealer_kit import tag_data_service
        from app.services.dealer_kit.viewer import ViewerContext

        product = _product(db)
        _image(db, product, access_levels=["end_user"], is_primary=True)
        _image(db, product, access_levels=["dealer"], sort_order=1)

        staff = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )
        consumer = tag_data_service.product_tag_data(
            db, product, ViewerContext(access_codes=frozenset({"end_user"}))
        )

        assert len(staff["images"]) == 2
        assert len(consumer["images"]) == 1

    def test_primary_photo_comes_first(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        _image(db, product, access_levels=["end_user"], sort_order=0)
        primary = _image(
            db, product, access_levels=["end_user"], is_primary=True, sort_order=9
        )

        images = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )["images"]

        assert images[0]["attachment_id"] == primary.id
        assert images[0]["is_primary"] is True

    def test_offer_price_comes_from_the_promotion_line(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db, list_price="1599.00")
        promotion = _promotion(db, product, promo_price="599.00")

        data = tag_data_service.product_tag_data(
            db,
            product,
            tag_data_service.staff_viewer(),
            promotion_id=promotion.id,
        )

        assert data["list_price"] == Decimal("1599.00")
        assert data["offer_price"] == Decimal("599.00")
        assert data["promotion_id"] == promotion.id

    def test_no_promotion_named_means_no_offer(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db, list_price="1599.00")
        _promotion(db, product, promo_price="599.00")

        data = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )

        assert data["offer_price"] is None
        assert data["promotion_id"] is None


# ---------------------------------------------------------------------------
# Product set tag data (AC-L.4)
# ---------------------------------------------------------------------------


class TestProductSetTagData:
    def test_members_carry_code_name_dimensions_and_quantity(self, db):
        from app.services.dealer_kit import tag_data_service

        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="200.00")
        product_set = _product_set(db, [(first, 1, True), (second, 2, True)])

        data = tag_data_service.product_set_tag_data(
            db, product_set, tag_data_service.staff_viewer()
        )

        assert data["id"] == product_set.id
        assert data["set_code"] == product_set.set_code
        assert data["name"] == product_set.name
        assert len(data["members"]) == 2
        member = data["members"][0]
        assert member["product_id"] == first.id
        assert member["code"] == first.product_code
        assert member["name"] == first.product_name
        assert member["dimensions"] == "800 x 500 x 220 mm"
        assert member["quantity"] == 1

    def test_list_price_sums_the_contributing_members(self, db):
        from app.services.dealer_kit import tag_data_service

        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="200.00")
        third = _product(db, list_price="500.00")
        product_set = _product_set(
            db, [(first, 1, True), (second, 2, True), (third, 1, False)]
        )

        data = tag_data_service.product_set_tag_data(
            db, product_set, tag_data_service.staff_viewer()
        )

        # 1000 x 1 + 200 x 2. The un-ticked member contributes nothing.
        assert data["list_price"] == Decimal("1400.00")

    def test_offer_price_uses_the_promotion_for_members_that_have_one(self, db):
        from app.services.dealer_kit import tag_data_service

        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="200.00")
        product_set = _product_set(db, [(first, 1, True), (second, 1, True)])
        promotion = _promotion(db, first, promo_price="700.00")

        data = tag_data_service.product_set_tag_data(
            db,
            product_set,
            tag_data_service.staff_viewer(),
            promotion_id=promotion.id,
        )

        # The promoted member at its offer, the other at list.
        assert data["offer_price"] == Decimal("900.00")
        assert data["promotion_id"] == promotion.id

    def test_a_member_with_no_price_cancels_the_set_offer(self, db):
        """An unpriceable member abandons the offer; it is not worth RM 0.

        The sum counted a member the pricing engine could not price as zero, so
        a three-piece set with one unpriced member printed a set offer far below
        the sum of its parts - a discount nobody authorised, on paper, in a
        dealer's hands. The list price is unaffected: that is the set's own
        rule, and it is the honest thing to print when the offer cannot be
        computed.
        """
        from app.services.dealer_kit import tag_data_service

        priced = _product(db, list_price="1000.00")
        promoted = _product(db, list_price="200.00")
        # Zero IS the absence of a price here: `products.list_price` is NOT NULL
        # and defaults to nought, so a product whose price was never imported
        # looks exactly like this and `_a_real_price` answers None for it.
        unpriced = _product(db, list_price="0.00")
        product_set = _product_set(
            db, [(priced, 1, True), (promoted, 1, True), (unpriced, 1, True)]
        )
        promotion = _promotion(db, promoted, promo_price="150.00")

        data = tag_data_service.product_set_tag_data(
            db,
            product_set,
            tag_data_service.staff_viewer(),
            promotion_id=promotion.id,
        )

        assert data["offer_price"] is None
        assert data["promotion_id"] is None

    def test_an_unpriced_member_that_does_not_count_leaves_the_offer_alone(
        self, db
    ):
        """Only a member that contributes to the price can cancel the offer."""
        from app.services.dealer_kit import tag_data_service

        promoted = _product(db, list_price="1000.00")
        freebie = _product(db, list_price="0.00")
        product_set = _product_set(db, [(promoted, 1, True), (freebie, 1, False)])
        promotion = _promotion(db, promoted, promo_price="700.00")

        data = tag_data_service.product_set_tag_data(
            db,
            product_set,
            tag_data_service.staff_viewer(),
            promotion_id=promotion.id,
        )

        assert data["offer_price"] == Decimal("700.00")

    def test_no_offer_on_any_member_means_no_set_offer(self, db):
        from app.services.dealer_kit import tag_data_service

        first = _product(db, list_price="1000.00")
        product_set = _product_set(db, [(first, 1, True)])
        promotion = _promotion(db, _product(db), promo_price="10.00")

        data = tag_data_service.product_set_tag_data(
            db,
            product_set,
            tag_data_service.staff_viewer(),
            promotion_id=promotion.id,
        )

        assert data["offer_price"] is None
        assert data["promotion_id"] is None


# ---------------------------------------------------------------------------
# Request line resolution (AC-L.8) - the mock is gone
# ---------------------------------------------------------------------------


class TestResolveLines:
    def _request_with_line(self, db, product, promotion_id=None):
        from app.models.access import RespondContact
        from app.services.price_tag_request_service import PriceTagRequestService

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
                "promotion_id": promotion_id,
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
        db.flush()
        return request

    def test_line_data_carries_real_product_and_prices(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db, list_price="1599.00")
        _spec(db, product, "Spec one")
        promotion = _promotion(db, product, promo_price="599.00")
        request = self._request_with_line(db, product, promotion_id=promotion.id)

        rows = tag_data_service.resolve_request_line_data(db, request)

        assert len(rows) == 1
        row = rows[0]
        assert row["code"] == product.product_code
        assert row["name"] == product.product_name
        assert row["dimensions"] == "800 x 500 x 220 mm"
        assert row["spec_lines"] == "Spec one"
        assert row["list_price"] == Decimal("1599.00")
        assert row["sell_price"] == Decimal("599.00")
        assert row["show_promo_price"] is True

    def test_marketing_override_wins_over_the_resolved_offer(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db, list_price="1599.00")
        promotion = _promotion(db, product, promo_price="599.00")
        request = self._request_with_line(db, product, promotion_id=promotion.id)

        request.lines[0].marketing_price_override = Decimal("499.00")
        db.flush()

        row = tag_data_service.resolve_request_line_data(db, request)[0]
        assert row["sell_price"] == Decimal("499.00")

    def test_a_set_line_carries_its_members(self, db):
        from app.models.access import RespondContact
        from app.services.dealer_kit import tag_data_service
        from app.services.price_tag_request_service import PriceTagRequestService

        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="200.00")
        product_set = _product_set(db, [(first, 1, True), (second, 1, True)])

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
                        "show_promo_price": False,
                        "quantity": 1,
                    }
                ],
            },
        )
        db.flush()

        row = tag_data_service.resolve_request_line_data(db, request)[0]
        assert row["code"] == product_set.set_code
        assert first.product_code in row["set_members"]
        assert second.product_code in row["set_members"]
        assert row["list_price"] == Decimal("1200.00")


# ---------------------------------------------------------------------------
# The specs a merge field draws on, key by key (D58, AC-M.24)
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


class TestMeasurementsPrintAsMeasured:
    """A dimension read out of JSONB is a float, and floats do not round-trip.

    ``Decimal(407.3)`` is 407.29999999999998863131622783839702606201171875, and
    ``normalize():f`` prints every one of those digits. The spec row wins over
    the master columns, so a product whose reviewed specs carry a fractional
    measurement had that on the physical tag.
    """

    def test_a_fractional_dimension_prints_as_it_was_measured(self):
        from app.services.dealer_kit.tag_data_service import format_dimensions_mm

        assert format_dimensions_mm(407.3, 500, 220) == "407.3 x 500 x 220 mm"

    def test_a_whole_float_keeps_its_shape_too(self):
        from app.services.dealer_kit.tag_data_service import format_dimensions_mm

        assert format_dimensions_mm(800.0, 500.0, 220.0) == "800 x 500 x 220 mm"

    def test_a_spec_row_measurement_reaches_the_tag_intact(self, db):
        """The path that actually feeds a printed tag: JSONB, not a column."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        _spec_values(
            db,
            product,
            {
                "dim_length": {"value": 407.3, "unit": "mm"},
                "dim_width": {"value": 500, "unit": "mm"},
                "dim_height": {"value": 220, "unit": "mm"},
            },
        )

        data = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer(), with_images=False
        )

        assert data["dimensions"] == "407.3 x 500 x 220 mm"


class TestProductSpecs:
    """``{{spec.<key>}}`` needs the product's specs key by key.

    ``spec_lines`` is the rendered SENTENCE and has always been there; nothing
    on a tag has ever been able to reach one value on its own. These pin the
    join: the registry says which keys exist and what they are called, the
    product's reviewed row says which of them it carries.
    """

    def test_specs_join_the_registry_to_the_reviewed_values(self, db):
        from app.services.dealer_kit import tag_data_service

        stem = unique_code("zztk").lower()
        _registry_key(db, f"{stem}_diameter", "Diameter", unit="mm")
        _registry_key(db, f"{stem}_material", "Material")
        # A key the registry knows and this product does not carry.
        _registry_key(db, f"{stem}_finish", "Finish")

        product = _product(db)
        _spec_values(
            db,
            product,
            {
                f"{stem}_diameter": {"value": 407, "unit": "mm"},
                # Stored bare rather than wrapped, which the catalogue does.
                f"{stem}_material": "ceramic",
                # A value whose key is not in the registry at all.
                "zzt_not_a_registry_key": {"value": "ignored"},
            },
        )

        specs = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )["specs"]

        mine = [row for row in specs if row["key"].startswith(stem)]
        assert mine == [
            {
                "key": f"{stem}_diameter",
                "label": "Diameter",
                "value": "407",
                "unit": "mm",
            },
            {
                "key": f"{stem}_material",
                "label": "Material",
                "value": "ceramic",
                "unit": None,
            },
        ]
        assert all(row["key"] != "zzt_not_a_registry_key" for row in specs)

    def test_a_product_with_no_reviewed_specs_carries_none(self, db):
        from app.services.dealer_kit import tag_data_service

        product = _product(db)

        assert (
            tag_data_service.product_tag_data(
                db, product, tag_data_service.staff_viewer()
            )["specs"]
            == []
        )

    def test_an_inactive_registry_key_is_not_offered(self, db):
        from app.services.dealer_kit import tag_data_service

        stem = unique_code("zztin").lower()
        _registry_key(db, f"{stem}_retired", "Retired", is_active=False)

        product = _product(db)
        _spec_values(db, product, {f"{stem}_retired": {"value": "yes"}})

        specs = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )["specs"]
        assert [row for row in specs if row["key"].startswith(stem)] == []


class TestLineSpecs:
    def test_a_product_line_carries_its_specs(self, db):
        from app.services.dealer_kit import tag_data_service

        stem = unique_code("zztl").lower()
        _registry_key(db, f"{stem}_material", "Material")

        product = _product(db)
        _spec_values(db, product, {f"{stem}_material": {"value": "granite"}})
        request = TestResolveLines()._request_with_line(db, product)

        row = tag_data_service.resolve_request_line_data(db, request)[0]

        assert {
            "key": f"{stem}_material",
            "label": "Material",
            "value": "granite",
            "unit": None,
        } in row["specs"]

    def test_a_set_line_carries_no_specs_of_its_own(self, db):
        from app.models.access import RespondContact
        from app.services.dealer_kit import tag_data_service
        from app.services.price_tag_request_service import PriceTagRequestService

        first = _product(db, list_price="1000.00")
        product_set = _product_set(db, [(first, 1, True)])

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
                "lines": [
                    {
                        "line_type": "product_set",
                        "product_set_id": product_set.id,
                        "quantity": 1,
                    }
                ],
            },
        )
        db.flush()

        assert tag_data_service.resolve_request_line_data(db, request)[0]["specs"] == []
