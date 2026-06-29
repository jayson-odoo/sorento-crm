"""Respond.io conversation-op worker tasks: close + set-assignee.

These run on the respond_io queue for resolve / reassign / takeover / escalate. Each
must write a Respond outbox row (integration_logs) on success AND failure and re-raise
on failure so RQ records the job FAILED. See PLAN-respond-sla-actions-async-logged.md.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.tasks.respond_io_tasks as tasks


def _db_with_tracking(tracking):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = tracking
    return db


# ---- close_respond_conversation -------------------------------------------

@patch("app.tasks.respond_io_tasks._log_respond_conversation_op")
@patch("app.tasks.respond_io_tasks._resolve_respond_io_id", return_value="888")
@patch("app.services.integration_service.RespondClient.for_contact_id")
@patch("app.database.SessionLocal")
def test_close_success_writes_success_log(SessionLocal, for_contact, _resolve, logop):
    SessionLocal.return_value = _db_with_tracking(
        SimpleNamespace(id="t1", respond_contact_id="c1")
    )
    client = MagicMock()
    client.close_conversation.return_value = {"ok": True}
    for_contact.return_value = client

    out = tasks.close_respond_conversation("t1")

    # respond_io_id (888), not the internal contact id, is what is sent.
    assert client.close_conversation.call_args.args[0] == "888"
    assert logop.call_args.kwargs["status"] == "success"
    assert out["status"] == "success"


@patch("app.tasks.respond_io_tasks._log_respond_conversation_op")
@patch("app.tasks.respond_io_tasks._resolve_respond_io_id", return_value="888")
@patch("app.services.integration_service.RespondClient.for_contact_id")
@patch("app.database.SessionLocal")
def test_close_failure_writes_failed_log_and_raises(SessionLocal, for_contact, _resolve, logop):
    SessionLocal.return_value = _db_with_tracking(
        SimpleNamespace(id="t2", respond_contact_id="c1")
    )
    client = MagicMock()
    client.close_conversation.side_effect = RuntimeError("403 WAF")
    for_contact.return_value = client

    with pytest.raises(RuntimeError):
        tasks.close_respond_conversation("t2")

    assert logop.call_args.kwargs["status"] == "failed"
    assert logop.call_args.kwargs["error"] is not None


@patch("app.tasks.respond_io_tasks._resolve_respond_io_id", return_value=None)
@patch("app.services.integration_service.RespondClient.for_contact_id")
@patch("app.database.SessionLocal")
def test_close_skips_when_no_respond_io_id(SessionLocal, for_contact, _resolve):
    SessionLocal.return_value = _db_with_tracking(
        SimpleNamespace(id="t3", respond_contact_id="c1")
    )
    out = tasks.close_respond_conversation("t3")
    for_contact.assert_not_called()
    assert out["status"] == "skipped_no_respond_id"


@patch("app.database.SessionLocal")
def test_close_skips_when_tracking_missing(SessionLocal):
    SessionLocal.return_value = _db_with_tracking(None)
    out = tasks.close_respond_conversation("nope")
    assert out["status"] == "skipped_no_tracking"


# ---- set_respond_conversation_assignee ------------------------------------

@patch("app.tasks.respond_io_tasks._log_respond_conversation_op")
@patch("app.tasks.respond_io_tasks._resolve_respond_io_id", return_value="rio-1")
@patch("app.services.integration_service.RespondClient.for_identifier")
@patch("app.database.SessionLocal")
def test_assignee_success_writes_success_log(SessionLocal, for_identifier, _resolve, logop):
    SessionLocal.return_value = _db_with_tracking(
        SimpleNamespace(id="t1", respond_contact_id="c1")
    )
    client = MagicMock()
    client.set_conversation_assignee.return_value = {"ok": True}
    for_identifier.return_value = client

    out = tasks.set_respond_conversation_assignee("t1", "r-me")

    client.set_conversation_assignee.assert_called_once_with("rio-1", "r-me")
    assert logop.call_args.kwargs["status"] == "success"
    assert out["status"] == "success"


@patch("app.tasks.respond_io_tasks._log_respond_conversation_op")
@patch("app.tasks.respond_io_tasks._resolve_respond_io_id", return_value="rio-2")
@patch("app.services.integration_service.RespondClient.for_identifier")
@patch("app.database.SessionLocal")
def test_assignee_failure_writes_failed_log_and_raises(SessionLocal, for_identifier, _resolve, logop):
    SessionLocal.return_value = _db_with_tracking(
        SimpleNamespace(id="t2", respond_contact_id="c1")
    )
    client = MagicMock()
    client.set_conversation_assignee.side_effect = RuntimeError("401 unauthorized")
    for_identifier.return_value = client

    with pytest.raises(RuntimeError):
        tasks.set_respond_conversation_assignee("t2", "r-me")

    assert logop.call_args.kwargs["status"] == "failed"
    assert "401" in str(logop.call_args.kwargs["error"])


@patch("app.services.integration_service.RespondClient.for_identifier")
@patch("app.database.SessionLocal")
def test_assignee_skips_when_no_respond_user_id(SessionLocal, for_identifier):
    SessionLocal.return_value = _db_with_tracking(
        SimpleNamespace(id="t3", respond_contact_id="c1")
    )
    out = tasks.set_respond_conversation_assignee("t3", "")
    for_identifier.assert_not_called()
    assert out["status"] == "skipped_no_assignee"
