"""Migration `gc_idx_0001_spo_from_po_key` (GOODSCHAIN-INDEX-QUERY), on scratch tables.

Each index build runs against a scratch table (search_path pinned to a scratch schema, outer
transaction rolled back), non-concurrently since CONCURRENTLY cannot run inside the test's
transaction; `upgrade()` itself builds it concurrently. Prod's case is the INVALID leftover:
the owner's interrupted CONCURRENTLY build on 27 Oct left one, and IF NOT EXISTS kept it.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database import engine

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


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_fits_and_the_graph_has_one_head_descending_from_it():
    module = _load()
    assert module.revision == REVISION and len(REVISION) <= 32
    assert [(t, n, c) for t, n, c, _p in CASES] == list(module.INDEXES)
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    ancestors = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert REVISION in ancestors


def _index(raw, schema, name):
    """(oid, indisvalid, definition) of the index in `schema`, or None."""
    return raw.execute(
        sa.text(
            "SELECT c.oid, i.indisvalid, pg_get_indexdef(c.oid) FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = :name"
        ),
        {"s": schema, "name": name},
    ).first()


def _scratch(raw, table):
    scratch = f"zzs_mig_gcidx_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    raw.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
    raw.exec_driver_sql(
        f'CREATE TABLE "{scratch}".{table} (id uuid PRIMARY KEY, {TABLES[table]}, '
        "product_id uuid, company_id uuid)"
    )
    raw.exec_driver_sql(f'SET LOCAL search_path TO "{scratch}"')
    return scratch


@by_index
def test_builds_the_index_when_there_is_none(table, name, columns, printed):
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            scratch = _scratch(raw, table)
            assert _index(raw, scratch, name) is None
            module._ensure_index(raw, table, name, columns, concurrently=False)
            _oid, valid, definition = _index(raw, scratch, name)
            assert valid is True
            assert definition.endswith(printed)
        finally:
            outer.rollback()


@by_index
def test_an_invalid_leftover_is_dropped_and_rebuilt_valid(table, name, columns, printed):
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            scratch = _scratch(raw, table)
            raw.exec_driver_sql(f"CREATE INDEX {name} ON {table} {columns}")
            raw.exec_driver_sql(
                "UPDATE pg_index SET indisvalid = false WHERE indexrelid = "
                f"'\"{scratch}\".{name}'::regclass"
            )
            stale_oid, valid, _ = _index(raw, scratch, name)
            assert valid is False
            module._ensure_index(raw, table, name, columns, concurrently=False)
            oid, valid, _ = _index(raw, scratch, name)
            assert valid is True and oid != stale_oid
        finally:
            outer.rollback()


@by_index
def test_a_valid_hand_made_index_is_kept(table, name, columns, printed):
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            scratch = _scratch(raw, table)
            raw.exec_driver_sql(f"CREATE INDEX {name} ON {table} {columns}")
            before = _index(raw, scratch, name)
            module._ensure_index(raw, table, name, columns, concurrently=False)
            assert _index(raw, scratch, name) == before
        finally:
            outer.rollback()
