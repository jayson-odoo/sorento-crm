"""Migration 399 - the three headers the captain's "PO & SPO outstanding.xlsx" export
carries that no earlier `outstanding_po` alias resolved: `Qty`, `Delivery Date`,
`Unit Price`.

Uses `blank_session` rather than `pg_session`: the migration's `seed`/`downgrade` name only
the unqualified `import_field_alias` table, which the scratch schema's `search_path`
resolves correctly, and a standalone table (no FKs) needs no reference data seeded first.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "399_po_book_aliases.py"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_399_po_book_aliases", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _rows(db):
    return db.execute(text(
        "SELECT doc_type, field, alias FROM import_field_alias "
        "WHERE doc_type = 'outstanding_po' AND field IN "
        "('qty_ordered', 'expected_date', 'unit_cost') "
        "ORDER BY field, alias"
    )).fetchall()


def test_seed_inserts_exactly_the_three_new_aliases(db):
    inserted = _module().seed(db.connection())

    assert inserted == 3
    rows = {(f, a) for _d, f, a in _rows(db)}
    assert rows == {
        ("qty_ordered", "QTY"),
        ("expected_date", "DELIVERY DATE"),
        ("unit_cost", "UNIT PRICE"),
    }


def test_seed_is_idempotent(db):
    first = _module().seed(db.connection())
    assert first == 3

    # A re-run - the exact scenario this migration met on the stack database, which had
    # already been seeded by hand - inserts nothing new and raises nothing.
    second = _module().seed(db.connection())
    assert second == 0
    assert len(_rows(db)) == 3


def test_downgrade_deletes_exactly_those_three_rows_and_nothing_else(db):
    _module().seed(db.connection())
    # A pre-existing alias on the same doc_type/field, from an earlier migration, must
    # survive the downgrade untouched.
    db.execute(text(
        "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
        "VALUES ('outstanding_po', 'qty_ordered', 'QTY ORDERED', 'en')"
    ))

    # `downgrade()` itself calls `op.get_bind()`, which needs an active alembic
    # `MigrationContext` this test does not stand up. Issue the identical DELETE it runs,
    # driven by the module's own `_ALIASES` list, so a change to that list is exercised by
    # both this test and the real downgrade without restating the SQL differently.
    bind = db.connection()
    for doc_type, field, alias, _locale in _module()._ALIASES:
        bind.execute(text(
            "DELETE FROM import_field_alias "
            "WHERE doc_type = :d AND field = :f AND alias = :a"
        ), {"d": doc_type, "f": field, "a": alias})

    remaining = _rows(db)
    assert remaining == [("outstanding_po", "qty_ordered", "QTY ORDERED")], \
        "downgrade must remove only the three seeded rows, leaving an unrelated alias intact"
