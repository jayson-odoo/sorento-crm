"""Migration `367_promote_flyer_provenance` - re-stamp every `source='flyer'`
provenance entry as `source='human'` + `migrated_from='flyer'`, idempotent and
mismatch-based, `values` untouched (AC-B.10, AC-B.16).

PR 4 contract: `documentation/plans/master-data/PLAN-spec-authoring-verification.md`
("PR 4 implementation contract"). `alembic/versions/367_promote_flyer_provenance.py`
does not exist yet, so `_load_migration()` raises at the first test that calls it -
that IS the expected red state.

Harness (`_load_migration` + `MigrationContext` + `Operations.context`) copied from
tests/test_migration_359_um_contacts_reference_perms.py, itself copied from
tests/test_migration_311_pr_approve_grants.py. Everything runs against a blank
Postgres schema (`blank_session`) inside a transaction that is rolled back; every
row is seeded by this file with a `ZZT-PROMOTE` marker prefix, never borrowed from
the live database (CI's is empty).

`test_merge_authored_over_keeps_a_promoted_value_against_a_differing_derived_value`
is the AC-B.16 pin the tester brief asks for explicitly - it exercises
`merge_authored_over` alone, needs no migration file at all, and is expected to PASS
today: `migrated_from` is inert extra metadata on an authored entry, and
`merge_authored_over`'s rule ("a person's value outranks derivation") keys off
`AUTHORED_SOURCES` membership alone.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import uuid
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_write import merge_authored_over
from tests._pg_fixture import blank_session

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "367_promote_flyer_provenance.py"
)

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-PROMOTE-KS", category_name="ZZT-PROMOTE-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PROMOTE-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-PROMOTE-SRT", brand_name="Sorento")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        yield s


def _product(db, code: str) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="SORENTO CERAMIC KITCHEN SINK",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    return row


def _spec_row(db, product, *, values: dict, provenance: dict, status: str) -> ProductSpecifications:
    row = ProductSpecifications(
        id=str(uuid.uuid4()),
        product_id=product.id,
        values=values,
        provenance=provenance,
        status=status,
        rendered_text="",
    )
    db.add(row)
    db.flush()
    return row


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_367", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()


def _run_downgrade(db) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.downgrade()


def _snapshot(db, product_id: str) -> tuple[dict, dict, str]:
    db.expire_all()
    row = db.query(ProductSpecifications).filter_by(product_id=product_id).first()
    return dict(row.values), dict(row.provenance), row.status


def _values_checksum(values: dict) -> str:
    return hashlib.md5(json.dumps(values, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# the four seeded shapes
# --------------------------------------------------------------------------- #
@pytest.fixture
def seeded(db):
    """(a) two flyer entries + one derived, status derived
    (b) only derived entries, status derived - the migration's WHERE clause excludes it
    (c) half-promoted: one already migrated_from='flyer', one still source='flyer'
    (d) status needs_review, one flyer entry
    """
    product_a = _product(db, "ZZT-PROMOTE-A")
    spec_a = _spec_row(
        db,
        product_a,
        values={"finish": {"value": "chrome"}, "material": {"value": "brass"}, "class": {"value": "Tap"}},
        provenance={
            "finish": {"source": "flyer", "confidence": 1.0, "evidence": "CHROME"},
            "material": {"source": "flyer", "confidence": 1.0, "evidence": "BRASS"},
            "class": {"source": "derived", "confidence": 1.0, "evidence": "TAP"},
        },
        status="derived",
    )

    product_b = _product(db, "ZZT-PROMOTE-B")
    spec_b = _spec_row(
        db,
        product_b,
        values={"class": {"value": "Tap"}, "material": {"value": "ceramic"}},
        provenance={
            "class": {"source": "derived", "confidence": 1.0, "evidence": "TAP"},
            "material": {"source": "derived", "confidence": 1.0, "evidence": "CERAMIC"},
        },
        status="derived",
    )

    product_c = _product(db, "ZZT-PROMOTE-C")
    spec_c = _spec_row(
        db,
        product_c,
        values={"finish": {"value": "chrome"}, "material": {"value": "brass"}},
        provenance={
            "finish": {
                "source": "human",
                "confidence": 1.0,
                "evidence": "flyer: CHROME",
                "migrated_from": "flyer",
            },
            "material": {"source": "flyer", "confidence": 1.0, "evidence": "BRASS"},
        },
        # Simulates a crashed prior run: provenance partially promoted, status not
        # yet repaired to match.
        status="derived",
    )

    product_d = _product(db, "ZZT-PROMOTE-D")
    spec_d = _spec_row(
        db,
        product_d,
        values={"seat_material": {"value": "pp"}},
        provenance={"seat_material": {"source": "flyer", "confidence": 1.0, "evidence": "PP SEAT"}},
        status="needs_review",
    )

    db.commit()
    return {
        "a": (product_a, spec_a),
        "b": (product_b, spec_b),
        "c": (product_c, spec_c),
        "d": (product_d, spec_d),
    }


# --------------------------------------------------------------------------- #
# upgrade
# --------------------------------------------------------------------------- #
def test_upgrade_promotes_every_flyer_entry_and_leaves_others_byte_identical(db, seeded):
    product_a, _ = seeded["a"]
    before_values, before_provenance, before_status = _snapshot(db, product_a.id)
    checksum_before = _values_checksum(before_values)

    _run_upgrade(db)

    values, provenance, status = _snapshot(db, product_a.id)
    assert values == before_values, "values must be byte-identical - only provenance moves"
    assert _values_checksum(values) == checksum_before

    assert provenance["finish"] == {
        "source": "human",
        "confidence": 1.0,
        "evidence": "flyer: CHROME",
        "migrated_from": "flyer",
    }
    assert provenance["material"] == {
        "source": "human",
        "confidence": 1.0,
        "evidence": "flyer: BRASS",
        "migrated_from": "flyer",
    }
    # untouched: was never source='flyer'
    assert provenance["class"] == before_provenance["class"]
    assert status == "authored"


def test_upgrade_leaves_a_row_with_no_flyer_entries_completely_untouched(db, seeded):
    product_b, _ = seeded["b"]
    before_values, before_provenance, before_status = _snapshot(db, product_b.id)

    _run_upgrade(db)

    values, provenance, status = _snapshot(db, product_b.id)
    assert values == before_values
    assert provenance == before_provenance
    assert status == before_status == "derived"


def test_upgrade_completes_a_half_promoted_row(db, seeded):
    product_c, _ = seeded["c"]

    _run_upgrade(db)

    values, provenance, status = _snapshot(db, product_c.id)
    # already promoted - byte-identical, not re-wrapped
    assert provenance["finish"] == {
        "source": "human",
        "confidence": 1.0,
        "evidence": "flyer: CHROME",
        "migrated_from": "flyer",
    }
    # completed
    assert provenance["material"] == {
        "source": "human",
        "confidence": 1.0,
        "evidence": "flyer: BRASS",
        "migrated_from": "flyer",
    }
    assert status == "authored"


def test_upgrade_leaves_a_needs_review_row_needs_review(db, seeded):
    product_d, _ = seeded["d"]

    _run_upgrade(db)

    values, provenance, status = _snapshot(db, product_d.id)
    assert provenance["seat_material"] == {
        "source": "human",
        "confidence": 1.0,
        "evidence": "flyer: PP SEAT",
        "migrated_from": "flyer",
    }
    assert status == "needs_review"


def test_a_second_upgrade_changes_nothing(db, seeded):
    _run_upgrade(db)

    snapshots_after_first = {
        key: _snapshot(db, product.id) for key, (product, _spec) in seeded.items()
    }

    _run_upgrade(db)

    snapshots_after_second = {
        key: _snapshot(db, product.id) for key, (product, _spec) in seeded.items()
    }

    assert snapshots_after_second == snapshots_after_first


# --------------------------------------------------------------------------- #
# `rendered_text` and `derived_hash` are declared untouched by the module docstring
# ("`values`, `rendered_text` and `derived_hash` are NOT touched") but the existing
# checksum assertions only ever compare `values` - `rendered_text`/`derived_hash` were
# never pinned at all, so a future edit to `_PROMOTE`/`_DEMOTE` that widened the
# `UPDATE ... SET` clause to touch either column would sail through every existing
# assertion in this file. Seeded with distinct, non-empty values here (rather than the
# `_spec_row` default `rendered_text=""` / unset `derived_hash`) so a regression that
# clears either column is actually visible rather than trivially "still empty".
# --------------------------------------------------------------------------- #
def test_upgrade_and_downgrade_leave_rendered_text_and_derived_hash_byte_identical(db):
    product = _product(db, "ZZT-PROMOTE-HASH")
    row = ProductSpecifications(
        id=str(uuid.uuid4()),
        product_id=product.id,
        values={"finish": {"value": "chrome"}},
        provenance={"finish": {"source": "flyer", "confidence": 1.0, "evidence": "CHROME"}},
        status="derived",
        rendered_text="Sorento. Chrome finish.",
        derived_hash="zzt-promote-hash-fixture-27",
    )
    db.add(row)
    db.commit()

    def _hash_snapshot() -> tuple[str, str]:
        db.expire_all()
        current = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
        return current.rendered_text, current.derived_hash

    before = _hash_snapshot()
    assert before == ("Sorento. Chrome finish.", "zzt-promote-hash-fixture-27")

    _run_upgrade(db)
    after_upgrade = _hash_snapshot()
    assert after_upgrade == before, "upgrade must not touch rendered_text or derived_hash"

    # Confirm the row really was promoted, or the assertion above is vacuous.
    db.expire_all()
    promoted = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
    assert promoted.provenance["finish"]["source"] == "human"
    assert promoted.status == "authored"

    _run_downgrade(db)
    after_downgrade = _hash_snapshot()
    assert after_downgrade == before, "downgrade must not touch rendered_text or derived_hash either"


# --------------------------------------------------------------------------- #
# downgrade
# --------------------------------------------------------------------------- #
def test_downgrade_restores_the_seeded_provenance_and_status_exactly(db, seeded):
    """Rows (a), (b) and (d) come back byte-identical.

    Row (c) - the hand-made HALF-promoted row - deliberately cannot, and asking it to
    would be asking for a downgrade that cannot exist. `migrated_from='flyer'` is the
    only marker either the upgrade or an earlier crashed run leaves behind, so nothing
    in the data distinguishes "this entry was promoted a moment ago" from "this entry
    was promoted by the run that died last week". The downgrade therefore demotes both,
    which is the state the promotion was completing anyway, and is what the next test
    pins.
    """
    keys = ("a", "b", "d")
    before = {key: _snapshot(db, seeded[key][0].id) for key in keys}

    _run_upgrade(db)
    _run_downgrade(db)

    after = {key: _snapshot(db, seeded[key][0].id) for key in keys}

    assert after == before


def test_downgrade_demotes_a_half_promoted_row_completely(db, seeded):
    product_c, _ = seeded["c"]

    _run_upgrade(db)
    _run_downgrade(db)

    values, provenance, status = _snapshot(db, product_c.id)
    assert provenance["finish"] == {
        "source": "flyer",
        "confidence": 1.0,
        "evidence": "CHROME",
    }
    assert provenance["material"] == {
        "source": "flyer",
        "confidence": 1.0,
        "evidence": "BRASS",
    }
    assert status == "derived"


# --------------------------------------------------------------------------- #
# AC-B.16 pin - already passes today, kept as evidence the promotion mechanic works
# with the existing merge rule and needs no special-casing for migrated_from
# --------------------------------------------------------------------------- #
def test_merge_authored_over_keeps_a_promoted_value_against_a_differing_derived_value():
    derived_values = {"finish": {"value": "chrome"}}
    derived_provenance = {"finish": {"source": "derived", "confidence": 1.0, "evidence": "CHROME"}}
    existing_values = {"finish": {"value": "matt black"}}
    existing_provenance = {
        "finish": {
            "source": "human",
            "confidence": 1.5,
            "evidence": "flyer: MATT BLACK",
            "migrated_from": "flyer",
        }
    }

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert values["finish"] == {"value": "matt black"}
    assert provenance["finish"]["migrated_from"] == "flyer"
    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == "human_override_conflict"
    assert conflicts[0]["spec_key"] == "finish"


# --------------------------------------------------------------------------- #
# single alembic head after both new migrations exist
# --------------------------------------------------------------------------- #
def test_there_is_one_alembic_head_and_367_is_on_its_path():
    """One head, and this revision is an ancestor of it.

    It used to assert the head IS 367, which was true for exactly as long as 367 was
    the newest migration - the bulk flyer-ingestion slice chained 370 onto it and the
    assertion failed for the one reason that is not a defect. The invariant worth
    guarding is that the branches never split, not which revision happens to be last,
    so it is written that way now.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script_dir = ScriptDirectory.from_config(cfg)

    # `get_heads()` returns a LIST, so the tuple this was first written against could
    # never have matched, single head or not.
    heads = list(script_dir.get_heads())
    assert len(heads) == 1, heads

    ancestry = {rev.revision for rev in script_dir.walk_revisions(base="base", head=heads[0])}
    assert "367_promote_flyer_provenance" in ancestry
