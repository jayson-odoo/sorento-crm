"""`applicable_keys_for_code` and the vocabulary duplicate guards - PR 2's backend.

UAC: AC-A.7 (applicability mirrors derivation's `_apply_scope`, NOT `keys-for-product`),
AC-A.10 (`similar` against key, label and merged synonym), AC-A.11 (the same comparison
for a value, enforced server-side per D11).

Postgres only, via `tests/_pg_fixture.blank_session` (AC-F.14). Every FK target is
seeded here with a `ZZT` marker; nothing is borrowed from an existing row, because CI's
database is empty.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.product_spec_registry import (
    applicable_keys_for_code,
    find_similar_key,
    find_similar_value,
    normalise_vocabulary,
)
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


def _fixtures(db):
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code="ZZT-AK-WC", category_name="ZZT-AK-WC"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-AK-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-AK-SRT", brand_name="Sorento")
    db.add_all([cat, uom, brand])
    db.flush()
    _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})


def _product(db, code: str) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="ZZT WATER CLOSET",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    return row


def _key(db, spec_key: str, **kwargs) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        spec_key=spec_key,
        label=kwargs.pop("label", spec_key.replace("_", " ").title()),
        data_type=kwargs.pop("data_type", "text"),
        unit=kwargs.pop("unit", None),
        allowed_values=kwargs.pop("allowed_values", []),
        synonyms=kwargs.pop("synonyms", {}),
        user_synonyms=kwargs.pop("user_synonyms", {}),
        user_values=kwargs.pop("user_values", []),
        suppressed_values=kwargs.pop("suppressed_values", []),
        suppressed_synonyms=kwargs.pop("suppressed_synonyms", {}),
        applies_when=kwargs.pop("applies_when", {}),
        is_active=kwargs.pop("is_active", True),
        source=kwargs.pop("source", "user"),
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _spec(db, product, values, provenance):
    row = ProductSpecifications(
        product_id=product.id, values=values, provenance=provenance, status="derived"
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# AC-A.7 - applicability is `applies_when`, evaluated the way derivation does
# --------------------------------------------------------------------------- #
def test_ungated_key_applies_to_everything(db):
    _key(db, "zzt_finish", allowed_values=["chrome"])
    product = _product(db, "ZZT-AK-0001")
    _spec(db, product, {}, {})

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_finish"]["applicable"] is True


def test_gate_the_product_contradicts_excludes_the_key(db):
    _key(db, "zzt_class", allowed_values=["water_closet", "kitchen_sink"])
    _key(db, "zzt_flush", applies_when={"zzt_class": ["water_closet"]})
    product = _product(db, "ZZT-AK-0002")
    _spec(db, product, {"zzt_class": {"value": "kitchen_sink"}}, {"zzt_class": {"source": "derived"}})

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_flush"]["applicable"] is False


def test_gate_the_product_satisfies_keeps_the_key(db):
    _key(db, "zzt_class", allowed_values=["water_closet"])
    _key(db, "zzt_flush", applies_when={"zzt_class": ["water_closet"]})
    product = _product(db, "ZZT-AK-0003")
    _spec(db, product, {"zzt_class": {"value": "WATER_CLOSET"}}, {"zzt_class": {"source": "derived"}})

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    # Compared case-insensitively, exactly as `_apply_scope` does.
    assert keys["zzt_flush"]["applicable"] is True


def test_absent_gate_value_never_excludes(db):
    """The module's standing rule: absence of a word is never evidence of absence."""
    _key(db, "zzt_flush", applies_when={"zzt_class": ["water_closet"]})
    product = _product(db, "ZZT-AK-0004")
    _spec(db, product, {}, {})

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_flush"]["applicable"] is True


def test_a_class_inherited_from_the_category_never_gates(db):
    """A decode of a filing code must not delete evidence read from the product."""
    _key(db, "zzt_class", allowed_values=["water_closet", "kitchen_sink"])
    _key(db, "zzt_smart", applies_when={"zzt_class": ["water_closet"]})
    product = _product(db, "ZZT-AK-0005")
    _spec(
        db,
        product,
        {"zzt_class": {"value": "kitchen_sink"}},
        {"zzt_class": {"source": "category"}},
    )

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_smart"]["applicable"] is True


def test_it_reports_which_keys_the_product_already_holds(db):
    """The picker's other half: applicable AND not already on the product."""
    _key(db, "zzt_finish", allowed_values=["chrome"])
    _key(db, "zzt_material", allowed_values=["ceramic"])
    product = _product(db, "ZZT-AK-0006")
    _spec(db, product, {"zzt_finish": {"value": "chrome"}}, {"zzt_finish": {"source": "derived"}})

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_finish"]["held"] is True
    assert keys["zzt_material"]["held"] is False


def test_a_removed_key_is_offered_again(db):
    """Removed means gone from the table, so the picker is the only way back on.

    The tombstone still lives in provenance - re-derivation must not refill the key -
    but a removed key that could never be re-added would be a delete with no undo.
    Setting a value by hand replaces the stamp wholesale, which clears the tombstone.
    """
    _key(db, "zzt_overflow", data_type="boolean")
    product = _product(db, "ZZT-AK-0007")
    _spec(db, product, {}, {"zzt_overflow": {"source": "human", "absent": True}})

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_overflow"]["held"] is False


