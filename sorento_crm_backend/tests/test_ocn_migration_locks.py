"""OCN-ORDER-CHANGE-NOTICE round 10: the migration's hot-table DDL waits a bounded time.

The aud_0001_audit_standard_s0 precedent: each step that alters a table other requests use
takes its lock in a savepoint under `lock_timeout`, retried with a backoff, and the last miss
fails with a message. The widened Conversation CHECK is added NOT VALID and ends VALID.

Runs the real `upgrade()` on the blank scratch schema (tests/test_ocn_migration.py's harness);
the held lock comes from a second connection. Postgres only.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from ._pg_fixture import blank_schema_engine
from .test_ocn_migration import _module, _upgrade, db  # noqa: F401  (fixture)

CHECK = "ck_entity_conversation_messages_entity_type"


def _run_upgrade(db, module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


def test_r10_the_conversation_check_ends_valid_and_admits_the_notice(db):
    before = db.execute(text("select current_setting('lock_timeout'), current_setting('statement_timeout')")).one()
    _upgrade(db, times=2)
    validated, definition = db.execute(
        text(
            "select convalidated, pg_get_constraintdef(oid) from pg_constraint "
            "where conname = :n and conrelid = 'entity_conversation_messages'::regclass"
        ),
        {"n": CHECK},
    ).one()
    assert validated is True
    assert "'order_change_notice'" in definition
    assert "'purchase_request'" in definition  # every earlier kind still admitted
    after = db.execute(text("select current_setting('lock_timeout'), current_setting('statement_timeout')")).one()
    assert tuple(after) == tuple(before)  # the timeouts are put back


def test_r10_a_held_lock_on_the_conversation_table_is_retried_then_refused_plainly(db):
    module = _module()
    module.LOCK_TIMEOUT = "100ms"
    waits: list[float] = []
    module.time = SimpleNamespace(sleep=waits.append)  # the backoff, recorded instead of slept

    schema = db.execute(text("select current_schema()")).scalar()
    holder = blank_schema_engine().connect()
    tx = holder.begin()
    try:
        # A long transaction that has read the table: ACCESS SHARE, which the ALTER must wait for.
        holder.execute(text(f'LOCK TABLE "{schema}".entity_conversation_messages IN ACCESS SHARE MODE'))
        with pytest.raises(RuntimeError) as exc:
            _run_upgrade(db, module)
    finally:
        tx.rollback()
        holder.close()
    message = str(exc.value)
    assert "could not lock entity_conversation_messages in 5 attempts" in message
    assert "pg_stat_activity" in message
    assert waits == [2, 4, 6, 8]  # four waits between five attempts, growing
    # The failed attempts left the caller's transaction usable (each rolled back its savepoint).
    assert db.execute(text("select 1")).scalar() == 1
