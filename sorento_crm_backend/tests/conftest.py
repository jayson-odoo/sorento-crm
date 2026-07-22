"""Global pytest fixtures / compatibility shims for the backend test suite.

The suite runs most unit tests against an in-memory **sqlite** engine, but the
ORM models declare Postgres-specific column types. When the full suite runs,
globally-registered SQLAlchemy metadata from many modules is emitted through a
single `create_all`, and sqlite's DDL compiler has no `visit_JSONB` /
`visit_ARRAY` — raising `AttributeError: 'SQLiteTypeCompiler' object has no
attribute 'visit_JSONB'` and cascading ~300 failures that have nothing to do
with the test under exercise.

Teach the sqlite dialect to render the Postgres-only types as their nearest
sqlite equivalent. This is DDL-only (type affinity); the values round-trip as
JSON/text, which is all the sqlite-backed unit tests need. Postgres-backed
tests (live DB) are unaffected — this compiler only fires for the sqlite
dialect.
"""
import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


def _sweep_orphan_scratch_schemas():
    """Drop every ``zzt_*`` scratch schema left by a prior run.

    The end-of-session drop below only fires if the process exits cleanly. A
    killed run -- a timeout, an interrupted agent, a crash -- leaves its ~199
    table schema behind, and those pile up (105 had accumulated across this
    migration's many interrupted runs). Sweeping at session START, before any
    test builds a new one, keeps the shared database from filling with them
    regardless of how the previous run died.
    """
    try:
        from sqlalchemy import text
        from app.database import engine

        admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            names = [
                r[0]
                for r in admin.execute(
                    text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'zzt_%'")
                )
            ]
            for name in names:
                admin.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        finally:
            admin.close()
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def _blank_schema_lifecycle():
    """Sweep stale scratch schemas before the run, drop this run's after it.

    Two halves because the two failure modes differ: the sweep handles schemas
    a *previous* killed run left behind; the drop handles *this* run's schema on
    a clean exit.
    """
    _sweep_orphan_scratch_schemas()
    yield
    try:
        from tests._pg_fixture import drop_blank_schema

        drop_blank_schema()
    except Exception:
        pass


_ORIGINAL_COLUMN_TYPES: dict = {}


def _snapshot_column_types():
    """Record every model column's declared type, once, before any test runs."""
    if _ORIGINAL_COLUMN_TYPES:
        return
    try:
        from app.database import Base
        from app import models  # noqa: F401  register every table

        for table in Base.metadata.tables.values():
            for column in table.columns:
                _ORIGINAL_COLUMN_TYPES[(table.key, column.key)] = (
                    column.type,
                    column.server_default,
                )
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _restore_column_types():
    """Undo any test's in-place rewrite of the shared model metadata.

    Several sqlite fixtures still do this in their setup:

        if isinstance(col.type, (JSONB, ARRAY)):
            col.type = JSON()

    ``Model.__table__`` is process-global and those rewrites were never undone.
    While the whole suite ran on sqlite that was invisible. Now that converted
    tests run on Postgres in the same process, one shimmed module leaves later
    tests binding JSON into columns Postgres types as ``varchar[]``:

        column "notify_stock_role_ids" is of type character varying[]
        but expression is of type json

    The symptom lands in files that contain no sqlite at all and only in
    full-suite runs -- test_sla_takeover_cooldown and test_sla_kpi both failed
    this way, from a shim in test_chat_latency.

    Restoring before each test makes the two substrates coexist: a shimming
    fixture still re-applies its rewrite for its own test, and the next test
    starts from the real schema. Once no shims remain this becomes a no-op that
    costs one dict walk per test, and it keeps a future one from silently
    corrupting its neighbours.
    """
    _snapshot_column_types()
    for (table_key, column_key), (col_type, server_default) in _ORIGINAL_COLUMN_TYPES.items():
        try:
            from app.database import Base

            column = Base.metadata.tables[table_key].columns[column_key]
            if column.type is not col_type:
                column.type = col_type
                column.server_default = server_default
        except Exception:
            pass
    yield


_IDEMP_REDIS = []  # process-wide cache: [client] or [None]


