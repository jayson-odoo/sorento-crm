"""
Tests for POST /api/v1/external/next-assignee (n8n): flags + round-robin assignee.
Mocks DB services to avoid real PostgreSQL.

AC-KA-11/12 (PLAN-keep-assignee-on-resolve-22sep, fix round 1, BLOCKER B1) are the
exception: they run against a real Postgres session so the actual
``get_tracking_by_contact_phone`` -> ``get_preferred_tracking_for_contact`` seam is
exercised, not a hand-built mock. Round-robin (``AccessAgentService``) and working
hours (``CalendarService``) stay mocked - unrelated to the seam under test.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.dependencies import get_db, get_external_api_user
from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate, ConversationSLATrackingUpdate
from app.services.sla_service import ConversationSLATrackingService
from tests._external_auth import external_permissions_granted
from tests._pg_fixture import blank_session


@pytest.fixture
def client():
    def _user():
        return {"id": "system"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_db] = _db
    # Authorization is deliberately out of scope here: this suite mocks the
    # database, so the real RBAC lookup cannot answer. Enforcement is covered
    # by test_external_permission_guard / _coverage.
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


ASSIGNEE = {
    "id": "user-1",
    "email": "a@test.com",
    "name": "Agent A",
    "respond_user_id": "971724",
}


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_working_hours_not_assigned(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000001",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["is_working_hours"] is True
    assert data["is_already_assigned"] is False
    assert data["status_flags"] == []
    assert "Within working hours" in data["message"]
    assert data["conversation_assignee_id"] is None
    assert data["conversation_assignee_email"] is None
    assert data["policy_id"] is None
    assert data["tier_response_hours"] is None
    assert data["tier_resolution_hours"] is None


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_non_working_hours_not_assigned(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = False
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000002",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["is_working_hours"] is False
    assert data["is_already_assigned"] is False
    assert data["status_flags"] == ["non_working_hours"]
    assert "Outside working hours" in data["message"]


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_working_hours_already_assigned(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = True
    tr = MagicMock(spec=["assigned_to_id", "assigned_to", "assigned_user"])
    tr.assigned_to_id = "x"
    tr.assigned_to = None
    tr.assigned_user = None
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = tr
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000003",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["is_working_hours"] is True
    assert data["is_already_assigned"] is True
    assert data["status_flags"] == ["already_assigned"]
    assert "already has an assignee" in data["message"]
    assert data["conversation_assignee_id"] is None
    assert data["conversation_assignee_email"] is None
    assert data["conversation_assignee_name"] is None
    assert data["conversation_assignee_respond_user_id"] is None


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_non_working_hours_already_assigned(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = False
    # is_resolved=False: an unspecced MagicMock auto-creates any attribute as a
    # truthy MagicMock, so leaving it unset would read as resolved (AC-KA-11's
    # fix) and flip this "already assigned" case to False.
    tr = MagicMock(assigned_to_id="x", assigned_to=None, is_resolved=False)
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = tr
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000004",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["is_working_hours"] is False
    assert data["is_already_assigned"] is True
    assert set(data["status_flags"]) == {"non_working_hours", "already_assigned"}
    assert "Outside working hours" in data["message"]


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_assigned_legacy_assigned_to_text_only(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = True
    tr = MagicMock(spec=["assigned_to_id", "assigned_to", "assigned_user"])
    tr.assigned_to_id = None
    tr.assigned_to = "  resp_123  "
    tr.assigned_user = None
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = tr
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000005",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200
    assert r.json()["is_already_assigned"] is True
    assert "already_assigned" in r.json()["status_flags"]
    assert r.json()["conversation_assignee_respond_user_id"] == "resp_123"


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_already_assigned_includes_conversation_assignee_from_user(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    from app.models.user import User

    mock_cal.return_value.is_within_working_time.return_value = True
    u = object.__new__(User)
    # Bypass SQLAlchemy instrumented setters (no session / mapper init)
    u.__dict__.update(
        {
            "id": "crm-user-1",
            "email": "owner@example.com",
            "name": "Owner Name",
            "respond_user_id": "888",
        }
    )
    tr = MagicMock(spec=["assigned_to_id", "assigned_to", "assigned_user"])
    tr.assigned_to_id = "crm-user-1"
    tr.assigned_to = None
    tr.assigned_user = u
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = tr
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000007",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["is_already_assigned"] is True
    assert data["conversation_assignee_id"] == "crm-user-1"
    assert data["conversation_assignee_email"] == "owner@example.com"
    assert data["conversation_assignee_name"] == "Owner Name"
    assert data["conversation_assignee_respond_user_id"] == "888"


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_current_assignee_in_body_ignored_uses_cursor_only(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    """current_assignee must not anchor rotation; same user on multiple tiers stays independent."""
    mock_cal.return_value.is_within_working_time.return_value = False
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000006",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
            "current_assignee": "999",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["is_working_hours"] is False
    assert data["status_flags"] == ["non_working_hours"]
    mock_access.return_value.get_next_assignee.assert_called_once_with(
        "agent-1", "team-1", None, brand_code=None
    )
    mock_access.return_value.get_next_assignee_after.assert_not_called()


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
@patch("app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee")
def test_sla_policy_tier_fields_when_requested(
    mock_sla_resolve, mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.get_team_id_by_tier.return_value = "team-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE
    mock_sla_resolve.return_value = {
        "policy_id": "policy-uuid-1",
        "tier_response_hours": 2,
        "tier_resolution_hours": 48,
    }

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000008",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
            "policy_code": "stock_inquiry",
            "tier": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["policy_id"] == "policy-uuid-1"
    assert data["tier_response_hours"] == 2
    assert data["tier_resolution_hours"] == 48
    mock_sla_resolve.assert_called_once()


PREFERRED = {
    "id": "user-2",
    "email": "b@test.com",
    "name": "Agent B",
    "respond_user_id": "555",
}


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_preferred_assignee_skips_round_robin(mock_cal, mock_sla, mock_access, client: TestClient):
    """preferred_assignee_id returns that member directly; cursor NOT advanced."""
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_member_assignee.return_value = PREFERRED

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000010",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
            "preferred_assignee_id": "user-2",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-2"
    assert data["assignee_respond_user_id"] == "555"
    mock_access.return_value.get_member_assignee.assert_called_once_with(
        "team-1", "user-2", brand_code=None
    )
    mock_access.return_value.get_next_assignee.assert_not_called()


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_preferred_assignee_not_member_returns_404(mock_cal, mock_sla, mock_access, client: TestClient):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_member_assignee.return_value = None

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000011",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
            "preferred_assignee_id": "ghost",
        },
    )
    assert r.status_code == 404
    assert "not a member" in r.json()["detail"].lower()
    mock_access.return_value.get_next_assignee.assert_not_called()


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_blank_preferred_assignee_falls_back_to_round_robin(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000012",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
            "preferred_assignee_id": "  ",
        },
    )
    assert r.status_code == 200
    assert r.json()["assignee_id"] == "user-1"
    mock_access.return_value.get_next_assignee.assert_called_once_with(
        "agent-1", "team-1", None, brand_code=None
    )
    mock_access.return_value.get_member_assignee.assert_not_called()


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_policy_code_without_tier_returns_400(mock_cal, mock_sla, mock_access, client: TestClient):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": "+60120000009",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
            "policy_code": "stock_inquiry",
        },
    )
    assert r.status_code == 400
    assert "both" in r.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# AC-KA-11/12: a resolved tracker is never "already assigned" for routing      #
# --------------------------------------------------------------------------- #


@pytest.fixture
def real_db():
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture
def real_db_client(real_db):
    def _user():
        return {"id": "system"}

    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_db] = lambda: real_db
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_ka(db):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="ZZT-KA-NA", name="ZZT KA Next Assignee"))
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
    phone = f"+601{uuid.uuid4().int % 10**8:08d}"
    db.add(
        RespondContact(
            id=contact_id,
            phone_number=phone,
            name="ZZT KA NA Contact",
            respond_io_id=f"zzt-ka-na-{uuid.uuid4().hex[:8]}",
            session_vars={},
        )
    )
    assignee_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email=f"zzt-ka-na-{uuid.uuid4().hex[:8]}@test.com", name="Agent One"))
    agent_id = str(uuid.uuid4())
    agent_code = f"ZZT_KA_NA_{uuid.uuid4().hex[:6]}"
    db.add(AccessAgent(id=agent_id, code=agent_code, name="ZZT KA NA Agent"))
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="ZZT KA NA Team"))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code="zzt_ka_na_general",
            team_id=team_id,
            tier=1,
            policy_id=policy_id,
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "phone": phone,
        "assignee_id": assignee_id,
        "agent_code": agent_code,
        "team_set_code": "zzt_ka_na_general",
    }


def _ticket_ka(db, seed, *, source_message_id):
    return ConversationSLATrackingService(db).create_tracking(
        ConversationSLATrackingCreate(
            agent_code=seed["agent_code"],
            team_set_code=seed["team_set_code"],
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=seed["phone"],
            source_message_id=source_message_id,
            source_message_text="Please connect me to a person.",
        )
    )


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_ac_ka_11_a_resolved_tracker_is_not_already_assigned(
    mock_cal, mock_access, real_db_client: TestClient, real_db
):
    """A returning contact whose only ticket is resolved must draw a fresh
    assignee, not read as already handled by whoever last closed it out."""
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    seed = _seed_ka(real_db)
    tracking = _ticket_ka(real_db, seed, source_message_id="ka-11")
    ConversationSLATrackingService(real_db).update_tracking(
        str(tracking.id), ConversationSLATrackingUpdate(is_resolved=True)
    )

    r = real_db_client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": seed["phone"],
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_already_assigned"] is False
    assert "already_assigned" not in data["status_flags"]
    assert data["assignee_id"] == "user-1"


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_ac_ka_12_an_open_assigned_tracker_is_already_assigned(
    mock_cal, mock_access, real_db_client: TestClient, real_db
):
    """Pins the other direction: an OPEN, assigned ticket still reads as
    already assigned - only the resolved case changed."""
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE

    seed = _seed_ka(real_db)
    _ticket_ka(real_db, seed, source_message_id="ka-12")

    r = real_db_client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone": seed["phone"],
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_already_assigned"] is True
    assert "already_assigned" in data["status_flags"]
