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
from contextlib import contextmanager

import pytest

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
from app.services.brochure_image_service import (
    list_brochure_images,
    set_brochure_image,
)
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code


class _SigningBackend:
    """A storage backend whose signer works, whatever this machine has installed.

    Without this these tests passed for the wrong reason. Real signing needs a
    CloudFront private key that is absent here, `resolve_signed_url` used to
    fail open and hand back the raw path, and an assertion of "a url came back"
    was satisfied by that fallback - so the suite proved nothing about signing
    and would have changed answer on a machine that HAD the key. Now that the
    image paths sign strictly, the stub is what makes these tests about access
    control rather than about local configuration.
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


def _reference_rows(db):
    """A category and a UOM, because Postgres enforces the FKs sqlite ignored."""
    from app.models.product import ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("c")[:20],
        category_name=unique_code("cat"),
    )
    # `[:10]` used to survive only 4 hex chars of unique_code's suffix ("ZZT-u-" is 6
    # chars already), which collided under CI's parallel xdist workers
    # (units_of_measure_uom_code_key UniqueViolation). uom_code is String(50); widen to
    # match every other test file's `[:20]`/`[:50]` convention.
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_name=unique_code("uom"), uom_code=unique_code("u")[:20])
    db.add_all([category, uom])
    db.flush()
    return category.id, uom.id


def _product(db, code: str | None = None, company_id: str | None = None) -> Product:
    category_id, uom_id = _reference_rows(db)
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code or unique_code("sku"),
        product_name="Test product",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=100,
        # Left unset, the scope layer stamps the incumbent company. An explicit
        # one is how a genuinely other-company row is built.
        company_id=company_id,
    )
    db.add(product)
    db.flush()
    return product


def _other_company(db) -> str:
    """A second company, so out-of-scope can be constructed rather than mocked."""
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("Other Co"),
        code=unique_code("OC")[:20],
        is_active=True,
    )
    db.add(company)
    db.flush()
    return company.id


def _attach(
    db,
    product: Product,
    filename: str,
    mime: str = "image/jpeg",
    deleted: bool = False,
    company_id: str | None = None,
) -> ProductAttachment:
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"product/{filename}",
        mime_type=mime,
        is_deleted=deleted,
    )
    db.add(attachment)
    db.flush()
    link = ProductAttachment(
        id=str(uuid.uuid4()),
        product_id=product.id,
        attachment_id=attachment.id,
        company_id=company_id,
    )
    db.add(link)
    db.flush()
    return link


def _promotion(db, products) -> str:
    """A promotion holding the given products, the way a flyer's is built."""
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(id=str(uuid.uuid4()), description=unique_code("promo"))
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name=unique_code("grp"))
    db.add(group)
    db.flush()
    for product in products:
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promotion.id,
                promotion_group_id=group.id,
                product_id=product.id,
            )
        )
    db.flush()
    return promotion.id


@contextmanager
def _rows_read(db):
    """How many rows each statement touching the product tables returned.

    The point of the measurement: the default screen state has no filter, so
    "materialise the filtered set and page it in Python" means reading all
    22,805 products and every image link on every keystroke of a debounced
    search. A statement that returns more rows than the page is that defect,
    whatever the response happens to look like.
    """
    from sqlalchemy import event

    counts: list[int] = []
    engine = db.connection().engine

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if "products" in statement or "product_attachments" in statement:
            counts.append(max(cursor.rowcount, 0))

    event.listen(engine, "after_cursor_execute", _record)
    try:
        yield counts
    finally:
        event.remove(engine, "after_cursor_execute", _record)


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

        # 400 exactly, not "400 or 404": an implementation that refused
        # everything with a 404 would satisfy the looser assertion while
        # telling the user the file does not exist rather than that it is the
        # wrong kind of file.
        assert raised.value.status_code == 400

    def test_a_deleted_photo_cannot_be_chosen(self, db) -> None:
        # 611 of the 2,924 live product-to-image links point at an attachment
        # somebody deleted in Resource Management. The product's own
        # attachments tab already hides those, so accepting one here would have
        # two surfaces of the same feature disagree about what exists - and the
        # catalogue tile would sign a URL for a file the system calls deleted.
        product = _product(db)
        gone = _attach(db, product, "gone.jpg", deleted=True)

        with pytest.raises(AppException) as raised:
            set_brochure_image(db, product.id, gone.attachment_id)

        assert raised.value.status_code == 404

    def test_a_choice_deleted_afterwards_cannot_be_re_chosen(self, db) -> None:
        # The picker offers what it offers; the deletion can happen after the
        # click. Re-confirming a since-deleted choice must fail the same way.
        product = _product(db)
        link = _attach(db, product, "a.jpg")
        set_brochure_image(db, product.id, link.attachment_id)

        db.query(Attachment).filter(Attachment.id == link.attachment_id).update(
            {Attachment.is_deleted: True}
        )
        db.flush()

        with pytest.raises(AppException) as raised:
            set_brochure_image(db, product.id, link.attachment_id)

        assert raised.value.status_code == 404


