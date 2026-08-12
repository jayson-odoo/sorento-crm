"""S0 - POST /api/v1/external/next-assignee echoes the resolved routing company.

Team resolution is deliberately NOT affected in this slice: the endpoint reports
which company it *would* route to so real n8n traffic can be observed before any
routing behaviour changes (PLAN S0, AC-A5).

DB is mocked, like tests/test_next_assignee_external.py - the resolver itself is
covered against a real Postgres in tests/test_company_routing_service.py.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_external_api_user
from app.services.company_routing_service import DEFAULT_COMPANY_ID, RoutingCompany
from tests._external_auth import external_permissions_granted


@pytest.fixture
def client():
    def _user():
        return {"id": "system"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_db] = _db
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


ASSIGNEE = {
    "id": "user-1",
    "email": "a@test.com",
    "name": "Agent A",
    "respond_user_id": "971724",
}

MOCHA = RoutingCompany(
    company_id="5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f",
    company_code="MOCHA",
    source="contact",
    ambiguous=False,
)
SORENTO_DEFAULT = RoutingCompany(
    company_id=DEFAULT_COMPANY_ID,
    company_code="SRT",
    source="default",
    ambiguous=False,
)
SORENTO_AMBIGUOUS = SORENTO_DEFAULT._replace(ambiguous=True)


def _happy_path_mocks(mock_cal, mock_sla, mock_access):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE


BODY = {
    "contact_phone_number": "+60120000001",
    "agent_code": "general_enquiries",
    "team_code": "marketing",
}


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_echoes_company_resolved_from_contact(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """AC-A5: company_id / company_code / company_source are in the response."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = MOCHA

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    data = r.json()
    assert data["company_id"] == "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f"
    assert data["company_code"] == "MOCHA"
    assert data["company_source"] == "contact"
    assert "ambiguous_company" not in data["status_flags"]
    # S0 is inert: the assignee still comes from the unchanged round-robin path.
    assert data["assignee_id"] == "user-1"


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_untagged_contact_echoes_default_company(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """AC-A4: an untagged contact still gets an assignee, reported as the default."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    data = r.json()
    assert data["company_id"] == DEFAULT_COMPANY_ID
    assert data["company_source"] == "default"
    assert data["assignee_id"] == "user-1"


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_multi_company_contact_flags_ambiguous(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """AC-A3: never pick one arbitrarily - fall to default and say so."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_AMBIGUOUS

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    data = r.json()
    assert "ambiguous_company" in data["status_flags"]
    assert data["company_id"] == DEFAULT_COMPANY_ID
    assert data["company_source"] == "default"


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_existing_flags_survive_alongside_company_flag(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """ambiguous_company is ADDED to the flag list, it does not replace it."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_cal.return_value.is_within_working_time.return_value = False
    mock_resolve.return_value = SORENTO_AMBIGUOUS

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    flags = r.json()["status_flags"]
    assert "non_working_hours" in flags
    assert "ambiguous_company" in flags


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_phone_is_passed_to_the_resolver(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """AC-A2: n8n sends phone only today, so phone must reach the resolver."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    kwargs = mock_resolve.call_args.kwargs
    assert kwargs["phone"] == "+60120000001"
    assert kwargs["contact_id"] is None
    assert kwargs["company_code"] is None


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_contact_id_space_id_and_company_code_are_passed_through(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """AC-A1 / D3: body company_code is accepted as an override."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = MOCHA

    r = client.post(
        "/api/v1/external/next-assignee",
        json={**BODY, "contact_id": "rio-123", "space_id": "364817", "company_code": "MOCHA"},
    )

    assert r.status_code == 200
    kwargs = mock_resolve.call_args.kwargs
    assert kwargs["contact_id"] == "rio-123"
    assert kwargs["space_id"] == "364817"
    assert kwargs["company_code"] == "MOCHA"


@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_resolver_failure_never_breaks_routing(
    mock_cal, mock_sla, mock_access, mock_resolve, client: TestClient
):
    """AC-J1: a resolver blow-up degrades to the default, it does not 500."""
    _happy_path_mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.side_effect = RuntimeError("database on fire")

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == "user-1"
    assert data["company_id"] == DEFAULT_COMPANY_ID
    assert data["company_source"] == "default"
