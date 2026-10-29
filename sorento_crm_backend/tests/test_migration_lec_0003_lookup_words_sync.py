"""lec_0003_lookup_words_sync seeds the scheduled task `lookup_words_sync` (every 600 s), like migration 143."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "lec_0003_lookup_words_sync.py"


def _module():
    assert MIGRATION.exists(), f"missing {MIGRATION.name}"
    spec = importlib.util.spec_from_file_location("_lec_0003_test", MIGRATION)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(db, fn):
    m = _module()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(m, fn)()


def _rows(db):
    return db.execute(
        text("SELECT enabled, interval_unit, interval_value FROM scheduled_tasks WHERE key = 'lookup_words_sync'")
    ).all()


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def test_revision_id_fits_and_chains():
    m = _module()
    assert m.revision == "lec_0003_lookup_words_sync" and len(m.revision) <= 32
    assert m.down_revision == "lec_0002_embedding_indexes"


def test_upgrade_seeds_one_task_every_600_seconds_and_is_idempotent(db):
    _run(db, "upgrade")
    _run(db, "upgrade")
    assert [tuple(r) for r in _rows(db)] == [(True, "seconds", 600)]


def test_downgrade_removes_the_task(db):
    _run(db, "upgrade")
    _run(db, "downgrade")
    assert _rows(db) == []
