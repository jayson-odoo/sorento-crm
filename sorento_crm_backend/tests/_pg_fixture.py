"""A Postgres session that rolls back, for tests of real database behaviour.

sqlite is the wrong substrate for anything transactional here. It does not
share Postgres's SAVEPOINT semantics, its constraint enforcement differs, and
`schema="scm"` models cannot be created on it at all — so a sqlite test can
pass while proving nothing about production, and break the moment an unrelated
module registers a global Session listener.

Everything runs inside one outer transaction that is rolled back at teardown, so
`begin_nested()` becomes a real nested savepoint and no test data survives —
verified against the shared local database, which holds real records.

**Scope your assertions.** The tables are not empty. Counting all rows in
`warehouses` will pick up production data, so filter by whatever prefix the test
creates. `unique_code()` exists to make that easy and collision-free.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.database import Base, engine

# Prefix reserved for test-created rows. Distinctive enough to filter on and to
# recognise if one ever escapes a rollback.
TEST_PREFIX = "ZZT"


def unique_code(stem: str = "") -> str:
    """A collision-free code for a test-created record."""
    return f"{TEST_PREFIX}-{stem}-{uuid.uuid4().hex[:8]}" if stem else f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}"


@contextmanager
def pg_session() -> Session:
    """Yield a session whose work is discarded at the end."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _globally_required_tables():
    """Tables the app's global SQLAlchemy listeners query on every flush.

    Importing ``app.main`` -- which the TestClient suites must do -- registers
    audit and lookup-validation listeners. Those fire on any flush and query
    these tables regardless of what the test is doing, so a scratch schema
    without them fails with UndefinedTable on the first insert.
    """
    from app.models.audit import AuditLog
    from app.models.lookup import LookupBinding, LookupOption, LookupSet

    return [
        LookupBinding.__table__,
        LookupOption.__table__,
        LookupSet.__table__,
        AuditLog.__table__,
    ]


def _with_dependencies(tables):
    """Close the set over foreign keys, in dependency order.

    Anything reachable in the default schema is included; tables in another
    schema (the ``scm.*`` models) are skipped, since the translate map only
    redirects the default one.
    """
    seen: dict[str, object] = {}

    def visit(table):
        if table.key in seen or table.schema is not None:
            return
        seen[table.key] = table
        for fk in table.foreign_keys:
            visit(fk.column.table)

    for table in tables:
        visit(table)

    return list(seen.values())


@contextmanager
def pg_empty_schema(tables) -> Session:
    """A session over an *empty* set of the given tables, still on Postgres.

    Some behaviour is only meaningful against a blank slate -- seeding, chiefly:
    "creates one integration per entry" cannot be asserted on the real database,
    where migration 297 already created them and the seed is a no-op.

    sqlite was the old way to get that blank slate, at the cost of testing
    against a schema with different types, no enforced foreign keys, and no
    JSONB. Instead this creates the tables in a throwaway Postgres schema via
    ``schema_translate_map``, so the DDL is the real DDL and only the data is
    empty. The schema is dropped afterwards.

    ``tables`` is an explicit list because the full metadata cannot be emitted
    wholesale: the SCM models declare ``schema="scm"``, which the translate map
    would not redirect. Whatever those tables reference is pulled in for you --
    Postgres validates FK targets at DDL time where sqlite did not, so an
    incomplete list fails loudly here instead of silently not enforcing.
    """
    tables = _with_dependencies(list(tables) + _globally_required_tables())
    name = f"zzt_scratch_{uuid.uuid4().hex[:12]}"
    admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    admin.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    admin.close()

    scoped = engine.execution_options(schema_translate_map={None: name})
    connection = scoped.connect()
    try:
        # create_all rather than per-table create(): it sorts by dependency and
        # breaks FK cycles with a follow-up ALTER, which a naive loop cannot.
        Base.metadata.create_all(connection, tables=tables, checkfirst=True)
        connection.commit()

        session = Session(bind=connection)
        try:
            yield session
        finally:
            session.close()
    finally:
        connection.close()
        cleanup = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        cleanup.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        cleanup.close()
