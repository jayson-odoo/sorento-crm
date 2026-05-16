"""Tests for the outbox enqueue + coalesce + cancel/retry service.

Uses a real in-memory PostgreSQL substitute is overkill; the service interacts with the DB
via three operations (query, add, flush) all of which we can drive with MagicMock against
the model layer. Where we need state we use a tiny fake session.
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta

from app.models.email_outbox import EmailEventConfig, EmailOutbox
from app.services.email_outbox_service import (
    UnknownEmailEvent,
    enqueue,
    enqueue_or_merge,
)


class FakeQuery:
    def __init__(self, result=None, all_result=None):
        self._first = result
        self._all = all_result or []

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class FakeSession:
    """Captures rows added via .add() so tests can assert payload."""

    def __init__(self, event_cfg=None, existing_outbox=None):
        self.added: list = []
        self.flushed = False
        self.committed = False
        self._event_cfg = event_cfg
        self._existing_outbox = existing_outbox

    def query(self, model):
        if model is EmailEventConfig:
            return FakeQuery(result=self._event_cfg)
        if model is EmailOutbox:
            return FakeQuery(result=self._existing_outbox)
        return FakeQuery()

    def add(self, row):
        self.added.append(row)

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True


def _cfg(event_key="password_reset", display="Password reset", enabled=True, coalesce_override=None, priority_override=None):
    return EmailEventConfig(
        event_key=event_key,
        display_name=display,
        enabled=enabled,
        rate_per_window_override=None,
        window_seconds_override=None,
        priority_override=priority_override,
        coalesce_window_seconds_override=coalesce_override,
    )


def test_enqueue_unknown_event_raises():
    db = FakeSession()
    with pytest.raises(UnknownEmailEvent):
        enqueue(
            db,
            event_key="this_event_does_not_exist",
            to="user@example.com",
            subject="x",
            body_text="y",
        )


def test_enqueue_creates_row_with_registry_priority():
    db = FakeSession(event_cfg=_cfg("password_reset"))
    new_id = enqueue(
        db,
        event_key="password_reset",
        to="user@example.com",
        subject="Reset",
        body_text="link",
        body_html="<a>link</a>",
    )
    assert isinstance(new_id, str)
    assert len(db.added) == 1
    row: EmailOutbox = db.added[0]
    assert row.event_key == "password_reset"
    assert row.recipient_email == "user@example.com"
    assert row.status == "pending"
    assert row.priority == 0
    assert row.attempt_count == 0


def test_enqueue_priority_override_wins():
    db = FakeSession(event_cfg=_cfg("notification_delivery", priority_override=5))
    enqueue(db, event_key="notification_delivery", to="x@y", subject="s", body_text="b")
    assert db.added[0].priority == 5


def test_enqueue_explicit_priority_arg_beats_override():
    db = FakeSession(event_cfg=_cfg("notification_delivery", priority_override=5))
    enqueue(db, event_key="notification_delivery", to="x@y", subject="s", body_text="b", priority=99)
    assert db.added[0].priority == 99


def test_enqueue_or_merge_no_coalesce_window_falls_back_to_single_row():
    db = FakeSession(event_cfg=_cfg("password_reset"))
    _id, merged = enqueue_or_merge(
        db,
        event_key="password_reset",
        to="x@y",
        subject="s",
        body_text="b",
    )
    assert merged is False
    assert len(db.added) == 1


def test_enqueue_or_merge_creates_new_row_when_no_match():
    db = FakeSession(event_cfg=_cfg("external_product_attachment", coalesce_override=20))
    _id, merged = enqueue_or_merge(
        db,
        event_key="external_product_attachment",
        to="x@y",
        subject="s",
        body_text="b",
        body_html="<p>b</p>",
        metadata={"attachment_html_items": ["<li>A</li>"]},
        merge_metadata_list_keys=["attachment_html_items"],
    )
    assert merged is False
    assert len(db.added) == 1
    row: EmailOutbox = db.added[0]
    assert row.coalesce_key.startswith("external_product_attachment:x@y")
    assert row.scheduled_for > datetime.utcnow()


def test_enqueue_or_merge_merges_into_existing_pending_row():
    existing = EmailOutbox(
        id="00000000-0000-0000-0000-000000000001",
        event_key="external_product_attachment",
        recipient_email="x@y",
        subject="s",
        body_text="initial",
        body_html="<p>initial</p>",
        priority=10,
        status="pending",
        scheduled_for=datetime.utcnow() + timedelta(seconds=15),
        attempt_count=0,
        max_attempts=5,
        coalesce_key="external_product_attachment:x@y:None",
        metadata_json={"attachment_html_items": ["<li>A</li>"]},
    )
    existing.created_at = datetime.utcnow() - timedelta(seconds=5)
    db = FakeSession(event_cfg=_cfg("external_product_attachment", coalesce_override=20), existing_outbox=existing)

    captured: dict = {}

    def rebuild(meta):
        captured["meta"] = meta
        return "merged_plain", "merged_html"

    out_id, merged = enqueue_or_merge(
        db,
        event_key="external_product_attachment",
        to="x@y",
        subject="s",
        body_text="b",
        metadata={"attachment_html_items": ["<li>B</li>", "<li>C</li>"]},
        merge_metadata_list_keys=["attachment_html_items"],
        rebuild_body=rebuild,
    )
    assert merged is True
    assert out_id == str(existing.id)
    assert existing.body_text == "merged_plain"
    assert existing.body_html == "merged_html"
    assert captured["meta"]["attachment_html_items"] == ["<li>A</li>", "<li>B</li>", "<li>C</li>"]
    assert len(db.added) == 0


def test_enqueue_or_merge_dedupes_merged_list_items():
    existing = EmailOutbox(
        id="00000000-0000-0000-0000-000000000002",
        event_key="external_product_attachment",
        recipient_email="x@y",
        subject="s",
        body_text="initial",
        body_html="<p>initial</p>",
        priority=10,
        status="pending",
        scheduled_for=datetime.utcnow() + timedelta(seconds=15),
        attempt_count=0,
        max_attempts=5,
        coalesce_key="external_product_attachment:x@y:None",
        metadata_json={"attachment_ids": ["a1", "a2"]},
    )
    existing.created_at = datetime.utcnow() - timedelta(seconds=5)
    db = FakeSession(event_cfg=_cfg("external_product_attachment", coalesce_override=20), existing_outbox=existing)

    enqueue_or_merge(
        db,
        event_key="external_product_attachment",
        to="x@y",
        subject="s",
        body_text="b",
        metadata={"attachment_ids": ["a2", "a3"]},
        merge_metadata_list_keys=["attachment_ids"],
    )
    assert existing.metadata_json["attachment_ids"] == ["a1", "a2", "a3"]
