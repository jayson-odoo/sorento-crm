"""
Unit tests for tier-based SLA escalation: get_escalation_assignee_for_tier.
Uses mocks to avoid PostgreSQL-specific DB (ARRAY, UUID). Run with: pytest tests/test_sla_escalation.py -v
"""
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from app.services.sla_service import ConversationSLATrackingService


def _http_exception_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or "")
    return str(detail or "")


def test_entity_type_to_agent_code_mapping():
    """Verify source_entity_type maps to expected agent codes."""
    assert ConversationSLATrackingService.ENTITY_TYPE_TO_AGENT_CODE.get("complaint") == "complaint"
    assert ConversationSLATrackingService.ENTITY_TYPE_TO_AGENT_CODE.get("stock_inquiry") == "lead_time_enquiries"
    assert ConversationSLATrackingService.ENTITY_TYPE_TO_AGENT_CODE.get("purchase_request") == "purchase_request"
    # Unknown or None defaults to complaint in the method logic
    assert "complaint" in ConversationSLATrackingService.ENTITY_TYPE_TO_AGENT_CODE.values()


def test_get_escalation_assignee_for_tier_returns_assignee_when_configured():
    """When agent/team/assignee exist, returns assignee dict with respond_user_id."""
    mock_db = MagicMock()
    service = ConversationSLATrackingService(mock_db)
    expected = {"id": "u1", "email": "a@test.com", "name": "A", "respond_user_id": "971724"}

    with patch("app.services.user_service.AccessAgentService") as AccessAgentService:
        svc = AccessAgentService.return_value
        svc.get_agent_id_by_code.return_value = "agent1"
        svc.get_team_id_by_tier.return_value = "team1"
        svc.get_next_assignee.return_value = expected

        assignee = service.get_escalation_assignee_for_tier("complaint", 2)

        assert assignee == expected
        svc.get_agent_id_by_code.assert_called_once_with("complaint")
        svc.get_team_id_by_tier.assert_called_once_with("agent1", 2)
        svc.get_next_assignee.assert_called_once_with("agent1", "team1")


def test_get_escalation_assignee_for_tier_defaults_none_to_complaint():
    """When source_entity_type is None, agent code defaults to complaint."""
    mock_db = MagicMock()
    service = ConversationSLATrackingService(mock_db)
    expected = {"id": "u1", "respond_user_id": "123"}

    with patch("app.services.user_service.AccessAgentService") as AccessAgentService:
        svc = AccessAgentService.return_value
        svc.get_agent_id_by_code.return_value = "agent1"
        svc.get_team_id_by_tier.return_value = "team1"
        svc.get_next_assignee.return_value = expected

        assignee = service.get_escalation_assignee_for_tier(None, 2)

        assert assignee == expected
        svc.get_agent_id_by_code.assert_called_once_with("complaint")
        svc.get_team_id_by_tier.assert_called_once_with("agent1", 2)


def test_get_escalation_assignee_for_tier_unknown_agent_raises():
    """When agent code does not exist, raises validation error."""
    mock_db = MagicMock()
    service = ConversationSLATrackingService(mock_db)

    with patch("app.services.user_service.AccessAgentService") as AccessAgentService:
        svc = AccessAgentService.return_value
        svc.get_agent_id_by_code.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_escalation_assignee_for_tier("stock_inquiry", 2)
        assert exc_info.value.status_code == 400
        msg = _http_exception_message(exc_info.value)
        assert "lead_time_enquiries" in msg


def test_get_escalation_assignee_for_tier_missing_tier_team_raises():
    """When agent exists but has no tier team, raises validation error."""
    mock_db = MagicMock()
    service = ConversationSLATrackingService(mock_db)

    with patch("app.services.user_service.AccessAgentService") as AccessAgentService:
        svc = AccessAgentService.return_value
        svc.get_agent_id_by_code.return_value = "agent1"
        svc.get_team_id_by_tier.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_escalation_assignee_for_tier("complaint", 3)
        assert exc_info.value.status_code == 400
        msg = _http_exception_message(exc_info.value)
        assert "tier 3" in msg or "3" in msg


def test_get_escalation_assignee_for_tier_empty_team_raises():
    """When tier team has no members (get_next_assignee returns None), raises validation error."""
    mock_db = MagicMock()
    service = ConversationSLATrackingService(mock_db)

    with patch("app.services.user_service.AccessAgentService") as AccessAgentService:
        svc = AccessAgentService.return_value
        svc.get_agent_id_by_code.return_value = "agent1"
        svc.get_team_id_by_tier.return_value = "team1"
        svc.get_next_assignee.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_escalation_assignee_for_tier("purchase_request", 2)
        assert exc_info.value.status_code == 400
        msg = _http_exception_message(exc_info.value)
        assert "No assignee" in msg
