"""PUT /conversation-sla-tracking/integration/{id} stores naive UTC, like every
other writer of these columns.

The tracking columns are `DateTime(timezone=False)` holding naive **UTC**:
`create_tracking` stamps `initiated_at` / `current_tier_started_at` / `due_at`
from `_now_utc()`, `update_tracking` normalizes every datetime field through
`_to_aware_utc` (naive means UTC), and `mark_ticket_responded` stamps aware UTC.
The integration route, though, ran an aware `responded_at` / `resolved_at`
through `to_naive_datetime`, which converts to naive **Malaysia** wall clock -
so an n8n-reported reply at 03:00 UTC landed in the column as 11:00, eight
hours late, and the duration it computed alongside it was inflated by the same
eight hours (`_calculate_duration_hours` reads BOTH datetimes as UTC+8, and
`initiated_at` is naive UTC).

Nothing else re-normalizes it: `update_tracking`'s `_to_aware_utc` reads the
naive value as UTC and stores it verbatim.

Run:
    venv/bin/pytest tests/test_conversation_sla_integration_timestamps.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
BASE = "/api/v1/sla-management/conversation-sla-tracking"

# A reply at 03:00 UTC on a ticket raised at 01:00 UTC: two hours, and the
# column must read 03:00 - not 11:00 (Malaysia wall clock).
INITIATED_AT = datetime(2026, 8, 12, 1, 0, 0)
REPLIED_AT_UTC = "2026-08-12T03:00:00Z"
REPLIED_AT_STORED = datetime(2026, 8, 12, 3, 0, 0)


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
    service = ConversationSLATrackingService(db)
    tracking = service.create_tracking(
        ConversationSLATrackingCreate(
            agent_code=seed["agent_code"],
            team_set_code=seed["team_set_code"],
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
            source_message_id=source_message_id,
        )
    )
    # Pin the clock start so the duration assertions are exact.
    tracking.initiated_at = INITIATED_AT
    db.commit()
    return tracking


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

    # Same stub the sibling suites use: create_integration_log json.dumps-es the
    # request payload without `default=str`, so a payload carrying a datetime
    # 500s for reasons unrelated to what is under test here.
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


def _fresh(db, tracking_id):
    db.expire_all()
    return (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.id == str(tracking_id))
        .one()
    )


def test_integration_responded_at_is_stored_as_naive_utc(client, db):
    seed = _seed(db)
    ticket = _ticket(db, seed)

    resp = client.put(
        f"{BASE}/integration/{ticket.id}",
        json={"is_responded": True, "responded_at": REPLIED_AT_UTC},
    )
    assert resp.status_code == 200, resp.text

    row = _fresh(db, ticket.id)
    assert row.is_responded is True
    assert row.responded_at == REPLIED_AT_STORED, (
        "the column holds naive UTC; a Malaysia wall-clock conversion stores the "
        "reply eight hours after it happened"
    )
    assert row.response_time == Decimal("2.00")


def test_integration_resolved_at_is_stored_as_naive_utc(client, db):
    seed = _seed(db)
    ticket = _ticket(db, seed, source_message_id="wamid.msg-2")

    resp = client.put(
        f"{BASE}/integration/{ticket.id}",
        json={"is_resolved": True, "resolved_at": REPLIED_AT_UTC},
    )
    assert resp.status_code == 200, resp.text

    row = _fresh(db, ticket.id)
    assert row.is_resolved is True
    assert row.resolved_at == REPLIED_AT_STORED
    assert row.resolution_duration == Decimal("2.00")


def test_integration_accepts_a_naive_timestamp_as_utc_unchanged(client, db):
    """n8n may post without an offset. Naive already means UTC everywhere else
    in this table, so it is stored verbatim - the fix must not start shifting
    those the other way."""
    seed = _seed(db)
    ticket = _ticket(db, seed, source_message_id="wamid.msg-3")

    resp = client.put(
        f"{BASE}/integration/{ticket.id}",
        json={"is_responded": True, "responded_at": "2026-08-12T03:00:00"},
    )
    assert resp.status_code == 200, resp.text

    row = _fresh(db, ticket.id)
    assert row.responded_at == REPLIED_AT_STORED
    assert row.response_time == Decimal("2.00")


def test_integration_honours_a_non_utc_offset(client, db):
    """13:00 +08:00 is 05:00 UTC, and that is what the column must hold."""
    seed = _seed(db)
    ticket = _ticket(db, seed, source_message_id="wamid.msg-4")
    ticket.initiated_at = datetime(2026, 8, 12, 1, 0, 0)
    db.commit()

    resp = client.put(
        f"{BASE}/integration/{ticket.id}",
        json={"is_responded": True, "responded_at": "2026-08-12T13:00:00+08:00"},
    )
    assert resp.status_code == 200, resp.text

    row = _fresh(db, ticket.id)
    assert row.responded_at == datetime(2026, 8, 12, 5, 0, 0)
    assert row.response_time == Decimal("4.00")
