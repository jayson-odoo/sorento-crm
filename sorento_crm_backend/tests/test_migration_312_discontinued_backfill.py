"""Migration 312 must silence the historical backlog and nothing else.

Getting this wrong in either direction is costly: stamp too little and the first
scheduler tick after the company-scope fix sends one notification naming thousands of
products (observed for real: 2716); stamp too much and a genuinely new discontinuation
is marked as already-handled and never reported.

Runs the migration's own upgrade() against a blank schema inside a rolled-back
transaction, so the shared dev database is untouched.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure

from ._pg_fixture import blank_session, unique_code

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "312_backfill_discontinued_notified_at.py"
)


def _run_upgrade(db) -> None:
    spec = importlib.util.spec_from_file_location("migration_312", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()


def _fk_targets(db) -> tuple[str, str]:
    """Products carry NOT NULL FKs to category and UOM - Postgres enforces them, so the
    real rows have to exist rather than being invented UUIDs."""
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT"), category_name=unique_code("CAT")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM"), uom_name=unique_code("UOM"))
    db.add_all([category, uom])
    db.flush()
    return category.id, uom.id


def _product(db, *, discontinued: bool, notified: bool, fks: tuple[str, str]) -> str:
    """Only the columns under test are set beyond what NOT NULL demands."""
    from datetime import datetime

    code = unique_code("SKU")
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=fks[0],
        base_uom_id=fks[1],
        list_price=0,
        is_discontinued=discontinued,
        discontinued_notified_at=datetime.utcnow() if notified else None,
    )
    db.add(row)
    db.flush()
    return row.id


def _notified_at(db, pid: str):
    return db.execute(
        text("SELECT discontinued_notified_at FROM products WHERE id = :id"), {"id": pid}
    ).scalar()


def _batch_id(db, pid: str):
    return db.execute(
        text("SELECT discontinued_notify_batch_id FROM products WHERE id = :id"), {"id": pid}
    ).scalar()


@pytest.fixture()
def seeded():
    with blank_session() as db:
        fks = _fk_targets(db)
        rows = {
            "fks": fks,
            "backlog": _product(db, discontinued=True, notified=False, fks=fks),
            "already_notified": _product(db, discontinued=True, notified=True, fks=fks),
            "live_product": _product(db, discontinued=False, notified=False, fks=fks),
        }
        db.flush()
        yield db, rows


def test_the_backlog_is_stamped(seeded):
    """The whole point: these must not be reported on the first tick."""
    db, rows = seeded
    _run_upgrade(db)
    assert _notified_at(db, rows["backlog"]) is not None


def test_a_product_that_is_not_discontinued_is_left_alone(seeded):
    """Stamping a live product would silence its future discontinuation forever."""
    db, rows = seeded
    _run_upgrade(db)
    assert _notified_at(db, rows["live_product"]) is None


def test_an_already_notified_product_keeps_its_original_timestamp(seeded):
    db, rows = seeded
    before = _notified_at(db, rows["already_notified"])
    _run_upgrade(db)
    assert _notified_at(db, rows["already_notified"]) == before


def test_no_fabricated_batch_id(seeded):
    """These rows were never part of a real batch; pointing them at one would make the
    batch drill-down claim they were sent."""
    db, rows = seeded
    _run_upgrade(db)
    assert _batch_id(db, rows["backlog"]) is None


def test_a_product_discontinued_after_the_backfill_still_notifies(seeded):
    """The regression that matters: the job must keep working afterwards."""
    db, rows = seeded
    _run_upgrade(db)
    fresh = _product(db, discontinued=True, notified=False, fks=rows["fks"])
    db.flush()
    pending = db.execute(
        text(
            "SELECT count(*) FROM products "
            "WHERE is_discontinued = true AND discontinued_notified_at IS NULL"
        )
    ).scalar()
    assert pending == 1, f"expected only the new discontinuation pending, found {pending}"
    assert _notified_at(db, fresh) is None


def test_running_twice_stamps_nothing_new(seeded):
    db, _ = seeded
    _run_upgrade(db)
    first = db.execute(
        text("SELECT count(*) FROM products WHERE discontinued_notified_at IS NOT NULL")
    ).scalar()
    _run_upgrade(db)
    second = db.execute(
        text("SELECT count(*) FROM products WHERE discontinued_notified_at IS NOT NULL")
    ).scalar()
    assert first == second
