"""
Tests for GET /api/v1/external/team-members (n8n): active roster for preferred-assignee picking.
Mocks AccessAgentService to avoid real PostgreSQL.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_external_api_user
from tests._external_auth import external_permissions_granted


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


MEMBERS = [
    {"user_id": "u1", "name": "Alice", "respond_user_id": "111", "email": "a@t.com", "sort_order": 0},
    {"user_id": "u2", "name": "Bob", "respond_user_id": "222", "email": "b@t.com", "sort_order": 1},
]


@patch("app.services.team_roster_service.AccessAgentService")
def test_list_members_by_agent_and_team_code(mock_access, client: TestClient):
    svc = mock_access.return_value
    svc.get_agent_id_by_code.return_value = "agent-1"
    svc.list_team_ids_for_agent_code.return_value = ["team-1"]
    svc.get_team_id_by_tier.return_value = None
    svc.list_active_team_members_detail.return_value = MEMBERS

    r = client.get(
        "/api/v1/external/team-members",
        params={"agent_code": "general_enquiries", "team_code": "marketing"},
    )
    assert r.status_code == 200
    assert r.json() == MEMBERS
    # The roster call always carries both opt-in filters; None = no filter.
    svc.list_active_team_members_detail.assert_called_once_with(
        "team-1", None, brand_code=None
    )


@patch("app.services.team_roster_service.AccessAgentService")
def test_list_members_by_team_id_no_agent(mock_access, client: TestClient):
    svc = mock_access.return_value
    svc.list_active_team_members_detail.return_value = MEMBERS

    r = client.get("/api/v1/external/team-members", params={"team_id": "team-9"})
    assert r.status_code == 200
    assert r.json() == MEMBERS
    # The roster call always carries both opt-in filters; None = no filter.
    svc.list_active_team_members_detail.assert_called_once_with(
        "team-9", None, brand_code=None
    )
    svc.get_agent_id_by_code.assert_not_called()


@patch("app.services.team_roster_service.AccessAgentService")
def test_team_code_without_agent_returns_400(mock_access, client: TestClient):
    r = client.get("/api/v1/external/team-members", params={"team_code": "marketing"})
    assert r.status_code == 400
    assert "agent" in r.json()["detail"].lower()


@patch("app.services.team_roster_service.AccessAgentService")
def test_unknown_agent_code_returns_404(mock_access, client: TestClient):
    mock_access.return_value.get_agent_id_by_code.return_value = None
    r = client.get(
        "/api/v1/external/team-members",
        params={"agent_code": "nope", "team_code": "marketing"},
    )
    assert r.status_code == 404
    assert "no agent" in r.json()["detail"].lower()


@patch("app.services.team_roster_service.AccessAgentService")
def test_tier_passed_through_for_multi_tier_team_code(mock_access, client: TestClient):
    svc = mock_access.return_value
    svc.get_agent_id_by_code.return_value = "agent-1"
    svc.get_team_id_by_tier.return_value = "team-tier2"
    svc.list_active_team_members_detail.return_value = MEMBERS

    r = client.get(
        "/api/v1/external/team-members",
        params={"agent_code": "purchasing", "team_code": "project_sales", "tier": 2},
    )
    assert r.status_code == 200
    svc.get_team_id_by_tier.assert_called_once_with(
        "agent-1", 2, team_set_code="project_sales", company_id="00000000-0000-0000-0000-000000000001"
    )
    # The roster call always carries both opt-in filters; None = no filter.
    svc.list_active_team_members_detail.assert_called_once_with(
        "team-tier2", None, brand_code=None
    )
