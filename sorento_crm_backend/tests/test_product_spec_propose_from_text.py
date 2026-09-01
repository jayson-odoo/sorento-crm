"""`propose_from_text` - the flyer text pass, lifted out of derivation into a pure
function (AC-B.18, captain amendment 2026-08-14).

PR 4 contract: `documentation/plans/master-data/PLAN-spec-authoring-verification.md`
("PR 4 implementation contract"). `propose_from_text(text, code, *, rules_by_key=None,
scopes_by_key=None) -> list[dict]` in `product_spec_derivation.py` does not exist yet,
so the module-level import below fails at collection - that IS the expected red state.

Four of the seven flyer tests named in the tester brief
(tests/test_product_spec_derivation.py:861, :967, :994, :1019) are LIFTED here nearly
verbatim - same text, same expected key/value/evidence - because they test the PASS
itself (a rule reading flyer-style text), which survives unchanged. The other three
(:881, :951, :1007) tested the flyer LOSING to the description inside one derivation
call; that ordering does not exist here because `propose_from_text` never sees a
description at all, so they are not lifted - see
`tests/test_product_spec_derivation.py` for the one-line note at each deletion site.

`derive()` / `derive_for_code()` losing their `flyer_text` parameter, and
`_input_hash` losing its `flyer_text` part, are pinned here too (same contract
paragraph) rather than in the derivation test file, because they are the other half
of the same seam: the flyer stops being an INPUT to derivation and becomes an input
to this function instead.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductFlyerText, ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import (
    _input_hash,
    derive,
    derive_for_code,
    description_first_keys,
    propose_from_text,
)
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


def _fixtures(db):
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-PFT-KS", category_name="ZZT-PFT-KS")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PFT-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-PFT-SRT", brand_name="Sorento")
    second = Company(id=str(uuid.uuid4()), name="ZZT PFT Second Co", code="ZZT-PFT2")
    db.add_all([cat, uom, brand, second])
    db.flush()
    backfill_category_signals(db)
    _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id, "company2": second.id})


def _product(db, code: str, description: str, *, brand=None) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS[brand] if brand else None,
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    return row


def _by_key(proposals: list[dict]) -> dict[str, dict]:
    return {p["spec_key"]: p for p in proposals}


# --------------------------------------------------------------------------- #
# lifted from test_product_spec_derivation.py - the pass itself, unchanged
# --------------------------------------------------------------------------- #
def test_propose_from_text_reads_material_from_pasted_text():
    """Lifted from :861 (test_the_flyer_fills_a_gap_the_description_left)."""
    proposals = propose_from_text("Brass Body. Matt Black", "ZZT-PFT-FLY-1")

    by_key = _by_key(proposals)
    assert by_key["material"]["value"] == "brass"
    assert by_key["material"]["evidence"] == "BRASS"
    assert by_key["material"]["origin"] == "flyer"
    assert by_key["material"]["description_first"] is False


def test_propose_from_text_flyer_words_beat_the_code_suffix():
    """Lifted from :967 (test_words_on_the_flyer_beat_a_letter_pair_in_the_code).

    `-GY` maps to grey; pasted text saying "Golden Yellow" in words must still win,
    because the source-major order (flyer before code) survives the lift.
    """
    proposals = propose_from_text("Art Basin. Golden Yellow", "ZZT-PFT-SRC-2-GY")

    by_key = _by_key(proposals)
    assert by_key["finish"]["value"] == "golden_yellow"
    assert by_key["finish"]["origin"] == "flyer"


def test_propose_from_text_supplies_dimensions_the_text_states():
    """Lifted from :994 (test_the_flyer_supplies_dimensions_the_description_never_states)."""
    proposals = propose_from_text("Washdown. D: L680xW375xH770mm", "ZZT-PFT-DIM-1")

    by_key = _by_key(proposals)
    assert by_key["dim_length"]["value"] == 680
    assert by_key["dim_length"]["unit"] == "mm"
    assert by_key["dim_length"]["origin"] == "flyer"
    assert by_key["dim_length"]["description_first"] is True
    assert by_key["dim_width"]["value"] == 375
    assert by_key["dim_height"]["value"] == 770


def test_propose_from_text_reads_seat_material_from_pasted_text():
    """Lifted from :1019 (test_the_seat_cover_material_is_read_from_the_flyer)."""
    proposals = propose_from_text("Washdown With Rimless. *PP Seat Cover", "ZZT-PFT-SEAT-1")

    by_key = _by_key(proposals)
    assert by_key["seat_material"]["value"] == "pp"
    assert by_key["seat_material"]["origin"] == "flyer"
    assert by_key["seat_material"]["description_first"] is False


# --------------------------------------------------------------------------- #
# the documented shape
# --------------------------------------------------------------------------- #
def test_every_proposal_has_the_documented_fields():
    proposals = propose_from_text("Brass Body. Matt Black", "ZZT-PFT-SHAPE-1")

    assert proposals, "expected at least one proposal from this text"
    for item in proposals:
        assert set(item.keys()) >= {
            "spec_key",
            "value",
            "unit",
            "evidence",
            "origin",
            "description_first",
        }


def test_description_first_is_true_only_for_the_description_first_keys():
    proposals = propose_from_text(
        "Washdown. D: L680xW375xH770mm. Brass Body.", "ZZT-PFT-SHAPE-2"
    )
    by_key = _by_key(proposals)

    for key, item in by_key.items():
        assert item["description_first"] == (key in description_first_keys()), key


# --------------------------------------------------------------------------- #
# source scoping: "description" never fires on pasted text; "flyer" and "any" do
# --------------------------------------------------------------------------- #
def test_a_rule_scoped_to_description_never_fires_on_pasted_text():
    proposals = propose_from_text(
        "SOLID BRASS BODY",
        "ZZT-PFT-SCOPE-DESC",
        rules_by_key={
            "material": [
                {"match": "contains", "pattern": "BRASS", "value": "brass", "source": "description"}
            ]
        },
    )

    assert "material" not in _by_key(proposals)


def test_a_rule_scoped_to_flyer_fires_on_pasted_text():
    proposals = propose_from_text(
        "SOLID BRASS BODY",
        "ZZT-PFT-SCOPE-FLYER",
        rules_by_key={
            "material": [
                {"match": "contains", "pattern": "BRASS", "value": "brass", "source": "flyer"}
            ]
        },
    )

    assert _by_key(proposals)["material"]["value"] == "brass"


def test_a_rule_scoped_to_any_fires_on_pasted_text():
    proposals = propose_from_text(
        "SOLID BRASS BODY",
        "ZZT-PFT-SCOPE-ANY",
        rules_by_key={
            "material": [
                {"match": "contains", "pattern": "BRASS", "value": "brass", "source": "any"}
            ]
        },
    )

    assert _by_key(proposals)["material"]["value"] == "brass"


def test_a_code_suffix_rule_still_fires():
    """The code passes stay in the mix - source-major order is (flyer, code)."""
    proposals = propose_from_text(
        "",
        "ZZT-PFT-CODE-GY",
        rules_by_key={"finish": [{"match": "code_suffix", "pattern": "GY", "value": "grey"}]},
    )

    assert _by_key(proposals)["finish"]["value"] == "grey"
    assert _by_key(proposals)["finish"]["origin"] == "code"


# --------------------------------------------------------------------------- #
# `_apply_scope` still gates a key - exercised via the accumulator's own values,
# same mechanic as `derive()`'s docstring describes
# --------------------------------------------------------------------------- #
def test_apply_scope_keeps_a_key_when_the_text_itself_establishes_the_gating_class():
    proposals = propose_from_text(
        "One Piece Toilet with PP Seat Cover",
        "ZZT-PFT-SCOPE-KEEP",
        rules_by_key={
            "class": [
                {"match": "contains", "pattern": "TOILET", "value": "Water Closet", "source": "any"}
            ],
            "seat_material": [
                {"match": "contains", "pattern": "PP", "value": "pp", "source": "any"}
            ],
        },
        scopes_by_key={"seat_material": {"class": ["Water Closet"]}},
    )

    assert _by_key(proposals)["seat_material"]["value"] == "pp"


def test_apply_scope_drops_a_key_when_the_text_never_establishes_the_gating_class():
    proposals = propose_from_text(
        "Basin Tap with PP Handle",
        "ZZT-PFT-SCOPE-DROP",
        rules_by_key={
            "class": [{"match": "contains", "pattern": "TAP", "value": "Tap", "source": "any"}],
            "seat_material": [
                {"match": "contains", "pattern": "PP", "value": "pp", "source": "any"}
            ],
        },
        scopes_by_key={"seat_material": {"class": ["Water Closet"]}},
    )

    assert "seat_material" not in _by_key(proposals)


# --------------------------------------------------------------------------- #
# purity: no db, no writes
# --------------------------------------------------------------------------- #
def test_propose_from_text_takes_no_db_session():
    import inspect

    params = inspect.signature(propose_from_text).parameters
    assert "db" not in params, "propose_from_text must stay pure - no session argument"


def test_propose_from_text_writes_nothing_to_the_database(db):
    before_specs = db.query(ProductSpecifications).count()
    before_flyers = db.query(ProductFlyerText).count()

    propose_from_text("Brass Body. Matt Black", "ZZT-PFT-WRITE-1")

    assert db.query(ProductSpecifications).count() == before_specs
    assert db.query(ProductFlyerText).count() == before_flyers


# --------------------------------------------------------------------------- #
# derivation stops reading the flyer as an input
# --------------------------------------------------------------------------- #
def test_derive_no_longer_accepts_flyer_text_kwarg(db):
    product = _product(db, "ZZT-PFT-DRV-1", "SORENTO CERAMIC BASIN ZZT-PFT-DRV-1", brand="brand")

    with pytest.raises(TypeError):
        derive(product, None, flyer_text="Brass")


def test_derive_for_code_no_longer_accepts_flyer_text_kwarg(db):
    _product(db, "ZZT-PFT-DRV-2", "SORENTO CERAMIC BASIN ZZT-PFT-DRV-2", brand="brand")

    with pytest.raises(TypeError):
        derive_for_code(db, "ZZT-PFT-DRV-2", flyer_text="Brass")


def test_input_hash_no_longer_accepts_flyer_text(db):
    product = _product(db, "ZZT-PFT-DRV-3", "SORENTO CERAMIC BASIN ZZT-PFT-DRV-3", brand="brand")

    with pytest.raises(TypeError):
        _input_hash(product, None, "", flyer_text="Brass")


def test_derive_for_code_ignores_a_stored_flyer_text_row(db):
    """A code with a `ProductFlyerText` row still on the table must not have its
    values change because of it - the row is no longer an input at all."""
    _product(db, "ZZT-PFT-DRV-4", "SORENTO CERAMIC BASIN ZZT-PFT-DRV-4", brand="brand")
    db.add(
        ProductFlyerText(
            product_code="ZZT-PFT-DRV-4",
            source_label="ZZT FLYER",
            lines=["Brass Body"],
            text="Brass Body",
        )
    )
    db.flush()

    derive_for_code(db, "ZZT-PFT-DRV-4", commit=True)

    spec = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "ZZT-PFT-DRV-4")
        .first()
    )
    # The description of this fixture says CERAMIC, so `material` IS derived - from the
    # product master, which is legitimate. What must not survive the lift is the FLYER's
    # answer: "Brass Body" would have read `material=brass` when the row was an input.
    assert (spec.values or {}).get("material", {}).get("value") != "brass", (
        "material=brass only ever came from the flyer row; it must not survive the lift"
    )
