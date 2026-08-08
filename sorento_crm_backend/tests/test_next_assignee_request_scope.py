"""S1 / AC-F3 - next-assignee pins the request to the coalesced routing company.

The coalesced company, not the contact's raw company set. An untagged contact
coalesces to Sorento here; the request-entry scope resolver would give the same
contact ``frozenset()`` = zero rows and strand the call. Two resolvers, opposite
empty cases, on purpose (D6).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_external_api_user
from app.models.base import UNSET, get_company_scope
from app.api.v1.external.next_assignee import _scope_request_to_company
from app.services.company_routing_service import DEFAULT_COMPANY_ID, RoutingCompany
from tests._external_auth import external_permissions_granted
from tests._pg_fixture import blank_session


MOCHA_ID = "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f"


def test_scope_helper_pins_the_single_resolved_company():
    with blank_session() as db:
        _scope_request_to_company(
            db, RoutingCompany(company_id=MOCHA_ID, company_code="MOCHA", source="contact")
        )
        assert get_company_scope(db) == frozenset({MOCHA_ID})


def test_untagged_contact_is_pinned_to_sorento_not_to_the_empty_set():
    """The distinction that keeps a shared channel routable."""
    with blank_session() as db:
        _scope_request_to_company(
            db, RoutingCompany(company_id=DEFAULT_COMPANY_ID, company_code="SRT", source="default")
        )
        scope = get_company_scope(db)
        assert scope == frozenset({DEFAULT_COMPANY_ID})
        assert scope != frozenset()
        assert scope is not UNSET


def test_scope_helper_never_raises():
    """AC-J1 again: pinning is best effort, it must not 500 an assignment."""

    class Boom:
        @property
        def info(self):
            raise RuntimeError("no session info")

    _scope_request_to_company(
        Boom(), RoutingCompany(company_id=MOCHA_ID, company_code="MOCHA", source="contact")
    )


# ------------------------------------------------------------------- endpoint


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


@patch("app.api.v1.external.next_assignee.set_company_scope")
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_endpoint_pins_scope_before_resolving_a_team(
    mock_cal, mock_sla, mock_access, mock_resolve, mock_scope, client: TestClient
):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_team_id_by_tier.return_value = None
    mock_access.return_value.get_next_assignee.return_value = {
        "id": "user-1",
        "email": "a@test.com",
        "name": "A",
        "respond_user_id": "1",
    }
    mock_resolve.return_value = RoutingCompany(
        company_id=MOCHA_ID, company_code="MOCHA", source="contact"
    )

    r = client.post(
        "/api/v1/external/next-assignee",
        json={
            "contact_phone_number": "+60120000001",
            "agent_code": "general_enquiries",
            "team_code": "marketing",
        },
    )

    assert r.status_code == 200
    mock_scope.assert_called_once()
    assert mock_scope.call_args.args[1] == frozenset({MOCHA_ID})
