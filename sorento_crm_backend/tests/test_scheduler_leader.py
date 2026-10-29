"""HA-TIER1-N8N-BOX: the scheduler never runs on a read-only standby, and never twice.

documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 8.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import settings
from app.scheduler import leader, task_scheduler


@pytest.fixture(autouse=True)
def _no_leftover_leadership(monkeypatch):
    monkeypatch.delenv(leader.LEADER_URL_ENV, raising=False)
    leader.release_leadership()
    yield
    leader.release_leadership()


class _FakeConnection:
    def __init__(self, in_recovery):
        self.in_recovery = in_recovery
        self.closed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        value = self.in_recovery if "pg_is_in_recovery" in sql else True

        class _R:
            def scalar(self_inner):
                return value

        return _R()

    def commit(self):
        pass

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _FakeEngine:
    def __init__(self, in_recovery):
        self.connection = _FakeConnection(in_recovery)

    def connect(self):
        return self.connection


def test_standby_database_refuses_without_lock_url(monkeypatch):
    import app.database as database

    monkeypatch.setattr(database, "engine", _FakeEngine(in_recovery=True))
    with pytest.raises(leader.SchedulerNotLeader, match="standby"):
        leader.acquire_leadership()


def test_standby_database_refuses_with_lock_url(monkeypatch):
    fake = _FakeEngine(in_recovery=True)
    monkeypatch.setenv(leader.LEADER_URL_ENV, "postgresql://unused/never")
    monkeypatch.setattr(leader, "create_engine", lambda *a, **kw: fake)
    with pytest.raises(leader.SchedulerNotLeader, match="standby"):
        leader.acquire_leadership()
    assert fake.connection.closed, "a refused attempt must not keep its connection"


def test_primary_without_lock_url_starts(monkeypatch):
    leader.acquire_leadership()  # the test database is a primary


def _other_session():
    return create_engine(settings.database_url, poolclass=NullPool).connect()


def test_lock_is_held_for_the_process_and_freed_on_release(monkeypatch):
    monkeypatch.setenv(leader.LEADER_URL_ENV, settings.database_url)
    leader.acquire_leadership()
    leader.acquire_leadership()  # idempotent in the same process

    other = _other_session()
    try:
        assert other.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": leader.LEADER_LOCK_KEY}).scalar() is False
        leader.release_leadership()
        assert other.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": leader.LEADER_LOCK_KEY}).scalar() is True
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": leader.LEADER_LOCK_KEY})
    finally:
        other.close()


def test_second_scheduler_against_the_same_primary_refuses(monkeypatch):
    monkeypatch.setenv(leader.LEADER_URL_ENV, settings.database_url)
    first = _other_session()  # stands in for the scheduler on the other node
    try:
        assert first.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": leader.LEADER_LOCK_KEY}).scalar() is True
        with pytest.raises(leader.SchedulerNotLeader, match="another process"):
            leader.acquire_leadership()
    finally:
        first.close()  # session end frees it
    leader.acquire_leadership()  # the other node died: this one may take over


def test_start_scheduler_takes_leadership_before_any_job(monkeypatch):
    created = []

    def _refuse():
        raise leader.SchedulerNotLeader("standby")

    monkeypatch.setattr(leader, "acquire_leadership", _refuse)
    monkeypatch.setattr(task_scheduler, "BackgroundScheduler", lambda *a, **kw: created.append(1))
    with pytest.raises(leader.SchedulerNotLeader):
        task_scheduler.start_scheduler()
    assert created == [], "no scheduler may be built when leadership is refused"


def test_lost_lock_session_exits_the_process(monkeypatch):
    """A Postgres restart ends the lock's session: the heartbeat must not run on unlocked."""
    monkeypatch.setenv(leader.LEADER_URL_ENV, settings.database_url)
    leader.acquire_leadership()
    pid = leader._held.execute(text("SELECT pg_backend_pid()")).scalar()
    leader._held.commit()
    killer = _other_session()
    try:
        killer.execute(text("SELECT pg_terminate_backend(:p)"), {"p": pid})
        killer.commit()
    finally:
        killer.close()

    exits = []
    monkeypatch.setattr(leader.os, "_exit", lambda code: exits.append(code))
    ran = []
    monkeypatch.setattr(task_scheduler, "run_due_tasks", lambda db: ran.append(1))
    task_scheduler._scheduled_tasks_heartbeat()
    assert exits == [1]
    leader._held = None  # the session is already gone


def test_live_lock_lets_the_heartbeat_run(monkeypatch):
    monkeypatch.setenv(leader.LEADER_URL_ENV, settings.database_url)
    leader.acquire_leadership()
    exits = []
    monkeypatch.setattr(leader.os, "_exit", lambda code: exits.append(code))
    leader.exit_if_leadership_lost()
    assert exits == []
