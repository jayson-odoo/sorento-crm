"""Migration `bfd_idx_0001_billing_from_doc_no` (BILLING-FROM-DOC-INDEX).

`documentation/plans/finance/PLAN-billing-from-doc-index-27oct.md`. DOC-RELATIONS looks up an SO's /
DO's billing documents by `finance.billing_document_lines.from_doc_no`
(`app/services/document_relations.py` `billing_ids_for_sales_order` /
`billing_ids_for_delivery_order`), which had no index. Same build rules as GOODSCHAIN-INDEX-QUERY
(`app/utils/online_index.py`, covered in depth by `test_migration_gc_idx_0001_spo_from_po_key.py`):
CONCURRENTLY, the repo's migration limits, fail-soft, retried by
`scripts/ensure_goods_chain_indexes.py`.

The table is schema-qualified (`finance.`), unlike the goods chain ones, so these tests build in a
scratch schema that is deliberately NOT on the search_path: an unqualified index name would miss.
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
REVISION = "bfd_idx_0001_billing_from_doc_no"
NAME = "ix_finance_billing_document_lines_from_doc_no"


@pytest.fixture(autouse=True)
def _wait_out_other_tests(monkeypatch):
    """A CONCURRENTLY build waits for every open transaction in the database (other xdist
    workers' included); the success paths wait that out, the timeout test sets its own limit."""
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "0")


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _scratch(monkeypatch):
    """(schema, autocommit connection). An empty `<schema>.billing_document_lines`, and
    BILLING_FROM_DOC_INDEXES pointed at it in place of `finance.`. search_path left alone."""
    schema = f"zzs_mig_bfdidx_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            conn.exec_driver_sql(
                f'CREATE TABLE "{schema}".billing_document_lines (id uuid PRIMARY KEY, '
                "document_id uuid, from_doc_type varchar(10), from_doc_no varchar(50))"
            )
            (_table, name, columns), = online_index.BILLING_FROM_DOC_INDEXES
            monkeypatch.setattr(
                online_index,
                "BILLING_FROM_DOC_INDEXES",
                ((f'"{schema}".billing_document_lines', name, columns),),
            )
            yield schema, conn
        finally:
            conn.exec_driver_sql("RESET lock_timeout")
            conn.exec_driver_sql("RESET statement_timeout")
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def _index(conn, schema, name=NAME):
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


def _run_upgrade(module):
    """upgrade() as `alembic/env.py` runs it: a transactional MigrationContext."""
    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx), ctx.begin_transaction():
                module.upgrade()
        finally:
            conn.rollback()


# ------------------------------------------------------------------------- the revision


def test_revision_fits_and_the_graph_has_one_head_descending_from_it():
    module = _load()
    assert module.revision == REVISION and len(REVISION) <= 32
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    ancestors = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert REVISION in ancestors


def test_the_index_matches_the_lookup_on_the_raw_column():
    """document_relations compares `from_doc_no` raw (== / IN), no lower()/btrim(), and the
    company filter there is on the joined header, so a plain single-column index."""
    assert online_index.BILLING_FROM_DOC_INDEXES == (
        ("finance.billing_document_lines", NAME, "(from_doc_no)"),
    )


def test_the_model_declares_it_so_create_all_databases_get_it_too():
    from app.models.finance import BillingDocumentLine

    found = {ix.name: [c.name for c in ix.columns] for ix in BillingDocumentLine.__table__.indexes}
    assert found.get(NAME) == ["from_doc_no"]


# ------------------------------------------------------------------------- build


def test_the_migration_builds_it_valid_in_a_schema_off_the_search_path(monkeypatch):
    module = _load()
    with _scratch(monkeypatch) as (schema, conn):
        _run_upgrade(module)
        _oid, valid, definition = _index(conn, schema)
        assert valid is True and definition.endswith("(from_doc_no)")


def test_an_invalid_leftover_off_the_search_path_is_dropped_and_rebuilt(monkeypatch):
    """The drop of an interrupted build's leftover must name the table's schema: an
    unqualified DROP INDEX IF EXISTS resolves along search_path, misses it, and CREATE ... IF
    NOT EXISTS then keeps the INVALID one forever."""
    with _scratch(monkeypatch) as (schema, conn):
        (table, name, columns), = online_index.BILLING_FROM_DOC_INDEXES
        conn.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON {table} {columns}")
        conn.exec_driver_sql(
            f"UPDATE pg_index SET indisvalid = false WHERE indexrelid = '\"{schema}\".{name}'::regclass"
        )
        stale_oid, valid, _ = _index(conn, schema)
        assert valid is False
        assert online_index.ensure_index_online(conn, table, name, columns) is True
        oid, valid, _ = _index(conn, schema)
        assert valid is True and oid != stale_oid


def test_the_migration_succeeds_when_the_build_times_out(monkeypatch, caplog):
    """Fail-soft: a build stuck behind live work logs a WARNING and the revision completes."""
    module = _load()
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "300ms")
    caplog.set_level(logging.WARNING, logger=online_index.__name__)
    with _scratch(monkeypatch) as (schema, conn):
        with engine.connect() as other:
            tx = other.begin()
            other.exec_driver_sql(
                f"INSERT INTO \"{schema}\".billing_document_lines (id) VALUES ('{uuid.uuid4()}')"
            )
            try:
                _run_upgrade(module)
                left = _index(conn, schema)
                assert left is None or left[1] is False
            finally:
                tx.rollback()
        assert any("not built" in r.getMessage() for r in caplog.records)


def test_the_retry_script_builds_it(monkeypatch):
    from scripts import ensure_goods_chain_indexes as retry

    monkeypatch.setattr(online_index, "GOODS_CHAIN_KEY_INDEXES", ())
    with _scratch(monkeypatch) as (schema, conn):
        assert retry.run(engine) is True
        assert _index(conn, schema)[1] is True


def test_the_planner_uses_it_for_the_relations_lookup(monkeypatch):
    """EXPLAIN of the DO Invoices lookup's predicate on 200k lines: a sequential scan before the
    index, an index scan after."""
    with _scratch(monkeypatch) as (schema, conn):
        table = f'"{schema}".billing_document_lines'
        conn.execute(sa.text(
            f"INSERT INTO {table} (id, document_id, from_doc_type, from_doc_no) "
            "SELECT gen_random_uuid(), gen_random_uuid(), CASE WHEN n % 2 = 0 THEN 'DO' ELSE 'SO' END, "
            "'DO-' || n FROM generate_series(1, 200000) n"
        ))
        conn.exec_driver_sql(f"ANALYZE {table}")
        query = (
            f"EXPLAIN SELECT document_id FROM {table} "
            "WHERE from_doc_type = 'DO' AND from_doc_no = 'DO-1234'"
        )
        before = "\n".join(r[0] for r in conn.exec_driver_sql(query))
        assert "Seq Scan" in before
        _run_upgrade(_load())
        conn.exec_driver_sql(f"ANALYZE {table}")
        after = "\n".join(r[0] for r in conn.exec_driver_sql(query))
        assert NAME in after and "Seq Scan" not in after
