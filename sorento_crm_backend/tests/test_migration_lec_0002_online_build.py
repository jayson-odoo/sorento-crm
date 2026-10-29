"""Review fix round 6, R6-1: lec_0002_embedding_indexes builds its HNSW indexes online.

Contract: `embedding_indexes.online_indexes(model)` / `MIGRATION_INDEXES`, and lec_0002 `upgrade()` calls
`online_index.ensure_indexes_online(op.get_bind(), MIGRATION_INDEXES)` inside an autocommit block with
`maintenance_work_mem = '512MB'` set for the call and reset after. Modelled on
`test_migration_bfd_idx_0001_billing_from_doc_no.py`; builds happen in a scratch schema.
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
from app.utils import online_index

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
MODEL = "text-embedding-3-small"


@pytest.fixture(autouse=True)
def _wait_out_other_tests(monkeypatch):
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "0")


def _load():
    spec = importlib.util.spec_from_file_location("m_lec_0002_online", VERSIONS / "lec_0002_embedding_indexes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ei():
    from app.services import embedding_indexes

    return embedding_indexes


@contextmanager
def _scratch(monkeypatch, rows=0):
    """(schema, autocommit connection, scratch tuples). MIGRATION_INDEXES points at a scratch embedding_chunks."""
    ei = _ei()
    assert hasattr(ei, "online_indexes") and hasattr(ei, "MIGRATION_INDEXES"), "embedding_indexes lacks the R6-1 API"
    schema = f"zzs_mig_lec2_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            conn.exec_driver_sql(
                f'CREATE TABLE "{schema}".embedding_chunks (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), '
                "embedding vector(1536), model_name varchar(100), is_current boolean, source_type varchar(60))"
            )
            if rows:
                conn.exec_driver_sql(
                    f'INSERT INTO "{schema}".embedding_chunks (embedding, model_name, is_current, source_type) '
                    f"SELECT array_fill((n %% 7 + 1)::real / 10, ARRAY[1536])::vector, "
                    f"'{MODEL}', true, 'product' FROM generate_series(1, {rows}) n"
                )
            scratch = tuple((f'"{schema}".embedding_chunks', n, c) for _t, n, c in ei.online_indexes(MODEL))
            monkeypatch.setattr(ei, "MIGRATION_INDEXES", scratch)
            yield schema, conn, scratch
        finally:
            conn.exec_driver_sql("RESET lock_timeout")
            conn.exec_driver_sql("RESET statement_timeout")
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def _index(conn, schema, name):
    return conn.execute(
        sa.text(
            "SELECT c.oid, i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = :s AND c.relname = :name"
        ),
        {"s": schema, "name": name},
    ).first()


def _run_upgrade(module, after=None):
    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx), ctx.begin_transaction():
                module.upgrade()
            if after:
                after(conn)
        finally:
            conn.rollback()


# ------------------------------------------------------------------ the shared tuples


def test_online_indexes_are_the_index_ddl_one_predicate_source():
    ei = _ei()
    tuples = ei.online_indexes(MODEL)
    ddl = ei.index_ddl(MODEL)
    assert len(tuples) == len(ddl) == 3
    assert [n for _t, n, _c in tuples] == list(ei.index_names(MODEL).values())
    for (table, name, columns), stmt in zip(tuples, ddl):
        assert table == "embedding_chunks"
        assert f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {columns}" == stmt


def test_migration_indexes_constant_is_the_default_model_set():
    ei = _ei()
    assert ei.MIGRATION_INDEXES == ei.online_indexes(MODEL)


# ------------------------------------------------------------------ upgrade wiring


def test_upgrade_calls_ensure_indexes_online_with_512mb_work_mem_and_resets_it(monkeypatch):
    ei = _ei()
    seen = {}

    def spy(bind, indexes):
        seen["indexes"] = indexes
        seen["mem"] = bind.execute(sa.text("SHOW maintenance_work_mem")).scalar()
        seen["bind"] = bind
        return True

    monkeypatch.setattr(online_index, "ensure_indexes_online", spy)
    state = {}

    def after(conn):
        state["after"] = conn.execute(sa.text("SHOW maintenance_work_mem")).scalar()

    with engine.connect() as probe:
        before = probe.execute(sa.text("SHOW maintenance_work_mem")).scalar()
    _run_upgrade(_load(), after)
    assert seen["indexes"] == ei.MIGRATION_INDEXES
    assert seen["mem"] == "512MB"
    assert state["after"] == before and state["after"] != "512MB"


def test_work_mem_is_reset_even_when_the_helper_raises(monkeypatch):
    seen = {}

    def boom(bind, indexes):
        seen["bind"] = bind
        seen["during"] = bind.execute(sa.text("SHOW maintenance_work_mem")).scalar()
        raise RuntimeError("boom")

    monkeypatch.setattr(online_index, "ensure_indexes_online", boom)
    with engine.connect() as probe:
        before = probe.execute(sa.text("SHOW maintenance_work_mem")).scalar()
    state = {}

    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            try:
                with Operations.context(ctx), ctx.begin_transaction():
                    _load().upgrade()
            except RuntimeError:
                pass
            state["after"] = conn.execute(sa.text("SHOW maintenance_work_mem")).scalar()
        finally:
            conn.rollback()
    assert seen["during"] == "512MB"
    assert state["after"] == before and state["after"] != "512MB"


# ------------------------------------------------------------------ real builds


def test_the_migration_builds_all_three_valid(monkeypatch):
    with _scratch(monkeypatch) as (schema, conn, scratch):
        _run_upgrade(_load())
        for _t, name, _c in scratch:
            found = _index(conn, schema, name)
            assert found is not None and found[1] is True, name


def test_an_invalid_leftover_of_the_keep_index_is_dropped_and_rebuilt(monkeypatch):
    with _scratch(monkeypatch) as (schema, conn, scratch):
        table, name, columns = scratch[0]
        conn.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON {table} {columns}")
        conn.exec_driver_sql(
            f"UPDATE pg_index SET indisvalid = false WHERE indexrelid = '\"{schema}\".{name}'::regclass"
        )
        stale_oid, valid = _index(conn, schema, name)
        assert valid is False
        _run_upgrade(_load())
        oid, valid = _index(conn, schema, name)
        assert valid is True and oid != stale_oid


def test_a_build_timeout_does_not_raise_logs_a_warning_and_leaves_no_invalid_index(monkeypatch, caplog):
    monkeypatch.setenv("MIGRATION_STATEMENT_TIMEOUT", "1ms")
    caplog.set_level(logging.WARNING, logger=online_index.__name__)
    with _scratch(monkeypatch, rows=3000) as (schema, conn, scratch):
        _run_upgrade(_load())
        for _t, name, _c in scratch:
            found = _index(conn, schema, name)
            assert found is None or found[1] is True, f"INVALID {name} left behind"
        assert any(r.levelno == logging.WARNING and "not built" in r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ retry + graph


def test_the_retry_script_passes_the_embedding_indexes_too(monkeypatch):
    from scripts import ensure_goods_chain_indexes as retry

    captured = {}

    def spy(bind, indexes):
        captured["indexes"] = tuple(indexes)
        return True

    monkeypatch.setattr(online_index, "ensure_indexes_online", spy)
    assert retry.run(engine) is True
    got = captured["indexes"]
    for t in (*_ei().MIGRATION_INDEXES, *online_index.GOODS_CHAIN_KEY_INDEXES, *online_index.BILLING_FROM_DOC_INDEXES):
        assert t in got, t
    assert len(_ei().MIGRATION_INDEXES) == 3


def test_the_graph_keeps_one_head():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1
