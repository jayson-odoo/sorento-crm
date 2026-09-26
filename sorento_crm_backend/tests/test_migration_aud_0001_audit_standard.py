"""Migration `aud_0001_audit_standard_s0` (#1281 S0): up and down, on a scratch copy of audit_logs.

AC-S0-24. The revision runs through a real alembic `Operations` context against a scratch copy
of `audit_logs` (search_path pinned to the scratch schema, outer transaction rolled back), so
the DDL that reaches production is what runs here.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.database import engine

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
REVISION = "aud_0001_audit_standard_s0"
NEW_COLUMNS = {
    "root_entity_type", "root_entity_id", "event", "principal_type", "principal_id",
    "on_behalf_of_user_id", "source", "reason", "correlation_id",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"m_{name}", VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def test_revision_fits_and_the_graph_has_one_head_descending_from_it():
    module = _load(REVISION)
    assert module.revision == REVISION and len(REVISION) <= 32
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    ancestors = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert REVISION in ancestors


def _triggers(raw, schema):
    return set(
        raw.execute(
            sa.text(
                "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :s AND c.relname = 'audit_logs' AND NOT t.tgisinternal"
            ),
            {"s": schema},
        ).scalars()
    )


def _check(raw, schema):
    return raw.execute(
        sa.text(
            "SELECT pg_get_constraintdef(co.oid) FROM pg_constraint co "
            "JOIN pg_namespace n ON n.oid = co.connamespace "
            "WHERE n.nspname = :s AND co.conname = 'audit_logs_action_check'"
        ),
        {"s": schema},
    ).scalar()


def _default(raw, schema):
    return raw.execute(
        sa.text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'audit_logs' AND column_name = 'changed_at'"
        ),
        {"s": schema},
    ).scalar()


def test_upgrade_then_downgrade():
    module = _load(REVISION)
    scratch = f"zzs_mig_aud1_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            raw.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
            # The pre-S0 shape: the columns main had, plus the CHECK from migration 271.
            raw.exec_driver_sql(
                f'CREATE TABLE "{scratch}".audit_logs ('
                "id uuid PRIMARY KEY, entity_type varchar(100) NOT NULL, "
                "entity_id varchar(100) NOT NULL, action varchar(20) NOT NULL, user_id uuid, "
                "contact_id varchar(100), changed_at timestamp NOT NULL DEFAULT now(), "
                "old_values jsonb, new_values jsonb, description text, ip_address varchar(100), "
                "trace_id varchar(64), company_id uuid, "
                "CONSTRAINT audit_logs_action_check CHECK (action IN "
                "('CREATE','READ','UPDATE','DELETE','IMPORT')))"
            )
            raw.exec_driver_sql(f'SET LOCAL search_path TO "{scratch}"')
            conn = raw.execution_options(schema_translate_map={None: scratch})

            _run(conn, module.upgrade)
            cols = {c["name"] for c in sa.inspect(raw).get_columns("audit_logs", schema=scratch)}
            assert NEW_COLUMNS <= cols
            assert "'EVENT'" in _check(raw, scratch)
            assert "clock_timestamp" in _default(raw, scratch)
            assert _triggers(raw, scratch) == {
                "audit_logs_append_only_row", "audit_logs_append_only_truncate",
            }
            raw.exec_driver_sql(
                f"INSERT INTO \"{scratch}\".audit_logs (id, entity_type, entity_id, action) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'probe', 'p', 'EVENT')"
            )
            sp = raw.begin_nested()
            with pytest.raises(Exception, match="append-only"):
                raw.exec_driver_sql(f'DELETE FROM "{scratch}".audit_logs')
            sp.rollback()

            raw.exec_driver_sql("SET LOCAL sorento.audit_maintenance = 'on'")
            raw.exec_driver_sql(f'DELETE FROM "{scratch}".audit_logs')
            _run(conn, module.downgrade)
            cols = {c["name"] for c in sa.inspect(raw).get_columns("audit_logs", schema=scratch)}
            assert not (NEW_COLUMNS & cols)
            assert "'EVENT'" not in _check(raw, scratch)
            assert "now()" in _default(raw, scratch)
            assert _triggers(raw, scratch) == set()
        finally:
            outer.rollback()
