"""AC-LEC-11: migration lec_0002_embedding_indexes creates / drops the per-model HNSW indexes.

CREATE INDEX CONCURRENTLY cannot run in a rolled-back transaction, so this runs the real upgrade through an
autocommit-capable connection. It runs on a private scratch schema holding a copy of embedding_chunks (search_path
points there), so no other test's open transaction on the public table can make it wait or flake under -n 2.
"""
from __future__ import annotations

import importlib.util
import uuid
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


SCHEMA = f"zzs_lec2_{uuid.uuid4().hex[:8]}"


def _run(fn: str) -> None:
    m = _module()
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql(f"SET search_path TO {SCHEMA}, public")
            conn.commit()
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                getattr(m, fn)()
            conn.commit()
        finally:
            conn.rollback()
            conn.exec_driver_sql("RESET search_path")
            conn.commit()


def _present(names) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = 'embedding_chunks' AND indexname = ANY(:n)"),
            {"s": SCHEMA, "n": list(names)},
        ).all()
    return {r[0] for r in rows}


def _names() -> set[str]:
    from app.services import embedding_indexes

    return set(embedding_indexes.index_names(MODEL).values())


@pytest.fixture
def scratch():
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"CREATE TABLE {SCHEMA}.embedding_chunks (LIKE public.embedding_chunks INCLUDING DEFAULTS)"))
    yield
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


def test_ac_lec_11_revision_id_fits_and_chains():
    m = _module()
    assert m.revision == "lec_0002_embedding_indexes" and len(m.revision) <= 32
    assert m.down_revision == "lec_0001_embedding_setting"


def test_ac_lec_11_upgrade_creates_the_indexes_idempotently_and_downgrade_drops_them(scratch):
    names = _names()
    assert len(names) == 3
    _run("upgrade")
    assert _present(names) == names
    _run("upgrade")  # IF NOT EXISTS: a second run is safe
    assert _present(names) == names
    _run("downgrade")
    assert _present(names) == set()
