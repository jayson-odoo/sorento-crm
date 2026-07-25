"""A Postgres session that rolls back, for tests of real database behaviour.

sqlite is the wrong substrate for anything transactional here. It does not
share Postgres's SAVEPOINT semantics, its constraint enforcement differs, and
`schema="scm"` models cannot be created on it at all -- so a sqlite test can
pass while proving nothing about production, and break the moment an unrelated
module registers a global Session listener.

Everything runs inside one outer transaction that is rolled back at teardown, so
`begin_nested()` becomes a real nested savepoint and no test data survives --
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


_BLANK = {}


def blank_schema_engine():
    """An Engine over a blank copy of the **entire** schema, built once per run.

    This is the replacement for ``create_engine("sqlite:///:memory:")`` plus
    ``Base.metadata.create_all(engine)``, which was the dominant fixture shape
    in this suite. It gives the same thing that pattern was reaching for -- an
    empty database with every table present -- without sqlite's differences in
    typing, constraint enforcement and transaction semantics.

    All 199 tables emit in well under a second, so the cost is paid once for the
    whole session rather than per test. Data isolation is the caller's job: use
    ``blank_session()``, which discards writes.

    ``scm`` is translated alongside the default schema, so the ``scm.*`` models
    -- which could not be created on sqlite at all -- are included.
    """
    if "engine" not in _BLANK:
        from app import models  # noqa: F401  register every model's table

        name = f"zzt_blank_{uuid.uuid4().hex[:10]}"
        admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        admin.exec_driver_sql(f'CREATE SCHEMA "{name}"')
        admin.exec_driver_sql(f'CREATE SCHEMA "{name}_scm"')
        admin.close()

        scoped = engine.execution_options(
            schema_translate_map={None: name, "scm": f"{name}_scm"}
        )
        with scoped.connect() as connection:
            Base.metadata.create_all(connection, checkfirst=False)
            connection.commit()

        _BLANK["engine"] = scoped
        _BLANK["name"] = name
    return _BLANK["engine"]


def drop_blank_schema():
    """Tear down the shared blank schema. Called from the session fixture."""
    name = _BLANK.pop("name", None)
    _BLANK.pop("engine", None)
    if name:
        admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        admin.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        admin.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}_scm" CASCADE')
        admin.close()


@contextmanager
def blank_session() -> Session:
    """A session over the blank schema whose writes are all discarded.

    ``join_transaction_mode="create_savepoint"`` is what makes this work with
    tests that call ``commit()``: the session's commits land on a savepoint
    inside the outer transaction, so they are visible to the test and to any
    code under it, and the outer rollback still discards everything. Without it
    a committing test would leak rows into the next one.
    """
    connection = blank_schema_engine().connect()
    transaction = connection.begin()

    # schema_translate_map only rewrites ORM/Table constructs. A route issuing
    # raw text() SQL -- and several do -- resolves its table names through
    # search_path instead, which would send those writes to the REAL public
    # tables while the test read an empty scratch schema and saw nothing.
    #
    # That failure is silent and writes live data, so pin search_path too. SET
    # LOCAL scopes it to this transaction, which is discarded below.
    name = _BLANK["name"]
    connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", "{name}_scm"')

    session = Session(bind=connection, join_transaction_mode="create_savepoint")
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
