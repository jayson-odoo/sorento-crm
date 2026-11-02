"""Migration `il_0001_integration_log_indexes` (INTEGRATION-LOG-INDEXES).

`documentation/plans/infra/PLAN-integration-log-indexes-02nov.md`. integration_log never got the
five indexes its model declares (no migration created them; create_all skips an existing table),
so the upload-activity bell's latest-log query seq-scanned ~1.2M rows on every page.

Every build runs for real, CONCURRENTLY, through `app/utils/online_index.py` against a COMMITTED
scratch schema holding its own `integration_log` (search_path pinned to it), dropped in teardown.
The shared table is never touched.
"""
from __future__ import annotations

import importlib.util
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
REVISION = "il_0001_integration_log_indexes"

#: (index, what Postgres prints back after "USING btree "). The composite keeps the name and
#: shape crew built by hand on the dev DB (2 Nov 2026), so it is kept there as it is.
EXPECTED = (
    ("ix_integration_log_business_table_business_id", "(business_table, business_id, created_at DESC)"),
    ("ix_integration_log_status", "(status)"),
    ("ix_integration_log_integration_channel", "(integration_channel)"),
    ("ix_integration_log_created_at", "(created_at)"),
    ("ix_integration_log_next_retry_at", "(next_retry_at)"),
)
UNIQUE = "uq_integration_log_ideation_status_event"

TABLE_DDL = (
    "CREATE TABLE {s}.integration_log ("
    "id uuid PRIMARY KEY, integration_channel varchar(100) NOT NULL, "
    "business_table varchar(100) NOT NULL, business_id uuid NOT NULL, "
    "status varchar(50) NOT NULL, next_retry_at timestamp, "
    "created_at timestamp NOT NULL DEFAULT now())"
)


@pytest.fixture(autouse=True)
def _wait_out_other_tests(monkeypatch):
    """A CONCURRENTLY build waits for every open transaction in the database; under xdist other
    workers hold theirs for seconds. Wait as long as that takes (lock_timeout 0)."""
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "0")


def _load():
    files = sorted(VERSIONS.glob("il_0001*.py"))
    assert len(files) == 1, f"expected one il_0001 migration, found {files}"
    spec = importlib.util.spec_from_file_location("_il_0001_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _scratch():
    schema = f"zzs_mig_il_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            conn.exec_driver_sql(TABLE_DDL.format(s=f'"{schema}"'))
            conn.exec_driver_sql(
                f'CREATE UNIQUE INDEX {UNIQUE} ON "{schema}".integration_log (business_id) '
                "WHERE business_table = 'ideation_status_events'"
            )
            conn.exec_driver_sql(f'SET search_path TO "{schema}"')
            yield schema, conn
        finally:
            conn.exec_driver_sql("RESET search_path")
            conn.exec_driver_sql("RESET lock_timeout")
            conn.exec_driver_sql("RESET statement_timeout")
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


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


def _run(module, schema, step="upgrade"):
    """upgrade()/downgrade() as `alembic/env.py` runs it: a transactional MigrationContext on its
    own pooled connection, search_path undone before the connection goes back to the pool."""
    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx), ctx.begin_transaction():
                conn.exec_driver_sql(f'SET search_path TO "{schema}"')
                getattr(module, step)()
        finally:
            conn.rollback()
            conn.exec_driver_sql("RESET search_path")
            conn.commit()


# ------------------------------------------------------------------------- the revision


def test_revision_fits_and_the_graph_has_one_head_descending_from_it():
    module = _load()
    assert module.revision == REVISION and len(REVISION) <= 32
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    assert REVISION in {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}


def test_the_helper_lists_the_models_names_composite_first():
    """The composite is the one the bell needs, so it builds first inside the shared budget."""
    assert [n for _t, n, _c in online_index.INTEGRATION_LOG_INDEXES] == [n for n, _d in EXPECTED]
    assert all(t == "integration_log" for t, _n, _c in online_index.INTEGRATION_LOG_INDEXES)


def test_the_model_declares_the_same_indexes():
    from app.models.integration import IntegrationLog

    declared = {ix.name: ix for ix in IntegrationLog.__table__.indexes}
    for name, _d in EXPECTED:
        assert name in declared, name
    composite = declared["ix_integration_log_business_table_business_id"]
    rendered = [str(e) for e in composite.expressions]
    assert rendered[:2] == ["integration_log.business_table", "integration_log.business_id"]
    assert rendered[2].replace("integration_log.", "") == "created_at DESC"
    assert UNIQUE in declared


