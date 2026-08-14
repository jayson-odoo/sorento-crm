"""AC-F.10 - the source-keyed boost branch, and AC-F.9 - the `human_source_boost` seed.

Contract: PR1-CONTRACT.md sections 3 and 4.

`search_specs` currently hardcodes `source == "flyer"` (app/services/product_spec_search.py
:620-621) and the ranker's policy seed carries no `human_source_boost` key
(app/services/product_spec_registry.py:101-onwards). Neither of those is touched by this
file - it only asserts the behaviour the contract requires once they are, so most tests
here are expected to fail on a real assertion (equal scores where a boost was expected),
not on an import error. The one exception is the migration test at the bottom, which
imports a revision file that does not exist yet and is expected to fail on that import.

Fixture shape follows `tests/test_product_spec_search.py`'s
`test_the_flyer_source_boost_lifts_only_flyer_sourced_specs` (compare a product against
itself at two policy settings, never against a different product).
"""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecSearchPolicy
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_search_policy, seed_spec_registry
from app.services.product_spec_search import search_specs
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-SB-KS", category_name="ZZT-SB-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-SB-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SB-SRT", brand_name="SORENTO")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        seed_search_policy(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        yield s


def _product(db, code: str, description: str = "SORENTO MIRROR") -> Product:
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


def _stamp_is_frameless(db, product: Product, source: str) -> None:
    """Hand-stamp a searchable spec with a chosen provenance source.

    Direct assignment (not through the write service) stays acceptable in tests per
    tests/test_product_spec_search.py:983-984.
    """
    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
    spec.values = {**(spec.values or {}), "is_frameless": {"value": True}}
    spec.provenance = {**(spec.provenance or {}), "is_frameless": {"source": source}}
    db.flush()


def _set_policy(db, key: str, value: float) -> None:
    db.query(ProductSpecSearchPolicy).filter_by(policy_key=key).update({"value": value})
    db.flush()


def _score(db, code: str) -> float:
    result = search_specs(db, specs=[{"key": "is_frameless", "value": True}], free_terms=[])
    return next(c["score"] for c in result["candidates"] if c["product_code"] == code)


# --------------------------------------------------------------------------- #
# AC-F.10 - both boost cases
# --------------------------------------------------------------------------- #
def test_a_flyer_sourced_entry_is_still_boosted_by_flyer_source_boost(db):
    """The pre-existing branch must survive the refactor to a source-keyed lookup."""
    product = _product(db, "ZZT-SB-FLYER-1")
    _stamp_is_frameless(db, product, "flyer")

    _set_policy(db, "flyer_source_boost", 1.0)
    at_one = _score(db, "ZZT-SB-FLYER-1")
    _set_policy(db, "flyer_source_boost", 3.0)
    at_three = _score(db, "ZZT-SB-FLYER-1")

    assert at_three > at_one


def test_a_human_sourced_entry_is_boosted_by_human_source_boost(db):
    product = _product(db, "ZZT-SB-HUMAN-1")
    _stamp_is_frameless(db, product, "human")

    _set_policy(db, "human_source_boost", 1.0)
    at_one = _score(db, "ZZT-SB-HUMAN-1")
    _set_policy(db, "human_source_boost", 3.0)
    at_three = _score(db, "ZZT-SB-HUMAN-1")

    assert at_three > at_one


def test_a_supplier_sourced_entry_is_boosted_by_human_source_boost_too(db):
    """M2-S1 - 'supplier' is in AUTHORED_SOURCES, so it shares the human knob."""
    product = _product(db, "ZZT-SB-SUPPLIER-1")
    _stamp_is_frameless(db, product, "supplier")

    _set_policy(db, "human_source_boost", 1.0)
    at_one = _score(db, "ZZT-SB-SUPPLIER-1")
    _set_policy(db, "human_source_boost", 3.0)
    at_three = _score(db, "ZZT-SB-SUPPLIER-1")

    assert at_three > at_one


