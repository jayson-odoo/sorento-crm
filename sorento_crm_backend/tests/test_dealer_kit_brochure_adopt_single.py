"""Taking the only photo a product has, without asking.

This REVERSES an earlier decision that is worth restating, because the reversal
is only correct for one specific reason. The original rule was that nothing is
chosen on the user's behalf: a wrong photo is a wrong product in front of a
customer, so even a product with one candidate took a click.

That argument needs a choice to get wrong. With exactly ONE candidate there is
none - the renderer already falls back to the first linked photo, so adopting it
changes nothing a reader sees and only records what was already true. With two,
somebody still has to look, and these tests exist mostly to prove that line is
where it is claimed to be.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

from app.models.resources import Attachment
from app.models.base import company_scope
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.services import brochure_image_service
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _product(db) -> Product:
    code = unique_code("ZZTBI")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=code,
        product_name=f"ZZT {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("10.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _link(db, product, *, mime="image/jpeg", deleted=False) -> ProductAttachment:
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{unique_code('zzt')}.jpg",
        stored_filename=f"{unique_code('zzt')}.jpg",
        file_path=f"product_photos/{unique_code('zzt')}.jpg",
        mime_type=mime,
        is_deleted=deleted,
    )
    db.add(attachment)
    db.flush()
    link = ProductAttachment(product_id=product.id, attachment_id=attachment.id)
    db.add(link)
    db.flush()
    return link


def _chosen(db, product_id):
    return (
        db.query(ProductAttachment.attachment_id)
        .filter(
            ProductAttachment.product_id == product_id,
            ProductAttachment.is_primary.is_(True),
        )
        .scalar()
    )


def test_the_only_photo_is_taken():
    with pg_session() as db, company_scope(db, None):
        product = _product(db)
        link = _link(db, product)

        adopted = brochure_image_service.adopt_single_candidates(db, [product.id])

        assert adopted == [product.id]
        assert _chosen(db, product.id) == link.attachment_id


def test_a_product_with_two_photos_is_left_for_a_human():
    """The whole point of the line. Two candidates is a decision."""
    with pg_session() as db, company_scope(db, None):
        product = _product(db)
        _link(db, product)
        _link(db, product)

        adopted = brochure_image_service.adopt_single_candidates(db, [product.id])

        assert adopted == []
        assert _chosen(db, product.id) is None


def test_a_product_with_no_photo_is_untouched():
    """The answer there is a photo shoot, not a click."""
    with pg_session() as db, company_scope(db, None):
        product = _product(db)

        assert brochure_image_service.adopt_single_candidates(db, [product.id]) == []


def test_a_pdf_is_not_a_candidate():
    """`product_attachments` links whatever is attached, including 532 PDFs. A
    spec sheet rendered as the product photo is worse than no photo."""
    with pg_session() as db, company_scope(db, None):
        product = _product(db)
        _link(db, product, mime="application/pdf")

        assert brochure_image_service.adopt_single_candidates(db, [product.id]) == []
        assert _chosen(db, product.id) is None


def test_a_deleted_file_is_not_a_candidate():
    with pg_session() as db, company_scope(db, None):
        product = _product(db)
        _link(db, product, deleted=True)

        assert brochure_image_service.adopt_single_candidates(db, [product.id]) == []


def test_one_image_plus_one_pdf_still_counts_as_one_candidate():
    """The condition is on CANDIDATES, not on linked rows."""
    with pg_session() as db, company_scope(db, None):
        product = _product(db)
        photo = _link(db, product)
        _link(db, product, mime="application/pdf")

        adopted = brochure_image_service.adopt_single_candidates(db, [product.id])

        assert adopted == [product.id]
        assert _chosen(db, product.id) == photo.attachment_id


def test_a_choice_already_made_is_not_overwritten():
    """Idempotent, and it has to be: the screen calls this on every page load."""
    with pg_session() as db, company_scope(db, None):
        product = _product(db)
        first = _link(db, product)
        brochure_image_service.set_brochure_image(db, product.id, first.attachment_id)

        assert brochure_image_service.adopt_single_candidates(db, [product.id]) == []
        assert _chosen(db, product.id) == first.attachment_id


def test_it_answers_only_the_products_it_was_given():
    with pg_session() as db, company_scope(db, None):
        named = _product(db)
        _link(db, named)
        other = _product(db)
        _link(db, other)

        adopted = brochure_image_service.adopt_single_candidates(db, [named.id])

        assert adopted == [named.id]
        assert _chosen(db, other.id) is None
