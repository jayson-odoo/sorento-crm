"""S0 / AC-B1 - market-segment scoping must fire on the phone-only path.

Today ``next_assignee`` only scopes by segment when the body carries
``contact_id`` / ``respond_io_id`` (next_assignee.py, the contact_ref branch).
n8n sends ``contact_phone_number``, so in production the filter never runs and a
phone-only caller silently gets an UNFILTERED round-robin pool.

DB is mocked here; the contact lookup itself is covered against real Postgres in
tests/test_company_routing_service.py.
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


ASSIGNEE = {"id": "user-1", "email": "a@test.com", "name": "A", "respond_user_id": "1"}
SORENTO = RoutingCompany(
    company_id=DEFAULT_COMPANY_ID, company_code="SRT", source="default"
)
BODY = {
    "contact_phone_number": "+60120000001",
    "agent_code": "general_enquiries",
    "team_code": "marketing",
}


def _happy(mock_cal, mock_sla, mock_access):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = ASSIGNEE


@patch("app.services.market_segment_service.MarketSegmentService")
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_phone_only_call_applies_segment_filter(
    mock_cal, mock_sla, mock_access, mock_resolve, mock_seg, client: TestClient
):
    """AC-B1: the pool is scoped even though the body has no contact_id."""
    _happy(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO
    mock_seg.return_value.resolve_contact_segments.return_value = {"retail"}

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    mock_seg.return_value.resolve_contact_segments.assert_called_once()
    kwargs = mock_seg.return_value.resolve_contact_segments.call_args.kwargs
    assert kwargs["phone"] == "+60120000001"
    # The scoped overload is the one that must be used.
    mock_access.return_value.get_next_assignee.assert_called_once_with(
        "agent-1", "team-1", {"retail"}
    )


@patch("app.services.market_segment_service.MarketSegmentService")
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_untagged_contact_still_unfiltered(
    mock_cal, mock_sla, mock_access, mock_resolve, mock_seg, client: TestClient
):
    """An untagged contact resolves to no segments, so the pool stays unfiltered."""
    _happy(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO
    mock_seg.return_value.resolve_contact_segments.return_value = set()

    r = client.post("/api/v1/external/next-assignee", json=BODY)

    assert r.status_code == 200
    mock_access.return_value.get_next_assignee.assert_called_once_with(
        "agent-1", "team-1"
    )


@patch("app.services.market_segment_service.MarketSegmentService")
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_contact_id_path_still_passes_id_and_space(
    mock_cal, mock_sla, mock_access, mock_resolve, mock_seg, client: TestClient
):
    """The existing id-based path keeps working, now with phone as a fallback."""
    _happy(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO
    mock_seg.return_value.resolve_contact_segments.return_value = {"project"}

    r = client.post(
        "/api/v1/external/next-assignee",
        json={**BODY, "contact_id": "rio-9", "space_id": "364817"},
    )

    assert r.status_code == 200
    kwargs = mock_seg.return_value.resolve_contact_segments.call_args.kwargs
    assert kwargs["respond_io_id"] == "rio-9"
    assert kwargs["space_id"] == "364817"
    assert kwargs["phone"] == "+60120000001"


@patch("app.services.market_segment_service.MarketSegmentService")
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_preferred_assignee_still_skips_segment_scoping(
    mock_cal, mock_sla, mock_access, mock_resolve, mock_seg, client: TestClient
):
    """preferred_assignee_id short-circuits round-robin, so no segment lookup."""
    _happy(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO
    mock_access.return_value.get_member_assignee.return_value = ASSIGNEE

    r = client.post(
        "/api/v1/external/next-assignee",
        json={**BODY, "preferred_assignee_id": "user-1"},
    )

    assert r.status_code == 200
    mock_seg.return_value.resolve_contact_segments.assert_not_called()