class TestAnotherCompanysProduct:
    """AC-B2. Out of scope answers 404, never 403.

    Built out of a real second company and the ordinary scope filter
    (`do_orm_execute`), not a patched query: the point is that the isolation
    layer produces the 404, and a mocked one would prove only that the mock was
    called.
    """

    def test_it_cannot_be_given_a_brochure_image(self, db) -> None:
        elsewhere = _other_company(db)
        product = _product(db, company_id=elsewhere)
        link = _attach(db, product, "a.jpg", company_id=elsewhere)

        with pytest.raises(AppException) as raised:
            set_brochure_image(db, product.id, link.attachment_id)

        # 403 would confirm the row exists to somebody who may not know it does.
        assert raised.value.status_code == 404

    def test_its_choice_cannot_be_cleared(self, db) -> None:
        from app.services.brochure_image_service import clear_brochure_image

        elsewhere = _other_company(db)
        product = _product(db, company_id=elsewhere)

        with pytest.raises(AppException) as raised:
            clear_brochure_image(db, product.id)

        assert raised.value.status_code == 404

    def test_it_is_not_listed_or_counted(self, db) -> None:
        elsewhere = _other_company(db)
        product = _product(db, company_id=elsewhere)
        _attach(db, product, "a.jpg", company_id=elsewhere)

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        assert result["items"] == []
        assert result["total"] == 0
        # Counted as outstanding work, it would tell this company to photograph
        # a product it does not sell.
        assert result["remaining"] == 0


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

    def test_a_deleted_photo_is_not_offered(self, db) -> None:
        # A photo deleted in Resource Management is gone everywhere or it is
        # gone nowhere. 20% of the live links point at one.
        product = _product(db)
        _attach(db, product, "a.jpg")
        _attach(db, product, "gone.jpg", deleted=True)

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert [candidate["filename"] for candidate in row["candidates"]] == ["a.jpg"]

    def test_a_choice_deleted_afterwards_is_no_longer_the_choice(self, db) -> None:
        # Otherwise the screen reports the product as done while the tile has no
        # image the system will serve, and the work never resurfaces.
        product = _product(db)
        link = _attach(db, product, "a.jpg")
        _attach(db, product, "b.jpg")
        set_brochure_image(db, product.id, link.attachment_id)

        db.query(Attachment).filter(Attachment.id == link.attachment_id).update(
            {Attachment.is_deleted: True}
        )
        db.flush()

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert row["chosenAttachmentId"] is None
        assert result["remaining"] == 1

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

    def test_a_promotion_narrows_the_set_to_its_products(self, db) -> None:
        # The headline capability: a whole A3 flyer in one sitting rather than a
        # hunt through 22,805 products.
        inside = _product(db)
        outside = _product(db)
        _attach(db, inside, "a.jpg")
        _attach(db, outside, "b.jpg")
        promotion_id = _promotion(db, [inside])

        result = list_brochure_images(db, promotion_id=promotion_id, only_unset=False)

        assert [item["productId"] for item in result["items"]] == [inside.id]
        assert result["total"] == 1

    def test_an_unknown_promotion_matches_nothing(self, db) -> None:
        # Not "everything": an unfiltered 22,805-row answer to a filter the user
        # did ask for reads as though the filter worked.
        product = _product(db)
        _attach(db, product, "a.jpg")

        result = list_brochure_images(
            db, promotion_id=str(uuid.uuid4()), only_unset=False
        )

        assert result["items"] == []
        assert result["total"] == 0
        assert result["remaining"] == 0

    def test_a_promotion_and_a_search_narrow_together(self, db) -> None:
        wanted = _product(db, code=unique_code("WANTED"))
        sibling = _product(db, code=unique_code("OTHER"))
        _attach(db, wanted, "a.jpg")
        _attach(db, sibling, "b.jpg")
        promotion_id = _promotion(db, [wanted, sibling])

        result = list_brochure_images(
            db, promotion_id=promotion_id, only_unset=False, query="WANTED"
        )

        assert [item["productId"] for item in result["items"]] == [wanted.id]
        assert result["total"] == 1

    def test_a_search_matches_the_product_code(self, db) -> None:
        wanted = _product(db, code=unique_code("WANTED"))
        other = _product(db, code=unique_code("OTHER"))
        _attach(db, wanted, "a.jpg")
        _attach(db, other, "b.jpg")

        result = list_brochure_images(
            db, product_ids=[wanted.id, other.id], only_unset=False, query="WANTED"
        )

        assert [item["productId"] for item in result["items"]] == [wanted.id]


