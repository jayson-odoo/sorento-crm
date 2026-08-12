"""`/my-pending` emits the intervention-ticket fields the FE contract needs (S2.7).

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-B1 (worklist), AC-F1-adjacent (multi-row, no de-dup)
PLAN: documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S2.7)

`interventionTicketService.ts`'s contract header documents these as the delta
`/my-pending` must add on conversation-scope rows: `is_intervention_ticket`,
`contact_name`, `contact_phone`, `enquiry_snippet`, `source_message_id`,
`team_label`, `initiated_at`, `escalated_at`. This pins:

  1. A row with ticket identity (source_message_id) carries every new field.
  2. Two open tickets for ONE contact both appear - no de-dup by contact.
  3. A legacy row with NO ticket identity keeps `is_intervention_ticket` false/absent
     (the widget's documented "pre-migration row keeps its old behaviour").
  4. A form-SLA row never gets the ticket fields, regardless of source_message_id.
  5. `enquiry_snippet` is the trigger message's own text, truncated to 140 chars.
  6. `team_label` resolves via the tracking's (agent_id, team_set_code, current_tier).

Run:
    venv/bin/pytest tests/test_intervention_ticket_my_pending.py -q
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)

    with blank_session() as session:
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
            name="Aisyah Rahman",
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


def _ticket_payload(seed, *, source_message_id, source_message_text=None):
    return ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        assigned_to_id=seed["assignee_id"],
        contact_phone_number=PHONE,
        source_message_id=source_message_id,
        source_message_text=source_message_text,
    )


def _row_by_id(rows: list[dict], tracking_id: str) -> dict:
    return next(r for r in rows if r["id"] == tracking_id)


def test_ticket_row_carries_every_new_field(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)

    tracking = service.create_tracking(
        _ticket_payload(
            seed,
            source_message_id="wamid.msg-1",
            source_message_text="Yes, please connect me to a person.",
        )
    )

    rows = service.list_my_pending(seed["assignee_id"])
    row = _row_by_id(rows, str(tracking.id))

    assert row["is_intervention_ticket"] is True
    assert row["contact_name"] == "Aisyah Rahman"
    assert row["contact_phone"] == PHONE
    assert row["enquiry_snippet"] == "Yes, please connect me to a person."
    assert row["source_message_id"] == "wamid.msg-1"
    assert row["team_label"] == "Customer Service - Tier 1"
    assert row["initiated_at"] is not None
    assert row["escalated_at"] is None
    # Never re-derived: is_form_sla stays the authoritative false alongside it.
    assert row["is_form_sla"] is False


def test_two_tickets_for_one_contact_both_appear_no_dedup(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)

    t1 = service.create_tracking(
        _ticket_payload(seed, source_message_id="wamid.msg-1", source_message_text="First enquiry")
    )
    t2 = service.create_tracking(
        _ticket_payload(seed, source_message_id="wamid.msg-2", source_message_text="Second enquiry")
    )

    rows = service.list_my_pending(seed["assignee_id"])
    ids = {r["id"] for r in rows}
    assert str(t1.id) in ids and str(t2.id) in ids
    assert len(rows) == 2
    snippets = {r["enquiry_snippet"] for r in rows}
    assert snippets == {"First enquiry", "Second enquiry"}


def test_legacy_row_without_ticket_identity_is_not_flagged_a_ticket(db):
    """No source_message_id (and no message_id) => the old contact-singleton
    fallback path - the widget's documented "pre-migration row keeps its old
    behaviour" (Respond inbox link, inline Escalate/Resolve), never a drawer
    with no enquiry to show."""
    seed = _seed(db)
    service = ConversationSLATrackingService(db)

    tracking = service.create_tracking(
        ConversationSLATrackingCreate(
            agent_code=seed["agent_code"],
            team_set_code=seed["team_set_code"],
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
        )
    )

    rows = service.list_my_pending(seed["assignee_id"])
    row = _row_by_id(rows, str(tracking.id))
    assert row.get("is_intervention_ticket") is not True
    assert "contact_name" not in row
    assert "enquiry_snippet" not in row


def test_enquiry_snippet_truncates_to_140_chars(db):
    seed = _seed(db)
    service = ConversationSLATrackingService(db)
    long_text = "x" * 200

    tracking = service.create_tracking(
        _ticket_payload(seed, source_message_id="wamid.long", source_message_text=long_text)
    )

    rows = service.list_my_pending(seed["assignee_id"])
    row = _row_by_id(rows, str(tracking.id))
    assert row["enquiry_snippet"] == "x" * 140


def test_form_sla_row_never_gets_ticket_fields(db):
    """Defensive: a form-SLA stage row must never be flagged a ticket even if it
    somehow carried a source_message_id (it never does in practice)."""
    from app.models.sla import ConversationSLATracking
    from datetime import datetime, timedelta

    seed = _seed(db)
    tracking = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=seed["policy_id"],
        current_tier=1,
        assigned_to_id=seed["assignee_id"],
        due_at=datetime.utcnow() + timedelta(hours=4),
        source_entity_type="stock_inquiry",
        source_entity_id=str(uuid.uuid4()),
        respond_contact_id=seed["contact_id"],
        source_message_id="should-be-ignored",
    )
    db.add(tracking)
    db.commit()

    service = ConversationSLATrackingService(db)
    rows = service.list_my_pending(seed["assignee_id"])
    row = _row_by_id(rows, str(tracking.id))
    assert row["is_form_sla"] is True
    assert row.get("is_intervention_ticket") is not True
    assert "contact_name" not in row
