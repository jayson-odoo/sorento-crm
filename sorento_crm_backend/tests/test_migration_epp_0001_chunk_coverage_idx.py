"""Migration `epp_0001_chunk_coverage_idx` (EMBED-PAGE-PERF).

`documentation/plans/system/PLAN-embed-page-perf-30oct.md`. The Embeddings overview and the backfill guard probe
"active documents with no current chunk of a model" (`_MISSING_SQL`); this partial index answers the probe from the
index alone. Same build rules as `bfd_idx_0001_billing_from_doc_no` (`app/utils/online_index.py`, covered in depth by
`test_migration_gc_idx_0001_spo_from_po_key.py`): CONCURRENTLY, the repo's migration limits, fail-soft, retried by
`scripts/ensure_goods_chain_indexes.py`. These tests build on a scratch `embedding_chunks` off the search_path.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.database import engine
from app.services import embedding_indexes
from app.utils import online_index

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
REVISION = "epp_0001_chunk_coverage_idx"
NAME = "ix_embedding_chunks_current_model_doc"


@pytest.fixture(autouse=True)
def _wait_out_other_tests(monkeypatch):
    """A CONCURRENTLY build waits for every open transaction in the database (other xdist workers' included)."""
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "0")


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _scratch(monkeypatch):
    """(schema, autocommit connection): an empty `<schema>.embedding_chunks`, COVERAGE_INDEXES pointed at it."""
    schema = f"zzs_mig_eppidx_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            conn.exec_driver_sql(
                f'CREATE TABLE "{schema}".embedding_chunks (id uuid PRIMARY KEY, document_id uuid, '
                "model_name varchar(128), is_current boolean)"
            )
            (_table, name, columns), = embedding_indexes.COVERAGE_INDEXES
            monkeypatch.setattr(
                embedding_indexes, "COVERAGE_INDEXES", ((f'"{schema}".embedding_chunks', name, columns),)
            )
            yield schema, conn
        finally:
            conn.exec_driver_sql("RESET lock_timeout")
            conn.exec_driver_sql("RESET statement_timeout")
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def _index(conn, schema):
    """(indisvalid, definition) of the index in `schema`, or None."""
    return conn.execute(
        sa.text(
            "SELECT i.indisvalid, pg_get_indexdef(c.oid) FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = :name"
        ),
        {"s": schema, "name": NAME},
    ).first()


def _run_upgrade(module):
    """upgrade() as `alembic/env.py` runs it: a transactional MigrationContext."""
    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx), ctx.begin_transaction():
                module.upgrade()
        finally:
            conn.rollback()


def test_revision_fits_and_the_graph_has_one_head():
    assert len(REVISION) <= 32
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert script.get_revision(REVISION) is not None


def test_the_retry_script_passes_it(monkeypatch):
    from scripts import ensure_goods_chain_indexes as retry

    captured = {}

    def spy(_bind, indexes):
        captured["indexes"] = tuple(indexes)
        return True

    monkeypatch.setattr(online_index, "ensure_indexes_online", spy)
    assert retry.run(engine) is True
    assert embedding_indexes.COVERAGE_INDEXES[0] in captured["indexes"]


def test_the_model_declares_the_same_index_so_create_all_databases_get_it_too():
    from app.models.embeddings import EmbeddingChunk

    (ix,) = [ix for ix in EmbeddingChunk.__table__.indexes if ix.name == NAME]
    assert [c.name for c in ix.columns] == ["model_name", "document_id"]
    assert str(ix.dialect_options["postgresql"]["where"]) == "is_current"
    (_table, name, columns), = embedding_indexes.COVERAGE_INDEXES
    assert name == NAME and columns == "(model_name, document_id) WHERE is_current"


def test_the_migration_builds_it_valid(monkeypatch):
    module = _load()
    with _scratch(monkeypatch) as (schema, conn):
        _run_upgrade(module)
        valid, definition = _index(conn, schema)
        assert valid is True
        assert definition.endswith("(model_name, document_id) WHERE is_current")


def test_the_migration_succeeds_when_the_build_times_out(monkeypatch, caplog):
    """Fail-soft: a build stuck behind live work logs a WARNING and the revision completes."""
    module = _load()
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "300ms")
    caplog.set_level(logging.WARNING, logger=online_index.__name__)
    with _scratch(monkeypatch) as (schema, conn):
        with engine.connect() as other:
            tx = other.begin()
            other.exec_driver_sql(f"INSERT INTO \"{schema}\".embedding_chunks (id) VALUES ('{uuid.uuid4()}')")
            try:
                _run_upgrade(module)
                left = _index(conn, schema)
                assert left is None or left[0] is False
            finally:
                tx.rollback()
        assert any("not built" in r.getMessage() for r in caplog.records)
