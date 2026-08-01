"""Choosing which photo of a product a brochure shows (UAC group B).

Written before the service. The defect this exists to close is live: nobody has
ever set `product_attachments.is_primary`, on any of the 1,087 photo rows behind
the flyer's products, so `product_images.py` - which already orders by that flag
- falls through to whichever row happened to be linked first. For SRTWC286-SH
that means one of 31 files including a blank page and two other products'
photographs.

The invariant that matters is **exactly one chosen image per product**. Two at
once would put the tile's photo back at the mercy of row order, which is the
whole defect.

Nothing is ever chosen automatically. A filename matching the product code would
identify the right image for 509 of 535 products; inferring from it is rejected,
because a wrong photo is a wrong product in front of a customer.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
from app.services.brochure_image_service import (
    list_brochure_images,
    set_brochure_image,
)
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _reference_rows(db):
    """A category and a UOM, because Postgres enforces the FKs sqlite ignored."""
    from app.models.product import ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("c")[:20],
        category_name=unique_code("cat"),
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_name=unique_code("uom"), uom_code=unique_code("u")[:10])
    db.add_all([category, uom])
    db.flush()
    return category.id, uom.id


def _product(db, code: str | None = None) -> Product:
    category_id, uom_id = _reference_rows(db)
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code or unique_code("sku"),
        product_name="Test product",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=100,
    )
    db.add(product)
    db.flush()
    return product


def _attach(db, product: Product, filename: str, mime: str = "image/jpeg") -> ProductAttachment:
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"product/{filename}",
        mime_type=mime,
    )
    db.add(attachment)
    db.flush()
    link = ProductAttachment(
        id=str(uuid.uuid4()),
        product_id=product.id,
        attachment_id=attachment.id,
    )
    db.add(link)
    db.flush()
    return link


class TestSetting:
    def test_choosing_an_image_marks_exactly_that_one(self, db) -> None:
        product = _product(db)
        first = _attach(db, product, "a.jpg")
        _attach(db, product, "b.jpg")

        set_brochure_image(db, product.id, first.attachment_id)

        chosen = [
            link.attachment_id
            for link in db.query(ProductAttachment).filter_by(product_id=product.id).all()
            if link.is_primary
        ]
        assert chosen == [first.attachment_id]

    def test_choosing_another_clears_the_previous_one(self, db) -> None:
        # The invariant. Two flagged at once and the tile's photo depends on row
        # order again, which is the defect this whole slice removes.
        product = _product(db)
        first = _attach(db, product, "a.jpg")
        second = _attach(db, product, "b.jpg")

        set_brochure_image(db, product.id, first.attachment_id)
        set_brochure_image(db, product.id, second.attachment_id)

        chosen = [
            link.attachment_id
            for link in db.query(ProductAttachment).filter_by(product_id=product.id).all()
            if link.is_primary
        ]
        assert chosen == [second.attachment_id]

    def test_choosing_the_same_one_twice_leaves_it_chosen(self, db) -> None:
        # Idempotent, not a toggle: a double click must not leave a product with
        # no brochure image.
        product = _product(db)
        only = _attach(db, product, "a.jpg")

        set_brochure_image(db, product.id, only.attachment_id)
        set_brochure_image(db, product.id, only.attachment_id)

        link = db.query(ProductAttachment).filter_by(product_id=product.id).one()
        assert link.is_primary is True

    def test_another_product_keeps_its_own_choice(self, db) -> None:
        one = _product(db)
        other = _product(db)
        one_image = _attach(db, one, "a.jpg")
        other_image = _attach(db, other, "b.jpg")

        set_brochure_image(db, one.id, one_image.attachment_id)
        set_brochure_image(db, other.id, other_image.attachment_id)

        assert db.query(ProductAttachment).filter_by(id=one_image.id).one().is_primary is True
        assert db.query(ProductAttachment).filter_by(id=other_image.id).one().is_primary is True

    def test_an_attachment_not_linked_to_the_product_is_refused(self, db) -> None:
        product = _product(db)
        elsewhere = _attach(db, _product(db), "b.jpg")

        with pytest.raises(AppException) as raised:
            set_brochure_image(db, product.id, elsewhere.attachment_id)

        # 404, never 403: a caller must not learn the row exists.
        assert raised.value.status_code == 404

    def test_an_unknown_product_is_refused(self, db) -> None:
        with pytest.raises(AppException) as raised:
            set_brochure_image(db, str(uuid.uuid4()), str(uuid.uuid4()))

        assert raised.value.status_code == 404

    def test_a_non_image_cannot_be_the_brochure_image(self, db) -> None:
        # `product_attachments` links whatever is attached to a product, and the
        # live data holds 532 PDFs. A spec sheet rendered as the product photo is
        # worse than no photo.
        product = _product(db)
        spec = _attach(db, product, "spec.pdf", mime="application/pdf")

        with pytest.raises(AppException) as raised:
            set_brochure_image(db, product.id, spec.attachment_id)

        assert raised.value.status_code in (400, 404)


class TestTheDatabaseEnforcesIt:
    def test_two_chosen_images_on_one_product_are_impossible(self, db) -> None:
        """The invariant is not left to this service alone.

        Every other write path - the existing attachment PUT, an import, a
        future script - could otherwise set a second primary and put the tile's
        photo back at the mercy of row order.
        """
        from sqlalchemy.exc import IntegrityError

        product = _product(db)
        first = _attach(db, product, "a.jpg")
        second = _attach(db, product, "b.jpg")

        first.is_primary = True
        db.flush()
        second.is_primary = True

        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_two_unchosen_photos_are_fine(self, db) -> None:
        # The index is partial for this reason: a full unique index would forbid
        # a product having two photos at all.
        product = _product(db)
        _attach(db, product, "a.jpg")
        _attach(db, product, "b.jpg")

        db.flush()  # no error


class TestListing:
    def test_a_product_lists_its_image_candidates(self, db) -> None:
        product = _product(db)
        _attach(db, product, "a.jpg")
        _attach(db, product, "b.png", mime="image/png")

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert {candidate["filename"] for candidate in row["candidates"]} == {"a.jpg", "b.png"}

    def test_candidates_are_images_only(self, db) -> None:
        product = _product(db)
        _attach(db, product, "a.jpg")
        _attach(db, product, "spec.pdf", mime="application/pdf")

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert [candidate["filename"] for candidate in row["candidates"]] == ["a.jpg"]

    def test_a_product_with_no_photo_still_appears(self, db) -> None:
        # 465 of the flyer's codes are in this state, and the answer is a photo
        # shoot rather than a click. Dropping them from the list would hide the
        # work instead of naming it.
        product = _product(db)

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert row["candidates"] == []
        assert row["chosenAttachmentId"] is None

    def test_only_unset_hides_products_already_chosen(self, db) -> None:
        chosen = _product(db)
        pending = _product(db)
        link = _attach(db, chosen, "a.jpg")
        _attach(db, pending, "b.jpg")
        set_brochure_image(db, chosen.id, link.attachment_id)

        result = list_brochure_images(
            db, product_ids=[chosen.id, pending.id], only_unset=True
        )

        assert [item["productId"] for item in result["items"]] == [pending.id]

    def test_it_reports_how_many_are_still_to_choose(self, db) -> None:
        chosen = _product(db)
        pending = _product(db)
        link = _attach(db, chosen, "a.jpg")
        _attach(db, pending, "b.jpg")
        set_brochure_image(db, chosen.id, link.attachment_id)

        result = list_brochure_images(
            db, product_ids=[chosen.id, pending.id], only_unset=False
        )

        assert result["total"] == 2
        assert result["remaining"] == 1

    def test_the_chosen_image_is_named(self, db) -> None:
        product = _product(db)
        link = _attach(db, product, "a.jpg")
        _attach(db, product, "b.jpg")
        set_brochure_image(db, product.id, link.attachment_id)

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert row["chosenAttachmentId"] == link.attachment_id

    def test_a_search_matches_the_product_code(self, db) -> None:
        wanted = _product(db, code=unique_code("WANTED"))
        other = _product(db, code=unique_code("OTHER"))
        _attach(db, wanted, "a.jpg")
        _attach(db, other, "b.jpg")

        result = list_brochure_images(
            db, product_ids=[wanted.id, other.id], only_unset=False, query="WANTED"
        )

        assert [item["productId"] for item in result["items"]] == [wanted.id]
