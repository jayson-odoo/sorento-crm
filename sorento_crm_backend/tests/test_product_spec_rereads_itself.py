"""S2 - a product re-reads its own specs whenever it changes, with no button pressed
(#1286, D9, D10). UAC AC-S2.9.

Reuses the pattern `tests/test_product_spec_change_listener.py` established: the
listener's inline re-derive opens its OWN fresh `SessionLocal()`, which cannot see a
`blank_session()` scratch schema. So `_rederive_inline` is monkeypatched here to run
`derive_for_code` against the SAME test session instead of a real one - the reliable
substitute the tester brief names, and the one that lets "the stored values changed
after that edit alone" be asserted directly rather than against real DB rows that would
have to be committed and cleaned up by hand.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db(monkeypatch):
    with blank_session() as s:
        import app.services.product_spec_change_listener as listener

        listener.register_product_spec_listeners()

        # `_rederive_inline` normally opens a brand new `SessionLocal()`, which cannot
        # see this scratch schema. It cannot simply be swapped for "run derive_for_code
        # on this same session right here" either: it runs from INSIDE the session's own
        # `after_commit` dispatch, and SQLAlchemy refuses to emit new SQL on a session
        # while it is still finishing that commit ("session is in 'committed' state").
        # So it is recorded here and drained by the test AFTER `db.commit()` returns,
        # which is exactly what a real post-commit worker pass does one tick later.
        pending: list[set[str]] = []
        monkeypatch.setattr(listener, "_rederive_inline", lambda codes: pending.append(set(codes)))
        s.info["pending_rederive"] = pending

        cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT"), category_name="cat")
        other_cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT2"), category_name="cat2")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM"), uom_name="uom")
        s.add_all([cat, other_cat, uom])
        s.flush()
        seed_spec_registry(s)
        s.info["refs"] = {"cat": cat.id, "other_cat": other_cat.id, "uom": uom.id}
        yield s


def _seed_product(db, description: str) -> Product:
    refs = db.info["refs"]
    code = unique_code("REREAD")
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=refs["cat"],
        base_uom_id=refs["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.commit()  # fires the after_insert listener, deriving the product's first specs
    _drain_rederive(db)
    return product


def _values_for(db, product_id: str) -> dict:
    spec = db.query(ProductSpecifications).filter_by(product_id=product_id).first()
    return dict(spec.values or {}) if spec else {}


def _drain_rederive(db) -> None:
    """Run whatever `_rederive_inline` was asked to do, one tick after the commit
    that queued it - see the fixture's comment on why this cannot happen inline."""
    from app.services.product_spec_derivation import derive_for_code

    pending = db.info.get("pending_rederive") or []
    while pending:
        for code in pending.pop(0):
            derive_for_code(db, code)


def test_ac_s2_9_editing_the_description_rereads_the_specs(db):
    product = _seed_product(db, "PLAIN STEEL BASIN")
    before = _values_for(db, product.id)
    assert before.get("material", {}).get("value") != "ceramic"

    product.description = "GLOSSY CERAMIC BASIN"
    db.commit()
    _drain_rederive(db)

    after = _values_for(db, product.id)
    assert after.get("material", {}).get("value") == "ceramic", (
        "editing the description alone must re-read the stored specs with no button pressed"
    )


def test_ac_s2_9_editing_the_product_code_rereads_the_specs(db):
    product = _seed_product(db, "STAINLESS STEEL BASIN")
    old_values = _values_for(db, product.id)
    assert old_values.get("material", {}).get("value") == "stainless_steel"

    new_code = unique_code("REREADCODE")
    product.product_code = new_code
    db.commit()
    _drain_rederive(db)

    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
    assert spec is not None and (spec.values or {}).get("material", {}).get("value") == "stainless_steel", (
        "a product_code change must re-derive rather than leave the old row untouched"
    )