def _idempotency_redis():
    if not _IDEMP_REDIS:
        try:
            from app.config import settings as _settings
            import redis as _redis

            _IDEMP_REDIS.append(_redis.from_url(_settings.redis_url, decode_responses=True))
        except Exception:
            _IDEMP_REDIS.append(None)
    return _IDEMP_REDIS[0]


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset leak-prone process-global / contextvar state after every test so
    ordering can't pollute. The dominant offender: an impersonation test sets a
    non-UUID audit actor (`set_audit_context("REAL_ADMIN")`) that, uncleared,
    leaks into later live-Postgres tests whose audit writes cast it to `uuid`
    and fail. Also clears the lookup-binding TTL cache."""
    yield
    try:
        from app.audit_context import set_audit_context

        set_audit_context(None, None)
    except Exception:
        pass
    try:
        from app.services.lookup_validator import _cache_clear

        _cache_clear()
    except Exception:
        pass
    try:
        # The RBAC permission cache (`_rbac_cache`, 30s TTL) is a process global.
        # Tests reuse user ids (e.g. a superadmin seeded under a fixed id) across
        # files; a stale non-superadmin `role_slugs`/`perm` entry cached by an
        # earlier test makes a later route's superadmin bypass miss and query the
        # `user_permissions` table — which many sqlite fixtures deliberately omit,
        # yielding "no such table: user_permissions". Clearing per test removes
        # the cross-test leak. Prod is unaffected (this only runs under pytest).
        from app.services.user_service import invalidate_rbac_cache

        invalidate_rbac_cache()
    except Exception:
        pass
    try:
        # The idempotency middleware caches 2xx responses in Redis for
        # ``idempotency_result_ttl`` seconds, keyed by a hash of (session, method,
        # path, body). Two route tests that POST the SAME body to the SAME endpoint
        # within that window collide: the second gets the first's cached response
        # (e.g. an escalate test at max-tier receives a prior test's "escalated"
        # payload). Flush the ``idemp:*`` keys after each test so ordering can't leak
        # a cached reply. Best-effort: no Redis in some envs → skip. The client is
        # cached process-wide to avoid a reconnect per test.
        _r = _idempotency_redis()
        if _r is not None:
            _keys = list(_r.scan_iter(match="idemp:*", count=500))
            if _keys:
                _r.delete(*_keys)
    except Exception:
        pass


def _prewarm_audit_table_cache_on_create():
    """Pre-warm the audit-table-existence cache at ``create_all`` time.

    ``audit_service._audit_table_exists`` lazily runs ``inspect(bind).has_table``
    the first time an audited flush happens. In the test suite the bind is a
    sqlite ``StaticPool`` engine that shares ONE dbapi connection between the
    fixture session and the route thread. Running that ``has_table`` SELECT on the
    shared connection *in the middle of a flush* corrupts the flush transaction —
    a freshly-seeded ``user_roles`` row silently disappears (via the
    ``UserRole.user_assignments`` delete-orphan cascade), which then makes the
    superadmin bypass fall through and query the (subset-schema) ``user_permissions``
    table → "no such table: user_permissions".

    Production uses a real connection pool (distinct connections), so the mid-flush
    ``has_table`` never touches the flush connection and this problem cannot occur.

    Fix: populate the per-engine cache during ``create_all`` (which runs in its own
    DDL transaction, before any ORM flush), so ``has_table`` never fires during a
    flush. We derive existence from the list of tables actually created — no SQL —
    so it is safe even on the shared connection. This is test-only (create_all on
    the model metadata is not part of the production request path)."""
    from sqlalchemy import event
    from app.database import Base

    @event.listens_for(Base.metadata, "after_create")
    def _after_create(_target, connection, **kw):  # noqa: ANN001
        try:
            from app.services import audit_service

            created = {t.name for t in kw.get("tables", []) or []}
            engine = getattr(connection, "engine", connection)
            key = id(engine)
            has = audit_service._audit_table_cache.get(key, False) or ("audit_logs" in created)
            audit_service._audit_table_cache[key] = has
        except Exception:
            pass


_prewarm_audit_table_cache_on_create()


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(element, compiler, **kw):  # noqa: ANN001
    # sqlite has no array type; store as JSON text (affinity only — the
    # sqlite-backed tests that touch these columns treat them as opaque).
    return "JSON"
