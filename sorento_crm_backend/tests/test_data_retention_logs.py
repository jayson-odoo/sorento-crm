"""DB-RETENTION: log-type rules (integration log, api call log, chat turn traces,
scheduler run history, superseded AI search chunks, import rows).

Plan: documentation/plans/infra/PLAN-db-retention-12nov.md (section 2 rules, section 7
contract). UAC: documentation/plans/infra/db-retention-acceptance-criteria.md, items 2-4,
6-8, 10, 11.

Blank Postgres schema (``blank_session``): every table starts empty, so a rule's counts
are exactly the rows seeded here. The service module is imported per test so a missing
module fails each test individually instead of erroring collection.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import null, text

from app.models.api_call_log import ApiCallLog
from app.models.base import set_company_scope
from app.models.chatbot_turn import ChatbotTurn
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.models.integration import IntegrationLog
from app.models.job import ImportJob, ImportJobRow, JobStatus
from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun
from tests._pg_fixture import blank_session

MARKER = "ZZTDBR"


def _svc():
    from app.services import data_retention_service

    return data_retention_service


def _u() -> str:
    return str(uuid.uuid4())


def _ago(days: float) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


def _pk(obj) -> str:
    """The primary key without touching an expired attribute: reading ``obj.id`` after a
    rule deleted the row raises ObjectDeletedError, which is not the assertion's point."""
    return str(sa_inspect(obj).identity[0])


def _counts(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in ("dry_run", "finished")}


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)  # what the scheduler gives a task run
        yield s


# --------------------------------------------------------------------------- #
# R2 integration log
# --------------------------------------------------------------------------- #

def _ilog(db, *, days, status="success", filled=True, channel="zzt") -> IntegrationLog:
    body = "body" if filled else None
    row = IntegrationLog(
        integration_channel=channel, business_table="zzt", business_id=_u(),
        direction="outbound", endpoint="/zzt", http_method="POST", status=status,
        request_payload=body, response_payload=body,
        request_headers=body, response_headers=body,
        created_at=_ago(days),
    )
    db.add(row)
    db.flush()
    return row


def _ilog_fields(db, row) -> tuple | None:
    got = db.execute(
        text(
            "SELECT request_payload, response_payload, request_headers, response_headers "
            "FROM integration_log WHERE id = :id"
        ),
        {"id": _pk(row)},
    ).first()
    return tuple(got) if got else None


def _integration_rule(db, **kw):
    return _svc().prune_integration_log(
        db, payload_retention_days=30, row_retention_days=180, **kw
    )


def test_integration_log_payloads_and_headers_blank_then_rows_delete(db):
    """UAC 6: payloads AND headers blank past 30 d, rows go past 180 d, recent untouched."""
    recent = _ilog(db, days=1)
    mid = _ilog(db, days=45)
    old = _ilog(db, days=200)
    db.commit()

    result = _integration_rule(db)

    assert result["payloads_cleared"] == 1 and result["rows_deleted"] == 1
    assert result["dry_run"] is False and result["finished"] is True
    assert _ilog_fields(db, recent) == ("body",) * 4
    assert _ilog_fields(db, mid) == (None,) * 4
    assert _ilog_fields(db, old) is None


@pytest.mark.parametrize("status", ["pending", "processing"])
def test_integration_log_pending_and_processing_rows_are_never_touched(db, status):
    """UAC 6: an in-flight row keeps its payload and its row, whatever its age."""
    mid = _ilog(db, days=45, status=status)
    old = _ilog(db, days=400, status=status)
    db.commit()

    result = _integration_rule(db)

    assert result["payloads_cleared"] == 0 and result["rows_deleted"] == 0
    assert _ilog_fields(db, mid) == ("body",) * 4
    assert _ilog_fields(db, old) == ("body",) * 4


