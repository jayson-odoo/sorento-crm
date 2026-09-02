"""A failed import job stores a one-line summary, not a raw traceback.

Reproduced from production: a failed import's `error` column held the full
Python exception traceback verbatim (RQ's own `exc_info`, or a caller passing
`str(exc)` on a multi-line message). The Upload activity drawer renders that
column on one row, and an unbroken traceback line pushed the row's status
icon off the drawer's right edge. `JobService.fail_job` now stores only the
exception's last line (plus the failing function when the text looks like a
traceback) - the full text still reaches the server log.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.job import ImportJob, JobStatus
from app.services.job_service import JobService
import app.services.job_service as job_service_mod
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _no_notifications(monkeypatch):
    """fail_job fans out a notification; this suite is about the `error` column."""
    monkeypatch.setattr(job_service_mod, "_notify_import_job_event", lambda *a, **k: None)


def _make_job(db, *, job_type="spo_import"):
    row = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        status=JobStatus.STARTED.value,
        user_id=unique_code("USER"),
        filename=f"{unique_code('SPO')}.xlsx",
        created_at=datetime.utcnow() - timedelta(minutes=5),
        started_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(row)
    # commit, not flush: `fail_job` opens with a `rollback()`, which would
    # discard a row that only existed on the flush.
    db.commit()
    return row


_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/'
    'venv/lib/python3.12/site-packages/rq/worker.py", line 1414, in perform_job\n'
    "    rv = job.perform()\n"
    '  File "/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/'
    'app/tasks/import_tasks.py", line 512, in process_outstanding_import\n'
    "    getattr(module, attr_name)\n"
    "ValueError: Invalid attribute name: process_outstanding_import"
)


def test_a_multiline_traceback_is_summarised_to_its_last_line(db):
    row = _make_job(db)

    JobService(db).fail_job(row.job_id, _TRACEBACK)

    db.refresh(row)
    assert row.status == JobStatus.FAILED.value
    assert row.error == (
        "ValueError: Invalid attribute name: process_outstanding_import "
        "(in process_outstanding_import)"
    )
    # No embedded newlines - a single row in the drawer can render this on one line.
    assert "\n" not in row.error
    assert "Traceback (most recent call last)" not in row.error


def test_a_single_line_message_passes_through_unchanged(db):
    row = _make_job(db)
    message = "Filename must provide SPO number (e.g. SPO-2025.10-0050.xlsx)"

    JobService(db).fail_job(row.job_id, message)

    db.refresh(row)
    assert row.error == message


def test_an_oversized_summary_is_capped_at_2000_chars(db):
    row = _make_job(db)
    huge = "x" * 5000

    JobService(db).fail_job(row.job_id, huge)

    db.refresh(row)
    assert len(row.error) == 2000


def test_the_full_traceback_reaches_the_log_even_though_the_column_is_trimmed(db, caplog):
    row = _make_job(db)

    with caplog.at_level("ERROR"):
        JobService(db).fail_job(row.job_id, _TRACEBACK)

    assert any(_TRACEBACK in record.getMessage() for record in caplog.records), (
        "the full traceback must survive somewhere - the server log - even "
        "though the DB column now only carries the summary"
    )