# ------------------------------------------------------------------------- build / keep / plan


def test_the_migration_builds_all_five_valid_and_keeps_the_unique_one():
    module = _load()
    with _scratch() as (schema, conn):
        unique_before = _index(conn, schema, UNIQUE)
        _run(module, schema)
        for name, printed in EXPECTED:
            found = _index(conn, schema, name)
            assert found is not None, name
            _oid, valid, definition = found
            assert valid is True and definition.endswith(f"USING btree {printed}"), definition
        assert _index(conn, schema, UNIQUE) == unique_before


def test_a_valid_hand_made_composite_is_kept_and_a_rerun_changes_nothing():
    """The dev DB already has crew's hand-built composite (same name, same shape)."""
    module = _load()
    name, printed = EXPECTED[0]
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON integration_log {printed}")
        hand_made = _index(conn, schema, name)
        _run(module, schema)
        assert _index(conn, schema, name) == hand_made
        built = [_index(conn, schema, n) for n, _d in EXPECTED]
        _run(module, schema)
        assert [_index(conn, schema, n) for n, _d in EXPECTED] == built


def test_an_invalid_leftover_is_rebuilt_valid():
    module = _load()
    name, printed = EXPECTED[0]
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON integration_log {printed}")
        conn.exec_driver_sql(
            f"UPDATE pg_index SET indisvalid = false WHERE indexrelid = '\"{schema}\".{name}'::regclass"
        )
        stale_oid = _index(conn, schema, name)[0]
        _run(module, schema)
        oid, valid, _d = _index(conn, schema, name)
        assert valid is True and oid != stale_oid


def test_the_upload_activity_query_reads_the_composite_not_the_whole_table():
    """The exact shape of `upload_activity.py`'s latest-log query, over 60k rows of which a
    handful are the user's attachments: no Seq Scan once the migration ran."""
    module = _load()
    with _scratch() as (schema, conn):
        conn.exec_driver_sql(
            "INSERT INTO integration_log (id, integration_channel, business_table, business_id, status, created_at) "
            "SELECT gen_random_uuid(), 'n8n', "
            "CASE WHEN mod(n, 3) = 0 THEN 'attachments' ELSE 'orders' END, gen_random_uuid(), "
            "CASE WHEN mod(n, 5) = 0 THEN 'failed' ELSE 'success' END, now() - (n || ' minutes')::interval "
            "FROM generate_series(1, 60000) n"
        )
        ids = [
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT business_id::text FROM integration_log WHERE business_table = 'attachments' LIMIT 25"
            )
        ]
        _run(module, schema)
        conn.exec_driver_sql("ANALYZE integration_log")
        in_list = ", ".join(f"'{i}'" for i in ids)
        plan = "\n".join(
            r[0]
            for r in conn.exec_driver_sql(
                "EXPLAIN SELECT * FROM integration_log WHERE business_table = 'attachments' "
                f"AND business_id IN ({in_list}) ORDER BY business_id, created_at DESC"
            )
        )
        assert "Seq Scan" not in plan, plan
        assert "ix_integration_log_business_table_business_id" in plan, plan


# ------------------------------------------------------------------------- downgrade + retry


def test_downgrade_drops_the_five_and_leaves_the_unique_index():
    module = _load()
    with _scratch() as (schema, conn):
        _run(module, schema)
        _run(module, schema, "downgrade")
        assert all(_index(conn, schema, n) is None for n, _d in EXPECTED)
        assert _index(conn, schema, UNIQUE) is not None


def test_the_retry_script_passes_them(monkeypatch):
    """A build the migration's budget could not reach is retried on the next backend start."""
    from scripts import ensure_goods_chain_indexes as retry

    captured = {}

    def spy(_bind, indexes):
        captured["indexes"] = tuple(indexes)
        return True

    monkeypatch.setattr(online_index, "ensure_indexes_online", spy)
    assert retry.run(engine) is True
    for t in online_index.INTEGRATION_LOG_INDEXES:
        assert t in captured["indexes"], t