def test_integration_log_audit_failure_rows_are_never_touched(db):
    """Security review: a channel-`audit` row is the record of a failed audit capture
    (audit_trail_gaps.integration_log_id points at it), so retention never blanks or
    deletes it however old, and dry-run does not count it either."""
    from app.services.audit_service import AUDIT_FAILURE_CHANNEL

    audit_mid = _ilog(db, days=45, channel=AUDIT_FAILURE_CHANNEL)
    audit_old = _ilog(db, days=400, channel=AUDIT_FAILURE_CHANNEL)
    _ilog(db, days=45)
    _ilog(db, days=400)
    db.commit()

    dry = _integration_rule(db, dry_run=True)
    assert dry["payloads_cleared"] == 1 and dry["rows_deleted"] == 1

    live = _integration_rule(db)

    assert live["payloads_cleared"] == 1 and live["rows_deleted"] == 1
    assert _ilog_fields(db, audit_mid) == ("body",) * 4
    assert _ilog_fields(db, audit_old) == ("body",) * 4


def test_integration_log_rerun_does_not_recount_blanked_rows(db):
    _ilog(db, days=45)
    db.commit()
    _integration_rule(db)
    assert _integration_rule(db)["payloads_cleared"] == 0


def test_integration_log_dry_run_counts_match_live_run_and_change_nothing(db):
    rows = [_ilog(db, days=d) for d in (1, 45, 60, 200, 300)]
    db.commit()
    before = [_ilog_fields(db, r) for r in rows]

    dry = _integration_rule(db, dry_run=True)

    assert dry["dry_run"] is True and dry["finished"] is True
    assert [_ilog_fields(db, r) for r in rows] == before

    live = _integration_rule(db)

    assert _counts(dry) == _counts(live)
    assert live["payloads_cleared"] == 2 and live["rows_deleted"] == 2


def test_integration_log_small_batch_size_still_finishes(db):
    for d in (45, 50, 55, 200, 250, 300):
        _ilog(db, days=d)
    db.commit()

    result = _integration_rule(db, batch_size=1)

    assert result["finished"] is True
    assert result["payloads_cleared"] == 3 and result["rows_deleted"] == 3
    assert db.query(IntegrationLog).count() == 3


def test_integration_log_time_budget_stops_after_one_batch_and_next_run_continues(db):
    for d in (200, 250, 300):
        _ilog(db, days=d)
    db.commit()

    first = _integration_rule(db, batch_size=1, max_seconds=0)

    assert first["finished"] is False and first["rows_deleted"] == 1
    assert db.query(IntegrationLog).count() == 2

    second = _integration_rule(db, batch_size=1)

    assert second["finished"] is True and second["rows_deleted"] == 2
    assert db.query(IntegrationLog).count() == 0


# --------------------------------------------------------------------------- #
# R2b api call log: existing behaviour (tests/test_api_call_log_prune.py) + new knobs
# --------------------------------------------------------------------------- #

def _alog(db, *, days) -> ApiCallLog:
    row = ApiCallLog(
        endpoint="/api/v1/external/thing", method="POST", source="n8n", outcome="success",
        status_code=200, request_payload="body", response_payload="body",
        created_at=_ago(days),
    )
    db.add(row)
    db.flush()
    return row


def _api_rule(db, **kw):
    from app.services.api_call_log_service import prune_api_call_log

    return prune_api_call_log(db, payload_retention_days=30, row_retention_days=180, **kw)


def test_api_call_log_old_kwargs_still_work_and_report_live_finished(db):
    for d in (1, 45, 200):
        _alog(db, days=d)
    db.commit()

    result = _api_rule(db)

    assert result["payloads_cleared"] == 1 and result["rows_deleted"] == 1
    assert result["dry_run"] is False and result["finished"] is True


def test_api_call_log_dry_run_counts_match_live_run_and_change_nothing(db):
    for d in (1, 45, 60, 200):
        _alog(db, days=d)
    db.commit()

    dry = _api_rule(db, dry_run=True)

    assert dry["dry_run"] is True
    assert db.query(ApiCallLog).count() == 4
    assert db.query(ApiCallLog).filter(ApiCallLog.request_payload.is_(None)).count() == 0

    live = _api_rule(db)

    assert _counts(dry) == _counts(live)
    assert live["payloads_cleared"] == 2 and live["rows_deleted"] == 1


def test_api_call_log_small_batch_size_still_finishes(db):
    for d in (45, 50, 200, 250, 300):
        _alog(db, days=d)
    db.commit()

    result = _api_rule(db, batch_size=1)

    assert result["finished"] is True
    assert result["payloads_cleared"] == 2 and result["rows_deleted"] == 3


