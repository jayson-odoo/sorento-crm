"""Drainer state-machine tests.

Verifies: rate-limit deferral, event_disabled cancellation, SMTP success, SMTP failure
retry with backoff, max_attempts terminal failure.
"""
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from app.models.email_outbox import EmailEventConfig, EmailOutbox
from app.tasks import email_outbox_tasks
from app.tasks.email_outbox_tasks import drain_email_outbox, _next_backoff


def test_next_backoff_progression():
    assert _next_backoff(0) == 60
    assert _next_backoff(1) == 60
    assert _next_backoff(2) == 300
    assert _next_backoff(3) == 1800
    assert _next_backoff(99) == 43200


def _make_row(event_key="password_reset", attempt=0, max_attempts=5):
    row = EmailOutbox(
        id="00000000-0000-0000-0000-000000000001",
        event_key=event_key,
        recipient_email="u@example.com",
        subject="s",
        body_text="b",
        body_html="<p>b</p>",
        priority=0,
        status="pending",
        scheduled_for=datetime.utcnow() - timedelta(seconds=1),
        attempt_count=attempt,
        max_attempts=max_attempts,
        metadata_json={},
        recipients_json=None,
    )
    return row


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._first = rows[0] if rows else None

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._first


def _patch_sessionlocal(rows, cfg, settings_row=None):
    db = MagicMock()
    settings_default = MagicMock(
        email_outbox_drain_batch_size=20,
        email_global_rate_per_window=60,
        email_global_window_seconds=60,
        email_per_recipient_rate_per_window=10,
        email_per_recipient_window_seconds=3600,
    )
    settings_row = settings_row or settings_default

    def query(model):
        from app.models.user import SystemSetting
        from app.models.notification import NotificationDelivery

        if model is SystemSetting:
            return _FakeQuery([settings_row])
        if model is EmailEventConfig:
            return _FakeQuery([cfg] if cfg else [])
        if model is EmailOutbox:
            return _FakeQuery(rows)
        if model is NotificationDelivery:
            return _FakeQuery([])
        return _FakeQuery([])

    db.query.side_effect = query
    return db


def test_disabled_event_cancels_row():
    row = _make_row()
    cfg = EmailEventConfig(event_key="password_reset", display_name="x", enabled=False)
    fake_db = _patch_sessionlocal([row], cfg)
    with patch.object(email_outbox_tasks, "SessionLocal", return_value=fake_db):
        with patch.object(email_outbox_tasks, "send_mime_email") as smtp:
            summary = drain_email_outbox()
    assert summary["cancelled"] == 1
    assert row.status == "cancelled"
    assert row.cancel_reason == "event_disabled"
    smtp.assert_not_called()


def test_rate_limit_defers_row_without_calling_smtp():
    row = _make_row()
    cfg = EmailEventConfig(event_key="password_reset", display_name="x", enabled=True)
    fake_db = _patch_sessionlocal([row], cfg)
    with patch.object(email_outbox_tasks, "SessionLocal", return_value=fake_db):
        with patch.object(email_outbox_tasks, "rate_check") as rc:
            rc.return_value = MagicMock(allowed=False, reason="global_cap_exceeded:60/60", retry_after_seconds=42)
            with patch.object(email_outbox_tasks, "send_mime_email") as smtp:
                summary = drain_email_outbox()
    assert summary["deferred_rate"] == 1
    assert row.status == "pending"
    assert row.error_message == "global_cap_exceeded:60/60"
    smtp.assert_not_called()


def test_successful_send_flips_to_sent_and_records_counter():
    row = _make_row()
    cfg = EmailEventConfig(event_key="password_reset", display_name="x", enabled=True)
    fake_db = _patch_sessionlocal([row], cfg)
    with patch.object(email_outbox_tasks, "SessionLocal", return_value=fake_db):
        with patch.object(email_outbox_tasks, "rate_check") as rc:
            rc.return_value = MagicMock(allowed=True, reason=None, retry_after_seconds=None)
            with patch.object(email_outbox_tasks, "send_mime_email", return_value=None) as smtp:
                with patch.object(email_outbox_tasks, "record_send") as record:
                    summary = drain_email_outbox()
    assert summary["sent"] == 1
    assert row.status == "sent"
    assert row.sent_at is not None
    smtp.assert_called_once()
    record.assert_called_once()


def test_smtp_failure_under_max_attempts_reschedules_with_backoff():
    row = _make_row(attempt=0)
    cfg = EmailEventConfig(event_key="password_reset", display_name="x", enabled=True)
    fake_db = _patch_sessionlocal([row], cfg)
    with patch.object(email_outbox_tasks, "SessionLocal", return_value=fake_db):
        with patch.object(email_outbox_tasks, "rate_check") as rc:
            rc.return_value = MagicMock(allowed=True, reason=None)
            with patch.object(email_outbox_tasks, "send_mime_email", return_value="SMTP boom"):
                summary = drain_email_outbox()
    assert summary["failed"] == 1
    assert row.status == "pending"
    assert row.error_message == "SMTP boom"
    assert row.scheduled_for > datetime.utcnow()


def test_smtp_failure_at_max_attempts_terminal_failed():
    row = _make_row(attempt=4, max_attempts=5)
    cfg = EmailEventConfig(event_key="password_reset", display_name="x", enabled=True)
    fake_db = _patch_sessionlocal([row], cfg)
    with patch.object(email_outbox_tasks, "SessionLocal", return_value=fake_db):
        with patch.object(email_outbox_tasks, "rate_check") as rc:
            rc.return_value = MagicMock(allowed=True, reason=None)
            with patch.object(email_outbox_tasks, "send_mime_email", return_value="permanent failure"):
                summary = drain_email_outbox()
    assert summary["terminal_failed"] == 1
    assert row.status == "failed"
    assert row.cancel_reason == "max_attempts_exceeded"
