"""AC-LEC-11: migration lec_0002_embedding_indexes creates / drops the per-model HNSW indexes.

CREATE INDEX CONCURRENTLY cannot run in a rolled-back transaction, so this runs the real upgrade on the
lane's private database through an autocommit-capable connection and always drops the indexes it made.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.database import engine

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "lec_0002_embedding_indexes.py"
MODEL = "text-embedding-3-small"


def _module():
    assert MIGRATION.exists(), f"missing {MIGRATION.name}"
    spec = importlib.util.spec_from_file_location("_lec_0002_test", MIGRATION)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(fn: str) -> None:
    m = _module()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(m, fn)()
        conn.commit()


def _present(names) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'embedding_chunks' AND indexname = ANY(:n)"),
            {"n": list(names)},
        ).all()
    return {r[0] for r in rows}


def _names() -> set[str]:
    from app.services import embedding_indexes

    return set(embedding_indexes.index_names(MODEL).values())


@pytest.fixture
def cleanup():
    yield
    try:
        names = _names()
    except Exception:
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for n in names:
            conn.execute(text(f'DROP INDEX IF EXISTS "{n}"'))


def test_ac_lec_11_revision_id_fits_and_chains():
    m = _module()
    assert m.revision == "lec_0002_embedding_indexes" and len(m.revision) <= 32
    assert m.down_revision == "lec_0001_embedding_setting"


def test_ac_lec_11_upgrade_creates_the_indexes_idempotently_and_downgrade_drops_them(cleanup):
    names = _names()
    assert len(names) == 3
    _run("upgrade")
    assert _present(names) == names
    _run("upgrade")  # IF NOT EXISTS: a second run is safe
    assert _present(names) == names
    _run("downgrade")
    assert _present(names) == set()
