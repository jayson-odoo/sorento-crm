"""Pin for AC-D.17b (PR 3, UAC group D, task item 3 of the tester brief).

AC-D.17b: "GIVEN a key a user has answered WHEN the underlying data later changes so
the rules disagree with the authored value THEN the disagreement surfaces as
`human_override_conflict` (D8, AC-F.5), not as the original flag. An answered
question does not re-ask itself; a new question gets asked once."

Checked before writing this file (both greps ran clean against the intent below):

  * `tests/test_product_spec_authored_write.py::
    test_authoring_the_flagged_key_suppresses_its_exception_and_reverting_brings_it_back`
    pins AC-D.17 (answering a flagged key suppresses it; reverting brings the flag
    back) but never changes the underlying data after answering, so it never
    exercises AC-D.17b's disagreement case.
  * `human_override_conflict` otherwise appears only in `tests/test_product_spec_write.py`
    (unit-level `merge_authored_over` tests with no flagged key involved) and in
    `tests/test_product_spec_authored_write.py::
    test_a_conflicting_authored_write_surfaces_its_exception_in_the_same_call` (a
    plain authored conflict on a key that was never flagged in the first place).

Neither exercises, end to end through `derive_for_code`, "author a key that WAS
flagged, then change the input so derivation disagrees with the answer". This file
adds that combination.

Per the tester brief: PR 1 already shipped both halves this test needs - the
answered-key filter at `product_spec_derivation.py:1313` (`exceptions = [f for f in
result.exceptions if f["spec_key"] not in answered]`) and the independent
conflict-raising in `merge_authored_over` (`product_spec_write.py`), which is never
subject to that filter. So this test is expected to go GREEN immediately - it pins
EXISTING PR-1 behaviour, nothing PR 3 needs to build.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecException
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_write import apply_spec_values
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


def _fixtures(db):
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-EA-KS", category_name="ZZT-EA-KS")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-EA-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-EA-SRT", brand_name="Sorento")
    db.add_all([cat, uom, brand])
    db.flush()
    backfill_category_signals(db)
    _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})


def _product(
    db,
    code: str,
    description: str,
    *,
    length: Decimal | None = None,
    width: Decimal | None = None,
    height: Decimal | None = None,
) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
        dimensions_length=length,
        dimensions_width=width,
        dimensions_height=height,
    )
    db.add(row)
    db.flush()
    return row


def _open_exceptions(db, code: str) -> set[tuple[str, str]]:
    rows = (
        db.query(ProductSpecException)
        .filter(
            ProductSpecException.product_code == code,
            ProductSpecException.resolved_at.is_(None),
        )
        .all()
    )
    return {(r.spec_key, r.reason) for r in rows}


_ACTOR = {"email": "answered-pin@zzt.test"}


def test_an_answered_flagged_key_surfaces_a_conflict_instead_of_its_original_flag_when_the_data_later_disagrees(
    db,
):
    """AC-D.17b. Setup mirrors test_product_spec_authored_write.py's own shape pin:
    length == width with no round/square word in the description flags
    `shape`/`shape_mismatch` (the "1500x1500" fingerprint of a round/square product
    forced into rectangular columns). Authoring `shape` suppresses it (AC-D.17,
    already pinned elsewhere). THEN the description changes to state a shape the
    rules can read directly ("ROUND"), disagreeing with what the user set - and that
    disagreement must come back as `shape`/`human_override_conflict`, never again as
    `shape`/`shape_mismatch`."""
    product = _product(
        db,
        "ZZT-EA-SHAPE-1",
        "SORENTO ART BASIN",
        length=Decimal("1500"),
        width=Decimal("1500"),
        height=Decimal("140"),
    )
    derive_for_code(db, "ZZT-EA-SHAPE-1")
    assert ("shape", "shape_mismatch") in _open_exceptions(db, "ZZT-EA-SHAPE-1")

    apply_spec_values(
        db,
        "ZZT-EA-SHAPE-1",
        [{"spec_key": "shape", "op": "set", "value": "square"}],
        actor=_ACTOR,
    )
    assert ("shape", "shape_mismatch") not in _open_exceptions(db, "ZZT-EA-SHAPE-1"), (
        "answering shape by hand must suppress its own flag (AC-D.17)"
    )

    # The underlying data changes: the description now states a shape directly, and
    # it disagrees with what the user answered.
    product.description = "SORENTO ROUND ART BASIN"
    db.flush()
    derive_for_code(db, "ZZT-EA-SHAPE-1")

    reasons = _open_exceptions(db, "ZZT-EA-SHAPE-1")
    assert ("shape", "shape_mismatch") not in reasons, (
        "the answered key's ORIGINAL flag must never come back - an answered "
        "question does not re-ask itself"
    )
    assert ("shape", "human_override_conflict") in reasons, (
        "a later disagreement with the authored value must surface as a fresh, "
        "distinct conflict (AC-D.17b, AC-F.5)"
    )


def test_a_never_before_flagged_key_still_gets_asked_once_when_authored_and_derivation_disagree(db):
    """The other half of AC-D.17b's sentence - "a new question gets asked once" -
    restated here for a key that was never flagged in the first place, so both
    halves of AC-D.17b are pinned together in one file."""
    product = _product(db, "ZZT-EA-NEWKEY-1", "SORENTO CERAMIC KITCHEN SINK")
    derive_for_code(db, "ZZT-EA-NEWKEY-1")
    assert _open_exceptions(db, "ZZT-EA-NEWKEY-1") == set()

    apply_spec_values(
        db,
        "ZZT-EA-NEWKEY-1",
        [{"spec_key": "material", "op": "set", "value": "brass"}],
        actor=_ACTOR,
    )

    assert _open_exceptions(db, "ZZT-EA-NEWKEY-1") == {("material", "human_override_conflict")}