def test_api_call_log_time_budget_stops_after_one_batch_and_next_run_continues(db):
    for d in (200, 250, 300):
        _alog(db, days=d)
    db.commit()

    first = _api_rule(db, batch_size=1, max_seconds=0)
    assert first["finished"] is False and first["rows_deleted"] == 1

    second = _api_rule(db, batch_size=1)
    assert second["finished"] is True and second["rows_deleted"] == 2
    assert db.query(ApiCallLog).count() == 0


# --------------------------------------------------------------------------- #
# R3a chat turn traces
# --------------------------------------------------------------------------- #

def _turn(db, *, days, trace=True) -> ChatbotTurn:
    row = ChatbotTurn(
        id=_u(), contact_respond_id=f"{MARKER}-c", message_id=f"{MARKER}-{uuid.uuid4().hex[:8]}",
        envelope={}, status="done",
        # null(), not None: the ORM writes a Python None into JSONB as JSON 'null', which
        # IS NOT NULL to SQL and would count as a trace still to clear.
        trace=[{"stage": "parse"}] if trace else null(),
        created_at=datetime.now(timezone.utc) - timedelta(days=days),
    )
    db.add(row)
    db.flush()
    return row


def _trace_is_sql_null(db, row) -> bool | None:
    """SQL NULL, not JSON 'null': the rule's own selector is `trace IS NOT NULL`."""
    # A column query, so it reads the database rather than the identity map; ORM-built so
    # the blank schema's translate map applies (a raw `chatbot.turns` would hit the real one).
    got = db.query(ChatbotTurn.trace.is_(None)).filter(ChatbotTurn.id == _pk(row)).first()
    return None if got is None else bool(got[0])


def _turn_rule(db, **kw):
    return _svc().prune_chatbot_turn_traces(db, retention_days=90, **kw)


def test_old_chat_turns_lose_their_trace_and_keep_the_turn(db):
    """UAC 7."""
    old = _turn(db, days=100)
    recent = _turn(db, days=10)
    _turn(db, days=200, trace=False)  # nothing to clear: not counted
    db.commit()

    result = _turn_rule(db)

    assert result["traces_cleared"] == 1
    assert result["dry_run"] is False and result["finished"] is True
    assert _trace_is_sql_null(db, old) is True  # row kept, trace gone
    assert _trace_is_sql_null(db, recent) is False
    assert db.query(ChatbotTurn).count() == 3


def test_chat_turn_trace_dry_run_counts_match_live_run_and_change_nothing(db):
    rows = [_turn(db, days=d) for d in (10, 100, 150)]
    db.commit()

    dry = _turn_rule(db, dry_run=True)

    assert dry["dry_run"] is True
    assert all(_trace_is_sql_null(db, r) is False for r in rows)

    live = _turn_rule(db)

    assert _counts(dry) == _counts(live)
    assert live["traces_cleared"] == 2


def test_chat_turn_trace_small_batch_size_still_finishes(db):
    for d in (100, 150, 200):
        _turn(db, days=d)
    db.commit()

    result = _turn_rule(db, batch_size=1)

    assert result["finished"] is True and result["traces_cleared"] == 3


def test_chat_turn_trace_time_budget_stops_after_one_batch_and_next_run_continues(db):
    rows = [_turn(db, days=d) for d in (100, 150, 200)]
    db.commit()

    first = _turn_rule(db, batch_size=1, max_seconds=0)
    assert first["finished"] is False and first["traces_cleared"] == 1

    second = _turn_rule(db, batch_size=1)
    assert second["finished"] is True and second["traces_cleared"] == 2
    assert all(_trace_is_sql_null(db, r) is True for r in rows)


# --------------------------------------------------------------------------- #
# R3b scheduler run history
# --------------------------------------------------------------------------- #

def _task(db) -> ScheduledTask:
    t = ScheduledTask(
        id=_u(), key=f"{MARKER}-{uuid.uuid4().hex[:8]}", name=f"{MARKER} task",
        interval_unit="days", interval_value=1,
    )
    db.add(t)
    db.flush()
    return t


def _task_run(db, task, *, days) -> ScheduledTaskRun:
    r = ScheduledTaskRun(id=_u(), task_id=task.id, started_at=_ago(days), status="success")
    db.add(r)
    db.flush()
    return r


