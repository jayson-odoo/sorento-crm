"""AC-E3 ambiguity guard: pushed into the shared service update path so EVERY
caller that can set is_responded on a conversation-scope row enforces it, not
just the PUT /{tracking_id} route.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-E3 (Respond-app-reply fallback: 2+ open unanswered tickets for the
            replying user -> nothing changes; exactly one -> that ticket answers)

Code-review findings covered here (see the coder's report for detail):
  FINDING 1 - the guard used to exist ONLY on PUT /{tracking_id}; the sibling
    /integration/{tracking_id} route (no auth dependency) stamped
    is_responded/response_time and wrote a "response" event log unguarded.
    Fixed by moving the check into ConversationSLATrackingService.update_tracking,
    the method BOTH routes call.
  FINDING 5 - when the guard fired on PUT, the route skipped the ENTIRE
    update_tracking call (dropping is_resolved/assigned_to/current_tier/...)
    yet returned 200. Fixed: only the responded-family fields
    (is_responded, responded_at, responded_by, response_time) are stripped;
    the rest of the payload is applied normally, and
    `ambiguous_responded_skipped: true` is returned so the caller knows.

Run:
    venv/bin/pytest tests/test_conversation_sla_response_ambiguity.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
BASE = "/api/v1/sla-management/conversation-sla-tracking"


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
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
    other_assignee_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="cs1@test.com", name="Agent One", respond_user_id="900001"))
    db.add(User(id=other_assignee_id, email="cs2@test.com", name="Agent Two", respond_user_id="900002"))
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
        "other_assignee_id": other_assignee_id,
        "agent_code": "CS_AGENT",
        "team_set_code": "cs_general",
    }


def _create_ticket(db, seed, *, source_message_id, assignee_id=None, **over):
    service = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code=seed["agent_code"],
        team_set_code=seed["team_set_code"],
        policy_id=seed["policy_id"],
        assigned_to_id=assignee_id or seed["assignee_id"],
        contact_phone_number=PHONE,
        source_message_id=source_message_id,
        source_message_text="Yes, please connect me to a person.",
        **over,
    )
    return service.create_tracking(payload)


@pytest.fixture
def client(db, monkeypatch):
    from app.main import app
    from app.database import get_db as database_get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db as dependencies_get_db,
    )
    from app.services.integration_service import IntegrationLogService

    def _system_user():
        return {"id": "system", "auth_method": "api_key"}

    # Pre-existing, out-of-scope bug (present at HEAD before this file existed):
    # IntegrationLogService.create_integration_log does
    # `json.dumps(request_payload_dict)` with no `default=str`, and this route
    # passes model_dump() of a payload that still carries a real `datetime`
    # for responded_at -> unconditional 500 on ANY call that includes a
    # datetime field, unrelated to the ambiguity guard under test here.
    # Stubbed out (same choke point tests/test_conversation_ticket_integration_
    # response.py stubs) so it doesn't mask the assertions this file cares about.
    monkeypatch.setattr(
        IntegrationLogService, "create_integration_log", lambda self, *a, **k: None
    )

    app.dependency_overrides[database_get_db] = lambda: db
    app.dependency_overrides[dependencies_get_db] = lambda: db
    app.dependency_overrides[get_current_user_or_api_key] = _system_user
    app.dependency_overrides[get_current_user] = _system_user
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _response_event_logs(db, tracking_id):
    return (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracking_id),
            ConversationSLAEventLog.event_type == "response",
        )
        .all()
    )


# --------------------------------------------------------------------------- #
# FINDING 1: /integration/{tracking_id} used to bypass the AC-E3 guard        #
# entirely (no auth dependency, no pre-check like PUT /{tracking_id} had).    #
# --------------------------------------------------------------------------- #


def test_integration_route_does_not_bypass_the_ambiguity_guard(client, db):
    seed = _seed(db)
    # Two open, unanswered tickets for the SAME contact, SAME assignee - the
    # textbook ambiguous case even under the old (pre-FINDING-2) predicate, so
    # this test isolates FINDING 1 (route enforcement) from FINDING 2 (predicate
    # correctness).
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    t2 = _create_ticket(db, seed, source_message_id="wamid.msg-2")

    resp = client.put(
        f"{BASE}/integration/{t1.id}",
        json={"is_responded": True, "responded_at": "2026-08-12T03:00:00Z"},
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    fresh_t1 = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == t1.id).one()
    fresh_t2 = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == t2.id).one()

    assert fresh_t1.is_responded is False, (
        "ambiguous (contact, assignee) pair - the integration route must not "
        "stamp is_responded any more than the PUT route would"
    )
    assert fresh_t1.responded_at is None
    assert fresh_t2.is_responded is False, "sibling must never be touched by this call"

    assert _response_event_logs(db, t1.id) == [], (
        "a skipped (ambiguous) stamp must not leave a 'response' event log behind"
    )


# --------------------------------------------------------------------------- #
# FINDING 5: PUT /{tracking_id} used to skip the ENTIRE update_tracking call  #
# when ambiguous, dropping is_resolved/assigned_to/current_tier/... from a    #
# payload that also carried them, yet still answering 200.                   #
# --------------------------------------------------------------------------- #


def test_ambiguous_put_still_applies_the_rest_of_the_payload(client, db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _create_ticket(db, seed, source_message_id="wamid.msg-2")

    resp = client.put(
        f"{BASE}/{t1.id}",
        json={
            "is_responded": True,
            "responded_at": "2026-08-12T03:00:00Z",
            "escalation_reason": "manual note from a non-ambiguous field",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ambiguous_responded_skipped"] is True
    assert body["updated_in_request"] is True, (
        "the payload also carried a non-responded field that DID apply - "
        "must not report 'nothing happened'"
    )

    db.expire_all()
    fresh_t1 = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == t1.id).one()
    assert fresh_t1.is_responded is False, "the ambiguous responded-family fields are dropped"
    assert fresh_t1.responded_at is None
    assert fresh_t1.escalation_reason == "manual note from a non-ambiguous field", (
        "FINDING 5: only the responded-family fields are stripped when ambiguous - "
        "everything else in the payload must still apply"
    )


def test_ambiguous_put_with_only_responded_fields_reports_nothing_applied(client, db):
    seed = _seed(db)
    t1 = _create_ticket(db, seed, source_message_id="wamid.msg-1")
    _create_ticket(db, seed, source_message_id="wamid.msg-2")

    resp = client.put(
        f"{BASE}/{t1.id}",
        json={"is_responded": True, "responded_at": "2026-08-12T03:00:00Z"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ambiguous_responded_skipped"] is True
    assert body["updated_in_request"] is False, (
        "the entire payload was the ambiguous responded-family fields - nothing applied"
    )
