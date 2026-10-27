"""Matching a catalogue photo's printed codes to the master, and R5 dedupe.

Written before the module exists (CATALOG-IMAGES, Phase 2, red). Contract:
``documentation/plans/products/PLAN-catalog-image-extract-27oct.md``, R3 (match
ladder), R5 (dedupe) and the "Phase 2 contract" section.

Postgres only, on a blank scratch schema, every row seeded here. As in the flyer
matcher tests, a product with ``company_id=None`` is the active company's and a
product under ``_other_company`` is not.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.services.dealer_kit.catalog_photo_matching import (
    CodeMatch,
    already_on_file,
    match_codes,
)
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _product(db, code: str, *, company_id: str | None = None) -> Product:
    stem = unique_code("ZZTCP")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        company_id=company_id,
    )
    db.add(product)
    db.flush()
    return product


def _other_company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTOC")[:20],
        is_active=True,
    )
    db.add(company)
    db.flush()
    return company.id


def _supplier(db):
    from app.models.procurement import Supplier

    supplier = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("ZZTSUP")[:50],
        supplier_name="ZZT supplier",
    )
    db.add(supplier)
    db.flush()
    return supplier


def _alias(db, supplier_code: str, product: Product | None, *, company_id: str | None = None):
    from app.models.scm import SupplierProductCodeAlias

    supplier = _supplier(db)
    row = SupplierProductCodeAlias(
        id=str(uuid.uuid4()),
        supplier_id=supplier.id,
        supplier_code=supplier_code,
        product_id=product.id if product else None,
        source="manual" if product else "dismissed",
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _attachment(db, *, file_hash: str):
    from app.models.resources import Attachment

    name = f"ZZT-{uuid.uuid4().hex[:8]}.jpg"
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=name,
        stored_filename=name,
        file_path=f"https://cdn.test/{name}",
        file_hash=file_hash,
        is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


def _link(db, product: Product, attachment) -> None:
    db.add(
        ProductAttachment(
            id=str(uuid.uuid4()), product_id=product.id, attachment_id=attachment.id
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# R3 ladder
# --------------------------------------------------------------------------- #
class TestLadder:
    def test_exact_code_is_high_confidence(self, db) -> None:
        product = _product(db, "ZZTBF12613")

        result = match_codes(db, ["ZZTBF12613"])["ZZTBF12613"]

        assert isinstance(result, CodeMatch)
        assert result.code == "ZZTBF12613"
        assert result.rung == "exact"
        assert result.confidence == "high"
        assert result.product_id == product.id
        assert result.product_code == "ZZTBF12613"
        assert result.suggestion is None

    @pytest.mark.parametrize("printed", ["zztbf 12613", "ZZTBF.12613", "zzt bf.126 13"])
    def test_normalised_code_is_medium_confidence(self, db, printed: str) -> None:
        product = _product(db, "ZZTBF12613")

        result = match_codes(db, [printed])[printed]

        assert result.code == printed
        assert result.rung == "normalised"
        assert result.confidence == "medium"
        assert result.product_id == product.id
        assert result.product_code == "ZZTBF12613"

    def test_printed_code_without_the_master_suffix_matches_by_suffix(self, db) -> None:
        product = _product(db, "ZZTW5112-MW")

        result = match_codes(db, ["ZZTW5112"])["ZZTW5112"]

        assert result.rung == "suffix"
        assert result.confidence == "medium"
        assert result.product_id == product.id
        assert result.product_code == "ZZTW5112-MW"

    def test_printed_suffix_against_a_master_without_it_matches_by_suffix(self, db) -> None:
        product = _product(db, "ZZTW5112")

        result = match_codes(db, ["ZZTW5112-MW"])["ZZTW5112-MW"]

        assert result.rung == "suffix"
        assert result.confidence == "medium"
        assert result.product_id == product.id

    def test_two_suffix_candidates_is_no_match_with_a_low_suggestion(self, db) -> None:
        _product(db, "ZZTW5112-MW")
        _product(db, "ZZTW5112-BK")

        result = match_codes(db, ["ZZTW5112"])["ZZTW5112"]

        assert result.rung == "none"
        assert result.product_id is None
        assert result.product_code is None
        assert result.confidence == "low"
        assert result.suggestion in {"ZZTW5112-MW", "ZZTW5112-BK"}

    def test_a_supplier_alias_matches_at_medium(self, db) -> None:
        product = _product(db, "ZZTBF12613")
        _alias(db, "VENDOR-X-77", product)

        result = match_codes(db, ["VENDOR-X-77"])["VENDOR-X-77"]

        assert result.rung == "alias"
        assert result.confidence == "medium"
        assert result.product_id == product.id
        assert result.product_code == "ZZTBF12613"

    def test_a_dismissal_alias_is_not_a_match(self, db) -> None:
        _alias(db, "ZZTQQ9999", None)

        result = match_codes(db, ["ZZTQQ9999"])["ZZTQQ9999"]

        assert result.rung == "none"
        assert result.product_id is None

    def test_a_code_with_no_near_neighbour_is_none_without_a_suggestion(self, db) -> None:
        _product(db, "ZZTBF12613")

        result = match_codes(db, ["QWXYZ00987"])["QWXYZ00987"]

        assert result.rung == "none"
        assert result.confidence == "none"
        assert result.product_id is None
        assert result.product_code is None
        assert result.suggestion is None

    def test_a_near_miss_is_a_low_confidence_suggestion_never_applied(self, db) -> None:
        _product(db, "ZZTKS7851")

        result = match_codes(db, ["ZZTKS7850"])["ZZTKS7850"]

        assert result.rung == "none"
        assert result.confidence == "low"
        assert result.product_id is None
        assert result.suggestion == "ZZTKS7851"

    def test_exact_wins_over_a_suffix_candidate(self, db) -> None:
        exact = _product(db, "ZZTW5112")
        _product(db, "ZZTW5112-MW")

        result = match_codes(db, ["ZZTW5112"])["ZZTW5112"]

        assert result.rung == "exact"
        assert result.product_id == exact.id

    def test_one_entry_per_input_code(self, db) -> None:
        _product(db, "ZZTBF12613")
        _product(db, "ZZTW2600")

        result = match_codes(db, ["ZZTBF12613", "ZZTW2600", "QWXYZ00987"])

        assert set(result) == {"ZZTBF12613", "ZZTW2600", "QWXYZ00987"}
        assert [result[c].rung for c in ("ZZTBF12613", "ZZTW2600", "QWXYZ00987")] == [
            "exact",
            "exact",
            "none",
        ]

    def test_no_codes_is_an_empty_dict(self, db) -> None:
        assert match_codes(db, []) == {}


class TestCompanyScope:
    def test_a_product_under_another_company_is_not_matched(self, db) -> None:
        elsewhere = _other_company(db)
        _product(db, "ZZTBF12613", company_id=elsewhere)

        result = match_codes(db, ["ZZTBF12613"])["ZZTBF12613"]

        assert result.rung == "none"
        assert result.product_id is None
        assert result.suggestion is None

    def test_the_product_in_this_company_is_the_one_matched(self, db) -> None:
        elsewhere = _other_company(db)
        mine = _product(db, "ZZTBF12613")
        _product(db, "ZZTBF12613", company_id=elsewhere)

        result = match_codes(db, ["ZZTBF12613"])["ZZTBF12613"]

        assert result.product_id == mine.id

    def test_an_alias_to_another_companys_product_is_not_a_match(self, db) -> None:
        elsewhere = _other_company(db)
        theirs = _product(db, "ZZTBF12613", company_id=elsewhere)
        _alias(db, "VENDOR-X-77", theirs, company_id=elsewhere)

        result = match_codes(db, ["VENDOR-X-77"])["VENDOR-X-77"]

        assert result.rung == "none"
        assert result.product_id is None


# --------------------------------------------------------------------------- #
# R5 dedupe
# --------------------------------------------------------------------------- #
class TestAlreadyOnFile:
    HASH = "a" * 64

    def test_true_when_the_product_links_an_attachment_with_that_hash(self, db) -> None:
        product = _product(db, "ZZTBF12613")
        _link(db, product, _attachment(db, file_hash=self.HASH))

        assert already_on_file(db, product.id, self.HASH) is True

    def test_false_for_a_different_product_with_the_same_hash(self, db) -> None:
        owner = _product(db, "ZZTBF12613")
        other = _product(db, "ZZTW2600")
        _link(db, owner, _attachment(db, file_hash=self.HASH))

        assert already_on_file(db, other.id, self.HASH) is False

    def test_false_for_a_different_hash(self, db) -> None:
        product = _product(db, "ZZTBF12613")
        _link(db, product, _attachment(db, file_hash=self.HASH))

        assert already_on_file(db, product.id, "b" * 64) is False

    def test_false_when_the_product_has_no_attachments(self, db) -> None:
        product = _product(db, "ZZTBF12613")

        assert already_on_file(db, product.id, self.HASH) is False
