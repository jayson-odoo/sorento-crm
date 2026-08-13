"""The n8n integration routes must not fail a committed write over its own log.

PRINCIPLES.md: "Post-commit side effects are best-effort (catch + warn, never
raise - the retry takes the idempotent path)." Both n8n-facing conversation-SLA
routes write their `integration_log` AFTER the tracking row is committed:

- POST /integration          -> ticket created, then logged
- PUT|POST /integration/{id} -> stamp/resolve committed, then logged

A failure in that logging call was re-raised into `handle_internal_error`, so a
write that actually succeeded answered 500. n8n then reports a failed
intervention (no auto-reply to the contact) and retries: the create retry takes
the idempotent path, and the update retry lands on the already-responded /
already-resolved short-circuit - neither of which backfills the missing log,
so the 500 buys nothing and costs the contact their reply.

Run:
    venv/bin/pytest tests/test_conversation_sla_integration_log_best_effort.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456702"
BASE = "/api/v1/sla-management/conversation-sla-tracking"


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _seed(db):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="NORMAL", name="Normal"))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    contact_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=contact_id,
            phone_number=PHONE,
            name="Aisyah Rahman",
            respond_io_id="10025531",
            session_vars={},
        )
    )
    assignee_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="cs1@test.com", name="Agent One", respond_user_id="900001"))
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="CS_AGENT", name="CS Agent"))
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="Customer Service - Tier 1"))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code="cs_general",
            team_id=team_id,
            tier=1,
            policy_id=policy_id,
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "assignee_id": assignee_id,
        "agent_code": "CS_AGENT",
        "team_set_code": "cs_general",
    }


def _ticket(db, seed, *, source_message_id="wamid.msg-1"):
    return ConversationSLATrackingService(db).create_tracking(
        ConversationSLATrackingCreate(
            agent_code=seed["agent_code"],
            team_set_code=seed["team_set_code"],
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
            source_message_id=source_message_id,
        )
    )


@pytest.fixture
def client(db, monkeypatch):
    """Every integration_log write in the process raises, as a broken logging
    table / connection would."""
    from app.main import app
    from app.database import get_db as database_get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db as dependencies_get_db,
    )
    from app.services.integration_service import IntegrationLogService

    def _explode(self, *a, **k):
        raise RuntimeError("integration_log write failed")

    monkeypatch.setattr(IntegrationLogService, "create_integration_log", _explode)

    def _system_user():
        return {"id": "system", "auth_method": "api_key"}

    app.dependency_overrides[database_get_db] = lambda: db
    app.dependency_overrides[dependencies_get_db] = lambda: db
    app.dependency_overrides[get_current_user_or_api_key] = _system_user
    app.dependency_overrides[get_current_user] = _system_user
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _fresh(db, tracking_id):
    db.expire_all()
    return (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.id == str(tracking_id))
        .one()
    )


def test_a_failed_log_does_not_turn_a_stamped_ticket_into_a_500(client, db):
    seed = _seed(db)
    ticket = _ticket(db, seed)

    resp = client.put(
        f"{BASE}/integration/{ticket.id}",
        json={"is_responded": True, "responded_at": "2026-08-12T03:00:00Z"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "success"
    row = _fresh(db, ticket.id)
    assert row.is_responded is True, "the stamp committed; the answer must say so"


def test_a_failed_log_does_not_turn_a_resolved_ticket_into_a_500(client, db):
    seed = _seed(db)
    ticket = _ticket(db, seed, source_message_id="wamid.msg-2")

    resp = client.put(
        f"{BASE}/integration/{ticket.id}",
        json={"is_resolved": True, "resolved_at": "2026-08-12T03:00:00Z"},
    )

    assert resp.status_code == 200, resp.text
    row = _fresh(db, ticket.id)
    assert row.is_resolved is True


def test_a_failed_log_does_not_turn_a_created_ticket_into_a_500(client, db):
    seed = _seed(db)

    resp = client.post(
        f"{BASE}/integration",
        json={
            "agent_code": seed["agent_code"],
            "team_set_code": seed["team_set_code"],
            "policy_id": seed["policy_id"],
            "assigned_to_id": seed["assignee_id"],
            "contact_phone_number": PHONE,
            "source_message_id": "wamid.msg-created",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    # The ticket exists: a 500 here would have n8n tell the contact nothing while
    # an assignee already owns the enquiry.
    assert _fresh(db, body["tracking_id"]).source_message_id == "wamid.msg-created"
