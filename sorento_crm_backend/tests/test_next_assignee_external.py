"""
Tests for POST /api/v1/external/next-assignee (n8n): flags + round-robin assignee.
Mocks DB services to avoid real PostgreSQL.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_external_api_user


@pytest.fixture
def client():
    def _user():
        return {"id": "system"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_db] = _db
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
    tr = MagicMock(assigned_to_id="x", assigned_to=None)
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
    mock_access.return_value.get_next_assignee.assert_called_once_with("agent-1", "team-1")
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
    mock_access.return_value.get_member_assignee.assert_called_once_with("team-1", "user-2")
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
    mock_access.return_value.get_next_assignee.assert_called_once_with("agent-1", "team-1")
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
