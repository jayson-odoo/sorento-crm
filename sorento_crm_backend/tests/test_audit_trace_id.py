"""Sub-plan D Tier-2 — per-request trace_id correlation on audit rows.

trace_id lives in a request-scoped contextvar set by LoggingMiddleware; the audit
listener copies it onto every AuditLog written during the request, so a multi-row
change is filterable as one action. Also surfaced as the X-Trace-Id response header.
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.audit_context import set_trace_id, get_trace_id
from app.services.audit_service import log_audit, list_audit_logs


def test_contextvar_roundtrip():
    set_trace_id("abc123")
    assert get_trace_id() == "abc123"
    set_trace_id(None)
    assert get_trace_id() is None


def test_log_audit_stamps_trace_id_from_context():
    set_trace_id("trace-xyz")
    try:
        db = MagicMock()
        log_audit(db, "order", "oid-1", "UPDATE", skip_flush=True)
        added = db.add.call_args[0][0]
        assert added.trace_id == "trace-xyz"
    finally:
        set_trace_id(None)


def test_log_audit_trace_id_none_outside_request():
    set_trace_id(None)
    db = MagicMock()
    log_audit(db, "order", "oid-1", "INSERT", skip_flush=True)
    assert db.add.call_args[0][0].trace_id is None


def test_list_audit_logs_filters_by_trace_id():
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.count.return_value = 0
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    list_audit_logs(db, trace_id="trace-xyz")
    # trace_id filter must have been applied (filter called at least once)
    assert q.filter.called


def test_middleware_sets_trace_id_response_header():
    client = TestClient(app)
    r = client.get("/health")
    assert r.headers.get("X-Trace-Id")
    # honour an inbound trace id
    r2 = client.get("/health", headers={"X-Trace-Id": "inbound-42"})
    assert r2.headers.get("X-Trace-Id") == "inbound-42"
