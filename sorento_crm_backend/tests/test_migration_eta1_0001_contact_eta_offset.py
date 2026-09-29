"""Migration `eta1_0001_contact_eta_offset` (#1328): up, down, up, on a scratch table.

The migration's own `upgrade()` / `downgrade()` run through a real alembic `Operations`
context against a scratch schema that holds its own `respond_contacts` (the migration's SQL
names the table unqualified, so `search_path` points it at the scratch copy - never the
shared relation, lesson 114). The scratch schema is dropped afterwards.

Named `test_migration_*.py` so CI runs it in the serial migration pass.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

MIGRATION = (
    Path(__file__).resolve().parent
    / ".."
    / "alembic"
    / "versions"
    / "eta1_0001_contact_eta_offset.py"
).resolve()


def _load():
    spec = importlib.util.spec_from_file_location("m_eta1_0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def _column(conn, schema):
    return conn.execute(
        sa.text(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'respond_contacts' "
            "AND column_name = 'chatbot_eta_offset_applied'"
        ),
        {"s": schema},
    ).first()


def test_revision_chains_onto_mains_head():
    """Main's single head at the batch 6 join round is merge_29sep_batch6; this
    revision hangs off it, so the tree has exactly one head."""
    module = _load()
    assert module.revision == "eta1_0001_contact_eta_offset"
    assert len(module.revision) <= 32
    assert module.down_revision == "merge_29sep_batch6"


def test_up_down_up_adds_a_not_null_default_true_column():
    module = _load()
    schema = f"zzt_eta1_{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
        conn.commit()
        try:
            conn.execute(sa.text(f"SET search_path TO {schema}"))
            conn.execute(sa.text("CREATE TABLE respond_contacts (id text PRIMARY KEY)"))
            conn.execute(sa.text("INSERT INTO respond_contacts (id) VALUES ('existing')"))

            _run(conn, module.upgrade)
            col = _column(conn, schema)
            assert col is not None
            assert col.is_nullable == "NO"
            assert "true" in (col.column_default or "")
            # An existing contact reads ON: today's stock ask behaviour.
            assert conn.execute(
                sa.text("SELECT chatbot_eta_offset_applied FROM respond_contacts")
            ).scalar() is True

            # Re-runnable against a schema create_all already built.
            _run(conn, module.upgrade)

            _run(conn, module.downgrade)
            assert _column(conn, schema) is None

            _run(conn, module.upgrade)
            assert _column(conn, schema) is not None
            conn.rollback()
        finally:
            conn.execute(sa.text("SET search_path TO DEFAULT"))
            conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.commit()
