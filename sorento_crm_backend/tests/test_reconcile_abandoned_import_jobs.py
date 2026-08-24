"""A killed worker leaves a STARTED import row, and the reconciler settles it.

The bug, reproduced from production on 2026-08-19: an SPO import sat on
``started`` while RQ had already moved the job to its FailedJobRegistry with
``AbandonedJobError``. RQ raises that from ``StartedJobRegistry.cleanup`` when the
worker PARENT stops heartbeating - the started-registry entry expires
``job_monitoring_interval + 60`` seconds (about 90) after the last heartbeat,
nothing to do with ``job_timeout``. A deploy recreates the worker in place, Docker
gives it ten seconds to warm-shut-down, and an import still running at t+10s takes
the SIGKILL with it.

``_reconcile_orphan_import_jobs`` could not see that row: it only inspected
``QUEUED``. So the drawer said "Processing" for ever unless somebody happened to
open the job page, where ``JobService.sync_job_status`` settles it as a side
effect of rendering.

The asymmetry between the two statuses is deliberate and is what these tests pin:

- ``QUEUED`` + RQ has never heard of the job  -> failed. The job was never picked
  up, so a missing hash can only mean the enqueue is gone.
- ``STARTED`` + RQ has never heard of the job -> LEFT ALONE. A finished job's hash
  expires after ``result_ttl`` (500s by default), so "no hash" is exactly as
  consistent with "it succeeded and the task crashed before writing the row" as
  with "it died". Failing it would relabel completed imports as failures.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from rq.exceptions import NoSuchJobError

from app.models.job import ImportJob, JobStatus
import app.scheduler.task_scheduler as sched
import app.services.job_service as job_service_mod
from app.scheduler.task_scheduler import _reconcile_orphan_import_jobs
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _no_notifications(monkeypatch):
    """fail_job fans out a notification; this suite is about the status flip."""
    monkeypatch.setattr(job_service_mod, "_notify_import_job_event", lambda *a, **k: None)


class _FakeJob:
    """Stands in for an rq Job. ``status=None`` means Redis has never heard of it."""

    def __init__(self, status, exc_info=None):
        self._status = status
        self.exc_info = exc_info

    def get_status(self):
        return self._status


def _install_rq(monkeypatch, by_id: dict):
    """Point ``rq.job.Job.fetch`` at a dict of job_id -> _FakeJob (or None)."""
    import rq.job

    def _fetch(job_id, connection=None, **_kw):
        job = by_id.get(str(job_id), "missing")
        if job == "missing" or job is None:
            raise NoSuchJobError(job_id)
        return job

    monkeypatch.setattr(rq.job.Job, "fetch", staticmethod(_fetch))


def _make_job(db, *, status, age_minutes=30, job_type="spo_import"):
    row = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        status=status.value,
        user_id=unique_code("USER"),
        filename=f"{unique_code('SPO')}.xlsx",
        created_at=datetime.utcnow() - timedelta(minutes=age_minutes),
        started_at=datetime.utcnow() - timedelta(minutes=age_minutes),
    )
    db.add(row)
    # commit, not flush: `JobService.fail_job` opens with a `rollback()` (it is
    # usually called from an aborted transaction), which would discard a row that
    # only existed on the flush. `blank_session` runs with
    # join_transaction_mode="create_savepoint", so this stays inside the fixture's
    # outer transaction and is still thrown away at teardown.
    db.commit()
    return row


# ------------------------------------------------------- the production case

def test_started_row_whose_rq_job_failed_is_settled(db, monkeypatch):
    """The 19 Aug SPO import: RQ says failed, the row still says started."""
    row = _make_job(db, status=JobStatus.STARTED)
    abandoned = "Moved to FailedJobRegistry, due to AbandonedJobError, at 2026-08-19 03:28:40"
    _install_rq(monkeypatch, {row.job_id: _FakeJob("failed", exc_info=abandoned)})

    assert _reconcile_orphan_import_jobs(db) == 1

    db.refresh(row)
    assert row.status == JobStatus.FAILED.value
    assert row.completed_at is not None
    # RQ's own words survive, so the drawer and the job page say the same thing
    # as the FailedJobRegistry rather than a generic sentence of our own.
    assert "AbandonedJobError" in (row.error or "")


def test_started_row_still_running_is_left_alone(db, monkeypatch):
    """A long import must never be called dead while RQ is still running it."""
    row = _make_job(db, status=JobStatus.STARTED, age_minutes=90)
    _install_rq(monkeypatch, {row.job_id: _FakeJob("started")})

    assert _reconcile_orphan_import_jobs(db) == 0

    db.refresh(row)
    assert row.status == JobStatus.STARTED.value


def test_started_row_with_no_rq_job_is_left_alone(db, monkeypatch):
    """No hash for a STARTED row is ambiguous - a finished job's hash expires too."""
    row = _make_job(db, status=JobStatus.STARTED, age_minutes=240)
    _install_rq(monkeypatch, {})  # NoSuchJobError

    assert _reconcile_orphan_import_jobs(db) == 0

    db.refresh(row)
    assert row.status == JobStatus.STARTED.value


def test_started_row_younger_than_the_grace_is_left_alone(db, monkeypatch):
    """Never race a row that was enqueued seconds ago."""
    row = _make_job(db, status=JobStatus.STARTED, age_minutes=1)
    _install_rq(monkeypatch, {row.job_id: _FakeJob("failed", exc_info="boom")})

    assert _reconcile_orphan_import_jobs(db) == 0

    db.refresh(row)
    assert row.status == JobStatus.STARTED.value


# ------------------------------------------- the QUEUED behaviour, unchanged

def test_queued_row_with_no_rq_job_is_failed(db, monkeypatch):
    """Regression guard: the original reason this reconciler exists."""
    row = _make_job(db, status=JobStatus.QUEUED)
    _install_rq(monkeypatch, {})  # NoSuchJobError

    assert _reconcile_orphan_import_jobs(db) == 1

    db.refresh(row)
    assert row.status == JobStatus.FAILED.value
    assert "did not start" in (row.error or "")


def test_queued_row_still_queued_in_rq_is_left_alone(db, monkeypatch):
    row = _make_job(db, status=JobStatus.QUEUED)
    _install_rq(monkeypatch, {row.job_id: _FakeJob("queued")})

    assert _reconcile_orphan_import_jobs(db) == 0

    db.refresh(row)
    assert row.status == JobStatus.QUEUED.value