def _run_rule(db, **kw):
    return _svc().prune_scheduled_task_runs(db, retention_days=90, **kw)


def _runs_left(db, task) -> set[str]:
    return {str(i) for (i,) in db.query(ScheduledTaskRun.id).filter(ScheduledTaskRun.task_id == task.id)}


def test_old_task_runs_go_except_the_newest_run_of_each_task(db):
    """UAC 8: history past 90 d goes; a task that has not run since keeps its newest run."""
    busy = _task(db)
    for d in (200, 150, 120):
        _task_run(db, busy, days=d)
    recent = _task_run(db, busy, days=10)
    idle = _task(db)
    _task_run(db, idle, days=300)
    idle_newest = _task_run(db, idle, days=200)
    db.commit()

    result = _run_rule(db)

    assert result["rows_deleted"] == 4
    assert result["dry_run"] is False and result["finished"] is True
    assert _runs_left(db, busy) == {str(recent.id)}
    assert _runs_left(db, idle) == {str(idle_newest.id)}


def _three_old_runs_plus_newest(db):
    task = _task(db)
    for d in (400, 300, 200):
        _task_run(db, task, days=d)
    newest = _task_run(db, task, days=1)
    db.commit()
    return task, newest


def test_task_run_dry_run_counts_match_live_run_and_change_nothing(db):
    task, _ = _three_old_runs_plus_newest(db)

    dry = _run_rule(db, dry_run=True)

    assert dry["dry_run"] is True
    assert len(_runs_left(db, task)) == 4

    live = _run_rule(db)

    assert _counts(dry) == _counts(live)
    assert live["rows_deleted"] == 3


def test_task_run_small_batch_size_still_finishes(db):
    task, newest = _three_old_runs_plus_newest(db)

    result = _run_rule(db, batch_size=1)

    assert result["finished"] is True and result["rows_deleted"] == 3
    assert _runs_left(db, task) == {str(newest.id)}


def test_task_run_time_budget_stops_after_one_batch_and_next_run_continues(db):
    task, newest = _three_old_runs_plus_newest(db)

    first = _run_rule(db, batch_size=1, max_seconds=0)
    assert first["finished"] is False and first["rows_deleted"] == 1
    assert len(_runs_left(db, task)) == 3

    second = _run_rule(db, batch_size=1)
    assert second["finished"] is True and second["rows_deleted"] == 2
    assert _runs_left(db, task) == {str(newest.id)}


# --------------------------------------------------------------------------- #
# R3d superseded AI search chunks
# --------------------------------------------------------------------------- #

@pytest.fixture
def document(db):
    doc = EmbeddingDocument(
        id=_u(), source_type="zzt", source_id=f"{MARKER}-{uuid.uuid4().hex[:8]}",
        body_text="zzt", source_hash="h",
    )
    db.add(doc)
    db.flush()
    return doc


_chunk_index = iter(range(10_000))


def _chunk(db, doc, *, current, superseded_days=None, embedded_days=0) -> EmbeddingChunk:
    c = EmbeddingChunk(
        id=_u(), document_id=doc.id, source_type=doc.source_type, source_id=doc.source_id,
        chunk_index=next(_chunk_index), chunk_text="zzt", chunk_hash="h",
        embedding=[0.0] * 1536, model_name="zzt-model", model_version="1",
        embedding_provider="zzt", source_hash="h",
        is_current=current,
        superseded_at=None if superseded_days is None else _ago(superseded_days),
        embedded_at=_ago(embedded_days),
    )
    db.add(c)
    db.flush()
    return c


def _chunk_ids(db) -> set[str]:
    return {str(i) for (i,) in db.query(EmbeddingChunk.id)}


def _chunk_rule(db, **kw):
    return _svc().prune_superseded_embeddings(db, retention_days=90, **kw)


def test_chunks_superseded_long_ago_are_deleted_and_current_never(db, document):
    """UAC 10: superseded past 90 d goes; a current chunk stays however old it is."""
    old_current = _chunk(db, document, current=True, embedded_days=1000)
    _chunk(db, document, current=False, superseded_days=100, embedded_days=300)
    recent_superseded = _chunk(db, document, current=False, superseded_days=10, embedded_days=300)
    db.commit()

    result = _chunk_rule(db)

    assert result["rows_deleted"] == 1
    assert result["dry_run"] is False and result["finished"] is True
    assert _chunk_ids(db) == {str(old_current.id), str(recent_superseded.id)}