def test_a_product_with_no_spec_row_still_gets_the_whole_registry(db):
    """The empty product is the one that most needs the picker to work."""
    _key(db, "zzt_finish", allowed_values=["chrome"])
    product = _product(db, "ZZT-AK-0008")

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_finish"]["applicable"] is True
    assert keys["zzt_finish"]["held"] is False


def test_the_code_is_matched_whatever_case_it_arrives_in(db):
    """A code is a filing label, and every other lookup here reads it that way.

    An exact match 404s a caller who typed the same product in another case, and the
    picker renders that as "this product may carry nothing" rather than as a bad code.
    """
    _key(db, "zzt_finish", allowed_values=["chrome"])
    _product(db, "ZZT-AK-0014")

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, "zzt-ak-0014")}
    assert keys["zzt_finish"]["applicable"] is True


def test_inactive_keys_are_left_out(db):
    _key(db, "zzt_retired", is_active=False)
    product = _product(db, "ZZT-AK-0009")

    keys = {row["spec_key"] for row in applicable_keys_for_code(db, product.product_code)}
    assert "zzt_retired" not in keys


def test_an_unknown_code_raises_rather_than_returning_an_empty_list(db):
    """An empty list reads as "this product may carry nothing", which is a lie."""
    from app.services.error_handler import AppException

    with pytest.raises(AppException):
        applicable_keys_for_code(db, "ZZT-AK-NOSUCHCODE")


def test_the_vocabulary_returned_is_the_merged_one(db):
    """The picker's editor needs what a person may actually pick, not the seed list."""
    _key(
        db,
        "zzt_finish",
        allowed_values=["chrome", "white"],
        user_values=["brushed_brass"],
        suppressed_values=["white"],
    )
    product = _product(db, "ZZT-AK-0010")

    keys = {row["spec_key"]: row for row in applicable_keys_for_code(db, product.product_code)}
    assert keys["zzt_finish"]["allowed_values"] == ["chrome", "brushed_brass"]


# --------------------------------------------------------------------------- #
# AC-A.10 / AC-A.11 - the duplicate guards, normalised
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Brushed Brass", "brushed brass"),
        ("brushed_brass", "brushed brass"),
        ("  BRUSHED-BRASS  ", "brushed brass"),
        ("Matt/Black", "matt black"),
        ("finish!", "finish"),
    ],
)
def test_normalisation_folds_case_spacing_and_separators(raw, expected):
    assert normalise_vocabulary(raw) == expected


def test_similar_key_matches_on_the_key_itself(db):
    _key(db, "zzt_tap_hole", label="Tap hole")
    match = find_similar_key(db, "ZZT tap hole")
    assert match is not None and match["spec_key"] == "zzt_tap_hole"
    assert match["matched_on"] == "spec_key"


def test_similar_key_matches_on_the_label(db):
    _key(db, "zzt_finish", label="Finish or colour")
    match = find_similar_key(db, "finish  or  COLOUR")
    assert match is not None and match["spec_key"] == "zzt_finish"
    assert match["matched_on"] == "label"


def test_similar_key_matches_on_a_merged_synonym(db):
    _key(db, "zzt_finish", label="Finish", user_synonyms={"chrome": ["surface colour"]})
    match = find_similar_key(db, "Surface Colour")
    assert match is not None and match["spec_key"] == "zzt_finish"
    assert match["matched_on"] == "synonym"
    assert match["matched_text"] == "surface colour"


def test_similar_key_returns_none_for_a_genuinely_new_word(db):
    _key(db, "zzt_finish", label="Finish")
    assert find_similar_key(db, "Seat hinge material") is None


def test_similar_key_ignores_a_suppressed_synonym(db):
    """A word this business has taken away is not a word this business uses."""
    _key(
        db,
        "zzt_finish",
        label="Finish",
        user_synonyms={"chrome": ["surface colour"]},
        suppressed_synonyms={"chrome": ["surface colour"]},
    )
    assert find_similar_key(db, "surface colour") is None


def test_similar_value_matches_an_existing_value(db):
    row = _key(db, "zzt_finish", allowed_values=["brushed_brass"])
    match = find_similar_value(row, "Brushed Brass")
    assert match is not None and match["value"] == "brushed_brass"
    assert match["matched_on"] == "value"


def test_similar_value_matches_a_synonym_of_another_value(db):
    """`matte black` ships as a WORD for `black`; adding it as a value of its own
    would create one nothing can ever match."""
    row = _key(db, "zzt_finish", allowed_values=["black"], synonyms={"black": ["matte black"]})
    match = find_similar_value(row, "Matte Black")
    assert match is not None and match["value"] == "black"
    assert match["matched_on"] == "synonym"


def test_similar_value_returns_none_for_a_new_word(db):
    row = _key(db, "zzt_finish", allowed_values=["chrome"])
    assert find_similar_value(row, "brushed brass") is None
