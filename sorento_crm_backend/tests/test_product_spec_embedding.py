"""The `product_spec` embedding source type.

A SECOND product source type, not a replacement. The existing `product` body embeds the
product code twice, the category code, and the raw description (which contains other
products' codes), and it is consumed by order-filter fuzzy matching
(`order_service.py:344` and `:1313`) and the assistant RAG. Rewriting it in place would
change both in the same commit as a new feature. See documentation/adr/0013.

Ticket: jayson-odoo/sorento-crm#75. Contract: AC-T0d-01 .. AC-T0d-07.
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.embedding_worker import _SOURCE_MODEL_FOR_COMPANY, _canonical_for_source
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_rendering import CODE_SHAPES
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        # The brand is read off the product's own brand row, not off the `SRT` in the
        # category code, so a product with no brand renders no brand. The sentence this
        # file asserts on names one, which means the fixture has to give it one.
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        yield s


def _product(db, code: str, description: str) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


# AC-T0d-01: the existing source type is untouched. If this ever fails, order filtering
# and the assistant changed behaviour as a side effect of a spec-search commit.
def test_the_existing_product_source_type_is_unchanged(db):
    product = _product(db, "ZZT-EMB-1", "SORENTO S/STEEL KITCHEN SINK (1000X500X140MM)")

    canonical = _canonical_for_source(db, "product", product.id)

    assert canonical["body_text"].startswith("Source Type: Product")
    assert "Product Code: ZZT-EMB-1" in canonical["body_text"]
    assert "Description: SORENTO S/STEEL KITCHEN SINK" in canonical["body_text"]


def test_product_spec_is_a_separate_source_type(db):
    product = _product(db, "ZZT-EMB-2", "SORENTO S/STEEL KITCHEN SINK (1000X500X140MM)")

    spec_doc = _canonical_for_source(db, "product_spec", product.id)
    product_doc = _canonical_for_source(db, "product", product.id)

    assert spec_doc["body_text"] != product_doc["body_text"]


# AC-T0d-02, AC-T0d-03: the body is the rendered sentence, and no code survives.
def test_the_body_is_the_rendered_sentence_with_no_codes(db):
    product = _product(db, "ZZT-EMB-3", "SORENTO S/STEEL KITCHEN SINK (1000X500X140MM)")

    body = _canonical_for_source(db, "product_spec", product.id)["body_text"]

    assert "Sorento kitchen sink." in body
    assert "Stainless steel." in body
    assert "1000 x 500 x 140 mm." in body
    assert "ZZT-EMB-3" not in body
    for pattern in CODE_SHAPES:
        assert not re.search(pattern, body), pattern


def test_a_foreign_code_in_the_description_never_reaches_the_index(db):
    # The exact failure that made product resolution code-only: a cross-reference to
    # another product's code must not become searchable text for THIS row.
    product = _product(db, "ZZT-EMB-4", "SPARE SEAT COVER USED FOR SRTWC6015-RL-UF")

    body = _canonical_for_source(db, "product_spec", product.id)["body_text"]

    assert "SRTWC6015" not in body


# AC-T0d-04: a round product reads as a diameter, not as length by width.
def test_a_round_product_embeds_as_a_diameter(db):
    product = _product(db, "ZZT-EMB-5", "CONCRETE ROUND BASIN WITH VALVE (407X120X10MM)")

    body = _canonical_for_source(db, "product_spec", product.id)["body_text"]

    assert "407 mm diameter." in body
    assert " x " not in body


# AC-T0d-05: nothing to say means no document at all.
def test_a_product_with_no_spec_text_is_refused(db):
    product = Product(
        id=str(uuid.uuid4()),
        product_code="ZZT-EMB-6",
        product_name="ZZT-EMB-6",
        description=None,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    db.add(ProductSpecifications(product_id=product.id, values={}, provenance={}, rendered_text=None))
    db.flush()

    with pytest.raises(ValueError, match="no spec text"):
        _canonical_for_source(db, "product_spec", product.id)


def test_metadata_carries_the_code_and_the_keys_present(db):
    product = _product(db, "ZZT-EMB-7", "SORENTO CERAMIC WALL HUNG WATER CLOSET")

    metadata = _canonical_for_source(db, "product_spec", product.id)["metadata"]

    assert metadata["product_code"] == "ZZT-EMB-7"
    assert "material" in metadata["spec_keys"]


def test_company_resolution_is_wired_for_the_new_source_type():
    # Without this, a fresh product_spec document would be company-less while its
    # source has a company, and multi-company isolation would leak it everywhere.
    assert _SOURCE_MODEL_FOR_COMPANY["product_spec"] is Product
