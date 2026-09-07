"""Migration `488_spo_alloc_stated_received` (D28c, spo-xlsx-supersede round 4, AC-X39).

Adds the nullable `stated_received` integer column to `spo_allocations` and
backfills `stated_received = quantity_received` for `source_system = 'autocount'`
rows only. A raw-inserted autocount row's backfill semantics are NOT testable
post-hoc here (the fixture converges through `Base.metadata.create_all`, not
`alembic upgrade`, so there is no PRE-migration table state to backfill FROM
without first dropping the model's own column) - this file asserts only the
two things that ARE independently checkable: the column exists, nullable, and
the migration's own revision id stays under alembic's 32-character limit.

Loaded by file path (`importlib`, the `_run_migration` idiom used across this
suite - see `tests/test_chatbot_warehouse_cue_migration.py` /
`tests/test_migration_324_grn_line_spo_number_raw.py`) since the filename
starts with a digit and cannot be imported by module path.

RED today (before the coder's migration lands): `MIGRATION.exists()` is
False, so the very first assertion below fails with a clear message rather
than a bare `FileNotFoundError` deep inside `importlib`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "488_spo_alloc_stated_received.py"
)


def _load_migration():
    assert MIGRATION.exists(), (
        f"{MIGRATION} does not exist yet - migration 488 (D28c) has not "
        "been written"
    )
    spec = importlib.util.spec_from_file_location("m488_stated_received", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_id_is_under_32_characters():
    """AC-X39. Alembic's own head-revision-id limit is 32 characters
    (LESSONS-LEARNT); `alembic heads` must also stay single, which this file
    cannot assert on its own (that is a whole-project property, checked by
    `check-migration-heads` in CI / the pre-push hook), so only the id length
    is pinned here.
    """
    module = _load_migration()
    assert len(module.revision) <= 32, (
        module.revision, len(module.revision)
    )


def test_upgrade_adds_the_nullable_stated_received_column():
    """AC-X39. `upgrade()` must add `stated_received` to `spo_allocations` -
    nullable (NULL reads as 0 on every row written before this migration
    existed), with no NOT NULL / server default forcing a value onto rows
    the migration's own backfill deliberately leaves untouched (any
    non-`autocount` row).
    """
    module = _load_migration()
    with blank_session() as db:
        # Undo what `Base.metadata.create_all` already emitted from the
        # model (once the coder adds the column there too), so `upgrade()`
        # is exercised against the pre-migration shape, same pattern as
        # `tests/test_migration_324_grn_line_spo_number_raw.py`.
        db.execute(text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS stated_received"))
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()

        row = db.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'spo_allocations' AND column_name = 'stated_received' "
                "AND table_schema = current_schema()"
            )
        ).mappings().first()
        assert row is not None, "stated_received column was not created by upgrade()"
        assert row["is_nullable"] == "YES", (
            "stated_received must be nullable - NULL reads as 0 on every "
            f"pre-migration row - got {row}"
        )
