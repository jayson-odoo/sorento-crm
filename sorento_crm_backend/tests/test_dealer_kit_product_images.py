"""Golden set for product photos on catalogue tiles.

Written BEFORE the implementation.

A brochure without pictures is not a brochure. Tiles have always been able to
DISPLAY a photo - it is in the tile-design whitelist - but the resolver sent
``image_url: None`` every time, so every tile in every catalogue rendered a
broken-image placeholder.

The reason this needs care rather than a one-line join: a product photo is
itself access-controlled. ``product_attachments.access_levels`` says who a given
image is for, and a dealer-only render (a cutaway with fitting instructions, a
price-list card) must not reach a consumer looking at the public catalogue. So
the image goes through the same viewer gate as the price, and it fails CLOSED:
if we cannot establish that the viewer is allowed to see it, it is absent.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
SCOPE = frozenset({SORENTO})

STAFF = ViewerContext(is_staff=True)
DEALER = ViewerContext(access_codes=frozenset({"dealer"}))
CONSUMER = ViewerContext(access_codes=frozenset({"end_user"}))


def _product(db):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTI")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _image(db, product, *, access_levels, is_primary=False, sort_order=0, thumb=None,
           mime="image/jpeg", suffix="jpg", deleted=False):
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment

    name = unique_code("zztimg")
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{name}.{suffix}",
        stored_filename=f"{name}.{suffix}",
        file_path=f"https://cdn.example.test/products/{name}.{suffix}",
        thumbnail_path=thumb,
        mime_type=mime,
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=deleted,
    )
    db.add(attachment)
    db.flush()

    link = ProductAttachment(
        product_id=product.id,
        attachment_id=attachment.id,
        is_primary=is_primary,
        sort_order=sort_order,
        access_levels=access_levels,
        company_id=SORENTO,
    )
    db.add(link)
    db.flush()
    return attachment


def test_a_product_with_no_image_resolves_to_nothing():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        assert product_images.primary_image_urls(db, [product], CONSUMER) == {}


def test_a_consumer_sees_an_end_user_image():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(db, product, access_levels=["dealer", "end_user"], is_primary=True)

        urls = product_images.primary_image_urls(db, [product], CONSUMER)
        assert product.id in urls
        assert urls[product.id]


def test_a_consumer_never_sees_a_dealer_only_image():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(db, product, access_levels=["dealer"], is_primary=True)

        # A cutaway with fitting notes is for the trade, not the showroom floor.
        assert product_images.primary_image_urls(db, [product], CONSUMER) == {}
        assert product.id in product_images.primary_image_urls(db, [product], DEALER)


def test_staff_see_an_image_whoever_it_was_tagged_for():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(db, product, access_levels=["dealer"], is_primary=True)

        assert product.id in product_images.primary_image_urls(db, [product], STAFF)


def test_an_untagged_image_is_treated_as_public():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        # Legacy rows predate access levels. Hiding every one of them would
        # empty the catalogue, and they were uploaded as catalogue imagery.
        _image(db, product, access_levels=[], is_primary=True)

        assert product.id in product_images.primary_image_urls(db, [product], ANONYMOUS)


def test_the_primary_image_wins_over_a_lower_sort_order():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(db, product, access_levels=["end_user"], is_primary=False, sort_order=0)
        chosen = _image(
            db, product, access_levels=["end_user"], is_primary=True, sort_order=9
        )

        url = product_images.primary_image_urls(db, [product], CONSUMER)[product.id]
        # Somebody deliberately marked one as primary; ordering must not override it.
        assert chosen.original_filename.split(".")[0] in url


def test_the_thumbnail_is_preferred_over_the_full_image():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(
            db,
            product,
            access_levels=["end_user"],
            is_primary=True,
            thumb="https://cdn.example.test/products/zzt-thumb.jpg",
        )

        # A tile is ~300px. Sending the full-size photo makes a 40-product page
        # download tens of megabytes.
        assert "thumb" in product_images.primary_image_urls(db, [product], CONSUMER)[product.id]


def test_several_products_resolve_in_one_go():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        products = [_product(db) for _ in range(3)]
        for product in products:
            _image(db, product, access_levels=["end_user"], is_primary=True)

        urls = product_images.primary_image_urls(db, products, CONSUMER)
        assert len(urls) == 3


def test_a_pdf_attached_to_a_product_is_never_its_photo():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        # The live catalogue links 532 PDFs and a couple of videos to products.
        # A spec sheet rendered as the product photo is worse than no photo.
        _image(
            db,
            product,
            access_levels=["end_user"],
            is_primary=True,
            mime="application/pdf",
            suffix="pdf",
        )

        assert product_images.primary_image_urls(db, [product], CONSUMER) == {}


def test_a_deleted_photo_is_never_a_tile_image():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        # 611 of the 2,924 live product-to-image links point at an attachment
        # deleted in Resource Management. Signing a URL for a file the system
        # considers deleted is the catalogue disagreeing with the file manager.
        _image(db, product, access_levels=["end_user"], is_primary=True, deleted=True)

        assert product_images.primary_image_urls(db, [product], CONSUMER) == {}


def test_a_live_photo_wins_over_a_deleted_one_marked_primary():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(db, product, access_levels=["end_user"], is_primary=True, deleted=True)
        live = _image(db, product, access_levels=["end_user"], sort_order=5)

        url = product_images.primary_image_urls(db, [product], CONSUMER)[product.id]
        assert live.original_filename.split(".")[0] in url


def test_a_photo_wins_over_a_pdf_marked_primary():
    from app.services.dealer_kit import product_images

    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        _image(db, product, access_levels=["end_user"], is_primary=True,
               mime="application/pdf", suffix="pdf")
        photo = _image(db, product, access_levels=["end_user"], sort_order=5)

        url = product_images.primary_image_urls(db, [product], CONSUMER)[product.id]
        assert photo.original_filename.split(".")[0] in url
