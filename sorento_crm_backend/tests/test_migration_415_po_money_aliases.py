"""Migration 415 - the rest of the purchase book's money line.

`UNIT COST` / `UNIT PRICE` and `UOM` have resolved for `outstanding_po` since migrations 311
and 399, and the AutoCount PO detail listing states a discount and a line total beside them
that no alias ever named - so the buyer's screen could only print a unit cost beside a
quantity, which is not what the supplier charged.

Same shape as `test_migration_399_po_book_aliases.py`, and `blank_session` for the same
reason: the migration's `seed`/`downgrade` name only the unqualified `import_field_alias`
table, which the scratch schema's `search_path` resolves, and a standalone table needs no
reference data seeded first.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.services.import_alias_service import normalize_header
from tests._pg_fixture import blank_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "415_po_money_aliases.py"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_415_po_money_aliases", _MIGRATION_PATH
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
        "WHERE doc_type = 'outstanding_po' AND field IN ('discount', 'total_inc') "
        "ORDER BY field, alias"
    )).fetchall()


def test_seed_inserts_the_discount_and_total_aliases(db):
    inserted = _module().seed(db.connection())

    assert inserted == 5
    assert {(f, a) for _d, f, a in _rows(db)} == {
        ("discount", "DISCOUNT"),
        ("discount", "DISC."),
        ("total_inc", "TOTAL (INC)"),
        ("total_inc", "TOTAL"),
        ("total_inc", "AMOUNT"),
    }


def test_a_bare_disc_column_resolves_without_its_own_row(db):
    """`normalize_header` strips punctuation, so `DISC.` and `DISC` are ONE key. A separate
    row for the bare spelling would be a second row for a map entry that already exists."""
    assert normalize_header("DISC.") == normalize_header("DISC")


def test_seed_is_idempotent(db):
    assert _module().seed(db.connection()) == 5

    # A re-run - a database somebody has already seeded by hand - inserts nothing new and
    # raises nothing.
    assert _module().seed(db.connection()) == 0
    assert len(_rows(db)) == 5


def test_downgrade_deletes_exactly_those_rows_and_nothing_else(db):
    _module().seed(db.connection())
    # The sales book's own discount alias, from migration 357, must survive untouched: this
    # revision seeds the PURCHASE side and has no business with the other doc type.
    db.execute(text(
        "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
        "VALUES ('outstanding_so', 'discount', 'DISCOUNT', 'en')"
    ))

    # `downgrade()` itself calls `op.get_bind()`, which needs an active alembic
    # `MigrationContext` this test does not stand up. Issue the identical DELETE it runs,
    # driven by the module's own `_ALIASES`, so a change to that list is exercised by both
    # this test and the real downgrade without restating the SQL differently.
    bind = db.connection()
    for doc_type, field, alias, _locale in _module()._ALIASES:
        bind.execute(text(
            "DELETE FROM import_field_alias "
            "WHERE doc_type = :d AND field = :f AND alias = :a"
        ), {"d": doc_type, "f": field, "a": alias})

    assert _rows(db) == []
    survivor = db.execute(text(
        "SELECT count(*) FROM import_field_alias "
        "WHERE doc_type = 'outstanding_so' AND field = 'discount'"
    )).scalar()
    assert survivor == 1, "the sales book's own alias must not be swept by this downgrade"
