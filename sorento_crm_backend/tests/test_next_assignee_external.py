"""
Tests for POST /api/v1/external/next-assignee (n8n): flags + round-robin assignee.
Mocks DB services to avoid real PostgreSQL.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_db, get_external_api_user
from app.main import app


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
    mock_access.return_value.get_team_id_by_code.return_value = "team-1"
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


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_non_working_hours_not_assigned(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = False
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.get_team_id_by_code.return_value = "team-1"
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
    tr = MagicMock(assigned_to_id="x", assigned_to=None)
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = tr
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.get_team_id_by_code.return_value = "team-1"
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
    mock_access.return_value.get_team_id_by_code.return_value = "team-1"
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
    tr = MagicMock(assigned_to_id=None, assigned_to="  resp_123  ")
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = tr
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.get_team_id_by_code.return_value = "team-1"
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


@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_current_assignee_branch_includes_flags(
    mock_cal, mock_sla, mock_access, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = False
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.get_team_id_by_code.return_value = "team-1"
    mock_access.return_value.get_next_assignee_after.return_value = ASSIGNEE

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
    mock_access.return_value.get_next_assignee_after.assert_called_once()
