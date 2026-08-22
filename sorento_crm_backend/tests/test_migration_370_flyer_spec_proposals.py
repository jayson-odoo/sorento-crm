"""Migration `370_flyer_spec_proposals` - the two batch tables, run rather than read.

Every other test of the flyer batch builds its schema from `Base.metadata.create_all`,
so a drift between the model and this migration's DDL - the UNIQUE on
`flyer_reading_id` that `start_batch`'s insert race turns into a 409, the CHECKs on
`kind` and `origin`, the `origin` backfill a database holding the earlier shape of
the table needs - would ship green. This file drops the two tables the scratch
schema already carries, runs `upgrade()` against the empty schema, and asserts what
the tables then DO: which inserts they refuse, what they default, what a second
run leaves alone, and what `downgrade()` takes away.

Harness (`_load_migration` + `MigrationContext` + `Operations.context`) copied from
tests/test_migration_367_promote_flyer_provenance.py. Everything runs against a
blank Postgres schema (`blank_session`) inside a transaction that is rolled back;
every row is seeded here with a `ZZT-M370` marker, never borrowed (CI's database is
empty).

The one row this file writes OUTSIDE the scratch schema is the flyer reading. The
migration names `dealer_kit.flyer_reading` schema-qualified (a cross-schema key), so
the FK it creates points at the live table wherever the migration runs, and a batch
row needs a reading there to point at. It is written inside the same rolled-back
transaction as everything else, so nothing survives the test.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import blank_session

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "370_flyer_spec_proposals.py"
)

_BATCHES = "product_spec_flyer_batches"
_PROPOSALS = "product_spec_flyer_proposals"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_370", _MIGRATION)
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


@pytest.fixture
def db():
    """The scratch schema WITHOUT the two tables, plus one product and one reading."""
    with blank_session() as s:
        s.execute(sa.text(f"DROP TABLE IF EXISTS {_PROPOSALS}"))
        s.execute(sa.text(f"DROP TABLE IF EXISTS {_BATCHES}"))

        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-M370-KS", category_name="ZZT-M370-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-M370-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-M370-SRT", brand_name="Sorento")
        s.add_all([cat, uom, brand])
        s.flush()
        product = Product(
            id=str(uuid.uuid4()),
            product_code="ZZT-M370-P1",
            product_name="ZZT-M370-P1",
            description="SORENTO ONE PIECE WC",
            category_id=cat.id,
            base_uom_id=uom.id,
            brand_id=brand.id,
            list_price=Decimal("1.00"),
        )
        s.add(product)
        s.flush()

        reading_id = str(uuid.uuid4())
        s.execute(
            sa.text(
                "INSERT INTO dealer_kit.flyer_reading (id, filename, byte_size, reading_json) "
                "VALUES (:id, 'ZZT-M370.pdf', 1, '{}'::jsonb)"
            ),
            {"id": reading_id},
        )
        s.info["product_id"] = product.id
        s.info["reading_id"] = reading_id
        yield s


def _table_exists(db, table: str) -> bool:
    return db.execute(sa.text(f"SELECT to_regclass('{table}') IS NOT NULL")).scalar()


def _insert_batch(db, reading_id: str) -> str:
    batch_id = str(uuid.uuid4())
    db.execute(
        sa.text(f"INSERT INTO {_BATCHES} (id, flyer_reading_id) VALUES (:id, :reading)"),
        {"id": batch_id, "reading": reading_id},
    )
    return batch_id


def _insert_proposal(db, batch_id: str, product_id: str, *, spec_key: str, kind: str = "new", **columns) -> str:
    row_id = str(uuid.uuid4())
    names = ["id", "batch_id", "product_id", "product_code", "spec_key", "value", "kind", *columns]
    params = {
        "id": row_id,
        "batch_id": batch_id,
        "product_id": product_id,
        "product_code": "ZZT-M370-P1",
        "spec_key": spec_key,
        "value": '"s_trap"',
        "kind": kind,
        **columns,
    }
    placeholders = ", ".join(f"CAST(:{name} AS jsonb)" if name == "value" else f":{name}" for name in names)
    db.execute(
        sa.text(f"INSERT INTO {_PROPOSALS} ({', '.join(names)}) VALUES ({placeholders})"),
        params,
    )
    return row_id


def _refused(db, statement: str, params: dict) -> bool:
    """True when Postgres refuses the statement, the transaction left usable."""
    try:
        with db.begin_nested():
            db.execute(sa.text(statement), params)
    except IntegrityError:
        return True
    return False


# --------------------------------------------------------------------------- #
# upgrade from nothing
# --------------------------------------------------------------------------- #
def test_upgrade_builds_both_tables_and_one_batch_per_reading_is_enforced(db):
    assert not _table_exists(db, _BATCHES)
    assert not _table_exists(db, _PROPOSALS)

    _run_upgrade(db)

    reading_id = db.info["reading_id"]
    assert _refused(
        db,
        f"INSERT INTO {_BATCHES} (id, flyer_reading_id, status) VALUES (:id, :reading, 'bogus')",
        {"id": str(uuid.uuid4()), "reading": reading_id},
    ), "the status CHECK"

    _insert_batch(db, reading_id)

    # The insert race `start_batch` converts to 409: a second batch on the same
    # reading is what the UNIQUE refuses.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_batch(db, reading_id)

    status, *counts = db.execute(
        sa.text(
            f"SELECT status, product_count, proposal_count, new_count, change_count, "
            f"conflict_count, unchanged_count, suppressed_count, applied_count "
            f"FROM {_BATCHES} WHERE flyer_reading_id = :reading"
        ),
        {"reading": reading_id},
    ).one()
    assert status == "proposing", "a batch starts proposing"
    assert counts == [0] * 8

    assert _refused(
        db,
        f"INSERT INTO {_BATCHES} (id, flyer_reading_id) VALUES (:id, :reading)",
        {"id": str(uuid.uuid4()), "reading": str(uuid.uuid4())},
    ), "the FK onto dealer_kit.flyer_reading"


def test_upgrade_proposals_default_origin_flyer_and_refuse_bad_kind_origin_and_duplicates(db):
    _run_upgrade(db)
    batch_id = _insert_batch(db, db.info["reading_id"])
    product_id = db.info["product_id"]

    row_id = _insert_proposal(db, batch_id, product_id, spec_key="trap_type")

    origin, edited_at, edited_by, pages, evidence = db.execute(
        sa.text(f"SELECT origin, edited_at, edited_by, pages, evidence FROM {_PROPOSALS} WHERE id = :id"),
        {"id": row_id},
    ).one()
    assert origin == "flyer", "a row nobody said anything about came off the paper"
    assert (edited_at, edited_by) == (None, None)
    assert (pages, evidence) == ([], "")

    duplicate = str(uuid.uuid4())
    assert _refused(
        db,
        f"INSERT INTO {_PROPOSALS} (id, batch_id, product_id, product_code, spec_key, value, kind) "
        f"VALUES (:id, :batch, :product, 'ZZT-M370-P1', 'trap_type', '\"p_trap\"'::jsonb, 'new')",
        {"id": duplicate, "batch": batch_id, "product": product_id},
    ), "one row per key per product per batch"

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_proposal(db, batch_id, product_id, spec_key="seat_material", kind="maybe")

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_proposal(db, batch_id, product_id, spec_key="seat_material", origin="guess")

    manual = _insert_proposal(db, batch_id, product_id, spec_key="seat_material", origin="manual")
    assert db.execute(
        sa.text(f"SELECT origin FROM {_PROPOSALS} WHERE id = :id"), {"id": manual}
    ).scalar() == "manual"


def test_deleting_the_batch_takes_its_proposals_with_it(db):
    _run_upgrade(db)
    batch_id = _insert_batch(db, db.info["reading_id"])
    _insert_proposal(db, batch_id, db.info["product_id"], spec_key="trap_type")

    db.execute(sa.text(f"DELETE FROM {_BATCHES} WHERE id = :id"), {"id": batch_id})

    assert db.execute(
        sa.text(f"SELECT count(*) FROM {_PROPOSALS} WHERE batch_id = :id"), {"id": batch_id}
    ).scalar() == 0


# --------------------------------------------------------------------------- #
# idempotence: a second run, and a run over the earlier shape of the table
# --------------------------------------------------------------------------- #
def test_a_second_upgrade_changes_nothing_and_keeps_the_rows(db):
    _run_upgrade(db)
    batch_id = _insert_batch(db, db.info["reading_id"])
    row_id = _insert_proposal(db, batch_id, db.info["product_id"], spec_key="trap_type")

    def _shape() -> list[tuple]:
        return db.execute(
            sa.text(
                "SELECT table_name, column_name, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name IN (:b, :p) "
                "ORDER BY table_name, ordinal_position"
            ),
            {"b": _BATCHES, "p": _PROPOSALS},
        ).all()

    before = _shape()

    _run_upgrade(db)

    assert _shape() == before
    assert db.execute(
        sa.text(f"SELECT count(*) FROM {_PROPOSALS} WHERE id = :id"), {"id": row_id}
    ).scalar() == 1
    # Still one batch per reading after the second run.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_batch(db, db.info["reading_id"])


def test_upgrade_over_the_earlier_shape_adds_origin_backfilled_flyer_and_the_edited_columns(db):
    """A database that ran the first cut of 370 holds the proposals table without
    `origin` / `edited_at` / `edited_by`. Re-running must add them, stamp every
    existing row `flyer` (the paper is the only place a row could have come from
    before a person could add one), and make `origin` NOT NULL with its CHECK."""
    _run_upgrade(db)
    batch_id = _insert_batch(db, db.info["reading_id"])
    product_id = db.info["product_id"]

    db.execute(sa.text(f"ALTER TABLE {_PROPOSALS} DROP COLUMN origin"))
    db.execute(sa.text(f"ALTER TABLE {_PROPOSALS} DROP COLUMN edited_at"))
    db.execute(sa.text(f"ALTER TABLE {_PROPOSALS} DROP COLUMN edited_by"))
    old_row = _insert_proposal(db, batch_id, product_id, spec_key="trap_type")

    _run_upgrade(db)

    origin, edited_at, edited_by = db.execute(
        sa.text(f"SELECT origin, edited_at, edited_by FROM {_PROPOSALS} WHERE id = :id"),
        {"id": old_row},
    ).one()
    assert (origin, edited_at, edited_by) == ("flyer", None, None)

    assert _refused(
        db,
        f"INSERT INTO {_PROPOSALS} (id, batch_id, product_id, product_code, spec_key, value, kind, origin) "
        f"VALUES (:id, :batch, :product, 'ZZT-M370-P1', 'seat_material', '\"pp\"'::jsonb, 'new', NULL)",
        {"id": str(uuid.uuid4()), "batch": batch_id, "product": product_id},
    ), "origin is NOT NULL again"
    assert _refused(
        db,
        f"INSERT INTO {_PROPOSALS} (id, batch_id, product_id, product_code, spec_key, value, kind, origin) "
        f"VALUES (:id, :batch, :product, 'ZZT-M370-P1', 'seat_material', '\"pp\"'::jsonb, 'new', 'guess')",
        {"id": str(uuid.uuid4()), "batch": batch_id, "product": product_id},
    ), "and its CHECK is back"

    new_row = _insert_proposal(db, batch_id, product_id, spec_key="seat_material")
    assert db.execute(
        sa.text(f"SELECT origin FROM {_PROPOSALS} WHERE id = :id"), {"id": new_row}
    ).scalar() == "flyer"


# --------------------------------------------------------------------------- #
# downgrade
# --------------------------------------------------------------------------- #
def test_downgrade_drops_both_tables_and_a_further_upgrade_rebuilds_them(db):
    _run_upgrade(db)
    _insert_batch(db, db.info["reading_id"])

    _run_downgrade(db)

    assert not _table_exists(db, _PROPOSALS)
    assert not _table_exists(db, _BATCHES)

    _run_upgrade(db)

    assert _table_exists(db, _BATCHES)
    assert db.execute(sa.text(f"SELECT count(*) FROM {_BATCHES}")).scalar() == 0
