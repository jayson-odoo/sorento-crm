"""``classify_spec_proposal`` - the kind decision lifted out of `extract_spec_
proposals` so the bulk flyer-ingestion job (S2) can share it byte-for-byte
(AC-A.3).

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` section 3.2
("Kind classification" row). UAC: `flyer-spec-ingestion-acceptance-criteria.md`
AC-A.3. `app.services.product_spec_extract.classify_spec_proposal` does not
exist yet, so every import below fails at collection - that IS the expected red
state (see the tester brief: "Import failures ARE the red state").

Written before the function exists (test-first, PRINCIPLES.md Phase 2). Table
pinned, in the order the plan states it:

    tombstoned key                              -> "suppressed"
    equal after `_canonical_entry`               -> "unchanged"
    stored source in AUTHORED_SOURCES            -> "conflict"
    no stored entry                              -> "new"
    key in `description_first_keys()`             -> "conflict"
    else                                          -> "change"

The two regression tests at the bottom pin that `extract_spec_proposals`
(PR 4's route, unrelated to this slice's routes) keeps its EXISTING caller-
facing behaviour after the lift: a tombstone still reads as `conflict` to that
caller (never `suppressed`, which is new vocabulary this slice introduces for
the STORED batch only) and an `unchanged` proposal is still dropped from what
it returns. Postgres only, via `tests/_pg_fixture.py::blank_session`; every row
is seeded here with a `ZZT-FLYCLS` marker, never borrowed.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code, description_first_keys
from app.services.product_spec_extract import classify_spec_proposal, extract_spec_proposals
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_write import AUTHORED_SOURCES
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-FLYCLS-KS", category_name="ZZT-FLYCLS-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-FLYCLS-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-FLYCLS-SRT", brand_name="Sorento")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        seed_spec_registry(s, commit=False)
        s.flush()
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
    return row


# --------------------------------------------------------------------------- #
# AC-A.3 - the pure table, no DB needed
# --------------------------------------------------------------------------- #
def test_a_tombstoned_key_classifies_as_suppressed():
    proposed = {"value": "pp"}
    stored_stamp = {"source": "human", "absent": True}

    kind = classify_spec_proposal(proposed, None, stored_stamp, "seat_material")

    assert kind == "suppressed"


def test_an_equal_value_after_canonicalisation_classifies_as_unchanged():
    proposed = {"value": "pp", "unit": None}
    stored = {"value": "pp"}

    kind = classify_spec_proposal(proposed, stored, {"source": "derived"}, "seat_material")

    assert kind == "unchanged"


def test_a_stored_authored_source_classifies_as_conflict():
    """`human` is in AUTHORED_SOURCES; a person's value is never overwritten quietly."""
    proposed = {"value": "pp"}
    stored = {"value": "uf"}
    stored_stamp = {"source": "human"}
    assert "human" in AUTHORED_SOURCES

    kind = classify_spec_proposal(proposed, stored, stored_stamp, "seat_material")

    assert kind == "conflict"


def test_no_stored_entry_classifies_as_new():
    proposed = {"value": "brass"}

    kind = classify_spec_proposal(proposed, None, {}, "material")

    assert kind == "new"


def test_a_description_first_key_with_a_differing_derived_value_classifies_as_conflict():
    """`dim_length` is description-first: the master's own description beats a
    flyer's rounded figure, so a differing derived value is a conflict a reviewer
    must confirm rather than a plain gap-fill."""
    assert "dim_length" in description_first_keys()
    proposed = {"value": 680, "unit": "mm"}
    stored = {"value": 700, "unit": "mm"}
    stored_stamp = {"source": "derived"}

    kind = classify_spec_proposal(proposed, stored, stored_stamp, "dim_length")

    assert kind == "conflict"


def test_a_plain_differing_derived_value_classifies_as_change():
    """`finish` is not description-first, so a differing derived value is a plain
    gap-fill/correction, not something needing confirmation."""
    assert "finish" not in description_first_keys()
    proposed = {"value": "chrome"}
    stored = {"value": "black"}
    stored_stamp = {"source": "derived"}

    kind = classify_spec_proposal(proposed, stored, stored_stamp, "finish")

    assert kind == "change"


def test_a_new_stored_entry_wins_over_the_description_first_rule():
    """The order matters: 'no stored entry' is checked BEFORE the description-first
    rule, so an unset description-first key is `new`, not `conflict`."""
    proposed = {"value": 680, "unit": "mm"}

    kind = classify_spec_proposal(proposed, None, {}, "dim_length")

    assert kind == "new"


# --------------------------------------------------------------------------- #
# regression - extract_spec_proposals (PR 4) keeps its own present behaviour
# byte-for-byte once classify_spec_proposal is lifted out of it (AC-A.3)
# --------------------------------------------------------------------------- #
def test_extract_spec_proposals_still_reads_a_tombstone_as_conflict_never_suppressed(db):
    """`extract_spec_proposals`'s callers never see the new `suppressed` kind - it
    is vocabulary this slice introduces only for the STORED flyer batch."""
    product = _product(db, "ZZT-FLYCLS-TOMB", "SORENTO ONE PIECE WC ZZT-FLYCLS-TOMB")
    db.commit()
    derive_for_code(db, "ZZT-FLYCLS-TOMB", commit=True)

    from app.services.product_spec_write import apply_spec_values

    apply_spec_values(
        db,
        "ZZT-FLYCLS-TOMB",
        [{"spec_key": "seat_material", "op": "absent", "source": "human"}],
        actor={"id": str(uuid.uuid4()), "email": "zzt-flycls@test.com"},
    )

    result = extract_spec_proposals(db, product, "*PP Seat Cover")

    by_key = {p["spec_key"]: p for p in result["proposals"]}
    assert by_key["seat_material"]["kind"] == "conflict"


def test_extract_spec_proposals_still_drops_an_unchanged_key_from_its_output(db):
    product = _product(
        db, "ZZT-FLYCLS-UNCH", "SORENTO ONE PIECE WC (700X400X800MM) ZZT-FLYCLS-UNCH"
    )
    db.commit()
    derive_for_code(db, "ZZT-FLYCLS-UNCH", commit=True)

    stored = (
        db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id == product.id)
        .first()
    )
    assert stored.values["dim_height"]["value"] == 800

    result = extract_spec_proposals(db, product, "Washdown. H800mm")

    by_key = {p["spec_key"]: p for p in result["proposals"]}
    assert "dim_height" not in by_key
    assert result["unchanged"] >= 1
