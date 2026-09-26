"""Identity S0 (#1280) fix lane round 2: the reviewer pass at 03d3b474.

1. B2: the production RQ work-horse (`worker.ForkSafeWorker.perform_job`) runs the
   job as the `worker` actor on behalf of its enqueuer (AC-10). Run in a fresh
   interpreter, like the other worker.py tests: importing worker.py loads `.env`.
2. S3: a job enqueued from a route behind `get_current_user_or_api_key` keeps the
   enqueuer in its meta. `current_actor_meta()` reads only the contextvar, which a
   sync (`def`) dependency's stamp never reaches, so this pins the `async def`.
3. N2: a stale `session.info["actor_contact_id"]` no longer overrides the stamped
   actor, and the dead legacy helpers are gone.
4. N3: the scheduler label names the scheduled task in words.
5. N4: `user_display_name` is the staff user, not their linked WhatsApp contact,
   on a `user` row; contact-first applies only to `contact` and `legacy` rows.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main  # noqa: F401  registers every model and router
from app import audit_context
from app.audit_context import AuditActor, clear_actor, stamp_actor
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.main import app as real_app
from app.middleware.logging_middleware import LoggingMiddleware
from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.services.audit_service import register_audit_listeners
from app.services.user_session_service import mint_session
from tests._pg_fixture import blank_session, unique_code

register_audit_listeners()

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _seed_user(db: Session, *, name: str, contact: RespondContact | None = None) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('r2')}@example.com".lower(),
        name=name,
        status="ACTIVE",
        respond_contact_id=contact.id if contact else None,
    )
    db.add(user)
    db.flush()
    return user


def _seed_contact(db: Session, *, name: str) -> RespondContact:
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+6011{uuid.uuid4().int % 10_000_000:07d}", name=name
    )
    db.add(contact)
    db.flush()
    return contact


# --------------------------------------------------------------------------- #
# 1. B2: the production work-horse hook                                        #
# --------------------------------------------------------------------------- #
def test_fork_safe_worker_perform_job_runs_the_job_as_worker_for_its_enqueuer():
    """Fresh interpreter. `rq.Worker.perform_job` is stubbed to record the actor the
    job body would see, so only `ForkSafeWorker.perform_job`'s own wrapping is tested."""
    code = (
        "import json, rq\n"
        "from app.audit_context import get_actor\n"
        "seen = {}\n"
        "def _fake_perform_job(self, job, queue):\n"
        "    a = get_actor()\n"
        "    seen['actor'] = None if a is None else {'actor_type': a.actor_type, 'user_id': a.user_id,\n"
        "        'real_user_id': a.real_user_id, 'job_id': a.job_id}\n"
        "    return True\n"
        "rq.Worker.perform_job = _fake_perform_job\n"
        "import worker\n"
        "class _Job:\n"
        "    id = 'zzt-r2-job'\n"
        "    meta = {'actor': {'user_id': 'u-enq', 'real_user_id': 'u-admin', 'trace_id': 't-1'}}\n"
        "w = worker.ForkSafeWorker.__new__(worker.ForkSafeWorker)\n"
        "assert w.perform_job(_Job(), None) is True\n"
        "after = get_actor()\n"
        "print('RESULT ' + json.dumps({'seen': seen.get('actor'), 'after': None if after is None else after.actor_type}))\n"
    )
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://x:x@localhost:5499/x",
        "DIRECT_URL": "postgresql://x:x@localhost:5499/x",
        "JWT_SECRET": "test-dummy-secret",
        "JWT_ALGORITHM": "HS256",
        "REDIS_URL": "redis://localhost:6399/0",
    }
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=120, env=env
    )
    assert proc.returncode == 0, proc.stderr
    import json

    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT "))
    result = json.loads(line[len("RESULT "):])
    seen = result["seen"]
    assert seen is not None, "the job body ran with no audit actor stamped"
    assert seen["actor_type"] == "worker"
    assert seen["user_id"] == "u-enq"
    assert seen["real_user_id"] == "u-admin"
    assert seen["job_id"] == "zzt-r2-job"
    assert result["after"] is None, "the job's actor must not outlive the job"


