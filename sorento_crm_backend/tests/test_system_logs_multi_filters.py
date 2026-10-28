"""FILTER-MULTISELECT PR2: API call logs (source, outcome), AI usage (feature) and Import job rows
(outcome, code) take several values (OR within a filter, AND across). Red first; Postgres only; rows
seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.ai_assistant import AIAssistantUsageLog
from app.models.api_call_log import ApiCallLog
from app.models.job import ImportJob, ImportJobRow
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

CALLS = "/api/v1/system/api-call-logs"
USAGE = "/api/v1/system/ai-assistant/usage"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def ctx(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, actor):
        yield c, actor


# ---- API call logs ------------------------------------------------------------------------------

def _call(db, source, outcome):
    row = ApiCallLog(id=str(uuid.uuid4()), endpoint="/zzt", method="GET", source=source, outcome=outcome,
                     status_code=200)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def calls(db):
    a = _call(db, "mcp", "success")
    b = _call(db, "n8n", "client_error")
    c = _call(db, "unknown", "server_error")
    d = _call(db, "mcp", "client_error")
    return dict(a=a, b=b, c=c, d=d)


def _calls(client, pairs):
    resp = client.get(CALLS, params=[("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_call_source_union(ctx, calls):
    c, _ = ctx
    s = calls
    assert _calls(c, [("source", "mcp,unknown")]) == {s["a"].id, s["c"].id, s["d"].id}


def test_call_source_single_and_repeated(ctx, calls):
    c, _ = ctx
    s = calls
    assert _calls(c, [("source", "n8n")]) == {s["b"].id}
    assert _calls(c, [("source", "n8n"), ("source", "unknown")]) == {s["b"].id, s["c"].id}


def test_call_outcome_union(ctx, calls):
    c, _ = ctx
    s = calls
    assert _calls(c, [("outcome", "success,server_error")]) == {s["a"].id, s["c"].id}


def test_call_outcome_single_and_repeated(ctx, calls):
    c, _ = ctx
    s = calls
    assert _calls(c, [("outcome", "client_error")]) == {s["b"].id, s["d"].id}
    assert _calls(c, [("outcome", "success"), ("outcome", "server_error")]) == {s["a"].id, s["c"].id}


def test_call_unknown_outcome_is_422(ctx, calls):
    c, _ = ctx
    assert c.get(CALLS, params=[("outcome", "bogus")]).status_code == 422
    assert c.get(CALLS, params=[("outcome", "success,bogus")]).status_code == 422


def test_call_filters_and_across_each_other(ctx, calls):
    c, _ = ctx
    s = calls
    got = _calls(c, [("source", "mcp,n8n"), ("outcome", "client_error,server_error")])
    assert got == {s["b"].id, s["d"].id}


# ---- AI usage -----------------------------------------------------------------------------------

def _usage(db, feature, tokens):
    row = AIAssistantUsageLog(id=str(uuid.uuid4()), feature=feature, total_tokens=tokens,
                              prompt_tokens=tokens, completion_tokens=0, created_at=datetime.utcnow())
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def usage(db):
    _usage(db, "ai_assistant", 1)
    _usage(db, "ai_extract", 10)
    _usage(db, "chatbot_parser", 100)
    _usage(db, "ai_extract", 10)


def _messages(client, pairs):
    resp = client.get(f"{USAGE}/summary", params=pairs)
    assert resp.status_code == 200, resp.text
    return resp.json()["total_messages"]


def test_usage_feature_union(ctx, usage):
    c, _ = ctx
    assert _messages(c, [("feature", "ai_assistant,chatbot_parser")]) == 2


def test_usage_feature_single_and_repeated(ctx, usage):
    c, _ = ctx
    assert _messages(c, [("feature", "ai_extract")]) == 2
    assert _messages(c, [("feature", "ai_assistant"), ("feature", "ai_extract")]) == 3


def test_usage_feature_union_on_the_daily_chart(ctx, usage):
    c, _ = ctx
    resp = c.get(f"{USAGE}/by-day", params=[("feature", "ai_extract,chatbot_parser")])
    assert resp.status_code == 200, resp.text
    assert sum(item["messages"] for item in resp.json()) == 3


# ---- Import job rows ----------------------------------------------------------------------------

def _job(db, actor):
    row = ImportJob(id=uuid.uuid4(), job_id=unique_code("job"), job_type="stock_import",
                    status="pending", user_id=actor.id)
    db.add(row)
    db.flush()
    return row


def _jrow(db, job, outcome, code, n):
    row = ImportJobRow(id=uuid.uuid4(), import_job_id=job.id, row_number=n, outcome=outcome, code=code)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def rows(db, ctx):
    _, actor = ctx
    job = _job(db, actor)
    a = _jrow(db, job, "created", "ok", 1)
    b = _jrow(db, job, "skipped", "dup", 2)
    c = _jrow(db, job, "failed", "bad_qty", 3)
    d = _jrow(db, job, "failed", "dup", 4)
    return dict(job=job, a=a, b=b, c=c, d=d)


def _rows(client, s, pairs):
    resp = client.get(f"/api/v1/system/jobs/{s['job'].id}/rows", params=[("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def _ids(*rs):
    return {str(r.id) for r in rs}


def test_rows_outcome_union(ctx, rows):
    c, _ = ctx
    s = rows
    assert _rows(c, s, [("outcome", "created,skipped")]) == _ids(s["a"], s["b"])


def test_rows_outcome_single_and_repeated(ctx, rows):
    c, _ = ctx
    s = rows
    assert _rows(c, s, [("outcome", "failed")]) == _ids(s["c"], s["d"])
    assert _rows(c, s, [("outcome", "created"), ("outcome", "skipped")]) == _ids(s["a"], s["b"])


def test_rows_code_union(ctx, rows):
    c, _ = ctx
    s = rows
    assert _rows(c, s, [("code", "ok,bad_qty")]) == _ids(s["a"], s["c"])


def test_rows_code_single_and_repeated(ctx, rows):
    c, _ = ctx
    s = rows
    assert _rows(c, s, [("code", "dup")]) == _ids(s["b"], s["d"])
    assert _rows(c, s, [("code", "ok"), ("code", "bad_qty")]) == _ids(s["a"], s["c"])


def test_rows_filters_and_across_each_other(ctx, rows):
    c, _ = ctx
    s = rows
    got = _rows(c, s, [("outcome", "skipped,failed"), ("code", "dup,ok")])
    assert got == _ids(s["b"], s["d"])


def test_rows_export_takes_the_same_filters(ctx, rows):
    c, _ = ctx
    s = rows
    resp = c.get(f"/api/v1/system/jobs/{s['job'].id}/rows/export", params=[("outcome", "created,skipped")])
    assert resp.status_code == 200, resp.text
    lines = [ln for ln in resp.text.splitlines() if ln.strip()]
    assert len(lines) == 3  # header + two rows
