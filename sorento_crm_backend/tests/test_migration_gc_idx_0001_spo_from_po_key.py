"""Migration `gc_idx_0001_spo_from_po_key` (GOODSCHAIN-INDEX-QUERY), on a scratch spo_allocations.

The index build runs against a scratch table (search_path pinned to a scratch schema, outer
transaction rolled back), non-concurrently since CONCURRENTLY cannot run inside the test's
transaction; `upgrade()` itself builds it concurrently. Prod's case is the INVALID leftover:
the owner's interrupted CONCURRENTLY build on 27 Oct left one, and IF NOT EXISTS kept it.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database import engine

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
REVISION = "gc_idx_0001_spo_from_po_key"
INDEX = "ix_spo_allocations_from_po_key"
DEFINITION = "(from_po_number, btrim(from_po_line_ref), product_id, company_id)"


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_fits_and_the_graph_has_one_head_descending_from_it():
    module = _load()
    assert module.revision == REVISION and len(REVISION) <= 32
    assert module.INDEX == INDEX
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    ancestors = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert REVISION in ancestors


def _index(raw, schema):
    """(oid, indisvalid, definition) of the index in `schema`, or None."""
    return raw.execute(
        sa.text(
            "SELECT c.oid, i.indisvalid, pg_get_indexdef(c.oid) FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = :name"
        ),
        {"s": schema, "name": INDEX},
    ).first()


def _scratch(raw):
    scratch = f"zzs_mig_gcidx_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    raw.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
    raw.exec_driver_sql(
        f'CREATE TABLE "{scratch}".spo_allocations (id uuid PRIMARY KEY, '
        "from_po_number varchar(100), from_po_line_ref varchar(255), product_id uuid, "
        "company_id uuid)"
    )
    raw.exec_driver_sql(f'SET LOCAL search_path TO "{scratch}"')
    return scratch


def test_builds_the_index_when_there_is_none():
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            scratch = _scratch(raw)
            assert _index(raw, scratch) is None
            module._ensure_index(raw, concurrently=False)
            oid, valid, definition = _index(raw, scratch)
            assert valid is True
            assert definition.endswith("(from_po_number, btrim((from_po_line_ref)::text), product_id, company_id)")
        finally:
            outer.rollback()


def test_an_invalid_leftover_is_dropped_and_rebuilt_valid():
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            scratch = _scratch(raw)
            raw.exec_driver_sql(f"CREATE INDEX {INDEX} ON spo_allocations {DEFINITION}")
            raw.exec_driver_sql(
                "UPDATE pg_index SET indisvalid = false WHERE indexrelid = "
                f"'\"{scratch}\".{INDEX}'::regclass"
            )
            stale_oid, valid, _ = _index(raw, scratch)
            assert valid is False
            module._ensure_index(raw, concurrently=False)
            oid, valid, _ = _index(raw, scratch)
            assert valid is True and oid != stale_oid
        finally:
            outer.rollback()


def test_a_valid_hand_made_index_is_kept():
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            scratch = _scratch(raw)
            raw.exec_driver_sql(f"CREATE INDEX {INDEX} ON spo_allocations {DEFINITION}")
            before = _index(raw, scratch)
            module._ensure_index(raw, concurrently=False)
            assert _index(raw, scratch) == before
        finally:
            outer.rollback()
