"""Audit capture is best-effort and loud (owner ruling 28 Sep 2026 19:1x MYT, PR #1299).

"hmm if writing to audit fails, the save shouldn't fail, right? for business flow shouldn't
fail if the audit writing fail?" then "go". Each test names its UAC line
(`documentation/plans/audit/audit-standard-26sep-acceptance-criteria.md`, "Best-effort
capture"). The forced failure is a real Postgres error (a NUL character JSONB refuses), so the
transaction is genuinely aborted at the audit INSERT, the case a savepoint has to survive.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import AuditActor, clear_actor, set_trace_id, stamp_actor
from app.config import settings
from app.models.audit import AuditLog, AuditTrailGap
from app.models.integration import IntegrationLog
from app.models.product import Brand
from app.services import audit_service
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners

from ._pg_fixture import blank_session, unique_code

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()


@pytest.fixture(autouse=True)
def _no_leaked_context():
    yield
    clear_actor()
    set_trace_id(None)


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def poisoned(monkeypatch):
    """Every audit payload carries a NUL, which Postgres JSONB rejects at INSERT."""
    real = audit_service._redact

    def _poison(values):
        return None if values is None else {"poison": "\u0000", "real": real(values)}

    monkeypatch.setattr(audit_service, "_redact", _poison)


def _audit_rows(db, entity_id):
    return db.query(AuditLog).filter(AuditLog.entity_id == str(entity_id)).all()


def _failures(db):
    return db.execute(select(IntegrationLog).where(IntegrationLog.integration_channel == "audit")).scalars().all()


def _new_failures(db, before):
    """The audit-channel rows written since ``before`` (a list from ``_failures``)."""
    seen = {f.id for f in before}
    return [f for f in _failures(db) if f.id not in seen]


def _gaps(db, entity_id):
    return db.query(AuditTrailGap).filter(AuditTrailGap.entity_id == str(entity_id)).all()


def _new_brand(db):
    brand = Brand(brand_code=unique_code("B")[:50], brand_name="Alpha")
    db.add(brand)
    db.flush()
    return brand


class TestBestEffort:
    def test_be01_a_failed_flush_capture_keeps_the_business_row_and_logs_once(self, db, poisoned):
        """AC-S0-30: the audit INSERT fails, the UPDATE commits, one integration_log row."""
        stamp_actor(AuditActor(actor_type="user", user_id="00000000-0000-4000-8000-000000000001"), db=db)
        brand = _new_brand(db)
        db.expire_all()
        failures_before = _failures(db)
        brand = db.get(Brand, brand.id)
        brand.brand_name = "Beta"
        db.commit()  # must not raise

        db.expire_all()
        assert db.get(Brand, brand.id).brand_name == "Beta"
        assert not [r for r in _audit_rows(db, brand.id) if r.action == "UPDATE"]
        failures = _new_failures(db, failures_before)
        assert len(failures) == 1, failures
        log = failures[0]
        assert log.status == "failed"
        assert log.business_table == "brands"
        assert log.external_reference == str(brand.id)
        assert log.error_message
        assert "00000000-0000-4000-8000-000000000001" in (log.request_payload or "")

    def test_be02_the_saved_record_is_marked_missing_its_trail(self, db, poisoned):
        """AC-S0-30: one open gap row for the record whose trail was lost."""
        brand = _new_brand(db)
        db.commit()
        db.expire_all()
        gaps = [g for g in _gaps(db, brand.id) if g.backfilled_at is None]
        assert [(g.entity_type, g.action) for g in gaps] == [("brands", "CREATE")]
        assert gaps[0].integration_log_id

    def test_be03_a_failed_bulk_capture_keeps_the_bulk_update(self, db, poisoned):
        """AC-S0-30: the ``do_orm_execute`` path, same contract."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(audit_service, "_redact", lambda v: v)
            brand = _new_brand(db)
            db.commit()
        failures_before = _failures(db)
        db.query(Brand).filter(Brand.id == brand.id).update({"brand_name": "Gamma"}, synchronize_session=False)
        db.commit()

        db.expire_all()
        assert db.get(Brand, brand.id).brand_name == "Gamma"
        assert not [r for r in _audit_rows(db, brand.id) if r.action == "UPDATE"]
        assert len(_new_failures(db, failures_before)) == 1
        assert [g.action for g in _gaps(db, brand.id)] == ["UPDATE"]

    def test_be04_a_healthy_capture_writes_no_failure(self, db):
        """The savepoint changes nothing on the happy path."""
        failures_before = _failures(db)
        brand = _new_brand(db)
        brand.brand_name = "Delta"
        db.commit()
        assert {r.action for r in _audit_rows(db, brand.id)} == {"CREATE", "UPDATE"}
        assert _new_failures(db, failures_before) == []
        assert not _gaps(db, brand.id)

    def test_be05_the_health_summary_counts_open_gaps(self, db, poisoned):
        """AC-S0-31: the system health page's audit card carries the missing-trail count."""
        from datetime import datetime, timedelta

        from app.api.v1.system.health import _audit_activity_health

        now = datetime.utcnow()
        before = _audit_activity_health(db, now - timedelta(hours=24), now).missing_trail
        _new_brand(db)
        db.commit()
        after = _audit_activity_health(db, now - timedelta(hours=24), datetime.utcnow()).missing_trail
        assert after == before + 1


    def test_be15_a_python_error_in_a_hook_is_recorded_not_raised(self, db, monkeypatch):
        """AC-S0-30: the registered listeners guard what the savepoints cannot, a Python
        error outside the database work, in all three hooks."""
        def _boom(*a, **k):
            raise TypeError("hook bug")

        failures_before = _failures(db)
        monkeypatch.setattr(audit_service, "_session_before_flush", _boom)
        monkeypatch.setattr(audit_service, "_session_after_flush", _boom)
        monkeypatch.setattr(audit_service, "_session_do_orm_execute", _boom)
        brand = _new_brand(db)
        db.query(Brand).filter(Brand.id == brand.id).update({"brand_name": "Theta"}, synchronize_session=False)
        db.commit()
        db.expire_all()
        assert db.get(Brand, brand.id).brand_name == "Theta"
        new = _new_failures(db, failures_before)
        assert new and all(f.error_code == "TypeError" for f in new)


