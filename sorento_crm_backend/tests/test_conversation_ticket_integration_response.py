"""POST /conversation-sla-tracking/integration - the response shape n8n reads.

UAC: conversation-intervention-tickets-acceptance-criteria.md AC-A2 (frozen
fields survive an idempotent hit) and AC-A4 (`in_working_hours` drives n8n's
in-hours vs out-of-hours auto-reply copy).

The contract is frozen in both directions: the five keys the current flow reads
(`status`, `message`, `tracking_id`, `is_update`, `already_active`) must never
disappear, and the clock/assignee fields plus `in_working_hours` must be present
on EVERY response - insert and retry alike - because n8n templates read them
without branching. Deploy order is BE before n8n, so an additive response keeps
the old flow working untouched.

Hermetic: the service is stubbed, so this pins the route's serialization only.

Run with:
    pytest tests/test_conversation_ticket_integration_response.py -v
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api.v1.sla.sla_tracking as mod
from app.database import get_db as database_get_db
from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db as dependencies_get_db,
)
from app.main import app

ENDPOINT = "/api/v1/sla-management/conversation-sla-tracking/integration"

PAYLOAD = {
    "agent_code": "AGENT1",
    "team_set_code": "general",
    "contact_phone_number": "+60123456789",
    "source_message_id": "msg-1",
}

TRACKING_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"


class _Tracking:
    """Just the attributes the route serializes, plus the smuggled markers."""

    def __init__(self, *, already_active=False, in_working_hours=True):
        self.id = TRACKING_ID
        self.initiated_at = datetime(2026, 6, 6, 2, 0, 0)
        self.due_at = datetime(2026, 6, 8, 5, 0, 0)
        self.due_at_resolution = datetime(2026, 6, 9, 1, 0, 0)
        self.assigned_to = "900001"
        self.assigned_to_id = USER_ID
        self._already_active = already_active
        self._in_working_hours = in_working_hours


@pytest.fixture
def client():
    """The SLA router sits behind the module guard; satisfy both principals."""

    def _user():
        return {"id": "system", "auth_method": "api_key"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_current_user_or_api_key] = _user
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[database_get_db] = _db
    app.dependency_overrides[dependencies_get_db] = _db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _stub_create(monkeypatch, tracking):
    monkeypatch.setattr(
        mod.ConversationSLATrackingService,
        "create_tracking",
        lambda self, data: tracking,
    )
    monkeypatch.setattr(
        mod.IntegrationLogService,
        "create_integration_log",
        lambda self, *a, **k: None,
    )


def test_insert_response_carries_the_clock_and_assignee_fields(client, monkeypatch):
    _stub_create(monkeypatch, _Tracking())

    body = client.post(ENDPOINT, json=PAYLOAD).json()

    assert body["status"] == "success"
    assert body["tracking_id"] == TRACKING_ID
    assert body["already_active"] is False
    assert body["is_update"] is False
    assert body["in_working_hours"] is True
    assert body["initiated_at"] == "2026-06-06T02:00:00"
    assert body["due_at"] == "2026-06-08T05:00:00"
    assert body["due_at_resolution"] == "2026-06-09T01:00:00"
    assert body["assigned_to"] == "900001"
    assert body["assigned_to_id"] == USER_ID


def test_idempotent_hit_keeps_every_field_the_flow_reads(client, monkeypatch):
    """AC-A2: a retry answers with the same shape, flagged - never a bare 200."""
    _stub_create(monkeypatch, _Tracking(already_active=True))

    body = client.post(ENDPOINT, json=PAYLOAD).json()

    assert body["already_active"] is True
    assert body["is_update"] is True
    for key in (
        "status",
        "message",
        "tracking_id",
        "is_update",
        "already_active",
        "in_working_hours",
        "initiated_at",
        "due_at",
        "due_at_resolution",
        "assigned_to",
    ):
        assert key in body, f"n8n reads {key}; it must survive an idempotent hit"
    assert body["initiated_at"] == "2026-06-06T02:00:00"
    assert body["assigned_to"] == "900001"


def test_out_of_hours_create_tells_n8n_which_auto_reply_to_send(client, monkeypatch):
    _stub_create(monkeypatch, _Tracking(in_working_hours=False))

    body = client.post(ENDPOINT, json=PAYLOAD).json()

    assert body["in_working_hours"] is False


def test_missing_clock_fields_serialize_as_null_not_omitted(client, monkeypatch):
    """A tracking with no resolution deadline still answers with the key."""
    tracking = _Tracking()
    tracking.due_at_resolution = None
    tracking.assigned_to = None
    tracking.assigned_to_id = None
    _stub_create(monkeypatch, tracking)

    body = client.post(ENDPOINT, json=PAYLOAD).json()

    assert body["due_at_resolution"] is None
    assert body["assigned_to"] is None
    assert body["assigned_to_id"] is None
