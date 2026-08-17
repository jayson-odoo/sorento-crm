"""GET .../{tracking_id}/ticket - drawer header + composer state (S2.7, AC-C1).

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-C1 (enquiry header + SLA chips), AC-C3 (viewer scope)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S2.7)

`ConversationSLATrackingService.get_ticket_detail` assembles the FE contract's
`InterventionTicketDetail` in one call: enquiry fields off the tracker itself,
`window` + `chat_template` inline via the same DB-only helpers the standalone
window-state/chat-template routes use (no Respond.io network call in this
suite - `RespondClient` is monkeypatched, matching test_respond_window_state.py).

Run:
    venv/bin/pytest tests/test_intervention_ticket_detail.py -q
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.error_handler import AppException
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"


class _NoMessagesRespondClient:
    """No Respond.io network calls in this suite - the window falls back to
    'no incoming, closed' immediately (matches test_respond_window_state.py)."""

    def list_messages(self, identifier, limit=50, cursor=None):
        return {"items": []}


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.integration_service.RespondClient",
        lambda *a, **k: _NoMessagesRespondClient(),
    )

    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _seed(db, *, respond_io_id="10025531"):
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
            respond_io_id=respond_io_id,
            session_vars={},
        )
    )
    assignee_id = str(uuid.uuid4())
    outsider_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="cs1@test.com", name="Agent One", respond_user_id="900001"))
    db.add(User(id=outsider_id, email="outsider@test.com", name="Someone Else"))
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
        "outsider_id": outsider_id,
        "agent_code": "CS_AGENT",
        "team_set_code": "cs_general",
    }


def _create_ticket(db, seed, **over):
    service = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        assigned_to_id=seed["assignee_id"],
        contact_phone_number=PHONE,
        source_message_id="wamid.msg-1",
        source_message_text="Yes, please connect me to a person.",
        **over,
    )
    return service.create_tracking(payload)


def test_detail_carries_the_enquiry_header_fields(db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    detail = service.get_ticket_detail(
        str(tracking.id), viewer_user_id=seed["assignee_id"], sender_name="Agent One"
    )

    assert detail["id"] == str(tracking.id)
    assert detail["contact_name"] == "Aisyah Rahman"
    assert detail["contact_phone"] == PHONE
    assert detail["respond_io_id"] == "10025531"
    assert detail["source_message_id"] == "wamid.msg-1"
    assert detail["source_message_text"] == "Yes, please connect me to a person."
    # No separate trigger-message timestamp is stored: source_message_at mirrors
    # initiated_at (the request time the trigger message caused).
    assert detail["source_message_at"] == detail["initiated_at"]
    assert detail["team_label"] == "Customer Service - Tier 1"
    assert detail["assignee_name"] == "Agent One"
    assert detail["policy_name"] == "Normal"
    assert detail["current_tier"] == 1
    assert detail["is_resolved"] is False
    assert detail["can_send"] is True
    assert detail["can_resolve"] is True
    assert detail["send_capabilities"] == ["text", "attachment"]
    assert detail["window"] == {"open": False, "expires_at": None}
    # Feedback 2026-08-16 (item 6): the drawer chips mark an extended deadline,
    # so the counter has to reach the wire - a fresh ticket has never been moved.
    assert detail["extension_count"] == 0


def test_detail_reports_how_many_times_the_deadline_was_extended(db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    tracking.extension_count = 2
    db.commit()
    service = ConversationSLATrackingService(db)

    detail = service.get_ticket_detail(
        str(tracking.id), viewer_user_id=seed["assignee_id"], sender_name="Agent One"
    )

    assert detail["extension_count"] == 2


def test_resolved_ticket_cannot_send_or_resolve_again(db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    tracking.is_resolved = True
    db.commit()
    service = ConversationSLATrackingService(db)

    detail = service.get_ticket_detail(
        str(tracking.id), viewer_user_id=seed["assignee_id"], sender_name="Agent One"
    )
    assert detail["is_resolved"] is True
    assert detail["can_send"] is False
    assert detail["can_resolve"] is False


def test_no_linked_contact_falls_back_to_a_safe_no_contact_state(db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    tracking.respond_contact_id = None
    db.commit()
    service = ConversationSLATrackingService(db)

    detail = service.get_ticket_detail(
        str(tracking.id), viewer_user_id=seed["assignee_id"], sender_name="Agent One"
    )
    assert detail["can_send"] is False
    assert detail["window"] == {"open": False, "expires_at": None}
    assert detail["chat_template"] == {"configured": False, "reason": "no_contact"}


def test_a_viewer_outside_the_ticket_scope_gets_not_found_not_a_leak(db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with pytest.raises(AppException):
        service.get_ticket_detail(
            str(tracking.id), viewer_user_id=seed["outsider_id"], sender_name="Someone Else"
        )


def test_unknown_tracking_id_raises_not_found(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)
    with pytest.raises(AppException):
        service.get_ticket_detail(
            str(uuid.uuid4()), viewer_user_id=seed["assignee_id"], sender_name="Agent One"
        )
