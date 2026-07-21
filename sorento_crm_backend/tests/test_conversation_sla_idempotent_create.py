"""Conversation SLA idempotent create + conversation-row scoping
(PLAN-conversation-sla-idempotent-create):

- create_tracking: active conversation row -> idempotent return (no 409, no new row,
  message_id refreshed, no duplicate assign log)
- create_tracking: active FORM row must not block a conversation create (old false 409)
- create_tracking: resolved row -> overwrite-in-place, event logs preserved
- backend-owned 'assign' event log on insert/overwrite, never on idempotent hit
- contact-keyed lookups ignore form-SLA stage rows

Run with:
    pytest tests/test_conversation_sla_idempotent_create.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"


# No DDL shims here any more. JSONB and its pg server_default are native, and
# AgentTeam's partial unique indexes keep their postgresql_where clause instead
# of collapsing into a plain UNIQUE that falsely collided multi-tier rows.
@pytest.fixture
def db():
    with blank_session() as session:
        # Some SLA lookups issue raw SQL against unqualified table names, which
        # schema_translate_map does not rewrite; align search_path so they hit
        # the blank schema.
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _seed(db) -> dict:
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
            name="Test Contact",
            session_vars={},
        )
    )
    user_id = str(uuid.uuid4())
    db.add(
        User(
            id=user_id,
            email="agent1@test.com",
            name="Agent One",
            respond_user_id="900001",
        )
    )
    # Schema now requires (agent_code, team_set_code); create_tracking resolves the
    # policy from the (agent, team_set) binding (PLAN-conversation-policy-binding).
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="AGENT1", name="Agent 1"))
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="Team 1"))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code="general",
            team_id=team_id,
            tier=1,
            policy_id=policy_id,
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "user_id": user_id,
        "agent_id": agent_id,
        "agent_code": "AGENT1",
        "team_set_code": "general",
    }


def _payload(seed, *, message_id=None) -> ConversationSLATrackingCreate:
    return ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        current_tier=1,
        assigned_to_id=seed["user_id"],
        contact_phone_number=PHONE,
        message_id=message_id,
    )


def _form_row(db, seed, *, is_resolved=False, src="complaint") -> ConversationSLATracking:
    row = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=seed["policy_id"],
        current_tier=1,
        assigned_to_id=seed["user_id"],
        due_at=datetime(2026, 6, 1, 12, 0, 0),
        is_resolved=is_resolved,
        respond_contact_id=seed["contact_id"],
        source_entity_type=src,
        source_entity_id=str(uuid.uuid4()),
    )
    db.add(row)
    db.commit()
    return row


def _assign_logs(db, tracking_id: str) -> list[ConversationSLAEventLog]:
    return (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracking_id),
            ConversationSLAEventLog.event_type == "assign",
        )
        .all()
    )


# ---------------------------------------------------------------------------
# create_tracking
# ---------------------------------------------------------------------------

def test_create_with_no_rows_inserts_and_writes_assign_log(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)

    tracking = service.create_tracking(_payload(seed, message_id=111))

    assert tracking.respond_contact_id == seed["contact_id"]
    assert bool(getattr(tracking, "_already_active", False)) is False
    assert db.query(ConversationSLATracking).count() == 1

    logs = _assign_logs(db, tracking.id)
    assert len(logs) == 1
    assert logs[0].from_tier == 1 and logs[0].to_tier == 1
    assert logs[0].assigned_to == "Agent One"
    assert logs[0].assigned_to_id == seed["user_id"]
    assert "Agent One" in (logs[0].reason or "")
    # Field parity with the reassignment-origin assign logs (update_tracking).
    assert logs[0].event_at is not None
    assert logs[0].due_at is not None


def test_create_succeeds_when_assign_log_write_fails(db, monkeypatch):
    """Tracking commit happens before the assign-log write; a log failure must
    not 500 the create (retry would take the idempotent path and n8n would see
    an error for a create that succeeded)."""
    seed = _seed(db)
    service = ConversationSLATrackingService(db)

    def _boom(*_a, **_k):
        raise RuntimeError("event log write failed")

    monkeypatch.setattr(service, "create_event_log", _boom)
    tracking = service.create_tracking(_payload(seed))

    assert tracking.respond_contact_id == seed["contact_id"]
    assert db.query(ConversationSLATracking).count() == 1
    assert len(_assign_logs(db, tracking.id)) == 0  # log missing, create intact


def test_create_with_active_row_is_idempotent(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)
    first = service.create_tracking(_payload(seed, message_id=111))
    first_id = str(first.id)
    first_started = first.current_tier_started_at
    first_due = first.due_at

    second = service.create_tracking(_payload(seed, message_id=222))

    # Same row returned, flagged, nothing about the SLA state changed.
    assert str(second.id) == first_id
    assert bool(getattr(second, "_already_active", False)) is True
    assert second.current_tier_started_at == first_started
    assert second.due_at == first_due
    assert second.is_resolved is False
    # message_id refreshed to the latest inbound message.
    assert second.message_id == 222
    # No duplicate rows, no duplicate assign event logs.
    assert db.query(ConversationSLATracking).count() == 1
    assert len(_assign_logs(db, first_id)) == 1


def test_create_with_active_form_row_does_not_conflict(db):
    """The old check scanned all rows for the contact; an active form-SLA stage
    row falsely blocked (409) the n8n conversation create."""
    seed = _seed(db)
    form = _form_row(db, seed, is_resolved=False)
    service = ConversationSLATrackingService(db)

    tracking = service.create_tracking(_payload(seed))

    assert str(tracking.id) != str(form.id)
    assert bool(getattr(tracking, "_already_active", False)) is False
    assert db.query(ConversationSLATracking).count() == 2
    # The form row is untouched.
    db.refresh(form)
    assert form.source_entity_type == "complaint"
    assert form.is_resolved is False


def test_create_with_resolved_row_overwrites_in_place(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)
    first = service.create_tracking(_payload(seed, message_id=111))
    first_id = str(first.id)
    first.is_resolved = True
    first.resolved_at = datetime(2026, 6, 2, 10, 0, 0)
    db.commit()

    second = service.create_tracking(_payload(seed, message_id=333))

    # Overwrite-in-place: same row id, reset to a fresh open conversation.
    assert str(second.id) == first_id
    assert bool(getattr(second, "_already_active", False)) is False
    assert second.is_resolved is False
    assert second.resolved_at is None
    assert second.message_id == 333
    assert db.query(ConversationSLATracking).count() == 1
    # History: first conversation's assign log preserved, new one appended.
    assert len(_assign_logs(db, first_id)) == 2


# ---------------------------------------------------------------------------
# contact-keyed lookups ignore form-SLA stage rows
# ---------------------------------------------------------------------------

def test_get_tracking_by_contact_phone_ignores_form_rows(db):
    seed = _seed(db)
    _form_row(db, seed, is_resolved=False)
    service = ConversationSLATrackingService(db)

    assert service.get_tracking_by_contact_phone(PHONE) is None

    conv = service.create_tracking(_payload(seed))
    found = service.get_tracking_by_contact_phone(PHONE)
    assert found is not None and str(found.id) == str(conv.id)


def test_get_existing_assignee_for_contact_phone_ignores_form_rows(db):
    """next-assignee / conversation-assignee endpoints must never surface a form
    row's assignee as the thread assignee."""
    seed = _seed(db)
    _form_row(db, seed, is_resolved=False)
    service = ConversationSLATrackingService(db)

    assert service.get_existing_assignee_for_contact_phone(PHONE) is None

    service.create_tracking(_payload(seed))
    info = service.get_existing_assignee_for_contact_phone(PHONE)
    assert info is not None
    assert info["id"] == seed["user_id"]


def test_get_tracking_by_contact_and_policy_ignores_form_rows(db):
    """Escalate-by-contact path must resolve the conversation row, not a form row
    sharing the same policy."""
    seed = _seed(db)
    form = _form_row(db, seed, is_resolved=False)
    service = ConversationSLATrackingService(db)

    assert (
        service.get_tracking_by_contact_and_policy(seed["contact_id"], seed["policy_id"])
        is None
    )

    conv = service.create_tracking(_payload(seed))
    found = service.get_tracking_by_contact_and_policy(seed["contact_id"], seed["policy_id"])
    assert found is not None
    assert str(found.id) == str(conv.id)
    assert str(found.id) != str(form.id)