def test_ac_s2_9_editing_the_category_rereads_the_specs(db):
    """`class` is read off the category as a weak signal when nothing else names it."""
    product = _seed_product(db, "NO RECOGNISABLE WORDS HERE AT ALL")
    refs = db.info["refs"]

    from app.models.product import ProductCategory as CategoryModel

    other = db.query(CategoryModel).filter_by(id=refs["other_cat"]).first()
    other.class_label = "Bathroom Furniture"
    db.flush()

    product.category_id = refs["other_cat"]
    db.commit()
    _drain_rederive(db)

    after = _values_for(db, product.id)
    assert after.get("class", {}).get("value") == "Bathroom Furniture", (
        "changing the category alone must re-read class off the new category"
    )


def test_ac_s2_9_editing_a_dimension_column_rereads_the_specs(db):
    product = _seed_product(db, "RECTANGULAR STEEL SINK")
    before = _values_for(db, product.id)
    assert before.get("dim_length") is None

    product.dimensions_length = Decimal("500.00")
    product.dimensions_width = Decimal("400.00")
    db.commit()
    _drain_rederive(db)

    after = _values_for(db, product.id)
    assert after.get("dim_length", {}).get("value") == 500, (
        "changing a dimension column alone must re-read the stored specs"
    )


def test_ac_s2_9_adopting_a_flyer_code_to_a_product_rereads_its_specs(db, monkeypatch):
    """The flyer is no longer a derivation input on its own
    (`product_spec_derivation.py`'s own comment: "THE FLYER IS NO LONGER AN INPUT"), so
    a save that newly ties a flyer reading to a product's code must itself call
    `rederive_codes` for that code - D9's "S2 starts by checking whether a new flyer
    reading re-reads the product the same way; if it does not, the flyer save calls
    rederive_codes for that one code."

    `adopt_code` (`app.services.dealer_kit.flyer_reading_service`) is the save that
    ties a printed code on a reading to a specific product - the point at which a
    flyer's content becomes "this product's flyer card" for the first time. Whichever
    module ends up calling it, the call must reach the shared
    `product_spec_change_listener.rederive_codes` so the same inline/worker split
    applies elsewhere. Patched there and asserted on, rather than driving the OCR
    extraction end to end.

    CONTRACT AMBIGUITY (flagged to the captain): neither the plan nor the contract
    names the exact save point ("a new flyer reading" could mean the raw OCR
    completion in `complete_reading`, or the point a code is tied to a product in
    `adopt_code`/`match_reading`). This test pins `adopt_code` as the most literal
    reading of D9 ("saving a new flyer reading FOR IT" - i.e. for the product); if the
    coder and captain settle on a different save point, this test's target function
    changes but its shape (assert `rederive_codes` was called with the product's code)
    should not.
    """
    import app.services.product_spec_change_listener as listener
    from app.services.dealer_kit import flyer_reading_service
    from app.services.dealer_kit.flyer_reading_service import ReadingStatus
    from app.models.dealer_kit import FlyerReadingRecord

    product = _seed_product(db, "PLAIN STEEL BASIN")

    record = FlyerReadingRecord(
        id=str(uuid.uuid4()),
        filename=unique_code("FLYER") + ".pdf",
        byte_size=1,
        sha256=uuid.uuid4().hex,
        status=ReadingStatus.DONE,
        reading_json=flyer_reading_service.empty_reading_json(),
    )
    db.add(record)
    db.commit()
    _drain_rederive(db)

    calls: list[set[str]] = []
    monkeypatch.setattr(listener, "rederive_codes", lambda codes: calls.append(set(codes)))
    monkeypatch.setattr(
        flyer_reading_service,
        "match_reading",
        lambda db, reading, overrides=None: type(
            "Report", (), {"matched": [], "unmatched": [
                type("Entry", (), {"code": "PRINTED-CODE", "pages": (1,)})()
            ]}
        )(),
    )

    flyer_reading_service.adopt_code(
        db, record, printed_code="PRINTED-CODE", product_id=product.id
    )

    assert any(product.product_code in codes for codes in calls), (
        "tying a flyer reading to this product's code must re-read its specifications"
    )
