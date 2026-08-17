"""Migration 325 tested by running it, not by asserting on the live database.

The switch defaults to ON, so the upgrade must be a no-op for behaviour: every
contact that existed before it ran keeps receiving messages. That is the only
interesting thing about this migration, and the only way to prove it is to
build the pre-migration shape and run `upgrade()` over real rows.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "325_respond_contact_outbound_enabled.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m325", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade"):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, direction)()


@pytest.fixture
def db():
    """The blank schema, rewound to the shape that existed before 325.

    `create_all` builds the table from today's model, which already carries the
    column, so drop it first.
    """
    with blank_session() as session:
        session.execute(
            text("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS outbound_enabled")
        )
        yield session


def _legacy_contact(db) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, phone_number, name, session_vars) "
            "VALUES (:i, :p, 'ZZT Legacy', '{}'::jsonb)"
        ),
        {"i": cid, "p": f"+6011{str(uuid.uuid4().int)[:8]}"},
    )
    return cid


def test_existing_rows_come_out_enabled(db):
    contact_id = _legacy_contact(db)

    _run(db)

    assert (
        db.execute(
            text("SELECT outbound_enabled FROM respond_contacts WHERE id = :i"),
            {"i": contact_id},
        ).scalar()
        is True
    ), "the upgrade silenced a contact that was messaging fine before it ran"


def test_the_column_is_not_null_and_defaults_on(db):
    _run(db)

    row = db.execute(
        text(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'respond_contacts' "
            "AND column_name = 'outbound_enabled'"
        )
    ).one()
    assert row[0] == "NO"
    assert "true" in (row[1] or "").lower()


def test_a_row_inserted_without_the_column_is_enabled(db):
    """The blue/green window: old containers do not know the column exists."""
    _run(db)
    contact_id = _legacy_contact(db)

    assert (
        db.execute(
            text("SELECT outbound_enabled FROM respond_contacts WHERE id = :i"),
            {"i": contact_id},
        ).scalar()
        is True
    )


def test_migration_is_rerunnable(db):
    """The shared dev database gets this DDL applied by hand, so it runs twice."""
    contact_id = _legacy_contact(db)
    _run(db)
    db.execute(
        text("UPDATE respond_contacts SET outbound_enabled = false WHERE id = :i"),
        {"i": contact_id},
    )

    _run(db)

    assert (
        db.execute(
            text("SELECT outbound_enabled FROM respond_contacts WHERE id = :i"),
            {"i": contact_id},
        ).scalar()
        is False
    ), "a re-run must not reset a deliberately muted contact"


def test_downgrade_drops_the_column(db):
    _run(db)
    _run(db, "downgrade")

    assert (
        db.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'respond_contacts' "
                "AND column_name = 'outbound_enabled'"
            )
        ).scalar()
        == 0
    )
