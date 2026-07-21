"""Test-only helper: make ``Base.metadata.create_all`` succeed on sqlite.

Some model columns declare postgres-specific server defaults such as
``text("'[]'::jsonb")``. The ``::jsonb`` cast is invalid SQL on sqlite and
makes a full ``Base.metadata.create_all(engine)`` blow up with
``OperationalError: unrecognized token: ":"``.

``create_all_sqlite_safe`` temporarily strips any server default whose SQL text
contains a postgres cast (``::``) for the duration of the DDL emit, then restores
it. The restore runs in a ``finally`` and completes synchronously before the
fixture yields, so tests that hit a real postgres later in the (single-threaded)
run see the untouched model metadata. This is a no-op against postgres — those
casts are only ever emitted on sqlite test binds.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import event


def _register_pg_functions(engine) -> None:
    """Register postgres builtins used inside functional indexes on the sqlite bind.

    ``customers`` declares a unique index on ``lower(btrim(...))``. sqlite has no
    ``btrim``, so the CREATE INDEX fails during ``create_all``. Registering a
    deterministic python shim lets the expression index compile and evaluate.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # pragma: no cover - trivial glue
        dbapi_conn.create_function(
            "btrim", 1, lambda s: s.strip() if s is not None else None, deterministic=True
        )
        dbapi_conn.create_function(
            "btrim",
            2,
            lambda s, chars: s.strip(chars) if s is not None else None,
            deterministic=True,
        )


def _has_pg_cast(server_default) -> bool:
    if server_default is None:
        return False
    arg = getattr(server_default, "arg", None)
    text = getattr(arg, "text", None)
    return isinstance(text, str) and "::" in text


@contextmanager
def _neutralized_pg_defaults(metadata):
    stashed = []
    for table in metadata.tables.values():
        for column in table.columns:
            if _has_pg_cast(column.server_default):
                stashed.append((column, column.server_default))
                column.server_default = None
    try:
        yield
    finally:
        for column, original in stashed:
            column.server_default = original


def enable_sqlite_savepoints(engine) -> None:
    """Make SAVEPOINT / ``begin_nested()`` work on sqlite.

    pysqlite does not emit BEGIN where SQLAlchemy expects it, so a nested
    transaction can fail with "no such savepoint" on RELEASE. Whether it does is
    order-dependent -- the same test passes alone and fails after another module
    has touched the engine -- which makes it a nasty thing to debug later.

    This is the workaround from SQLAlchemy's pysqlite notes: disable the
    driver's implicit transaction handling and emit BEGIN ourselves. Postgres
    needs none of this; production savepoints work natively.
    """
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _disable_implicit_begin(dbapi_connection, _record):  # pragma: no cover - infra
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_begin(conn):  # pragma: no cover - infra
        conn.exec_driver_sql("BEGIN")


def create_all_sqlite_safe(metadata, engine, tables=None) -> None:
    """Run ``metadata.create_all(engine)`` with pg-cast server defaults stripped.

    ``tables`` restricts creation to a specific list of ``Table`` objects. Pass it
    when the full metadata cannot be emitted on sqlite at all: the SCM models
    declare ``schema="scm"`` and sqlite has no schemas, so a whole-metadata
    create_all fails with "unknown database scm" regardless of type compatibility.
    """
    _register_pg_functions(engine)
    with _neutralized_pg_defaults(metadata):
        metadata.create_all(engine, tables=tables)
