"""Manual conversation-SLA escalate endpoint guard logic.

Calls the route coroutine directly with a patched ConversationSLATrackingService
(mirrors the mock style of test_sla_escalation.py — no DB/TestClient). Covers the
guards that run before assignee resolution + the happy-path delegation.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.sla import sla_tracking as mod
from app.api.v1.sla.sla_tracking import (
    escalate_conversation_sla_tracking,
    _ConversationEscalateRequest,
)


def _call(reason, tracking, *, assignee=None, escalated=None):
    """Run the route with a patched service; returns (result, service_mock)."""
    svc = MagicMock()
    svc.get_tracking.return_value = tracking
    svc.get_escalation_assignee_for_tier.return_value = assignee or {
        "id": "user-2",
        "respond_user_id": "r-2",
        "name": "Tier 2",
    }
    svc.escalate_tracking.return_value = escalated or tracking
    with patch.object(mod, "ConversationSLATrackingService", return_value=svc), patch.object(
        mod, "build_conversation_sla_tracking_response", return_value={"ok": True}
    ):
        result = asyncio.run(
            escalate_conversation_sla_tracking(
                tracking_id="t1",
                payload=_ConversationEscalateRequest(reason=reason),
                current_user={"id": "me"},
                db=MagicMock(),
            )
        )
    return result, svc


def _tracking(**over):
    base = dict(
        source_entity_type=None,
        is_resolved=False,
        current_tier=1,
        respond_contact_id="contact-1",
        policy_id="policy-1",
        team_set_code=None,
        agent_id=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_empty_reason_rejected():
    with pytest.raises(HTTPException) as ei:
        _call("   ", _tracking())
    assert ei.value.status_code == 422


def test_form_sla_row_rejected():
    with pytest.raises(HTTPException) as ei:
        _call("escalate pls", _tracking(source_entity_type="complaint"))
    assert ei.value.status_code == 400
    assert "form-SLA" in str(ei.value.detail)


def test_resolved_row_rejected():
    with pytest.raises(HTTPException) as ei:
        _call("escalate pls", _tracking(is_resolved=True))
    assert ei.value.status_code == 400


def test_top_tier_rejected():
    with pytest.raises(HTTPException) as ei:
        _call("escalate pls", _tracking(current_tier=3))
    assert ei.value.status_code == 400
    assert "maximum tier" in str(ei.value.detail)


def test_missing_contact_rejected():
    with pytest.raises(HTTPException) as ei:
        _call("escalate pls", _tracking(respond_contact_id=None))
    assert ei.value.status_code == 400


def test_happy_path_escalates_to_next_tier_with_manual_reason():
    result, svc = _call("Customer angry", _tracking(current_tier=1))
    assert result == {"ok": True}
    # Assignee resolved for the TARGET tier (current + 1).
    svc.get_escalation_assignee_for_tier.assert_called_once()
    assert svc.get_escalation_assignee_for_tier.call_args.args[1] == 2
    # escalate_tracking called with target tier + "manual: <reason>" + resolved assignee.
    kwargs = svc.escalate_tracking.call_args.kwargs
    assert kwargs["current_tier"] == 2
    assert kwargs["escalation_reason"] == "manual: Customer angry"
    assert kwargs["assigned_to_id"] == "user-2"
    assert kwargs["assigned_to_respond_user_id"] == "r-2"
