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


def _product(db, *, list_price="1599.00", description=None, code=None, currency="MYR"):
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
        currency=currency,
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

    def test_ac_a10_product_tag_data_carries_currency_default_myr(self, db):
        """AC-A10: `currency` equals the product's own column, default MYR."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db)

        data = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )

        assert data["currency"] == "MYR"

    def test_ac_a10_product_tag_data_carries_currency_sgd(self, db):
        """AC-A10: a product with `currency='SGD'` returns SGD, not MYR."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db, currency="SGD")

        data = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )

        assert data["currency"] == "SGD"


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

    def test_ac_a11_set_data_carries_the_first_members_currency(self, db):
        """AC-A11: set data returns `currency` (the first member's)."""
        from app.services.dealer_kit import tag_data_service

        first = _product(db, list_price="1000.00", currency="SGD")
        second = _product(db, list_price="200.00", currency="MYR")
        product_set = _product_set(db, [(first, 1, True), (second, 1, True)])

        data = tag_data_service.product_set_tag_data(
            db, product_set, tag_data_service.staff_viewer()
        )

        assert data["currency"] == "SGD"


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
                # D1 (S6): a promotion is a LINE fact - the header convenience
                # is gone, so it goes on the line's own dict. AC-S6-5: it must
                # cover the line's product (`_promotion` seeds a
                # `PromotionProduct` row for it) and be visible to the
                # viewer's audience - `create_request`'s default viewer is
                # `staff_viewer()`, which is not audience-gated, so
                # `_promotion`'s own `access_levels` default already covers
                # it.
                "price_mode": "selling",
                "lines": [
                    {
                        "line_type": "product",
                        "product_id": product.id,
                        "quantity": 1,
                        **({"promotion_id": promotion_id} if promotion_id else {}),
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

    def test_ac_a11_line_tag_row_carries_currency(self, db):
        """AC-A11: a line tag row returns `currency`, off the product it names."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db, list_price="1599.00", currency="SGD")
        request = self._request_with_line(db, product)

        rows = tag_data_service.resolve_request_line_data(db, request)

        assert rows[0]["currency"] == "SGD"

    def test_ac_a11_part_row_carries_its_own_products_currency(self, db):
        """AC-A11: a part row returns its OWN product's currency, not the
        host's - `_part_row` is the resolver every part on a combo tag goes
        through (`resolve_tags_live`)."""
        from app.services.dealer_kit import tag_data_service

        part_product = _product(db, list_price="99.00", currency="SGD")

        part = tag_data_service._part_row(
            db, part_product, tag_data_service.staff_viewer(), None, {}
        )

        assert part["currency"] == "SGD"

    def test_marketing_override_wins_over_the_resolved_offer(self, db):
        """The override beats the promotion engine's offer - on the TAG since S3.

        It moved off the line (D3) because two tags split off one line print two
        different basins at two different prices, and a line-level figure would
        put the same hand-set number on both. The rule it encodes is unchanged:
        a price somebody decided and logged a reason for wins over one the
        engine derived.
        """
        from app.services.dealer_kit import tag_data_service

        product = _product(db, list_price="1599.00")
        promotion = _promotion(db, product, promo_price="599.00")
        request = self._request_with_line(db, product, promotion_id=promotion.id)

        # One tag per line exists from creation (`_add_lines`), so there is a
        # tag to set this on without seeding one by hand.
        tag = request.lines[0].tags[0]
        tag.marketing_price_override = Decimal("499.00")
        db.flush()

        rows = tag_data_service.resolve_request_line_data(db, request)
        assert len(rows) == 1, "one row per TAG, and this line has one tag"
        row = rows[0]
        assert row["tag_id"] == tag.id
        assert row["line_id"] == request.lines[0].id
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
                # AC-S3-1 (r10): a stored slug title-cases automatically -
                # "ceramic" prints as "Ceramic", the same rule
                # `_spec_display_value` applies everywhere else.
                "value": "Ceramic",
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
            # AC-S3-1 (r10): title-cased, like every other stored slug.
            "value": "Granite",
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


# ---------------------------------------------------------------------------
# Photo tiebreak by attachment type (S10, D8). Written test-FIRST: today's
# ``gallery_images`` orders `is_primary DESC, sort_order NULLS LAST, created_at`
# with no attachment-type CASE at all, so a Technical Specifications image
# linked before a Product Photos one wins on `created_at` - the SRTKS8547 bug
# the plan measured on the 0907 copy.
# ---------------------------------------------------------------------------


def _attachment_type(db, type_name: str):
    from app.models.resources import AttachmentType

    row = AttachmentType(
        id=str(uuid.uuid4()), type_name=type_name, allowed_extensions="jpg,jpeg,png"
    )
    db.add(row)
    db.flush()
    return row


def _image_typed(db, product, *, type_name: str, is_primary: bool = False, sort_order: int = 0):
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment

    name = unique_code("zztimgtype")
    attachment_type = _attachment_type(db, type_name)
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{name}.jpg",
        stored_filename=f"{name}.jpg",
        file_path=f"https://cdn.example.test/products/{name}.jpg",
        mime_type="image/jpeg",
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=False,
        attachment_type_id=attachment_type.id,
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
            access_levels=["dealer", "end_user"],
            company_id=SORENTO,
        )
    )
    db.flush()
    return attachment


class TestProductPhotoTiebreak:
    def test_product_photo_beats_technical_drawing_when_no_primary(self, db):
        """AC-S10-1/2: the drawing was linked FIRST (wins on `created_at` today);
        the type-rank CASE must put the Product Photos row ahead of it anyway."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        drawing = _image_typed(db, product, type_name="Technical Specifications")
        photo = _image_typed(db, product, type_name="Product Photos")

        images = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )["images"]

        assert images[0]["attachment_id"] == photo.id, (
            f"drawing {drawing.id} still won the tiebreak"
        )

    def test_primary_still_wins(self, db):
        """AC-S10-1: `is_primary DESC` stays the FIRST ordering key."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        drawing_primary = _image_typed(
            db, product, type_name="Technical Specifications", is_primary=True
        )
        _image_typed(db, product, type_name="Product Photos")

        images = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )["images"]

        assert images[0]["attachment_id"] == drawing_primary.id

    def test_only_drawing_still_resolves(self, db):
        """AC-S10-3: the tiebreak is an ORDERING rule, never a filter."""
        from app.services.dealer_kit import tag_data_service

        product = _product(db)
        drawing = _image_typed(db, product, type_name="Technical Specifications")

        images = tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer()
        )["images"]

        assert len(images) == 1
        assert images[0]["attachment_id"] == drawing.id


# ---------------------------------------------------------------------------
# AC-S3-1 .. AC-S3-4 (PLAN-price-tag-r10.md S3): readable spec values.
#
# `_spec_display_value` gains a second argument, `value_labels` - the call
# below is the red import/signature until the coder adds it (`TypeError:
# _spec_display_value() takes 1 positional argument but 2 were given`).
# ---------------------------------------------------------------------------


class TestSpecDisplayValue:
    def test_ac_s3_1_a_slug_with_no_value_labels_title_cases_with_spaces(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("stainless_steel", {}) == "Stainless Steel"

    def test_ac_s3_2_rose_gold_and_single_lever_title_case(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("rose_gold", {}) == "Rose Gold"
        assert _spec_display_value("single_lever", {}) == "Single Lever"

    def test_ac_s3_2_acronym_words_upper_case(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("pvc", {}) == "PVC"
        assert _spec_display_value("pvc_pipe", {}) == "PVC Pipe"

    def test_ac_s3_3_a_value_label_wins_over_the_automatic_form(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("pp", {"pp": "Polypropylene"}) == "Polypropylene"

    def test_ac_s3_4_an_integer_valued_float_still_prints_bare(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value(407.0, {}) == "407"

    def test_ac_s3_4_a_bool_still_prints_yes_no(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value(True, {}) == "Yes"
        assert _spec_display_value(False, {}) == "No"

    def test_ac_s3_4_free_text_with_spaces_is_returned_unchanged(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("Made in Malaysia", {}) == "Made in Malaysia"

    def test_ac_s3_4_a_numeric_string_is_returned_unchanged(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("407", {}) == "407"

    def test_ac_s3_4_an_empty_string_is_returned_unchanged(self):
        from app.services.dealer_kit.tag_data_service import _spec_display_value

        assert _spec_display_value("", {}) == ""


def test_ac_s3_1_product_specs_reads_value_labels_off_the_registry_key(db):
    """`product_specs` must pass the registry key's OWN `value_labels`
    through to `_spec_display_value`, not an empty dict - a value label set
    on the key has to win over the automatic slug form end to end."""
    from app.services.dealer_kit import tag_data_service

    product = _product(db)
    key = _registry_key(db, "material", "Material")
    key.value_labels = {"stainless_steel": "18/8 Stainless"}
    db.flush()
    _spec_values(db, product, {"material": {"value": "stainless_steel"}})

    specs = tag_data_service.product_specs(db, product)

    assert specs[0]["value"] == "18/8 Stainless"


# ---------------------------------------------------------------------------
# AC-S4-4 (PLAN-price-tag-r10.md S4): `price_tag_description` on the line's
# product row and on every part row. Red until the coder adds the column
# (AttributeError off `Product.price_tag_description`) and threads it
# through `resolve_tags_live`/`_part_row`.
# ---------------------------------------------------------------------------


def test_ac_s4_4_resolve_tags_live_carries_price_tag_description_on_the_host():
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        product = _product(db)
        product.price_tag_description = "ZZT tag copy\nSecond line"
        db.flush()
        request = TestResolveLines()._request_with_line(db, product)

        rows = tag_data_service.resolve_request_line_data(db, request)

        assert rows[0]["price_tag_description"] == "ZZT tag copy\nSecond line"


def test_ac_s4_4_part_row_carries_its_own_products_price_tag_description():
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        part_product = _product(db)
        part_product.price_tag_description = "ZZT part copy"
        db.flush()

        part = tag_data_service._part_row(
            db, part_product, tag_data_service.staff_viewer(), None, {}
        )

        assert part["price_tag_description"] == "ZZT part copy"


# ---------------------------------------------------------------------------
# AC-S5-6 (PLAN-price-tag-r10.md S5): a line whose combo names an image
# resolves `images[0]` to it with `is_primary: true`, followed by the
# gallery; a line on the same product without a combo keeps the gallery
# order.
# ---------------------------------------------------------------------------


def test_ac_s5_6_a_combo_image_leads_the_line_images_list():
    from app.models.product_combo import ProductCombo
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        product = _product(db)
        gallery_photo = _image(db, product, access_levels=["dealer", "end_user"])
        combo_image = _image(db, product, access_levels=["dealer", "end_user"])
        combo = ProductCombo(
            id=str(uuid.uuid4()),
            host_product_id=product.id,
            name=unique_code("combo"),
            sort_order=0,
            image_attachment_id=combo_image.id,
        )
        db.add(combo)
        db.flush()

        request = TestResolveLines()._request_with_line(db, product)
        request.lines[0].combo_id = combo.id
        db.flush()

        rows = tag_data_service.resolve_request_line_data(db, request)

        images = rows[0]["images"]
        assert images[0]["attachment_id"] == combo_image.id
        assert images[0]["is_primary"] is True
        assert any(img["attachment_id"] == gallery_photo.id for img in images[1:])


def test_ac_s5_6_a_line_with_no_combo_keeps_the_plain_gallery_order():
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        product = _product(db)
        photo = _image(db, product, access_levels=["dealer", "end_user"], is_primary=True)
        request = TestResolveLines()._request_with_line(db, product)

        rows = tag_data_service.resolve_request_line_data(db, request)

        assert rows[0]["images"][0]["attachment_id"] == photo.id


# ---------------------------------------------------------------------------
# AC-S6-3 (PLAN-price-tag-r10.md S6): every tag of a combo line exposes ALL
# products of the combo - fixed parts plus every candidate of every open
# group - each carrying `role`/`chosen`; `own_parts` keeps today's narrower
# list (this tag's own resolved parts) for `set_members`/Tag total.
# ---------------------------------------------------------------------------


def _combo_line_request(db):
    """A cabinet with a fixed mirror part and a 3-candidate open Kitchen Tap
    group, submitted so it auto-splits into three tags (D6)."""
    from app.models.access import RespondContact
    from app.models.product_combo import ProductCombo, ProductComboPart
    from app.services.price_tag_request_service import PriceTagRequestService

    cabinet = _product(db, code=unique_code("ZZTCAB"))
    mirror = _product(db, code=unique_code("ZZTMIR"))
    taps = [_product(db, code=unique_code(f"ZZTTAP{i}")) for i in range(3)]
    combo = ProductCombo(
        id=str(uuid.uuid4()), host_product_id=cabinet.id, name="4 in 1", sort_order=0
    )
    db.add(combo)
    db.flush()
    db.add(
        ProductComboPart(
            id=str(uuid.uuid4()),
            combo_id=combo.id,
            part_product_id=mirror.id,
            choice_group=None,
            sort_order=0,
        )
    )
    for index, tap in enumerate(taps):
        db.add(
            ProductComboPart(
                id=str(uuid.uuid4()),
                combo_id=combo.id,
                part_product_id=tap.id,
                choice_group="Kitchen Tap",
                sort_order=index + 1,
            )
        )
    db.flush()

    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": cabinet.id,
                    "combo_id": combo.id,
                    "quantity": 3,
                    "parts": [
                        {"product_id": mirror.id},
                        {"role": "Kitchen Tap", "candidates": [tap.id for tap in taps]},
                    ],
                }
            ],
        },
    )
    db.commit()
    return request, cabinet, mirror, taps


def _combo_line_with_trailing_fixed_part(db):
    """X (fixed, sort 0), an open Kitchen Tap group of A/B/C (sort 1), Y
    (fixed, sort 2) - a fixed part AFTER the open group, so the WIDE order
    the group's leftover candidates get appended in is distinguishable from
    the pre-r10 narrow order they used to sit inside (AC-S6-13)."""
    from app.models.access import RespondContact
    from app.models.product_combo import ProductCombo, ProductComboPart
    from app.services.price_tag_request_service import PriceTagRequestService

    cabinet = _product(db, code=unique_code("ZZTIDX"))
    x = _product(db, code=unique_code("ZZTX"))
    y = _product(db, code=unique_code("ZZTY"))
    candidates = [_product(db, code=unique_code(f"ZZTC{i}")) for i in range(3)]
    combo = ProductCombo(
        id=str(uuid.uuid4()), host_product_id=cabinet.id, name="idx combo", sort_order=0
    )
    db.add(combo)
    db.flush()
    db.add(
        ProductComboPart(
            id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=x.id,
            choice_group=None, sort_order=0,
        )
    )
    for index, candidate in enumerate(candidates):
        db.add(
            ProductComboPart(
                id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=candidate.id,
                choice_group="Group", sort_order=1,
            )
        )
    db.add(
        ProductComboPart(
            id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=y.id,
            choice_group=None, sort_order=2,
        )
    )
    db.flush()

    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "lines": [
                {
                    "line_type": "product",
                    "product_id": cabinet.id,
                    "combo_id": combo.id,
                    "quantity": 1,
                    "parts": [
                        {"product_id": x.id},
                        {"role": "Group", "candidates": [c.id for c in candidates]},
                        {"product_id": y.id},
                    ],
                }
            ],
        },
    )
    db.commit()
    return request, x, y, candidates


def test_ac_s6_13_part_index_is_stable_own_order_first_then_leftover_candidates():
    """AC-S6-13: `parts` is the pre-r10 NARROW order first (this tag's own
    fixed parts and its chosen candidate, in sort order) with the group's
    non-chosen candidates APPENDED at the end, in combo order - never
    interleaved at the group's own sort position. `own_parts` is that narrow
    list alone."""
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        request, x, y, candidates = _combo_line_with_trailing_fixed_part(db)
        line = request.lines[0]
        tags = sorted(line.tags, key=lambda t: (t.sort_order or 0, t.id))
        assert len(tags) == 3, "one tag per candidate, D6"

        for tag in tags:
            chosen_id = next(iter((tag.choices or {}).values()))
            chosen = next(c for c in candidates if str(c.id) == str(chosen_id))
            leftovers = [c for c in candidates if c.id != chosen.id]

            rows = tag_data_service.resolve_tags_live(db, request, [tag])
            row = rows[0]

            own_codes = [p["code"] for p in row["own_parts"]]
            assert own_codes == [x.product_code, chosen.product_code, y.product_code], (
                tag.label if hasattr(tag, "label") else tag.id,
                own_codes,
            )

            codes = [p["code"] for p in row["parts"]]
            expected = (
                [x.product_code, chosen.product_code, y.product_code]
                + [c.product_code for c in leftovers]
            )
            assert codes == expected, codes
            # The captain's own worked numbers: Y always at index 2, the
            # chosen candidate always at index 1, whichever tag this is.
            assert codes.index(y.product_code) == 2
            assert codes.index(chosen.product_code) == 1


def test_ac_s6_3_tag_1a_parts_lists_every_candidate_own_parts_is_the_narrow_list():
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        request, _cabinet, mirror, taps = _combo_line_request(db)
        line = request.lines[0]
        tag_1a = sorted(line.tags, key=lambda t: (t.sort_order or 0, t.id))[0]

        rows = tag_data_service.resolve_tags_live(db, request, [tag_1a])

        row = rows[0]
        part_codes = {p["code"] for p in row["parts"]}
        assert part_codes == {mirror.product_code, *[t.product_code for t in taps]}, row["parts"]

        own_codes = [p["code"] for p in row["own_parts"]]
        chosen_tap = next(
            t for t in taps if str(t.id) in (tag_1a.choices or {}).values()
        )
        assert own_codes == [mirror.product_code, chosen_tap.product_code]

        chosen_flags = {p["code"]: p.get("chosen") for p in row["parts"]}
        assert chosen_flags[chosen_tap.product_code] is True
        for other in taps:
            if other.id != chosen_tap.id:
                assert not chosen_flags[other.product_code]

        roles = {
            p["code"]: p.get("role") for p in row["parts"] if p["code"] != mirror.product_code
        }
        assert all(role == "Kitchen Tap" for role in roles.values())


def test_ac_s6_3_set_members_still_prints_only_the_tags_own_parts():
    """An unchanged template must keep printing exactly what it printed
    before r10 - `set_members` reads `own_parts`, never the widened `parts`."""
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        request, _cabinet, mirror, taps = _combo_line_request(db)
        line = request.lines[0]
        tag_1a = sorted(line.tags, key=lambda t: (t.sort_order or 0, t.id))[0]
        chosen_tap = next(t for t in taps if str(t.id) in (tag_1a.choices or {}).values())

        rows = tag_data_service.resolve_tags_live(db, request, [tag_1a])

        set_members = rows[0]["set_members"]
        for other in taps:
            if other.id != chosen_tap.id:
                assert other.product_code not in set_members, set_members


# ---------------------------------------------------------------------------
# AC-S6-11: a pinned row written before r10 (no `own_parts`) still renders
# `set_members`/Tag total from `parts` - `_row_from_pin` falls back.
# ---------------------------------------------------------------------------


def test_ac_s6_11_row_from_pin_falls_back_to_parts_when_own_parts_is_absent():
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        request, _cabinet, mirror, taps = _combo_line_request(db)
        line = request.lines[0]
        tag = line.tags[0]
        pinned = {
            "code": "ZZT-PRE-R10",
            "parts": [{"code": mirror.product_code, "name": "Mirror"}],
            # deliberately NO "own_parts" key - the pre-r10 shape.
        }

        row = tag_data_service._row_from_pin(db, line, tag, pinned, "1a")

        assert row.get("own_parts") == pinned["parts"]


# ---------------------------------------------------------------------------
# AC-S5-9 / AC-S5-10 (PLAN-price-tag-r10.md S5): deleting the combo's image
# attachment nulls the combo's own pointer (the migration's ON DELETE SET
# NULL) and the line falls back to the gallery; changing the combo's picture
# changes the tag's pinned-data hash, so an open request sees the red dot.
# ---------------------------------------------------------------------------


def test_ac_s5_9_deleting_the_attachment_nulls_the_combo_and_falls_back_to_gallery():
    from app.models.product_combo import ProductCombo
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        product = _product(db)
        gallery_photo = _image(db, product, access_levels=["dealer", "end_user"])
        combo_image = _image(db, product, access_levels=["dealer", "end_user"])
        combo = ProductCombo(
            id=str(uuid.uuid4()),
            host_product_id=product.id,
            name=unique_code("combo"),
            sort_order=0,
            image_attachment_id=combo_image.id,
        )
        db.add(combo)
        db.flush()

        db.delete(combo_image)
        db.flush()
        db.refresh(combo)
        assert combo.image_attachment_id is None, (
            "the FK must be ON DELETE SET NULL - the migration's own contract"
        )

        request = TestResolveLines()._request_with_line(db, product)
        request.lines[0].combo_id = combo.id
        db.flush()

        rows = tag_data_service.resolve_request_line_data(db, request)
        images = rows[0]["images"]
        assert images[0]["attachment_id"] == gallery_photo.id, (
            "with no combo image, the line must fall back to the plain gallery"
        )


def test_ac_s5_10_changing_the_combo_image_changes_the_pinned_data_hash():
    from app.models.product_combo import ProductCombo
    from app.services.dealer_kit import tag_data_service

    with blank_session() as db:
        product = _product(db)
        first_image = _image(db, product, access_levels=["dealer", "end_user"])
        second_image = _image(db, product, access_levels=["dealer", "end_user"])
        combo = ProductCombo(
            id=str(uuid.uuid4()),
            host_product_id=product.id,
            name=unique_code("combo"),
            sort_order=0,
            image_attachment_id=first_image.id,
        )
        db.add(combo)
        db.flush()

        request = TestResolveLines()._request_with_line(db, product)
        request.lines[0].combo_id = combo.id
        db.flush()

        first_rows = tag_data_service.resolve_request_line_data(db, request)
        first_hash = tag_data_service.data_hash(first_rows[0])

        combo.image_attachment_id = second_image.id
        db.flush()

        second_rows = tag_data_service.resolve_request_line_data(db, request)
        second_hash = tag_data_service.data_hash(second_rows[0])

        assert first_hash != second_hash, (
            "swapping the combo picture must move the pinned-data hash, or "
            "an open request never sees the red dot for it"
        )