class TestPaging:
    """The counts describe the whole filtered set; only the page is read."""

    def _batch(self, db, count: int, chosen: int = 0):
        stem = unique_code("PAGE")
        products = [_product(db, code=f"{stem}-{index:02d}") for index in range(count)]
        for index, product in enumerate(products):
            link = _attach(db, product, "a.jpg")
            if index < chosen:
                set_brochure_image(db, product.id, link.attachment_id)
        return products

    def test_a_page_is_the_size_asked_for_and_the_counts_are_of_everything(self, db) -> None:
        products = self._batch(db, 5, chosen=2)

        result = list_brochure_images(
            db, product_ids=[p.id for p in products], only_unset=False, limit=2
        )

        assert len(result["items"]) == 2
        assert result["total"] == 5
        assert result["remaining"] == 3
        assert result["shown"] == 5

    def test_only_unset_shows_only_the_outstanding_ones_and_says_how_many(self, db) -> None:
        products = self._batch(db, 5, chosen=2)

        result = list_brochure_images(
            db, product_ids=[p.id for p in products], only_unset=True, limit=2
        )

        assert len(result["items"]) == 2
        assert result["total"] == 5
        assert result["remaining"] == 3
        # `shown` is what the user is paging through, not the page.
        assert result["shown"] == 3
        assert all(item["chosenAttachmentId"] is None for item in result["items"])

    def test_the_second_page_continues_where_the_first_stopped(self, db) -> None:
        products = self._batch(db, 5)
        by_code = [p.id for p in sorted(products, key=lambda p: p.product_code)]

        first = list_brochure_images(
            db, product_ids=by_code, only_unset=False, limit=2, page=1
        )
        second = list_brochure_images(
            db, product_ids=by_code, only_unset=False, limit=2, page=2
        )

        assert [item["productId"] for item in first["items"]] == by_code[:2]
        assert [item["productId"] for item in second["items"]] == by_code[2:4]

    def test_a_page_past_the_end_is_empty_not_an_error(self, db) -> None:
        products = self._batch(db, 3)

        result = list_brochure_images(
            db, product_ids=[p.id for p in products], only_unset=False, limit=2, page=9
        )

        assert result["items"] == []
        assert result["total"] == 3

    def test_only_the_page_is_read_out_of_the_database(self, db) -> None:
        # The defect: `.all()` on the filtered product set, then paging and both
        # counts in Python. With no filter that is 22,805 products and every
        # image link, on every keystroke of a 300ms-debounced search.
        products = self._batch(db, 12)

        with _rows_read(db) as rows:
            result = list_brochure_images(
                db, product_ids=[p.id for p in products], only_unset=False, limit=3
            )

        assert len(result["items"]) == 3
        assert result["total"] == 12
        # One image each, so the page's candidate rows number 3 as well. Any
        # statement returning more than that read products off the page.
        assert max(rows) <= 3, f"a statement returned {max(rows)} rows for a page of 3"

    def test_only_the_page_is_read_when_hiding_the_done_ones(self, db) -> None:
        # `only_unset` is the default screen state, and it used to be applied in
        # Python after everything had already been loaded.
        products = self._batch(db, 12, chosen=6)

        with _rows_read(db) as rows:
            result = list_brochure_images(
                db, product_ids=[p.id for p in products], only_unset=True, limit=3
            )

        assert len(result["items"]) == 3
        assert result["remaining"] == 6
        assert max(rows) <= 3, f"a statement returned {max(rows)} rows for a page of 3"


