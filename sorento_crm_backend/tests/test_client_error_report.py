"""CLIENT-ERROR-REPORT: browser crash reports.

Covers: a report is stored with the query string stripped and every field capped
server-side; an oversized body is refused before parsing; a user is rate-limited per
rolling hour; the list needs its own view slug; rows older than 30 days are pruned.
"""
import json
from datetime import datetime, timedelta

import pytest

from app.models.api_call_log import ApiCallLog  # noqa: F401  (the prune handler also touches it)
from app.models.client_error_report import ClientErrorReport
from app.services import client_error_report_service as svc
from tests._ai_usage_client import api_client
from tests._pg_fixture import blank_session

VIEW = "system_management.client_error.view"
URL = "/api/v1/system/client-errors"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _report(**over):
    body = {
        "boundary": "global",
        "name": "TypeError",
        "message": "undefined is not an object",
        "stack": "at foo (x.js:1:1)",
        "digest": "123abc",
        "path": "/inventory/stock-inquiries?q=customer+name#frag",
        "build_sha": "24189427cb",
        "is_chunk_error": False,
        "timestamp": "2026-11-04T06:05:00.000Z",
    }
    body.update(over)
    return body


def test_post_stores_one_row_path_only(db):
    with api_client(db, []) as client:
        r = client.post(URL, json=_report(), headers={"User-Agent": "Safari/605.1.15"})
    assert r.status_code == 204
    rows = db.query(ClientErrorReport).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.path == "/inventory/stock-inquiries"
    assert row.user_id == client.actor["id"]
    assert row.user_agent == "Safari/605.1.15"
    assert row.build_sha == "24189427cb"
    assert row.error_name == "TypeError"
    assert row.is_chunk_error is False
    assert row.client_ts == datetime(2026, 11, 4, 6, 5)


def test_fields_are_capped_server_side(db):
    body = _report(message="m" * 5000, stack="s" * 9000, name="n" * 400, build_sha="b" * 200)
    raw = json.dumps(body)
    assert len(raw.encode()) < svc.MAX_BODY_BYTES
    with api_client(db, []) as client:
        r = client.post(URL, content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 204
    row = db.query(ClientErrorReport).one()
    assert len(row.message) == svc.MAX_MESSAGE
    assert len(row.stack) == svc.MAX_STACK
    assert len(row.error_name) == svc.MAX_NAME
    assert len(row.build_sha) == svc.MAX_BUILD_SHA


def test_oversized_body_is_refused_and_nothing_stored(db):
    with api_client(db, []) as client:
        r = client.post(URL, json=_report(stack="s" * (svc.MAX_BODY_BYTES + 10)))
    assert r.status_code == 413
    assert db.query(ClientErrorReport).count() == 0


def test_invalid_body_is_422(db):
    with api_client(db, []) as client:
        r = client.post(URL, content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert db.query(ClientErrorReport).count() == 0


def test_rate_limited_per_user_per_hour(db):
    with api_client(db, []) as client:
        codes = [client.post(URL, json=_report()).status_code for _ in range(svc.RATE_LIMIT_PER_HOUR + 2)]
    assert codes[: svc.RATE_LIMIT_PER_HOUR] == [204] * svc.RATE_LIMIT_PER_HOUR
    assert codes[svc.RATE_LIMIT_PER_HOUR:] == [429, 429]
    assert db.query(ClientErrorReport).count() == svc.RATE_LIMIT_PER_HOUR


def test_rate_limit_window_is_one_hour(db):
    uid = "11111111-1111-1111-1111-111111111111"
    for _ in range(svc.RATE_LIMIT_PER_HOUR):
        db.add(ClientErrorReport(user_id=uid, boundary="global",
                                 created_at=datetime.utcnow() - timedelta(minutes=61)))
    db.commit()
    assert svc.is_rate_limited(db, uid) is False


def test_link_token_in_path_is_redacted():
    assert "abc123secret" not in svc.clean_path("/api/v1/public/file-links/abc123secret?x=1")


def test_list_requires_view_permission(db):
    with api_client(db, []) as client:
        assert client.get(URL).status_code == 403


def test_list_returns_rows_and_filters_chunk_errors(db):
    with api_client(db, [VIEW]) as client:
        client.post(URL, json=_report(message="first"))
        client.post(URL, json=_report(message="second", is_chunk_error=True))
        r = client.get(URL)
        chunk = client.get(URL, params={"chunk_only": "true"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert {d["message"] for d in data["data"]} == {"first", "second"}
    assert [d["message"] for d in chunk.json()["data"]] == ["second"]


def test_prune_deletes_rows_past_30_days(db):
    db.add(ClientErrorReport(boundary="global", message="old",
                             created_at=datetime.utcnow() - timedelta(days=31)))
    db.add(ClientErrorReport(boundary="global", message="new",
                             created_at=datetime.utcnow() - timedelta(days=29)))
    db.commit()
    assert svc.prune_client_error_reports(db) == 1
    db.commit()
    assert [r.message for r in db.query(ClientErrorReport).all()] == ["new"]


def test_chunked_oversized_body_is_refused_without_content_length(db):
    def gen():
        yield b'{"message": "'
        for _ in range(40):
            yield b"x" * 1024
        yield b'"}'

    with api_client(db, []) as client:
        r = client.post(URL, content=gen(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert db.query(ClientErrorReport).count() == 0


def test_link_tokens_in_message_and_stack_are_redacted(db):
    body = _report(
        message="Failed to fetch https://x.my/api/v1/public/file-links/sekrit1?token=sekrit2",
        stack="at load (https://x.my/view?token=sekrit3)",
    )
    with api_client(db, []) as client:
        assert client.post(URL, json=body).status_code == 204
    row = db.query(ClientErrorReport).one()
    for secret in ("sekrit1", "sekrit2", "sekrit3"):
        assert secret not in (row.message or "") + (row.stack or "")


def test_nul_and_extreme_timestamp_do_not_lose_the_report(db):
    body = _report(message="a\u0000b", timestamp="0001-01-01T00:00:00+01:00")
    with api_client(db, []) as client:
        assert client.post(URL, json=body).status_code == 204
    row = db.query(ClientErrorReport).one()
    assert row.message == "ab"
    assert row.client_ts is None


def test_bad_timestamp_keeps_the_report(db):
    with api_client(db, []) as client:
        assert client.post(URL, json=_report(timestamp="not a date")).status_code == 204
    assert db.query(ClientErrorReport).one().client_ts is None


def test_daily_prune_task_deletes_old_client_errors(db):
    """The 30-day retention rides the api_call_log_prune handler; guard the hook itself."""
    from app.scheduler.task_scheduler import _handler_api_call_log_prune

    db.add(ClientErrorReport(boundary="global", message="old",
                             created_at=datetime.utcnow() - timedelta(days=31)))
    db.add(ClientErrorReport(boundary="global", message="new",
                             created_at=datetime.utcnow() - timedelta(days=29)))
    db.commit()
    result = _handler_api_call_log_prune(db, None)
    assert result["client_error_reports_deleted"] == 1
    assert "rows_deleted" in result and "payloads_cleared" in result
    assert [r.message for r in db.query(ClientErrorReport).all()] == ["new"]