def test_the_two_knobs_are_independently_tunable(db):
    flyer_product = _product(db, "ZZT-SB-INDEP-FLYER")
    _stamp_is_frameless(db, flyer_product, "flyer")
    human_product = _product(db, "ZZT-SB-INDEP-HUMAN")
    _stamp_is_frameless(db, human_product, "human")

    _set_policy(db, "flyer_source_boost", 1.0)
    _set_policy(db, "human_source_boost", 1.0)
    flyer_before = _score(db, "ZZT-SB-INDEP-FLYER")
    human_before = _score(db, "ZZT-SB-INDEP-HUMAN")

    _set_policy(db, "human_source_boost", 5.0)
    flyer_after = _score(db, "ZZT-SB-INDEP-FLYER")
    human_after = _score(db, "ZZT-SB-INDEP-HUMAN")

    assert flyer_after == flyer_before, "moving human_source_boost must not move the flyer weight"
    assert human_after > human_before


def test_a_derived_or_unknown_source_is_left_at_a_one_times_multiplier(db):
    derived_product = _product(db, "ZZT-SB-DERIVED-1")
    _stamp_is_frameless(db, derived_product, "derived")
    unknown_product = _product(db, "ZZT-SB-CATEGORY-1")
    _stamp_is_frameless(db, unknown_product, "category")

    _set_policy(db, "human_source_boost", 1.0)
    _set_policy(db, "flyer_source_boost", 1.0)
    derived_before = _score(db, "ZZT-SB-DERIVED-1")
    unknown_before = _score(db, "ZZT-SB-CATEGORY-1")

    _set_policy(db, "human_source_boost", 5.0)
    _set_policy(db, "flyer_source_boost", 5.0)
    derived_after = _score(db, "ZZT-SB-DERIVED-1")
    unknown_after = _score(db, "ZZT-SB-CATEGORY-1")

    assert derived_after == derived_before
    assert unknown_after == unknown_before


# --------------------------------------------------------------------------- #
# AC-F.9 - the seed, tested directly
# --------------------------------------------------------------------------- #
def test_the_seed_carries_human_source_boost_at_one_point_five():
    from app.services.product_spec_registry import SEARCH_POLICY_SEED

    entry = next(
        (e for e in SEARCH_POLICY_SEED if e["policy_key"] == "human_source_boost"), None
    )
    assert entry is not None, "human_source_boost is missing from SEARCH_POLICY_SEED"
    assert entry["value"] == 1.5, "D1 - must match flyer_source_boost so the flyer migration is ranking-neutral"


def test_seeding_creates_the_human_source_boost_row(db):
    row = db.query(ProductSpecSearchPolicy).filter_by(policy_key="human_source_boost").first()
    assert row is not None
    assert float(row.value) == 1.5


# --------------------------------------------------------------------------- #
# AC-F.9 - the migration, run rather than assumed present on a live row
# --------------------------------------------------------------------------- #
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "356_human_source_boost_seed.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m356_human_source_boost_seed", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()
    return module


@pytest.fixture
def blank_db():
    """A schema with NO search policy rows at all - the migration's own precondition,
    not the seed function's (this file's `db` fixture already calls
    seed_search_policy(), which is deliberately NOT the thing under test here)."""
    with blank_session() as s:
        yield s


def test_the_migration_inserts_the_row_idempotently(blank_db):
    """AC-F.9 - CLAUDE.md: where the thing under test IS seed/migration wiring, import
    the migration and run its upgrade() inside a rolled-back transaction rather than
    asserting a production row. The revision file does not exist yet; loading it is
    expected to fail red until it is written (down_revision = 885010d94677, PR1-
    CONTRACT.md section 4).
    """
    assert (
        blank_db.query(ProductSpecSearchPolicy).filter_by(policy_key="human_source_boost").first()
        is None
    )

    _run_upgrade(blank_db)

    row = blank_db.query(ProductSpecSearchPolicy).filter_by(policy_key="human_source_boost").one()
    assert float(row.value) == 1.5

    _run_upgrade(blank_db)  # a second run must be a no-op, not a duplicate row
    count = (
        blank_db.query(ProductSpecSearchPolicy)
        .filter_by(policy_key="human_source_boost")
        .count()
    )
    assert count == 1
