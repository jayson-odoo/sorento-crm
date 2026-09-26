"""Audit standard, slice S0 (#1281): one append-only backbone that every write reaches.

Each test names the UAC line it proves (`documentation/plans/audit/
audit-standard-26sep-acceptance-criteria.md`). Everything runs on the blank Postgres
schema, rolled back, so it says the same thing on CI's empty database as on a prod copy.
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, select, text, update

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import (
    audit_context_scope,
    current_audit_context,
    restore_from_job_meta,
    set_actor_contact_id,
    set_audit_context,
    set_trace_id,
    snapshot_for_job,
)
from app.database import Base
from app.models.audit import AuditLog
from app.models.integration import Integration
from app.models.order import Customer, CustomerContact
from app.models.product import Brand
from app.models.user import SystemSetting, User
from app.services import audit_service
from app.services.audit_service import (
    BULK_AUDIT_CAP,
    audit_event,
    log_audit,
    record,
    register_audit_listeners,
)
from app.services.company_scope import register_company_scope_listeners

from ._pg_fixture import blank_session, unique_code

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()


@pytest.fixture(autouse=True)
def _no_leaked_context():
    yield
    set_audit_context(None, None)
    set_trace_id(None)
    set_actor_contact_id(None)


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _rows(db, entity_id, action=None):
    q = db.query(AuditLog).filter(AuditLog.entity_id == str(entity_id))
    if action:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.changed_at, AuditLog.id).all()


def _brand(db, **kw):
    b = Brand(brand_code=unique_code("B")[:50], brand_name=kw.pop("brand_name", "Alpha"), **kw)
    db.add(b)
    db.flush()
    return b


def _customer(db):
    c = Customer(customer_code=unique_code("C")[:50], customer_name="Alpha Trading")
    db.add(c)
    db.flush()
    return c


# --- Default-on emission ---------------------------------------------------------


class TestDefaultOn:
    def test_ac_s0_01_an_unflagged_class_is_audited(self, db):
        assert not getattr(Brand, "__audit_track__", False)
        b = _brand(db)
        b.brand_name = "Beta"
        db.flush()
        db.delete(b)
        db.flush()
        assert [r.action for r in _rows(db, b.id)] == ["CREATE", "UPDATE", "DELETE"]

    def test_ac_s0_02_a_skipped_class_writes_nothing(self, db):
        assert getattr(Integration, "__audit_skip__", None) is None  # audited, touch-filtered
        from app.models.user_session import UserSession

        assert isinstance(getattr(UserSession, "__audit_skip__", None), str)
        user = User(email=f"{uuid.uuid4().hex}@t.local", name="Skip", status="ACTIVE")
        db.add(user)
        db.flush()
        from datetime import datetime, timedelta

        s = UserSession(
            user_id=user.id,
            token=uuid.uuid4().hex,
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db.add(s)
        db.flush()
        assert _rows(db, s.id) == []

    def test_ac_s0_02_every_skip_names_a_reason(self):
        for mapper in Base.registry.mappers:
            reason = getattr(mapper.class_, "__audit_skip__", None)
            if reason is not None:
                assert isinstance(reason, str) and reason.strip(), mapper.class_.__name__

    def test_ac_s0_03_update_carries_only_changed_keys(self, db):
        b = _brand(db, manufacturer="Acme")
        b.brand_name = "Beta"
        db.flush()
        (row,) = _rows(db, b.id, "UPDATE")
        assert row.old_values == {"brand_name": "Alpha"}
        assert row.new_values == {"brand_name": "Beta"}
        (created,) = _rows(db, b.id, "CREATE")
        assert created.new_values["manufacturer"] == "Acme"
        assert "brand_code" in created.new_values

    def test_ac_s0_04_a_touch_only_update_writes_nothing(self, db):
        user = User(email=f"{uuid.uuid4().hex}@t.local", name="Toucher", status="ACTIVE")
        db.add(user)
        db.flush()
        from datetime import datetime

        user.last_sign_in_at = datetime.utcnow()
        db.flush()
        assert _rows(db, user.id, "UPDATE") == []


# --- Redaction -------------------------------------------------------------------


class TestRedaction:
    # Secret keys are DROPPED, never masked: the semantics S-1 (#1298) shipped with its scrub
    # migration, so rows written before and after it read the same. S0 widens the key set.
    def test_ac_s0_05_password_never_enters_the_trail(self, db):
        user = User(
            email=f"{uuid.uuid4().hex}@t.local", name="Pw", status="ACTIVE", password="$2b$hash-one"
        )
        db.add(user)
        db.flush()
        user.password = "$2b$hash-two"
        db.flush()
        rows = _rows(db, user.id)
        assert rows
        for row in rows:
            blob = f"{row.old_values} {row.new_values}"
            assert "hash-one" not in blob and "hash-two" not in blob
            assert "password" not in (row.old_values or {}) and "password" not in (row.new_values or {})

    def _settings(self, db):
        s = db.query(SystemSetting).first()
        if s is None:
            s = SystemSetting()
            db.add(s)
            db.flush()
        return s

    def test_ac_s0_05_smtp_password_is_redacted(self, db):
        s = self._settings(db)
        s.smtp_password = "hunter2-smtp"
        s.smtp_host = f"smtp-{uuid.uuid4().hex[:6]}.local"
        db.flush()
        rows = _rows(db, s.id, "UPDATE")
        assert rows
        assert all("hunter2-smtp" not in f"{r.old_values} {r.new_values}" for r in rows)
        assert all("smtp_password" not in (r.new_values or {}) for r in rows)
        assert rows[-1].new_values["smtp_host"] == s.smtp_host

    def test_ac_s0_05_explicit_log_audit_is_redacted(self, db):
        eid = str(uuid.uuid4())
        log_audit(
            db, "probe", eid, "UPDATE",
            old_values={"api_key_ciphertext": "c1", "note": "a"},
            new_values={"api_key_ciphertext": "c2", "sign_token": "t", "code_hash": "h", "note": "b"},
        )
        (row,) = _rows(db, eid)
        assert row.new_values == {"note": "b"}
        assert row.old_values == {"note": "a"}

    def test_ac_s0_05_bulk_update_is_redacted(self, db):
        s = self._settings(db)
        host = f"bulk-{uuid.uuid4().hex[:6]}.local"
        db.query(SystemSetting).filter(SystemSetting.id == s.id).update(
            {"smtp_password": "bulk-secret", "smtp_host": host}, synchronize_session=False
        )
        row = _rows(db, s.id, "UPDATE")[-1]
        assert row.new_values == {"smtp_host": host}
        assert "smtp_password" not in (row.old_values or {})
        assert "bulk-secret" not in f"{row.old_values} {row.new_values}"


# --- Bulk DML --------------------------------------------------------------------


class TestBulkDml:
    def test_ac_s0_06_query_update_writes_one_row_per_match(self, db):
        a, b = _brand(db, brand_name="A1"), _brand(db, brand_name="A2")
        db.query(Brand).filter(Brand.id.in_([a.id, b.id])).update(
            {"manufacturer": "Bulk Co"}, synchronize_session=False
        )
        for brand in (a, b):
            (row,) = _rows(db, brand.id, "UPDATE")
            assert row.old_values == {"manufacturer": None}
            assert row.new_values == {"manufacturer": "Bulk Co"}

    def test_ac_s0_06_orm_update_statement(self, db):
        a = _brand(db)
        db.execute(update(Brand).where(Brand.id == a.id).values(brand_name="Stmt"))
        (row,) = _rows(db, a.id, "UPDATE")
        assert row.new_values == {"brand_name": "Stmt"}
        assert row.old_values == {"brand_name": "Alpha"}

    def test_ac_s0_06_expression_values_are_marked(self, db):
        a = _brand(db)
        db.query(Brand).filter(Brand.id == a.id).update(
            {"brand_name": Brand.brand_name + "-x"}, synchronize_session=False
        )
        (row,) = _rows(db, a.id, "UPDATE")
        assert row.new_values == {"brand_name": "[expression]"}

    def test_ac_s0_07_query_delete_snapshots_each_row(self, db):
        a = _brand(db, manufacturer="Gone Co")
        db.query(Brand).filter(Brand.id == a.id).delete(synchronize_session=False)
        (row,) = _rows(db, a.id, "DELETE")
        assert row.old_values["manufacturer"] == "Gone Co"
        assert row.new_values is None

    def test_ac_s0_07_core_delete_through_session(self, db):
        a = _brand(db)
        db.execute(delete(Brand).where(Brand.id == a.id))
        assert len(_rows(db, a.id, "DELETE")) == 1

    def test_ac_s0_08_cap_then_one_summary_row(self, db):
        marker = unique_code("CAP")
        brands = [_brand(db, brand_name=f"{marker}-{i}") for i in range(4)]
        with patch.object(audit_service, "BULK_AUDIT_CAP", 2):
            db.query(Brand).filter(Brand.brand_name.like(f"{marker}-%")).update(
                {"manufacturer": "Capped"}, synchronize_session=False
            )
        per_row = [r for b in brands for r in _rows(db, b.id, "UPDATE")]
        assert len(per_row) == 2
        summary = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "brands", AuditLog.entity_id == "*",
                    AuditLog.description.like("%2 more rows%"))
            .all()
        )
        assert len(summary) == 1
        assert BULK_AUDIT_CAP == 500

    def test_ac_s0_09_bulk_on_a_skipped_table_writes_nothing(self, db):
        from app.models.user_session import UserSession

        before = db.query(AuditLog).count()
        db.query(UserSession).filter(UserSession.id == str(uuid.uuid4())).update(
            {"revoked_at": None}, synchronize_session=False
        )
        assert db.query(AuditLog).count() == before

    def test_ac_s0_09_session_skip_types_suppress_bulk(self, db):
        a = _brand(db)
        db.info["skip_audit_entity_types"] = ["brands"]
        try:
            db.query(Brand).filter(Brand.id == a.id).update({"brand_name": "Quiet"}, synchronize_session=False)
        finally:
            db.info.pop("skip_audit_entity_types", None)
        assert _rows(db, a.id, "UPDATE") == []


# --- Context, principal and source ----------------------------------------------


class TestContext:
    def test_ac_s0_10_a_sync_dependency_mutation_reaches_the_endpoint(self, db):
        """The `get_current_user_or_api_key` shape: sync dependency, sync endpoint."""
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient

        from app.audit_context import get_audit_context
        from app.middleware.logging_middleware import LoggingMiddleware

        actor = str(uuid.uuid4())
        probe = FastAPI()
        probe.add_middleware(LoggingMiddleware)

        def dep():
            set_audit_context(actor, "10.0.0.9")
            return actor

        @probe.get("/probe")
        def endpoint(_=Depends(dep)):
            return {"user": get_audit_context()[0]}

        assert TestClient(probe).get("/probe").json() == {"user": actor}

    def test_ac_s0_12_jwt_principal_and_source(self, db):
        user_id = str(uuid.uuid4())
        with audit_context_scope(ip_address="1.2.3.4"):
            set_audit_context(user_id, "1.2.3.4")
            b = _brand(db)
        (row,) = _rows(db, b.id)
        assert row.user_id == user_id
        assert (row.principal_type, row.principal_id, row.source) == ("user", user_id, "ui")
        assert row.on_behalf_of_user_id is None

    def test_ac_s0_12_impersonation_names_both(self, db):
        admin, target = str(uuid.uuid4()), str(uuid.uuid4())
        with audit_context_scope():
            set_audit_context(admin, None, effective_user_id=target)
            b = _brand(db)
        (row,) = _rows(db, b.id)
        assert row.user_id == admin
        assert row.on_behalf_of_user_id == target

    def test_ac_s0_13_portal_contact(self, db):
        contact = str(uuid.uuid4())
        with audit_context_scope():
            set_actor_contact_id(contact)
            b = _brand(db)
        (row,) = _rows(db, b.id)
        assert (row.principal_type, row.principal_id, row.source) == ("contact", contact, "portal")
        assert row.contact_id == contact

    def test_ac_s0_14_long_trace_id_is_clamped_and_correlation_header_kept(self, db):
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient

        from app.database import get_db
        from app.middleware.logging_middleware import LoggingMiddleware

        probe = FastAPI()
        probe.add_middleware(LoggingMiddleware)
        made = {}

        def _db():
            yield db

        @probe.post("/w")
        def w(session=Depends(_db)):
            made["id"] = _brand(session).id
            return {}

        client = TestClient(probe)
        client.post("/w", headers={"X-Trace-Id": "t" * 200, "X-Correlation-Id": "corr-1"})
        (row,) = _rows(db, made["id"])
        assert row.trace_id == "t" * 64
        assert row.correlation_id == "corr-1"
        client.post("/w")
        (row2,) = _rows(db, made["id"])
        assert row2.trace_id and row2.correlation_id == row2.trace_id
        assert get_db  # imported for parity with the real app's dependency

    def test_ac_s0_15_no_context_is_system(self, db):
        b = _brand(db)
        (row,) = _rows(db, b.id)
        assert row.principal_type == "system"
        assert row.user_id is None

    def test_ac_s0_15_scheduler_session_stamps_scheduler(self, db):
        from app.scheduler import task_scheduler

        with patch.object(task_scheduler, "SessionLocal", return_value=db), \
                patch.object(db, "close"):
            with task_scheduler.scheduler_session() as s:
                b = _brand(s)
                assert current_audit_context().source == "scheduler"
        (row,) = _rows(db, b.id)
        assert (row.principal_type, row.source) == ("scheduler", "scheduler")
        assert row.trace_id


# --- Worker ------------------------------------------------------------------------


class TestWorker:
    def test_ac_s0_16_enqueue_stamps_the_request_context(self):
        from app.services import queue_service

        user_id = str(uuid.uuid4())
        fake_queue = MagicMock()
        with audit_context_scope(request_id="req-1", correlation_id="corr-9"):
            set_audit_context(user_id, None)
            with patch.object(queue_service, "get_queue", return_value=fake_queue):
                queue_service.enqueue_job(print, "x", queue_name="imports")
        meta = fake_queue.enqueue.call_args.kwargs["meta"]["audit_context"]
        assert meta["user_id"] == user_id
        assert meta["correlation_id"] == "corr-9"

    def test_ac_s0_16_the_job_writes_as_the_requesting_user(self, db):
        user_id = str(uuid.uuid4())
        with audit_context_scope(request_id="req-2", correlation_id="corr-2"):
            set_audit_context(user_id, None)
            meta = {"audit_context": snapshot_for_job()}
        with restore_from_job_meta(meta, queue_name="imports", job_id="job-123"):
            b = _brand(db)
        (row,) = _rows(db, b.id)
        assert row.user_id == user_id
        assert row.correlation_id == "corr-2"
        assert (row.principal_type, row.source, row.trace_id) == ("worker", "import", "job-123")
        with restore_from_job_meta({}, queue_name="respond_io", job_id="job-9"):
            c = _brand(db)
        (row2,) = _rows(db, c.id)
        assert (row2.source, row2.correlation_id) == ("worker", "job-9")

    def test_ac_s0_16_perform_job_restores_the_context(self):
        code = (
            "import worker\n"
            "from unittest.mock import patch, MagicMock\n"
            "from rq import Worker\n"
            "from app.audit_context import current_audit_context\n"
            "def fake(self, job, queue):\n"
            "    c = current_audit_context()\n"
            "    print(c.user_id, c.source, c.request_id)\n"
            "job = MagicMock(); job.id = 'jid-7'; job.meta = {'audit_context': {'user_id': 'u-7'}}\n"
            "queue = MagicMock(); queue.name = 'imports'\n"
            "with patch.object(Worker, 'perform_job', fake):\n"
            "    worker.ForkSafeWorker.perform_job(object.__new__(worker.ForkSafeWorker), job, queue)\n"
        )
        out = _fresh(code)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip().splitlines()[-1] == "u-7 import jid-7"

    def test_ac_s0_16_in_process_drain_restores_the_context(self):
        from app.services import queue_service

        seen = {}

        def task():
            seen["ctx"] = current_audit_context()

        job = MagicMock()
        job.id = "jid-8"
        job.meta = {"audit_context": {"user_id": "u-8", "correlation_id": "c-8"}}
        job.func = task
        job.args, job.kwargs = (), {}
        from rq.job import JobStatus

        job.get_status.return_value = JobStatus.QUEUED
        q = MagicMock()
        q.connection.lpop.side_effect = [b"jid-8", None]
        with patch.object(queue_service, "get_queue", return_value=q), \
                patch.object(queue_service.Job, "fetch", return_value=job):
            queue_service.run_sync_rq_jobs("notifications", 2)
        ctx = seen["ctx"]
        assert (ctx.user_id, ctx.correlation_id, ctx.source, ctx.request_id) == ("u-8", "c-8", "worker", "jid-8")

    def test_ac_s0_17_worker_registers_the_audit_listeners(self):
        out = _fresh(
            "import worker\n"
            "worker.register_worker_listeners()\n"
            "from app.services import audit_service\n"
            "print(audit_service._listeners_registered)\n"
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip().splitlines()[-1] == "True"
        src = (BACKEND_ROOT / "worker.py").read_text()
        main_block = src.split("if __name__ == '__main__':", 1)[1]
        assert "register_worker_listeners()" in main_block


def _fresh(code):
    import os

    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://x:x@localhost:5499/x",
        "DIRECT_URL": "postgresql://x:x@localhost:5499/x",
        "JWT_SECRET": "test-dummy-secret",
        "JWT_ALGORITHM": "HS256",
        "REDIS_URL": "redis://localhost:6399/0",
    }
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=120, env=env
    )


# --- Business verbs and reason -------------------------------------------------------


class _Svc:
    def __init__(self, db):
        self.db = db

    @audit_event("test.brand.confirm", entity="brands", ids="ids", reason="reason")
    def confirm(self, ids, reason=None, touch=True):
        if touch:
            for b in self.db.query(Brand).filter(Brand.id.in_(ids)).all():
                b.manufacturer = "Confirmed"
            self.db.flush()
        return len(ids)

    @audit_event("test.brand.boom", entity="brands", ids="ids")
    def boom(self, ids):
        raise RuntimeError("boom")


class TestBusinessVerbs:
    def test_ac_s0_18_flushed_rows_carry_the_verb_and_reason(self, db):
        a = _brand(db)
        _Svc(db).confirm([a.id], reason="customer asked")
        (row,) = _rows(db, a.id, "UPDATE")
        assert (row.event, row.reason) == ("test.brand.confirm", "customer asked")
        assert _rows(db, a.id, "EVENT") == []
        ctx = current_audit_context()
        assert ctx is None or (ctx.event is None and ctx.reason is None)

    def test_ac_s0_18_context_restored_when_the_call_raises(self, db):
        with audit_context_scope():
            with pytest.raises(RuntimeError):
                _Svc(db).boom([str(uuid.uuid4())])
            assert current_audit_context().event is None

    def test_ac_s0_19_nothing_flushed_writes_one_event_row(self, db):
        a = _brand(db)
        _Svc(db).confirm([a.id], reason="looked only", touch=False)
        (row,) = _rows(db, a.id, "EVENT")
        assert (row.entity_type, row.event, row.reason) == ("brands", "test.brand.confirm", "looked only")

    def test_ac_s0_19_record_writes_an_event_row_with_context(self, db):
        user_id = str(uuid.uuid4())
        eid = str(uuid.uuid4())
        with audit_context_scope(request_id="req-r"):
            set_audit_context(user_id, "9.9.9.9")
            record(db, event="attachment.download", entity_type="attachment", entity_id=eid, reason="audit pull")
        (row,) = _rows(db, eid)
        assert (row.action, row.event, row.user_id, row.trace_id, row.reason) == (
            "EVENT", "attachment.download", user_id, "req-r", "audit pull"
        )
        assert row.ip_address == "9.9.9.9"


# --- Root entity ---------------------------------------------------------------------


class TestRootEntity:
    def test_ac_s0_20_child_rolls_up_to_its_parent(self, db):
        c = _customer(db)
        cc = CustomerContact(customer_id=c.id, full_name="Jane Tan")
        db.add(cc)
        db.flush()
        (row,) = _rows(db, cc.id)
        assert (row.root_entity_type, row.root_entity_id) == ("customer", str(c.id))

    def test_ac_s0_20_a_parentless_row_is_its_own_root(self, db):
        b = _brand(db)
        (row,) = _rows(db, b.id)
        assert (row.root_entity_type, row.root_entity_id) == ("brands", str(b.id))


# --- Append-only ---------------------------------------------------------------------


class TestAppendOnly:
    @pytest.mark.parametrize(
        "stmt",
        [
            "UPDATE audit_logs SET description = 'tampered' WHERE id = :id",
            "DELETE FROM audit_logs WHERE id = :id",
            "TRUNCATE audit_logs",
        ],
    )
    def test_ac_s0_21_the_database_refuses_edits(self, db, stmt):
        eid = str(uuid.uuid4())
        row = log_audit(db, "probe", eid, "UPDATE")
        sp = db.begin_nested()
        with pytest.raises(Exception, match="append-only"):
            db.execute(text(stmt), {"id": row.id})
        sp.rollback()

    def test_ac_s0_21_the_maintenance_flag_allows_it(self, db):
        eid = str(uuid.uuid4())
        row = log_audit(db, "probe", eid, "UPDATE")
        db.execute(text("SET LOCAL sorento.audit_maintenance = 'on'"))
        db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": row.id})
        db.execute(text("SET LOCAL sorento.audit_maintenance = 'off'"))
        assert _rows(db, eid) == []

    def test_ac_s0_22_module_purge_keeps_audit_rows(self, db):
        from app.services.module_purge_service import purge_audit

        eid = str(uuid.uuid4())
        log_audit(db, "probe", eid, "UPDATE")
        assert purge_audit(db) == {"audit_logs": 0}
        assert len(_rows(db, eid)) == 1


# --- API -----------------------------------------------------------------------------


def test_ac_s0_23_the_response_schema_carries_the_new_fields():
    from app.schemas.audit import AuditLogResponse

    row = AuditLog(
        id=str(uuid.uuid4()), entity_type="brands", entity_id="b1", action="EVENT",
        changed_at=__import__("datetime").datetime(2026, 9, 26), trace_id="req-1",
        correlation_id="corr-1", event="x.y.z", source="ui", reason="why",
        principal_type="user", principal_id="u1", on_behalf_of_user_id=None,
        root_entity_type="brands", root_entity_id="b1",
    )
    dumped = AuditLogResponse.model_validate(row).model_dump()
    for key, value in {
        "request_id": "req-1", "correlation_id": "corr-1", "event": "x.y.z", "source": "ui",
        "reason": "why", "principal_type": "user", "principal_id": "u1",
        "root_entity_type": "brands", "root_entity_id": "b1",
    }.items():
        assert dumped[key] == value, key
    assert "on_behalf_of_user_id" in dumped


def test_ac_s0_23_the_list_route_returns_the_new_fields(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user_or_api_key
    from app.main import app as real_app

    eid = str(uuid.uuid4())
    with audit_context_scope(request_id="req-api", correlation_id="corr-api"):
        record(db, event="probe.api", entity_type="probe", entity_id=eid, reason="r")

    def _db():
        yield db

    admin = {"id": str(uuid.uuid4()), "role_name": "superadmin", "email": "a@t.local", "name": "A"}
    real_app.dependency_overrides[get_db] = _db
    real_app.dependency_overrides[get_current_user_or_api_key] = lambda: admin
    try:
        # The read gate is S-1's (#1298, tests/test_audit_read_gate.py); this test is about
        # the fields, so the caller is simply an audit admin.
        with patch("app.services.company_scope.admin_listing_company_filter", return_value=None), \
                patch("app.api.v1.audit.audit_logs._is_audit_admin", return_value=True):
            r = TestClient(real_app).get(f"/api/v1/audit/logs/?entity_type=probe&entity_id={eid}")
    finally:
        real_app.dependency_overrides.pop(get_db, None)
        real_app.dependency_overrides.pop(get_current_user_or_api_key, None)
    assert r.status_code == 200, r.text
    (item,) = r.json()["data"]
    assert (item["request_id"], item["correlation_id"], item["event"], item["reason"]) == (
        "req-api", "corr-api", "probe.api", "r"
    )
    assert select  # keep the import used
