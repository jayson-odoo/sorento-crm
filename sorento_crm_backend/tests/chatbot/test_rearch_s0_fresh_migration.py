"""Regression test for `chatbot_rearch_s0` on a genuinely fresh migration chain
(prod deploy run 35652578646, 22 Sep 2026).

`seed_domains_and_kinds` (`alembic/versions/chatbot_rearch_s0.py`) reflects
`chatbot_entity_kinds` and unconditionally passed `id=str(uuid.uuid4())` to the
insert. On CI and on every local dev clone the equivalent substrate is built
via `Base.metadata.create_all` (`tests/_pg_fixture.py::blank_session`), which
stamps `chatbot_entity_kinds` with the `id` column `chatbot_rearch_s6f` adds
LATER in the chain - so the reflected table `seed_domains_and_kinds` sees there
always happened to have that column already, and the bug never had substrate
to show up on. A REAL `alembic upgrade head` against a genuinely empty database
runs s0's own `op.create_table("chatbot_entity_kinds", ...)` first, which
declares `kind` as the sole primary key and NO `id` column at all - s6f only
ADDS it, many revisions later. Prod was the first environment ever to run this
migration against a truly fresh chain, and `alembic upgrade head` died mid-
deploy with `sqlalchemy.exc.CompileError: Unconsumed column names: id`.

This test builds that exact "immediately before s0" substrate by hand: a
scratch schema holding only bare-bones versions of the three tables
`s0.upgrade()` ADDS COLUMNS to (`respond_contacts`, `conversation_frames`,
`system_settings`) - deliberately NOT the current ORM models for those tables,
which already carry the columns s0 adds (this migration shipped already) and
would make `add_column` raise "column already exists" instead, hiding this bug
behind a different error. `chatbot_domains` / `chatbot_entity_kinds` do not
exist at all going in, matching a real fresh chain. Never the shared dev
database, never `blank_session()` - a dedicated scratch schema, dropped in
`finally` whatever the outcome.
"""
from __future__ import annotations

import importlib.util
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.database import engine
from tests._pg_fixture import SCRATCH_SCHEMA_PREFIX

_ALEMBIC_DIR = Path(__file__).resolve().parent.parent.parent / "alembic"
_VERSIONS_DIR = _ALEMBIC_DIR / "versions"


def _load(filename: str):
    """Same convention `test_rearch_s12_config_ships.py::_load` uses (see its own
    docstring): a migration module loaded by file path needs `alembic/` on
    `sys.path` for its own bare `from _chatbot_policy_seed import ...`."""
    if str(_ALEMBIC_DIR) not in sys.path:
        sys.path.insert(0, str(_ALEMBIC_DIR))
    spec = importlib.util.spec_from_file_location(f"_zzt_test_{filename}", _VERSIONS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _fresh_chain_schema():
    """A scratch schema shaped like the real chain the instant before s0 runs.

    Yields ``(connection, schema_name)``. Everything happens on ONE connection
    so alembic's `MigrationContext` and this test's own verification queries
    share the same (uncommitted) transaction; the schema is dropped from a
    second connection in `finally`, whatever the outcome.
    """
    name = f"{SCRATCH_SCHEMA_PREFIX}_s0fresh_{uuid.uuid4().hex[:8]}"
    admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    admin.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    admin.close()

    connection = engine.connect()
    try:
        connection.exec_driver_sql(f'SET search_path TO "{name}"')
        # Bare-bones stand-ins for the three tables s0.upgrade() only ADDS
        # COLUMNS to - real columns/FKs are irrelevant to that call.
        connection.execute(text("CREATE TABLE respond_contacts (id text PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE conversation_frames (id uuid PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE system_settings (id uuid PRIMARY KEY)"))
        yield connection, name
    finally:
        connection.close()
        cleanup = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        cleanup.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        cleanup.close()


def _run_upgrade(connection: sa.Connection, module) -> None:
    """Drives the migration's real `upgrade()` through a live `Operations`
    context, exactly `test_rearch_s12_config_ships.py::_run_migration` does -
    needed because `upgrade()` calls `op.get_bind()` internally."""
    context = MigrationContext.configure(connection=connection)
    with Operations.context(context):
        module.upgrade()


def test_upgrade_does_not_raise_on_a_genuinely_fresh_chain():
    s0 = _load("chatbot_rearch_s0.py")
    with _fresh_chain_schema() as (connection, _name):
        _run_upgrade(connection, s0)


def test_chatbot_entity_kinds_has_no_id_column_at_s0():
    """The exact shape prod had when the deploy died: `s0` alone gives
    `chatbot_entity_kinds` a natural `kind` primary key and no `id` column -
    `chatbot_rearch_s6f` is the migration that adds one, many revisions later."""
    s0 = _load("chatbot_rearch_s0.py")
    with _fresh_chain_schema() as (connection, name):
        _run_upgrade(connection, s0)

        inspector = sa.inspect(connection)
        columns = {c["name"] for c in inspector.get_columns("chatbot_entity_kinds", schema=name)}
        assert "id" not in columns, columns
        assert "kind" in columns, columns


def test_chatbot_entity_kinds_seeded_with_every_kind_row():
    from _chatbot_policy_seed import DEFAULT_KIND_ROWS

    s0 = _load("chatbot_rearch_s0.py")
    with _fresh_chain_schema() as (connection, _name):
        _run_upgrade(connection, s0)

        kinds = {
            row[0]
            for row in connection.execute(text("SELECT kind FROM chatbot_entity_kinds"))
        }
        assert kinds == {row["kind"] for row in DEFAULT_KIND_ROWS}


def test_chatbot_domains_seeded_with_every_domain_row():
    from _chatbot_policy_seed import DEFAULT_DOMAIN_ROWS

    s0 = _load("chatbot_rearch_s0.py")
    with _fresh_chain_schema() as (connection, _name):
        _run_upgrade(connection, s0)

        names = {
            row[0]
            for row in connection.execute(text("SELECT name FROM chatbot_domains"))
        }
        assert names == {row["name"] for row in DEFAULT_DOMAIN_ROWS}