def _three_old_superseded(db, doc):
    keep = _chunk(db, doc, current=True, embedded_days=500)
    for d in (100, 200, 300):
        _chunk(db, doc, current=False, superseded_days=d, embedded_days=400)
    db.commit()
    return keep


def test_chunk_dry_run_counts_match_live_run_and_change_nothing(db, document):
    _three_old_superseded(db, document)

    dry = _chunk_rule(db, dry_run=True)

    assert dry["dry_run"] is True
    assert len(_chunk_ids(db)) == 4

    live = _chunk_rule(db)

    assert _counts(dry) == _counts(live)
    assert live["rows_deleted"] == 3


def test_chunk_small_batch_size_still_finishes(db, document):
    keep = _three_old_superseded(db, document)

    result = _chunk_rule(db, batch_size=1)

    assert result["finished"] is True and result["rows_deleted"] == 3
    assert _chunk_ids(db) == {str(keep.id)}


def test_chunk_time_budget_stops_after_one_batch_and_next_run_continues(db, document):
    keep = _three_old_superseded(db, document)

    first = _chunk_rule(db, batch_size=1, max_seconds=0)
    assert first["finished"] is False and first["rows_deleted"] == 1
    assert len(_chunk_ids(db)) == 3

    second = _chunk_rule(db, batch_size=1)
    assert second["finished"] is True and second["rows_deleted"] == 2
    assert _chunk_ids(db) == {str(keep.id)}


# --------------------------------------------------------------------------- #
# R3e import rows: existing function, new knobs
# --------------------------------------------------------------------------- #

@pytest.fixture
def import_job(db):
    job = ImportJob(
        id=uuid.uuid4(), job_id=str(uuid.uuid4()), job_type="zzt_import",
        status=JobStatus.FINISHED.value, user_id=_u(), total_rows=0,
    )
    db.add(job)
    db.flush()
    return job


def _import_row(db, job, *, days) -> ImportJobRow:
    r = ImportJobRow(
        id=uuid.uuid4(), import_job_id=job.id, outcome="created", code="created",
        created_at=_ago(days),
    )
    db.add(r)
    db.flush()
    return r


def _import_rule(db, **kw):
    from app.services.import_outcome import prune_import_job_rows

    return prune_import_job_rows(db, retention_days=90, **kw)


def test_import_rows_old_go_recent_stay_and_old_kwargs_still_work(db, import_job):
    """UAC 11: existing behaviour, plus dry_run/finished in the result."""
    _import_row(db, import_job, days=100)
    recent = _import_row(db, import_job, days=10)
    db.commit()

    result = _import_rule(db)

    assert result["rows_deleted"] == 1 and result["retention_days"] == 90
    assert result["dry_run"] is False and result["finished"] is True
    assert [r.id for r in db.query(ImportJobRow).all()] == [recent.id]


def test_import_rows_dry_run_counts_match_live_run_and_change_nothing(db, import_job):
    for d in (10, 100, 200):
        _import_row(db, import_job, days=d)
    db.commit()

    dry = _import_rule(db, dry_run=True)

    assert dry["dry_run"] is True
    assert db.query(ImportJobRow).count() == 3

    live = _import_rule(db)

    assert _counts(dry) == _counts(live)
    assert live["rows_deleted"] == 2


def test_import_rows_small_batch_size_still_finishes(db, import_job):
    for d in (100, 200, 300):
        _import_row(db, import_job, days=d)
    db.commit()

    result = _import_rule(db, batch_size=1)

    assert result["finished"] is True and result["rows_deleted"] == 3


def test_import_rows_time_budget_stops_after_one_batch_and_next_run_continues(db, import_job):
    for d in (100, 200, 300):
        _import_row(db, import_job, days=d)
    db.commit()

    first = _import_rule(db, batch_size=1, max_seconds=0)
    assert first["finished"] is False and first["rows_deleted"] == 1
    assert db.query(ImportJobRow).count() == 2

    second = _import_rule(db, batch_size=1)
    assert second["finished"] is True and second["rows_deleted"] == 2
    assert db.query(ImportJobRow).count() == 0
