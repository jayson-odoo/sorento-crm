"""api_call_log retention. Covers UAC OBS-S3-10.

Two-stage on purpose. Payloads are the bulk of the bytes and the shortest-lived
value; the metadata row (endpoint, latency, outcome) stays useful for trend
analysis long after the body does. So payloads NULL at 30d, rows DELETE at 180d.

Deleting rows at 30d would be the simpler design and would throw away the volume
history that makes the table worth having.
"""
from datetime import datetime, timedelta

import pytest

from app.services.api_call_log_service import prune_api_call_log
from app.models.api_call_log import ApiCallLog
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _row(session, *, days_ago, payload="body"):
    row = ApiCallLog(
        endpoint="/api/v1/external/thing",
        method="POST",
        source="n8n",
        outcome="success",
        status_code=200,
        request_payload=payload,
        response_payload=payload,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    )
    session.add(row)
    session.commit()
    return row


def test_recent_rows_are_untouched(db):
    _row(db, days_ago=1)
    prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)
    row = db.query(ApiCallLog).one()
    assert row.request_payload == "body"


def test_payloads_are_nulled_past_the_payload_window(db):
    _row(db, days_ago=45)
    prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)
    row = db.query(ApiCallLog).one()
    # Row survives - the metadata is the long-lived part.
    assert row.request_payload is None
    assert row.response_payload is None
    assert row.endpoint == "/api/v1/external/thing"


def test_rows_are_deleted_past_the_row_window(db):
    _row(db, days_ago=200)
    prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)
    assert db.query(ApiCallLog).count() == 0


def test_both_stages_in_one_run(db):
    _row(db, days_ago=1)
    _row(db, days_ago=45)
    _row(db, days_ago=200)
    result = prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)

    remaining = db.query(ApiCallLog).order_by(ApiCallLog.created_at.desc()).all()
    assert len(remaining) == 2
    assert remaining[0].request_payload == "body"   # 1 day old
    assert remaining[1].request_payload is None     # 45 days old
    assert result["payloads_cleared"] == 1
    assert result["rows_deleted"] == 1


def test_already_nulled_payloads_are_not_recounted(db):
    """Re-running must report 0 cleared, not re-clear the same rows forever - 
    otherwise the task's own output implies work that is not happening."""
    _row(db, days_ago=45)
    prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)
    second = prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)
    assert second["payloads_cleared"] == 0


def test_boundary_is_inclusive_of_newer_rows(db):
    """A row exactly at the window edge is kept: retention is "older than N days"."""
    _row(db, days_ago=29)
    prune_api_call_log(db, payload_retention_days=30, row_retention_days=180)
    assert db.query(ApiCallLog).one().request_payload == "body"
