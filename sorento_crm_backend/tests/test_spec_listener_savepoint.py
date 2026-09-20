"""RED tests pinning one defect: the product-spec re-derive listener fires on a
SAVEPOINT release, not only on the caller's OUTERMOST commit - and the re-derive it
fires reads through a FRESH `SessionLocal()` session that then blocks on the very row
lock the caller's own (still open) transaction holds.

`app/services/product_spec_change_listener.py`: `after_insert`/`after_update` on
`Product` collect codes into `session.info["_spec_codes_to_rederive"]` when a
DERIVATION_INPUT changed; a `Session` `after_commit` listener then pops them and calls
`rederive_codes(codes)`, which (<= 50 codes) runs `_rederive_inline` in a brand new
`SessionLocal()` and, through `product_spec_write.lock_product_code`, does
`SELECT products.id ... WHERE product_code = :code ... FOR UPDATE`.

SQLAlchemy's `SessionTransaction.commit()` dispatches `Session.after_commit` whenever
`self._parent is None OR self.nested` - i.e. on releasing a SAVEPOINT too, not only on
a real top-level commit (verified by reading
`venv/lib/python3.*/site-packages/sqlalchemy/orm/session.py::SessionTransaction.commit`
directly). `MasterIngestService._ingest_one` wraps every record in
`self.db.begin_nested()` (master_ingest_service.py ~754), so when a record changes a
DERIVATION_INPUT on an EXISTING product, releasing THAT record's savepoint fires the
listener while the caller's own outer transaction still holds the row lock from the
UPDATE. The fresh session's `FOR UPDATE` then waits on a lock its own caller holds -
seen live as pid A `idle in transaction` after `RELEASE SAVEPOINT`, pid B `active` on
the `FOR UPDATE`, 14 minutes, RQ worker wedged. It hits the dry-run preview AND the
real apply, and any push through `/external/ingest/products` that changes a
description.

Existing tests never saw it because their fixtures bind every session to ONE shared
connection (no lock conflict is possible between two sessions on the same connection).
This file is the first to give the listener TWO REAL Postgres connections with real
commits - a dedicated scratch schema (own `Base.metadata.create_all`, dropped at
module teardown, same `zzs_` scratch-schema convention as `tests/_pg_fixture.py`) and
a SEPARATE `Engine` (own connection pool, `lock_timeout` baked into every connection
it opens) that backs both the outer test session and the patched `app.database.
SessionLocal` `_rederive_inline` opens fresh. Two real engines pointed at the same
schema guarantee two distinct physical backends without relying on pool-checkout
timing.

HANG SAFETY: the red state of this bug is an unbounded wait. Two independent guards -
`lock_timeout=3s` on every connection this file's engine opens (so the blocked `FOR
UPDATE` fails fast on its own), and `_run_guarded` (a hard 20s wall-clock join on a
background thread, `pg_terminate_backend`-ing any backend still stuck on a lock if the
thread is still alive after that). Neither guard should ever fire in practice - the
listener swallows every exception (`_rederive_inline` never raises) - so the tests
assert observable, after-the-fact facts (whether the session was mid-savepoint, and
whether a THIRD connection can take a NOWAIT lock on the row) rather than expecting an
exception to surface.

Coder: keep `tests/test_product_spec_change_listener.py`,
`tests/test_product_spec_authored_write.py` and
`tests/test_product_spec_write_backstop.py` green - they exercise the same listener/
`lock_product_code` and already assume `register_product_spec_listeners()` may have
been called by an earlier test in the process.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import app.database as app_database
import app.services.product_spec_change_listener as listener
from app.config import settings
from app.database import Base, engine
from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.master_ingest_service import MasterIngestService

from tests._pg_fixture import SCRATCH_SCHEMA_PREFIX, unique_code

# Idempotent (module-global `_REGISTERED` guard) - safe even if an earlier test in
# this same process already called it.
listener.register_product_spec_listeners()

LOCK_TIMEOUT_MS = 3000
HANG_GUARD_SECONDS = 20.0


def _code(stem: str) -> str:
    return unique_code(stem)[:30]


# --------------------------------------------------------------------------------- #
# hang safety
# --------------------------------------------------------------------------------- #
def _terminate_blocked_backends() -> None:
    """Best-effort cleanup if the wall-clock guard below ever actually fires."""
    admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        admin.exec_driver_sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
        )
    finally:
        admin.close()


def _run_guarded(fn, *, timeout: float = HANG_GUARD_SECONDS):
    """Run `fn` in a thread; FAIL LOUDLY instead of hanging the suite if the
    savepoint-release deadlock-shape ever reproduces for real (``lock_timeout``
    above should already bound this to a few seconds - this is the backstop).
    Returns ``(value, elapsed_seconds)``.
    """
    box: dict = {}

    def _runner():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    start = time.monotonic()
    thread.start()
    thread.join(timeout)
    elapsed = time.monotonic() - start
    if thread.is_alive():
        _terminate_blocked_backends()
        thread.join(5)
        pytest.fail(
            f"did not return within {timeout}s wall clock - reproduces the "
            f"savepoint-release hang this file pins; terminated the blocked "
            f"backend(s) as cleanup"
        )
    if "error" in box:
        raise box["error"]
    return box["value"], elapsed


def _row_locked_elsewhere(functional_engine, product_id: str) -> bool:
    """True if some OTHER session currently holds a lock on this product row."""
    with functional_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(
                select(Product.id).where(Product.id == product_id).with_for_update(nowait=True)
            )
            return False
        except OperationalError:
            return True
        finally:
            trans.rollback()


# --------------------------------------------------------------------------------- #
# schema + engines - a dedicated scratch schema, two REAL connections
# --------------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def schema_map():
    name = f"{SCRATCH_SCHEMA_PREFIX}_specsp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    names = {
        None: name,
        "scm": f"{name}_scm",
        "dealer_kit": f"{name}_dealer_kit",
        "projects": f"{name}_projects",
        "chatbot": f"{name}_chatbot",
    }
    admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        for schema in names.values():
            admin.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    finally:
        admin.close()

    from app import models  # noqa: F401 - register every table on Base.metadata

    ddl_engine = engine.execution_options(schema_translate_map=names)
    with ddl_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        Base.metadata.create_all(conn, checkfirst=False)

    yield names

    cleanup = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        for schema in names.values():
            cleanup.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        cleanup.close()


@pytest.fixture(scope="module")
def functional_engine(schema_map):
    """A SEPARATE Engine (own pool), never the global `app.database.engine` - so a
    session from it and a session from another sessionmaker bound to it are ALWAYS
    two distinct physical backends, never the same connection handed out twice.
    `lock_timeout` is baked into `connect_args` so EVERY connection this engine ever
    opens has it from the first statement, with no per-session `SET` needed.
    """
    base = create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        connect_args={"options": f"-c timezone=utc -c lock_timeout={LOCK_TIMEOUT_MS}"},
    )
    scoped = base.execution_options(schema_translate_map=schema_map)
    yield scoped
    base.dispose()


@pytest.fixture(scope="module")
def session_factory(functional_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=functional_engine)


@pytest.fixture()
def patched_session_local(session_factory, monkeypatch):
    """`_rederive_inline` does `from app.database import SessionLocal` fresh on every
    call, so patching the module ATTRIBUTE (not a captured reference) is what it
    actually sees - a session on the SAME schema as the caller's, but a different
    physical connection.
    """
    monkeypatch.setattr(app_database, "SessionLocal", session_factory)
    return session_factory


@pytest.fixture()
def db(session_factory, schema_map):
    """The outer, caller-side session for one test. `search_path` is set explicitly
    (a plain `SET`, never `SET LOCAL` - this session does REAL commits, and `SET
    LOCAL` resets at the end of each one) because `MasterIngestService` issues raw
    `text()` SQL against bare table names in a few helpers (`_finalize_product_
    derived`, `_diff`) - `schema_translate_map` only rewrites ORM/Core constructs,
    never a hand-written SQL string, exactly the gotcha `tests/_pg_fixture.py`
    documents for `blank_session()`.
    """
    session = session_factory()
    set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
    search_path = ", ".join(
        f'"{schema_map[key]}"' for key in (None, "scm", "dealer_kit", "chatbot", "projects")
    )
    session.execute(text(f"SET search_path TO {search_path}"))
    try:
        yield session
    finally:
        session.close()


def _seed_product(db, *, description: str) -> tuple[str, str]:
    """One category, one uom, one product - all real, all committed."""
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=_code("ZZTSPCAT"),
        category_name="Spec savepoint test",
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=_code("ZZTSPUOM"),
        uom_name="Each",
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add_all([category, uom])
    db.flush()

    code = _code("ZZTSPPRD")
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(product)
    db.commit()
    return str(product.id), code


# --------------------------------------------------------------------------------- #
# T1 / T2 - through the real ESB ingest path (MasterIngestService)
# --------------------------------------------------------------------------------- #
class TestRederiveThroughMasterIngestService:
    def test_dry_run_preview_returns_promptly_and_must_not_rederive_mid_savepoint(
        self, db, patched_session_local, monkeypatch
    ):
        """T1: a dry-run preview changing an existing product's description. Today's
        listener fires `rederive_codes` DURING the record's own savepoint release,
        while the whole preview's outer transaction (rolled back at the very end of
        `ingest()`) is still open - the fresh session it opens then blocks on the row
        lock this same transaction holds. `lock_timeout` bounds the wait to a few
        seconds; the assertion pins the CONTRACT (must not fire mid-savepoint), not
        the timing.
        """
        product_id, code = _seed_product(db, description="Old widget description")

        calls: list[dict] = []
        real_rederive_codes = listener.rederive_codes

        def _spy(codes):
            calls.append({"codes": set(codes), "in_nested": db.in_nested_transaction()})
            return real_rederive_codes(codes)

        monkeypatch.setattr(listener, "rederive_codes", _spy)

        svc = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID)
        record = {
            "source_ref": f"AC-{code}",
            "code": code,
            "name": "New widget description text",
        }

        result, elapsed = _run_guarded(lambda: svc.ingest("products", [record], dry_run=True))

        assert elapsed < 10.0, (
            f"took {elapsed:.1f}s - lock_timeout ({LOCK_TIMEOUT_MS}ms) should bound "
            f"the blocked FOR UPDATE to a few seconds, not hang"
        )
        assert result.updated == 1, result.records[0].errors
        assert len(calls) == 1, "the description change must still queue exactly one code"
        assert calls[0]["codes"] == {code}
        assert calls[0]["in_nested"] is False, (
            "rederive_codes fired while the session was still inside THIS RECORD's "
            "own SAVEPOINT, before the preview's outer transaction had resolved - a "
            "fresh SessionLocal() session then blocks on the lock that same "
            "transaction still holds"
        )

    def test_real_ingest_rederive_must_wait_until_after_the_outermost_commit(
        self, db, patched_session_local, functional_engine, monkeypatch
    ):
        """T2: same shape, a real (non-dry-run) push. At the moment `rederive_codes`
        is invoked, a THIRD connection must be able to take a NOWAIT lock on the
        product row - proof the row is no longer held by an open transaction. Today
        it fires before the caller's own `db.commit()`, so the row is still locked by
        the very session that is about to call `rederive_codes`.
        """
        product_id, code = _seed_product(db, description="Old widget description")

        calls: list[dict] = []
        real_rederive_codes = listener.rederive_codes

        def _spy(codes):
            calls.append(
                {
                    "codes": set(codes),
                    "in_nested": db.in_nested_transaction(),
                    "row_locked_by_caller": _row_locked_elsewhere(functional_engine, product_id),
                }
            )
            return real_rederive_codes(codes)

        monkeypatch.setattr(listener, "rederive_codes", _spy)

        svc = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID)
        record = {
            "source_ref": f"AC-{code}",
            "code": code,
            "name": "Newer widget description text",
        }

        try:
            result, elapsed = _run_guarded(
                lambda: svc.ingest("products", [record], dry_run=False)
            )

            assert elapsed < 10.0, f"took {elapsed:.1f}s - should be bounded by lock_timeout"
            assert result.updated == 1, result.records[0].errors
            assert len(calls) == 1
            assert calls[0]["codes"] == {code}
            assert calls[0]["in_nested"] is False, (
                "fired during the record's own savepoint release, before the "
                "outermost commit"
            )
            assert calls[0]["row_locked_by_caller"] is False, (
                "the product row was STILL LOCKED by this same (uncommitted) "
                "transaction at the moment rederive_codes ran - proof it fired "
                "before the outermost commit, not after"
            )
        finally:
            # Never actually reaches a real commit under today's code (dry_run=False
            # still leaves the caller's own commit to a later step this test never
            # takes) - rolled back either way so nothing survives this test.
            db.rollback()


# --------------------------------------------------------------------------------- #
# T3 - a dry run must discard, never derive
# --------------------------------------------------------------------------------- #
class TestDryRunDiscardsPendingCodes:
    def test_a_rolled_back_dry_run_must_never_trigger_a_rederive_at_all(self, db, monkeypatch):
        """T3: nothing a dry run does survives, so nothing it changed should ever be
        spent on a re-derive - today's listener queues and fires regardless of
        `dry_run`, wasting the derive on a description that is about to be rolled
        back (and racing a fresh session's read against values that will not exist a
        moment later). No real derive needs to run here - a no-op spy is enough to
        pin "was it invoked at all".
        """
        product_id, code = _seed_product(db, description="Old widget description")

        calls: list[list[str]] = []
        monkeypatch.setattr(listener, "rederive_codes", lambda codes: calls.append(sorted(codes)))

        svc = MasterIngestService(db, company_id=DEFAULT_COMPANY_ID)
        record = {
            "source_ref": f"AC-{code}",
            "code": code,
            "name": "Dry run description change",
        }
        result = svc.ingest("products", [record], dry_run=True)

        assert result.updated == 1, result.records[0].errors
        assert calls == [], "a dry run discards everything - it must not have queued a rederive"
        assert listener._PENDING_KEY not in db.info

        # An unrelated later commit on the SAME session must not replay the
        # already-discarded code either.
        db.commit()
        assert calls == [], "a later, unrelated commit on the same session must not resurrect it"


# --------------------------------------------------------------------------------- #
# T4 / T5 - the minimal reproduction, no ingest service at all
# --------------------------------------------------------------------------------- #
class TestListenerFiresOnlyAfterTheOutermostCommit:
    """Pins the rule at the ONE place every caller (`MasterIngestService` included)
    goes through - no adoption matching, no ESB payload, just the ORM event chain the
    listener itself hooks.
    """

    def test_a_savepoint_release_alone_must_not_fire_the_listener(self, db, monkeypatch):
        """T4: `with db.begin_nested(): ...` releases a SAVEPOINT, not the session's
        outer transaction - that release alone must not fire the listener. It does
        today, because `SessionTransaction.commit()` dispatches `Session.after_commit`
        whenever `self.nested` is true, not only for a real top-level commit.
        """
        product_id, code = _seed_product(db, description="Old widget description")

        calls: list[list[str]] = []
        monkeypatch.setattr(listener, "rederive_codes", lambda codes: calls.append(sorted(codes)))

        product = db.get(Product, product_id)
        with db.begin_nested():
            product.description = "Changed inside a savepoint"

        assert calls == [], (
            "a SAVEPOINT release alone must not trigger a re-derive - the session's "
            "own outer transaction has not resolved yet"
        )

        db.commit()

        assert calls == [[code]], "the outermost commit must fire it exactly once"

    def test_an_ordinary_commit_with_no_savepoint_still_fires_once(self, db, monkeypatch):
        """T5 (guard, may already be green): the ordinary, no-savepoint path must be
        unaffected by whatever fixes T4.
        """
        product_id, code = _seed_product(db, description="Old widget description")

        calls: list[list[str]] = []
        monkeypatch.setattr(listener, "rederive_codes", lambda codes: calls.append(sorted(codes)))

        product = db.get(Product, product_id)
        product.description = "Changed with no savepoint at all"
        db.commit()

        assert calls == [[code]], "an ordinary top-level commit must still queue exactly one code"
