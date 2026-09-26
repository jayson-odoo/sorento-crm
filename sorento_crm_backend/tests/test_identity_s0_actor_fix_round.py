"""Identity S0 (#1280) fix round: the audit actor in the real worker, the scheduler
ticks that open their own session, and explicit `log_audit` callers with no stamp.

1. `worker.py` registers the audit flush listener at startup (AC-10 in the real
   worker, not only in the API's in-process drain).
2. `_drain_email_outbox_tick` runs as the `scheduler` actor named after the tick.
3. `log_audit(user_id=X)` with nothing stamped records a `user` row for X (the
   screen keeps showing the name); an explicit contact with no actor is `contact`;
   only no user and no contact at all is `system`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import app.main  # noqa: F401  registers every model and router
from app.audit_context import clear_actor, get_actor, set_audit_context
from app.models.audit import AuditLog
from app.models.user import User
from app.services.audit_service import log_audit, register_audit_listeners
from tests._pg_fixture import blank_session, unique_code

register_audit_listeners()

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _seed_user(db, name: str) -> User:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('fx')}@example.com".lower(), name=name, status="ACTIVE")
    db.add(user)
    db.commit()
    return user


def _rows(db, entity_id: str) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == entity_id)
        .order_by(AuditLog.changed_at.desc())
        .all()
    )


# --------------------------------------------------------------------------- #
# 1. The real worker registers the audit listener                             #
# --------------------------------------------------------------------------- #
def test_worker_startup_registers_the_audit_flush_listener():
    """Fresh interpreter: nothing but worker.py's own startup path has run."""
    code = (
        "import worker\n"
        "from app.services import audit_service\n"
        # register_audit_listeners wraps _session_before_flush in a closure, so its
        # idempotency flag is the observable fact, not event.contains().
        "assert audit_service._listeners_registered is False\n"
        "worker.register_worker_listeners()\n"
        "assert audit_service._listeners_registered is True\n"
        "print('ok')\n"
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
    assert "ok" in proc.stdout


def test_tracked_write_inside_job_actor_scope_is_a_worker_row():
    from app.services.queue_service import job_actor_scope

    class _Job:
        id = "zzt-fix-job"
        meta: dict = {}

    with blank_session() as db:
        enqueuer = _seed_user(db, "Enqueuer")
        target = _seed_user(db, "Job Target")
        _Job.meta = {"actor": {"user_id": enqueuer.id, "real_user_id": enqueuer.id, "trace_id": None}}

        with job_actor_scope(_Job()):
            target.name = "Renamed In Job"
            db.commit()

        row = next(r for r in _rows(db, target.id) if r.action == "UPDATE")
        assert row.actor_type == "worker"
        assert row.user_id == enqueuer.id
        assert row.job_id == "zzt-fix-job"


# --------------------------------------------------------------------------- #
# 2. The email outbox drainer tick is a scheduler actor                       #
# --------------------------------------------------------------------------- #
def test_email_outbox_drainer_tick_runs_as_scheduler(monkeypatch):
    from app.scheduler import task_scheduler
    from app.tasks import email_outbox_tasks

    seen = {}

    def _fake_drain():
        seen["actor"] = get_actor()
        return {"picked": 0}

    monkeypatch.setattr(email_outbox_tasks, "drain_email_outbox", _fake_drain)
    clear_actor()

    task_scheduler._drain_email_outbox_tick()

    actor = seen.get("actor")
    assert actor is not None, "the drainer ran with no audit actor stamped"
    assert actor.actor_type == "scheduler"
    assert actor.job_id == "email_outbox_drainer"
    assert actor.user_id is None
    assert get_actor() is None, "the tick's actor must not outlive the tick"


# --------------------------------------------------------------------------- #
# 3. Explicit callers with nothing stamped                                    #
# --------------------------------------------------------------------------- #
def test_log_audit_with_explicit_user_and_no_actor_is_a_user_row():
    with blank_session() as db:
        clear_actor(db)
        someone = _seed_user(db, "Explicit Someone")
        entity_id = str(uuid.uuid4())
        clear_actor(db)

        log_audit(db, "purchase_request", entity_id, "UPDATE", user_id=someone.id)
        db.commit()

        row = _rows(db, entity_id)[0]
        assert row.actor_type == "user"
        assert row.user_id == someone.id
        assert row.real_user_id == someone.id


def test_log_audit_with_explicit_contact_and_no_actor_is_a_contact_row():
    with blank_session() as db:
        clear_actor(db)
        entity_id = str(uuid.uuid4())
        contact_id = str(uuid.uuid4())

        log_audit(db, "complaint", entity_id, "INSERT", contact_id=contact_id)
        db.commit()

        row = _rows(db, entity_id)[0]
        assert row.actor_type == "contact"
        assert row.contact_id == contact_id
        assert row.user_id is None


def test_log_audit_with_no_user_no_contact_and_no_actor_is_system():
    with blank_session() as db:
        clear_actor(db)
        entity_id = str(uuid.uuid4())

        log_audit(db, "complaint", entity_id, "UPDATE")
        db.commit()

        assert _rows(db, entity_id)[0].actor_type == "system"


def test_flush_after_legacy_set_audit_context_is_a_user_row():
    with blank_session() as db:
        clear_actor(db)
        someone = _seed_user(db, "Legacy Context User")
        target = _seed_user(db, "Legacy Context Target")
        set_audit_context(someone.id, "10.0.0.9")

        target.name = "Renamed Under Legacy Context"
        db.commit()

        row = next(r for r in _rows(db, target.id) if r.action == "UPDATE")
        assert row.actor_type == "user"
        assert row.user_id == someone.id
        assert row.real_user_id == someone.id