class TestOffSwitch:
    def test_be06_capture_off_writes_no_audit_row_and_no_failure(self, db, monkeypatch):
        """AC-S0-32: AUDIT_CAPTURE_ENABLED=false skips capture, read at write time."""
        monkeypatch.setattr(settings, "audit_capture_enabled", False)
        failures_before = _failures(db)
        brand = _new_brand(db)
        brand.brand_name = "Epsilon"
        db.flush()
        db.query(Brand).filter(Brand.id == brand.id).update({"brand_name": "Zeta"}, synchronize_session=False)
        audit_service.record(db, event="test.off", entity_type="brands", entity_id=str(brand.id))
        db.commit()
        assert _audit_rows(db, brand.id) == []
        assert _new_failures(db, failures_before) == []
        assert not _gaps(db, brand.id)

        monkeypatch.setattr(settings, "audit_capture_enabled", True)
        brand.brand_name = "Eta"
        db.commit()
        assert [r.action for r in _audit_rows(db, brand.id)] == ["UPDATE"]

    def test_be07_the_setting_defaults_on(self):
        from app.config import Settings

        assert Settings.model_fields["audit_capture_enabled"].default is True


# --- Migration: lock_timeout, statement_timeout, bounded retry (AC-S0-24b) ---


def _load(name):
    spec = importlib.util.spec_from_file_location(f"m_be_{name}", VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Bind:
    def __init__(self, lock_failures=0):
        self.statements: list[tuple[str, bool]] = []
        self.autocommit = False
        self.lock_failures = lock_failures

    def execute(self, clause, *a, **k):
        sql = str(clause)
        self.statements.append((sql, self.autocommit))
        if sql.upper().startswith("LOCK TABLE") and self.lock_failures:
            self.lock_failures -= 1
            import sqlalchemy as sa

            class _Orig(Exception):
                pgcode = "55P03"

            raise sa.exc.OperationalError(sql, {}, _Orig("canceling statement due to lock timeout"))

        class _R:
            def scalar(self_inner):
                return None

        return _R()


class _Op:
    def __init__(self, bind):
        self._bind = bind
        outer = self

        class _Ctx:
            from contextlib import contextmanager

            @contextmanager
            def autocommit_block(self):
                outer._bind.autocommit = True
                try:
                    yield
                finally:
                    outer._bind.autocommit = False

        self._ctx = _Ctx()

    def get_bind(self):
        return self._bind

    def get_context(self):
        return self._ctx

    def execute(self, sql, *a, **k):
        return self._bind.execute(sql)

    def drop_column(self, table, column):
        self._bind.statements.append((f"DROP COLUMN {table}.{column}", self._bind.autocommit))


def _upgrade(lock_failures=0, monkeypatch=None):
    module = _load("aud_0001_audit_standard_s0")
    bind = _Bind(lock_failures)
    module.op = _Op(bind)
    if monkeypatch is not None:
        monkeypatch.setattr(module.time, "sleep", lambda s: None)
    module.upgrade()
    return module, bind.statements


class TestMigrationLockTimeout:
    def test_be08_lock_and_statement_timeout_precede_the_first_ddl(self):
        """AC-S0-24b: a waiting ALTER on audit_logs never queues every save behind it."""
        module, statements = _upgrade()
        sqls = [s for s, _ in statements]
        first_ddl = next(i for i, s in enumerate(sqls) if s.upper().startswith(("ALTER TABLE", "LOCK TABLE")))
        before = " ".join(sqls[:first_ddl]).lower()
        assert f"'lock_timeout', '{module.LOCK_TIMEOUT}'" in before
        assert f"'statement_timeout', '{module.STATEMENT_TIMEOUT}'" in before
        assert module.LOCK_TIMEOUT == "5s"

    def test_be09_no_timeout_is_set_inside_the_autocommit_block(self):
        """The CONCURRENTLY builds and VALIDATE scan the table; a statement_timeout there
        would kill a healthy build on a large table."""
        _module, statements = _upgrade()
        assert not [s for s, auto in statements if auto and "timeout" in s.lower()]
        indexes = [(s, a) for s, a in statements if "CREATE INDEX" in s.upper()]
        assert indexes and all("CONCURRENTLY" in s.upper() and a for s, a in indexes)

    def test_be10_a_lock_timeout_is_retried_then_succeeds(self, monkeypatch):
        _module, statements = _upgrade(lock_failures=2, monkeypatch=monkeypatch)
        locks = [s for s, _ in statements if s.upper().startswith("LOCK TABLE")]
        assert len(locks) == 3
        assert sum("ROLLBACK TO SAVEPOINT" in s.upper() for s, _ in statements) == 2

    def test_be11_a_lock_that_never_frees_fails_loudly(self, monkeypatch):
        module = _load("aud_0001_audit_standard_s0")
        with pytest.raises(RuntimeError, match="lock_timeout"):
            _upgrade(lock_failures=module.LOCK_ATTEMPTS, monkeypatch=monkeypatch)

    def test_be12_the_timeouts_are_restored_for_later_migrations(self):
        """SET LOCAL would otherwise leak 5s / 60s into every migration after this one in the
        same alembic transaction."""
        _module, statements = _upgrade()
        transactional = [s for s, auto in statements if not auto]
        last_alter = max(i for i, s in enumerate(transactional) if s.upper().startswith(("ALTER TABLE", "CREATE TRIGGER")))
        after = " ".join(transactional[last_alter:]).lower()
        assert "'lock_timeout'" in after and "'statement_timeout'" in after


def test_be13_aud_0002_creates_the_gap_table_on_one_head():
    module = _load("aud_0002_audit_trail_gaps")
    assert module.down_revision == "aud_0001_audit_standard_s0"
    assert len(module.revision) <= 32


def test_be14_the_gap_table_exists_in_the_blank_schema(db):
    assert db.execute(text("SELECT count(*) FROM audit_trail_gaps")).scalar() >= 0