class TestNothingToChooseFrom:
    """A company with no product photos at all lands on this screen.

    Its default state used to read "11390 of 11390 still to choose" over a full
    page of products with no photos under any of them - which is true, and reads
    exactly like a screen that failed to load. The list cannot tell the two
    apart from the page alone: "no photos anywhere" and "none on THIS page" look
    identical until you page through 1,139 of them.

    So the filter-wide count comes from the server, the same way `remaining`
    does, and for the same reason.
    """

    def test_a_filter_with_no_photos_anywhere_says_so(self, db) -> None:
        first = _product(db)
        second = _product(db)

        result = list_brochure_images(
            db, product_ids=[first.id, second.id], only_unset=False
        )

        assert result["total"] == 2
        assert result["choosable"] == 0

    def test_one_product_with_a_photo_is_not_nothing(self, db) -> None:
        """The boundary that matters: 1 is a working screen, 0 is an empty one."""
        bare = _product(db)
        photographed = _product(db)
        _attach(db, photographed, "a.jpg")

        result = list_brochure_images(
            db, product_ids=[bare.id, photographed.id], only_unset=False
        )

        assert result["choosable"] == 1

    def test_it_counts_the_whole_filter_and_not_the_page(self, db) -> None:
        """Otherwise page 2 of a photographed catalogue could claim it is empty."""
        products = [_product(db) for _ in range(4)]
        for product in products:
            _attach(db, product, "a.jpg")

        result = list_brochure_images(
            db, product_ids=[p.id for p in products], only_unset=False, limit=1
        )

        assert len(result["items"]) == 1
        assert result["choosable"] == 4

    def test_a_photo_that_cannot_be_chosen_does_not_count(self, db) -> None:
        """Mirrors the candidate query exactly - a PDF and a deleted file are
        both listed nowhere, so counting them would promise a choice the screen
        cannot offer."""
        product = _product(db)
        _attach(db, product, "spec.pdf", mime="application/pdf")
        _attach(db, product, "gone.jpg", deleted=True)

        result = list_brochure_images(db, product_ids=[product.id], only_unset=False)

        row = next(item for item in result["items"] if item["productId"] == product.id)
        assert row["candidates"] == []
        assert result["choosable"] == 0

    def test_hiding_the_answered_ones_does_not_hide_them_from_this_count(
        self, db
    ) -> None:
        """`choosable` answers "is there anything on this screen at all", so it
        is counted over the filter rather than over what the switch leaves
        visible. Counted over the visible set, a fully answered catalogue would
        report 0 and claim it has no photos."""
        product = _product(db)
        link = _attach(db, product, "a.jpg")
        link.is_primary = True
        db.flush()

        result = list_brochure_images(db, product_ids=[product.id], only_unset=True)

        assert result["items"] == []
        assert result["remaining"] == 0
        assert result["choosable"] == 1


class TestActionableProductsComeFirst:
    """The default screen must open on work somebody can actually do.

    Ordered by code alone, Sorento's picker opens on 25 products called
    "**NEW", "**REPAIR", "11X11" and so on - junk SKUs with no photograph
    attached, which sort to the top because they start with punctuation and
    digits. The 533 products that DO have a photo to choose between are
    somewhere in the remaining 456 pages, and the screen a human meets is a wall
    of "No photo is linked to this product yet".

    So products with a candidate sort first. Nothing is hidden - the ones with
    no photo are still listed, still counted, and still reachable by paging -
    but the first page is the one page that can be worked.
    """

    def test_a_product_with_a_photo_outranks_one_without(self, db) -> None:
        stem = unique_code("ORD")
        # Deliberately spelled so code order alone would put the bare one first.
        bare = _product(db, code=f"{stem}-AAA")
        photographed = _product(db, code=f"{stem}-ZZZ")
        _attach(db, photographed, "a.jpg")

        result = list_brochure_images(
            db, product_ids=[bare.id, photographed.id], only_unset=False
        )

        assert [item["productId"] for item in result["items"]] == [
            photographed.id,
            bare.id,
        ]

    def test_code_order_still_decides_within_each_group(self, db) -> None:
        """Otherwise the list has no order a human can predict."""
        stem = unique_code("ORD")
        second = _product(db, code=f"{stem}-B")
        first = _product(db, code=f"{stem}-A")
        _attach(db, first, "a.jpg")
        _attach(db, second, "b.jpg")

        result = list_brochure_images(
            db, product_ids=[second.id, first.id], only_unset=False
        )

        assert [item["productId"] for item in result["items"]] == [first.id, second.id]

    def test_a_product_with_no_photo_is_still_listed(self, db) -> None:
        """Sorted down the list, never dropped from it. 465 of the flyer's codes
        are in that state and the answer there is a photo shoot, not a click -
        hiding them would hide the work instead of naming it."""
        stem = unique_code("ORD")
        bare = _product(db, code=f"{stem}-AAA")
        photographed = _product(db, code=f"{stem}-ZZZ")
        _attach(db, photographed, "a.jpg")

        result = list_brochure_images(
            db, product_ids=[bare.id, photographed.id], only_unset=False
        )

        assert result["total"] == 2
        assert bare.id in {item["productId"] for item in result["items"]}

    def test_a_photo_that_cannot_be_chosen_does_not_promote_a_product(self, db) -> None:
        """Mirrors the candidate query, like every other count here. A product
        whose only file is a PDF shows an empty tile strip, so promoting it would
        put an unworkable row at the top of the screen."""
        stem = unique_code("ORD")
        pdf_only = _product(db, code=f"{stem}-AAA")
        _attach(db, pdf_only, "spec.pdf", mime="application/pdf")
        photographed = _product(db, code=f"{stem}-ZZZ")
        _attach(db, photographed, "a.jpg")

        result = list_brochure_images(
            db, product_ids=[pdf_only.id, photographed.id], only_unset=False
        )

        assert [item["productId"] for item in result["items"]] == [
            photographed.id,
            pdf_only.id,
        ]
