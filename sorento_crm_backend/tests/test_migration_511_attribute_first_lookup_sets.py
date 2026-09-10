"""Migration `511_attribute_first_lookup_sets` (D3, PLAN-attribute-first-asks.md).

Creates two EMPTY lookup sets - `certificate_scheme` and `attachment_type_alias` - with
no options; the owner enters options and keywords on System > Lookup Sets afterwards
(owner decision, 10 Sep 2026: "don't need to seed for scheme, I will enter"). Loaded by
file path since the filename starts with a digit (the `_run_migration` idiom, see
`tests/test_migration_491_chatbot_ladder_incoming_po.py`), against a Postgres blank
schema per PRINCIPLES - never sqlite.

Contract: `documentation/plans/chatbot/attribute-first-asks-acceptance-criteria.md`
AC-1314.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "511_attribute_first_lookup_sets.py"
)

SET_KEYS = ("certificate_scheme", "attachment_type_alias")


def _load_migration():
    assert MIGRATION.exists(), f"{MIGRATION} does not exist - work item D3 is not written yet"
    spec = importlib.util.spec_from_file_location("m511_attribute_first_lookup_sets", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_id_is_under_32_characters_and_chains_onto_head():
    module = _load_migration()
    assert len(module.revision) <= 32, (module.revision, len(module.revision))
    assert module.down_revision == "510_strip_rtf_so_notes"


def _set_rows(db):
    return db.execute(
        text("SELECT set_key, is_active FROM lookup_sets WHERE set_key = ANY(:keys)"),
        {"keys": list(SET_KEYS)},
    ).fetchall()


def _option_count(db, set_key: str) -> int:
    return db.execute(
        text(
            "SELECT count(*) FROM lookup_options o JOIN lookup_sets s ON s.id = o.set_id "
            "WHERE s.set_key = :key"
        ),
        {"key": set_key},
    ).scalar()


def test_migration_creates_two_empty_lookup_sets_and_downgrade_removes_them():
    module = _load_migration()
    with blank_session() as db:
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()

        rows = {row[0]: row[1] for row in _set_rows(db)}
        assert set(rows) == set(SET_KEYS), rows
        for key in SET_KEYS:
            assert rows[key] is True, (key, rows)
            assert _option_count(db, key) == 0, key

        with Operations.context(ctx):
            module.upgrade()  # a second run changes nothing (idempotent)
        rows_again = {row[0]: row[1] for row in _set_rows(db)}
        assert set(rows_again) == set(SET_KEYS)

        with Operations.context(ctx):
            module.downgrade()
        assert _set_rows(db) == []
