"""Migration `gc_idx_0001_spo_from_po_key` and `app/utils/online_index.py` (GOODSCHAIN-INDEX-QUERY).

Owner requirements (27 Oct 2026): CONCURRENTLY only, the repo's migration limits, and a build
that times out or fails logs a WARNING, drops its INVALID leftover and lets the deploy carry on;
the next backend start retries (`scripts/ensure_goods_chain_indexes.py`).

Every test builds for real, CONCURRENTLY, on an autocommit connection against a COMMITTED
scratch schema (search_path pinned to it), dropped in teardown. The shared tables are never
touched. A second connection plays the live work the build must not wait on.
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
from app.utils.online_index import GOODS_CHAIN_KEY_INDEXES, ensure_index_online

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
REVISION = "gc_idx_0001_spo_from_po_key"

#: (table, index, columns, the definition Postgres prints back).
CASES = (
    (
        "spo_allocations",
        "ix_spo_allocations_from_po_key",
        "(from_po_number, btrim(from_po_line_ref), product_id, company_id)",
        "(from_po_number, btrim((from_po_line_ref)::text), product_id, company_id)",
    ),
    (
        "purchase_order_lines",
        "ix_purchase_order_lines_src_key",
        "(btrim(source_ref), product_id, company_id)",
        "(btrim((source_ref)::text), product_id, company_id)",
    ),
)
TABLES = {
    "spo_allocations": "from_po_number varchar(100), from_po_line_ref varchar(255)",
    "purchase_order_lines": "source_ref varchar(255)",
}
by_index = pytest.mark.parametrize("table,name,columns,printed", CASES, ids=[c[1] for c in CASES])
SPO = CASES[0]


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _scratch():
    """(schema, autocommit connection with search_path on it). Both tables exist, empty."""
    schema = f"zzs_mig_gcidx_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            for table, columns in TABLES.items():
                conn.exec_driver_sql(
                    f'CREATE TABLE "{schema}".{table} (id uuid PRIMARY KEY, {columns}, '
                    "product_id uuid, company_id uuid)"
                )
            conn.exec_driver_sql(f'SET search_path TO "{schema}"')
            yield schema, conn
        finally:
            conn.exec_driver_sql("RESET search_path")
            conn.exec_driver_sql("RESET lock_timeout")
            conn.exec_driver_sql("RESET statement_timeout")
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


@contextmanager
def _open_writer(schema, table):
    """Live work: a transaction that wrote a row to `table` and has not committed. A
    CONCURRENTLY build waits for it."""
    with engine.connect() as other:
        tx = other.begin()
        other.exec_driver_sql(f"INSERT INTO \"{schema}\".{table} (id) VALUES ('{uuid.uuid4()}')")
        try:
            yield
        finally:
            tx.rollback()


def _index(conn, schema, name):
    """(oid, indisvalid, definition) of the index in `schema`, or None."""
    return conn.execute(
        sa.text(
            "SELECT c.oid, i.indisvalid, pg_get_indexdef(c.oid) FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = :name"
        ),
        {"s": schema, "name": name},
    ).first()


# ------------------------------------------------------------------------- the revision


def test_revision_fits_and_the_graph_has_one_head_descending_from_it():
    module = _load()
    assert module.revision == REVISION and len(REVISION) <= 32
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    ancestors = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert REVISION in ancestors


def test_the_indexes_are_prods_names_and_shapes():
    assert [(t, n, c) for t, n, c, _p in CASES] == list(GOODS_CHAIN_KEY_INDEXES)


def test_the_build_is_only_ever_concurrent():
    source = (BACKEND / "app" / "utils" / "online_index.py").read_text()
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in source
    assert source.count("CREATE INDEX") == source.count("CREATE INDEX CONCURRENTLY")
    assert source.count("DROP INDEX") == source.count("DROP INDEX CONCURRENTLY")


# ------------------------------------------------------------------------- build / keep / rebuild


@by_index
def test_builds_the_index_when_there_is_none(table, name, columns, printed):
    with _scratch() as (schema, conn):
        assert _index(conn, schema, name) is None
        assert ensure_index_online(conn, table, name, columns) is True
        _oid, valid, definition = _index(conn, schema, name)
        assert valid is True and definition.endswith(printed)


@by_index
def test_an_invalid_leftover_is_dropped_and_rebuilt_valid(table, name, columns, printed):
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON {table} {columns}")
        conn.exec_driver_sql(
            f"UPDATE pg_index SET indisvalid = false WHERE indexrelid = '\"{schema}\".{name}'::regclass"
        )
        stale_oid, valid, _ = _index(conn, schema, name)
        assert valid is False
        assert ensure_index_online(conn, table, name, columns) is True
        oid, valid, _ = _index(conn, schema, name)
        assert valid is True and oid != stale_oid


@by_index
def test_a_valid_hand_made_index_is_kept(table, name, columns, printed):
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON {table} {columns}")
        before = _index(conn, schema, name)
        assert ensure_index_online(conn, table, name, columns) is True
        assert _index(conn, schema, name) == before


# ------------------------------------------------------------------------- timeouts and fallback


def test_the_build_runs_under_the_repo_migration_limits_and_restores_the_session(monkeypatch):
    table, name, columns, _p = SPO
    seen = []
    real = online_index._set_limits

    def spy(bind, lock, statement):
        seen.append((lock, statement))
        real(bind, lock, statement)

    monkeypatch.delenv("MIGRATION_LOCK_TIMEOUT", raising=False)
    monkeypatch.delenv("MIGRATION_STATEMENT_TIMEOUT", raising=False)
    monkeypatch.setattr(online_index, "_set_limits", spy)
    with _scratch() as (_schema, conn):
        conn.exec_driver_sql("SET lock_timeout = '0'")
        conn.exec_driver_sql("SET statement_timeout = '0'")
        assert ensure_index_online(conn, table, name, columns) is True
        assert seen[0] == ("5s", "180s")
        assert conn.execute(sa.text("SHOW lock_timeout")).scalar() == "0"
        assert conn.execute(sa.text("SHOW statement_timeout")).scalar() == "0"


def test_a_build_stuck_behind_live_work_gives_up_logs_and_the_retry_builds_it(monkeypatch, caplog):
    """lock_timeout: the build waits for an open writer, times out, returns False with a
    WARNING instead of raising. Its INVALID leftover is dropped or, when that drop times out
    behind the same writer, left for the retry. Once the writer is gone, the retry builds it."""
    table, name, columns, _p = SPO
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "300ms")
    caplog.set_level(logging.WARNING, logger=online_index.__name__)
    with _scratch() as (schema, conn):
        with _open_writer(schema, table):
            assert ensure_index_online(conn, table, name, columns) is False
            left = _index(conn, schema, name)
            assert left is None or left[1] is False
        assert any(
            "not built" in r.getMessage() and "lock timeout" in r.getMessage()
            for r in caplog.records
        )
        assert ensure_index_online(conn, table, name, columns) is True
        assert _index(conn, schema, name)[1] is True


def test_a_build_past_the_statement_timeout_gives_up_and_drops_its_leftover(monkeypatch, caplog):
    table, name, columns, _p = SPO
    caplog.set_level(logging.WARNING, logger=online_index.__name__)
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(
            f"INSERT INTO {table} (id, from_po_number, from_po_line_ref) "
            "SELECT gen_random_uuid(), 'PO' || n, ' REF' || n FROM generate_series(1, 300000) n"
        )
        monkeypatch.setenv("MIGRATION_STATEMENT_TIMEOUT", "20ms")
        assert ensure_index_online(conn, table, name, columns) is False
        assert any("statement timeout" in r.getMessage() for r in caplog.records)
        monkeypatch.delenv("MIGRATION_STATEMENT_TIMEOUT")
        # Nothing waits on the drop here, so the leftover is gone, not left INVALID.
        assert _index(conn, schema, name) is None
        assert ensure_index_online(conn, table, name, columns) is True


def _run_upgrade(module, schema):
    """upgrade() as `alembic/env.py` runs it: a transactional MigrationContext on its own
    connection, search_path on the scratch schema."""
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx), ctx.begin_transaction():
            conn.exec_driver_sql(f'SET search_path TO "{schema}"')
            module.upgrade()


def test_the_migration_succeeds_when_its_builds_time_out(monkeypatch):
    """upgrade() itself, through a real alembic autocommit_block: both builds stuck behind
    live work, and the revision still completes without raising."""
    module = _load()
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "300ms")
    with _scratch() as (schema, conn):
        with _open_writer(schema, "spo_allocations"), _open_writer(schema, "purchase_order_lines"):
            _run_upgrade(module, schema)
            for _t, name, _c in GOODS_CHAIN_KEY_INDEXES:
                left = _index(conn, schema, name)
                assert left is None or left[1] is False


def test_the_migration_builds_both_indexes():
    module = _load()
    with _scratch() as (schema, conn):
        _run_upgrade(module, schema)
        assert all(_index(conn, schema, n)[1] is True for _t, n, _c in GOODS_CHAIN_KEY_INDEXES)


# ------------------------------------------------------------------------- the retry script


def _scratch_engine(schema):
    return sa.create_engine(
        engine.url,
        poolclass=sa.pool.NullPool,
        connect_args={"options": f"-csearch_path={schema}"},
    )


def test_the_retry_builds_what_is_missing_and_then_does_nothing():
    from scripts import ensure_goods_chain_indexes as retry

    with _scratch() as (schema, conn):
        scratch_engine = _scratch_engine(schema)
        assert retry.run(scratch_engine) is True
        built = [_index(conn, schema, n) for _t, n, _c in GOODS_CHAIN_KEY_INDEXES]
        assert all(row[1] is True for row in built)
        assert retry.run(scratch_engine) is True
        assert [_index(conn, schema, n) for _t, n, _c in GOODS_CHAIN_KEY_INDEXES] == built
        scratch_engine.dispose()


def test_the_retry_leaves_it_to_a_backend_already_building():
    from scripts import ensure_goods_chain_indexes as retry

    with _scratch() as (schema, conn):
        scratch_engine = _scratch_engine(schema)
        with engine.connect() as other:
            other.execute(sa.text("SELECT pg_advisory_lock(:k)"), {"k": online_index.ADVISORY_LOCK_KEY})
            try:
                assert retry.run(scratch_engine) is False
                assert all(_index(conn, schema, n) is None for _t, n, _c in GOODS_CHAIN_KEY_INDEXES)
            finally:
                other.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": online_index.ADVISORY_LOCK_KEY})
        scratch_engine.dispose()


def test_start_sh_runs_the_retry_in_the_background_after_migrating():
    start = (BACKEND / "start.sh").read_text()
    upgrade = start.index("alembic upgrade head")
    retry = start.index("python -m scripts.ensure_goods_chain_indexes &")
    assert upgrade < retry < start.index("exec python -m gunicorn")


def test_both_builds_share_one_statement_budget(monkeypatch, caplog):
    """Two builds may not each take a full migration statement_timeout (blue/green waits 4
    minutes): the first spends the budget, the second is skipped with a WARNING for the retry."""
    from app.utils.online_index import ensure_indexes_online

    caplog.set_level(logging.WARNING, logger=online_index.__name__)
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(
            "INSERT INTO spo_allocations (id, from_po_number, from_po_line_ref) "
            "SELECT gen_random_uuid(), 'PO' || n, ' REF' || n FROM generate_series(1, 300000) n"
        )
        monkeypatch.setenv("MIGRATION_STATEMENT_TIMEOUT", "50ms")
        seen = []
        real = online_index.ensure_index_online

        def spy(bind, table, name, columns, *, budget_ms=None):
            seen.append((name, budget_ms))
            if table == "spo_allocations":
                # Stands in for a build that ran the whole budget down.
                import time

                time.sleep(0.06)
            return real(bind, table, name, columns, budget_ms=budget_ms)

        monkeypatch.setattr(online_index, "ensure_index_online", spy)
        assert ensure_indexes_online(conn, GOODS_CHAIN_KEY_INDEXES) is False
        assert seen[0][0] == "ix_spo_allocations_from_po_key" and 0 < seen[0][1] <= 50
        assert [name for name, _b in seen] == ["ix_spo_allocations_from_po_key"]
        assert any("budget is spent" in r.getMessage() for r in caplog.records)
        assert _index(conn, schema, "ix_purchase_order_lines_src_key") is None


def test_duration_ms_reads_every_migration_timeout_form():
    from app.utils.online_index import duration_ms

    assert [duration_ms(v) for v in ("0", "5s", "2500ms", "3min", "1h", "250")] == [
        0, 5000, 2500, 180000, 3600000, 250,
    ]
