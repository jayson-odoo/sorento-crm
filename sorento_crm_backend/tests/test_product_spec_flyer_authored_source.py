"""AC-C.7 - `flyer` joins `AUTHORED_SOURCES`, and what that must mean everywhere
it is read.

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` section 3.5.
UAC: `flyer-spec-ingestion-acceptance-criteria.md` AC-C.7 (parent contract
AC-F.7, `spec-authoring-verification-acceptance-criteria.md`).

Written against the REAL module, unpatched - this is the behaviour the flip
must produce, not a future-proofing monkeypatch (that already exists, and
stays green either way: `tests/test_product_spec_search_boost.py::
test_flyer_keeps_its_own_knob_if_it_later_joins_authored_sources`). Today
`AUTHORED_SOURCES == frozenset({"human", "supplier"})`
(`app/services/product_spec_write.py:48`), so every assertion below either
raises where it must not, or fails to raise where it must - that IS the
expected red state; nothing here is an ImportError.

**Known conflict, listed per the tester brief rather than fixed here (the
coder updates it with the reason):**

  * `tests/test_product_spec_write.py::test_authored_sources_contains_human_and_supplier`
    (line 35) asserts `AUTHORED_SOURCES == frozenset({"human", "supplier"})` -
    this slice's flip breaks that assertion on purpose.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_write import (
    AUTHORED_SOURCES,
    _is_authored,
    _prepare,
    _status_for,
    authored_keys,
    merge_authored_over,
)
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-FLYSRC-KS", category_name="ZZT-FLYSRC-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-FLYSRC-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-FLYSRC-SRT", brand_name="Sorento")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        yield s


def test_authored_sources_is_human_supplier_and_flyer():
    assert AUTHORED_SOURCES == frozenset({"human", "supplier", "flyer"})


def test_prepare_accepts_source_flyer():
    entry = _prepare(
        {"spec_key": "material", "op": "set", "value": "brass", "source": "flyer", "evidence": "BRASS"},
        actor=None,
    )
    assert entry["source"] == "flyer"


def test_is_authored_treats_a_flyer_entry_as_authored():
    assert _is_authored({"source": "flyer", "value": "brass"}) is True


def test_authored_keys_includes_a_flyer_sourced_key():
    provenance = {
        "material": {"source": "flyer"},
        "finish": {"source": "derived"},
    }
    assert authored_keys(provenance) == {"material"}


def test_status_for_reads_a_flyer_only_provenance_as_authored():
    provenance = {"material": {"source": "flyer"}}
    assert _status_for(provenance, has_exceptions=False) == "authored"


def test_merge_authored_over_keeps_the_flyer_value_and_raises_a_conflict_when_derivation_disagrees():
    """Same mechanics as a `human` value: the flyer's accepted value survives a
    re-derivation that disagrees with it, and the disagreement is raised once as
    `human_override_conflict` rather than applied."""
    derived_values = {"material": {"value": "ceramic"}}
    derived_provenance = {"material": {"source": "derived"}}
    existing_values = {"material": {"value": "brass"}}
    existing_provenance = {"material": {"source": "flyer", "evidence": "flyer x.pdf: BRASS"}}

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert values["material"] == {"value": "brass"}
    assert provenance["material"]["source"] == "flyer"
    assert len(conflicts) == 1
    assert conflicts[0]["spec_key"] == "material"
    assert conflicts[0]["reason"] == "human_override_conflict"


def _product(db, code: str, description: str = "SORENTO ONE PIECE WC") -> Product:
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


def test_apply_spec_values_writes_a_flyer_sourced_entry_as_authored(db):
    from app.services.product_spec_write import apply_spec_values

    product = _product(db, "ZZT-FLYSRC-APPLY1")
    db.commit()

    apply_spec_values(
        db,
        "ZZT-FLYSRC-APPLY1",
        [
            {
                "spec_key": "material",
                "op": "set",
                "value": "brass",
                "source": "flyer",
                "evidence": "flyer ZZT.pdf: BRASS",
            }
        ],
        actor={"id": str(uuid.uuid4()), "email": "zzt-flysrc@test.com"},
    )

    spec = (
        db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id == product.id)
        .first()
    )
    assert spec.values["material"]["value"] == "brass"
    assert spec.provenance["material"]["source"] == "flyer"
    assert spec.status == "authored"