# --------------------------------------------------------------------------- #
# 2. S3: a job enqueued behind get_current_user_or_api_key keeps its user      #
# --------------------------------------------------------------------------- #
def test_job_enqueued_behind_current_user_or_api_key_carries_the_user_in_meta(monkeypatch):
    from app.services import queue_service

    captured: dict = {}

    class _FakeJob:
        id = "zzt-r2-enqueued"

    class _FakeQueue:
        def enqueue(self, func, *args, **kwargs):
            captured.update(kwargs)
            return _FakeJob()

    monkeypatch.setattr(queue_service, "get_queue", lambda name="imports": _FakeQueue())

    def _noop():
        return None

    with blank_session() as db:
        staff = _seed_user(db, name="R2 Enqueuer")
        db.commit()
        session_row = mint_session(db, staff.id, remember=True)

        test_app = FastAPI()
        test_app.add_middleware(LoggingMiddleware)

        # A plain `def` route, the shape most enqueueing routes have.
        def _enqueue(actor: dict = Depends(get_current_user_or_api_key)):
            queue_service.enqueue_job(_noop, queue_name="imports")
            return {"ok": True}

        test_app.post("/enqueue")(_enqueue)

        def _override_db():
            yield db

        test_app.dependency_overrides[get_db] = _override_db
        clear_actor()
        with TestClient(test_app) as client:
            resp = client.post("/enqueue", headers={"Authorization": f"Bearer {session_row.token}"})
        assert resp.status_code == 200, resp.text

    actor_meta = (captured.get("meta") or {}).get("actor") or {}
    assert actor_meta.get("user_id") == staff.id
    assert actor_meta.get("real_user_id") == staff.id


# --------------------------------------------------------------------------- #
# 3. N2: the legacy contact carrier is gone                                    #
# --------------------------------------------------------------------------- #
def test_stale_session_actor_contact_id_does_not_override_the_stamped_actor():
    with blank_session() as db:
        stale_contact = _seed_contact(db, name="Stale Contact")
        editor = _seed_user(db, name="R2 Editor")
        target = _seed_user(db, name="R2 Target")
        db.commit()

        stamp_actor(AuditActor(actor_type="user", user_id=editor.id, real_user_id=editor.id), db=db)
        db.info["actor_contact_id"] = stale_contact.id
        try:
            target.name = "R2 Renamed"
            db.commit()
        finally:
            db.info.pop("actor_contact_id", None)
            clear_actor(db)

        row = (
            db.query(AuditLog)
            .filter(AuditLog.entity_id == target.id, AuditLog.action == "UPDATE")
            .order_by(AuditLog.changed_at.desc())
            .first()
        )
        assert row is not None
        assert str(row.user_id) == editor.id
        assert row.contact_id is None


def test_dead_legacy_actor_helpers_are_removed():
    for name in ("set_audit_context", "set_actor_contact_id", "get_actor_contact_id", "get_real_and_effective_user_ids"):
        assert not hasattr(audit_context, name), f"{name} has no app caller and should be gone"


# --------------------------------------------------------------------------- #
# 4 and 5. The audit list's words                                              #
# --------------------------------------------------------------------------- #
def _fetch_row(db, entity_id: str) -> dict:
    def _override_db():
        yield db

    def _override_user():
        return {"id": "zzt-staff", "email": "staff@example.com", "name": "Staff"}

    real_app.dependency_overrides[get_db] = _override_db
    real_app.dependency_overrides[get_current_user_or_api_key] = _override_user
    try:
        resp = TestClient(real_app).get("/api/v1/audit/logs/", params={"entity_id": entity_id})
    finally:
        real_app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1, data
    return data[0]


def test_scheduler_label_names_the_scheduled_task_in_words():
    with blank_session() as db:
        key = f"zzt_r2_{uuid.uuid4().hex[:8]}"
        db.add(ScheduledTask(key=key, name="Daily reorder run", interval_unit="days", interval_value=1))
        entity_id = str(uuid.uuid4())
        db.add(AuditLog(entity_type="users", entity_id=entity_id, action="UPDATE", actor_type="scheduler", job_id=key))
        db.commit()
        row = _fetch_row(db, entity_id)
        assert row["actor_label"] == "Scheduled: Daily reorder run"
        assert row["job_id"] == key


def test_user_row_display_name_is_the_staff_user_not_their_linked_contact():
    with blank_session() as db:
        contact = _seed_contact(db, name="WhatsApp Name")
        staff = _seed_user(db, name="Staff Name", contact=contact)
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE", actor_type="user",
                user_id=staff.id, real_user_id=staff.id, contact_id=contact.id, auth_method="password",
            )
        )
        db.commit()
        row = _fetch_row(db, entity_id)
        assert row["user_display_name"] == "Staff Name"


def test_legacy_and_contact_rows_keep_contact_first_display_name():
    with blank_session() as db:
        contact = _seed_contact(db, name="Portal Person")
        staff = _seed_user(db, name="Some Staff")
        legacy_id, contact_row_id = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=legacy_id, action="UPDATE", actor_type="legacy",
                user_id=staff.id, contact_id=contact.id,
            )
        )
        db.add(
            AuditLog(
                entity_type="users", entity_id=contact_row_id, action="UPDATE", actor_type="contact",
                contact_id=contact.id, auth_method="portal_token",
            )
        )
        db.commit()
        assert _fetch_row(db, legacy_id)["user_display_name"] == "Portal Person"
        assert _fetch_row(db, contact_row_id)["user_display_name"] == "Portal Person"
