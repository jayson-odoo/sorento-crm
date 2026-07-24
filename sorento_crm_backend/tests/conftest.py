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
            # Key by the engine OBJECT, matching audit_service's weak-keyed cache.
            # It used to key by id(engine); CPython recycles those addresses, so a
            # new engine could inherit a dead one's answer.
            has = audit_service._audit_table_cache.get(engine, False) or ("audit_logs" in created)
            audit_service._audit_table_cache[engine] = has
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
