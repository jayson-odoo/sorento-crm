"""Migration `esc1_0001_escalation_allowed` (ESCALATION-CONTROL): up, down, up on scratch tables.

Owner, 30 Sep 2026: "all dealer block escalation by default". Every access type whose
name ends in the word "Dealer" (any case) is seeded barred; every other type stays
allowed. The migration's SQL names its tables unqualified, so `search_path` points it at
a scratch schema's own copies, never the shared relations. Named `test_migration_*.py` so
CI runs it in the serial migration pass.
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
    Path(__file__).resolve().parent / ".." / "alembic" / "versions" / "esc1_0001_escalation_allowed.py"
).resolve()

#: Dev's four dealer types, the bare "Dealer" type migration 094 seeds, and names that
#: only look like one.
DEALERS = ["Sorento Dealer", "Cabana Dealer", "Mocha Dealer", "NL Dealer", "Dealer", "  mocha DEALER "]
NOT_DEALERS = ["End User", "Sorento Office", "Dealership Staff", "Subdealer", "Dealer Office"]


def _load():
    spec = importlib.util.spec_from_file_location("m_esc1_0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def _columns(conn, schema):
    return {
        row.table_name: row.is_nullable
        for row in conn.execute(
            sa.text(
                "SELECT table_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = :s AND column_name = 'escalation_allowed'"
            ),
            {"s": schema},
        )
    }


def test_revision_chains_onto_mains_head():
    module = _load()
    assert module.revision == "esc1_0001_escalation_allowed"
    assert len(module.revision) <= 32
    assert module.down_revision == "oihr_0004_wide_line_table"


def test_every_dealer_type_is_seeded_barred_and_nothing_else():
    module = _load()
    schema = f"zzt_esc1_{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
        conn.commit()
        try:
            conn.execute(sa.text(f"SET search_path TO {schema}"))
            conn.execute(sa.text("CREATE TABLE contact_access_types (code varchar(50) PRIMARY KEY, name varchar(255) NOT NULL)"))
            conn.execute(sa.text("CREATE TABLE respond_contacts (id text PRIMARY KEY)"))
            for i, name in enumerate(DEALERS + NOT_DEALERS):
                conn.execute(
                    sa.text("INSERT INTO contact_access_types (code, name) VALUES (:c, :n)"),
                    {"c": f"t{i}", "n": name},
                )

            _run(conn, module.upgrade)
            assert _columns(conn, schema) == {"contact_access_types": "NO", "respond_contacts": "YES"}
            seeded = dict(conn.execute(sa.text("SELECT name, escalation_allowed FROM contact_access_types")).all())
            assert {n: seeded[n] for n in DEALERS} == {n: False for n in DEALERS}, seeded
            assert {n: seeded[n] for n in NOT_DEALERS} == {n: True for n in NOT_DEALERS}, seeded

            _run(conn, module.upgrade)  # re-runnable against a create_all schema
            _run(conn, module.downgrade)
            assert _columns(conn, schema) == {}
            _run(conn, module.upgrade)
            assert len(_columns(conn, schema)) == 2
            conn.rollback()
        finally:
            conn.execute(sa.text("SET search_path TO DEFAULT"))
            conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.commit()
