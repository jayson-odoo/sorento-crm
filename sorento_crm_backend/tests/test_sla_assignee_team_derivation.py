"""
Tests for assignee-driven team/agent derivation (PLAN-sla-assignee-team-derivation):
- ConversationSLATrackingService.derive_team_for_assignee (3-step algorithm)
- apply_assignee_team_derivation side effects (routing fields, clocks, cursor, event log)
- tier-1 membership invariant enforcement (TeamService / AccessAgentService)
- /integration/escalate signal-only auto-increment mode

Uses mocks to avoid PostgreSQL-specific DB. Run with:
    pytest tests/test_sla_assignee_team_derivation.py -v
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import AccessAgentService, TeamService


def _http_exception_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or "")
    return str(detail or "")


def _link(agent_id: str, code: str, team_id: str, tier: int = 1) -> MagicMock:
    link = MagicMock()
    link.agent_id = agent_id
    link.code = code
    link.team_id = team_id
    link.tier = tier
    return link


def _chain(all_result=None, first_result=None) -> MagicMock:
    """Chainable query mock: query(...).join(...).filter(...).order_by(...) -> all()/first()."""
    q = MagicMock()
    q.join.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.distinct.return_value = q
    q.with_for_update.return_value = q
    q.all.return_value = all_result if all_result is not None else []
    q.first.return_value = first_result
    return q


def _form_codes(*codes) -> MagicMock:
    """Mock for form_sla_agent_codes' query: db.query(FormSLAConfig.agent_code)
    .distinct().all() -> rows of (code,). Empty = no form-SLA agents, so the
    conversation/form split is a no-op and behaviour matches the pre-relaxation
    global invariant."""
    return _chain(all_result=[(c,) for c in codes])


# ---------------------------------------------------------------------------
# derive_team_for_assignee
# ---------------------------------------------------------------------------

def test_derive_tier1_member_returns_their_team_set():
    """Step 1: tier-1 membership anywhere wins, cross-agent included."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[_link("agent-b", "set_b", "team-b1")]),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee(
        "user-exec-b", current_agent_id="agent-a", current_team_set_code="set_a"
    )

    assert derived == {
        "agent_id": "agent-b",
        "team_set_code": "set_b",
        "tier": 1,
        "team_id": "team-b1",
    }


def test_derive_multiple_tier1_teams_is_ambiguous():
    """Invariant-violating config (user in two tier-1-linked TEAMS) → None, never a guess."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_a", "team-a1"),
            _link("agent-b", "set_b", "team-b1"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    assert service.derive_team_for_assignee("user-x") is None


def test_derive_excludes_form_tier1_teams_no_false_ambiguity():
    """New relaxation: with form-SLA agents present, the tier-1 probe filters them
    out (AccessAgent.code NOT IN form_codes). A user in one form tier-1 team + one
    conversation tier-1 team resolves to the CONVERSATION team, not None."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes("purchase_request", "complaint"),
        # DB already filtered form links → only the conversation tier-1 link remains
        _chain(all_result=[_link("agent-conv", "set_conv", "team-conv")]),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee("user-shared")
    assert derived == {
        "agent_id": "agent-conv",
        "team_set_code": "set_conv",
        "tier": 1,
        "team_id": "team-conv",
    }


def test_derive_shared_pool_team_prefers_current_agent():
    """Same team linked tier-1 under many agents → keep tracking's current agent."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-b", "customer_service", "team-cs"),
            _link("agent-c", "customer_service", "team-cs"),
            _link("agent-a", "customer_service_c", "team-cs"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee(
        "user-exec", current_agent_id="agent-c", current_team_set_code="warehouse"
    )

    assert derived == {
        "agent_id": "agent-c",
        "team_set_code": "customer_service",
        "tier": 1,
        "team_id": "team-cs",
    }


def test_derive_shared_pool_team_falls_back_to_first_link():
    """Current agent not among the team's tier-1 links → deterministic first link."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-b", "customer_service", "team-cs"),
            _link("agent-c", "customer_service", "team-cs"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee(
        "user-exec", current_agent_id="agent-x", current_team_set_code="set_x"
    )

    assert derived == {
        "agent_id": "agent-b",
        "team_set_code": "customer_service",
        "tier": 1,
        "team_id": "team-cs",
    }


def test_derive_tier2_member_scoped_to_current_team_set():
    """Step 2: no tier-1 membership; tier-2/3 lookup scoped to the tracking's current set."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[]),  # no tier-1 links
        _chain(first_result=_link("agent-a", "set_a", "team-a2", tier=2)),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee(
        "user-mgr", current_agent_id="agent-a", current_team_set_code="set_a"
    )

    assert derived == {
        "agent_id": "agent-a",
        "team_set_code": "set_a",
        "tier": 2,
        "team_id": "team-a2",
    }


def test_derive_tier23_without_current_context_returns_none():
    """Step 3: manager without tier-1 membership and no current team context → None."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [_form_codes(), _chain(all_result=[])]
    service = ConversationSLATrackingService(mock_db)

    assert service.derive_team_for_assignee("user-mgr") is None


def test_derive_unknown_user_returns_none():
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[]),
        _chain(first_result=None),
    ]
    service = ConversationSLATrackingService(mock_db)

    assert (
        service.derive_team_for_assignee(
            "user-unknown", current_agent_id="agent-a", current_team_set_code="set_a"
        )
        is None
    )


def test_derive_blank_user_id_returns_none():
    mock_db = MagicMock()
    service = ConversationSLATrackingService(mock_db)
    assert service.derive_team_for_assignee("") is None
    mock_db.query.assert_not_called()


# ---------------------------------------------------------------------------
# apply_assignee_team_derivation
# ---------------------------------------------------------------------------

def _tracking_mock(**overrides) -> MagicMock:
    tracking = MagicMock()
    tracking.id = "tracking-1"
    tracking.is_resolved = False
    tracking.agent_id = "agent-a"
    tracking.team_set_code = "set_a"
    tracking.current_tier = 1
    tracking.policy_id = "policy-1"
    tracking.due_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for key, value in overrides.items():
        setattr(tracking, key, value)
    return tracking


def _tier_row(response_hours=4.0, resolution_hours=24.0) -> MagicMock:
    tier_row = MagicMock()
    tier_row.response_hours = response_hours
    tier_row.resolution_hours = resolution_hours
    return tier_row


def test_apply_team_flip_updates_routing_clock_cursor_and_event_log():
    mock_db = MagicMock()
    tracking = _tracking_mock()
    cursor = MagicMock()
    mock_db.query.side_effect = [
        _chain(first_result=_tier_row()),  # SLAPolicyTier
        _chain(first_result=cursor),       # AgentTeamRoundRobinCursor
    ]
    service = ConversationSLATrackingService(mock_db)
    derived = {"agent_id": "agent-b", "team_set_code": "set_b", "tier": 1, "team_id": "team-b1"}

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee", return_value=derived), \
         patch.object(service, "create_event_log") as create_event_log:
        result = service.apply_assignee_team_derivation(
            "tracking-1", "user-exec-b", source="conversation-assignee"
        )

    assert result is not None
    assert result["routing_updated"] is True
    assert result["team_changed"] is True
    assert result["tier_changed"] is False
    assert result["from_tier"] == 1 and result["to_tier"] == 1
    assert tracking.agent_id == "agent-b"
    assert tracking.team_set_code == "set_b"
    assert tracking.current_tier == 1
    # Tier clock restarted with the matched tier's hours
    assert tracking.due_at - tracking.current_tier_started_at == timedelta(hours=4.0)
    assert tracking.due_at_resolution - tracking.current_tier_started_at == timedelta(hours=24.0)
    # Round-robin cursor advanced to the manual pick
    assert cursor.last_assigned_user_id == "user-exec-b"
    # Team-only change at the same tier still writes the audit row
    event = create_event_log.call_args[0][0]
    assert event.event_type == "reassignment"
    assert event.from_tier == 1 and event.to_tier == 1
    assert "set_a" in (event.reason or "") and "set_b" in (event.reason or "")
    assert "conversation-assignee" in (event.reason or "")


def test_apply_tier_reset_after_escalated_misroute():
    """Tier-2 tracking reassigned to the correct team's tier-1 exec → tier resets to 1."""
    mock_db = MagicMock()
    tracking = _tracking_mock(current_tier=2)
    mock_db.query.side_effect = [
        _chain(first_result=_tier_row()),
        _chain(first_result=None),  # no cursor yet → insert
    ]
    service = ConversationSLATrackingService(mock_db)
    derived = {"agent_id": "agent-b", "team_set_code": "set_b", "tier": 1, "team_id": "team-b1"}

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee", return_value=derived), \
         patch.object(service, "create_event_log") as create_event_log:
        result = service.apply_assignee_team_derivation(
            "tracking-1", "user-exec-b", source="sync-assignee"
        )

    assert result["tier_changed"] is True
    assert result["from_tier"] == 2 and result["to_tier"] == 1
    assert tracking.current_tier == 1
    mock_db.add.assert_called_once()  # cursor upsert (insert path)
    added_cursor = mock_db.add.call_args[0][0]
    assert added_cursor.last_assigned_user_id == "user-exec-b"
    event = create_event_log.call_args[0][0]
    assert event.event_type == "reassignment"
    assert event.from_tier == 2 and event.to_tier == 1


def test_apply_tier2_takeover_keeps_team_and_skips_cursor():
    """Tier-1 tracking reassigned to the current team's tier-2 manager → tier 2, same team."""
    mock_db = MagicMock()
    tracking = _tracking_mock(current_tier=1)
    mock_db.query.side_effect = [_chain(first_result=_tier_row())]
    service = ConversationSLATrackingService(mock_db)
    derived = {"agent_id": "agent-a", "team_set_code": "set_a", "tier": 2, "team_id": "team-a2"}

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee", return_value=derived), \
         patch.object(service, "create_event_log") as create_event_log:
        result = service.apply_assignee_team_derivation(
            "tracking-1", "user-mgr", source="conversation-assignee"
        )

    assert result["team_changed"] is False
    assert result["tier_changed"] is True
    assert tracking.current_tier == 2
    mock_db.add.assert_not_called()  # team unchanged → cursor untouched
    event = create_event_log.call_args[0][0]
    assert event.from_tier == 1 and event.to_tier == 2
    assert "team_set" not in (event.reason or "")


def test_apply_no_change_returns_none():
    mock_db = MagicMock()
    tracking = _tracking_mock()
    service = ConversationSLATrackingService(mock_db)
    derived = {"agent_id": "agent-a", "team_set_code": "set_a", "tier": 1, "team_id": "team-a1"}

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee", return_value=derived), \
         patch.object(service, "create_event_log") as create_event_log:
        assert (
            service.apply_assignee_team_derivation("tracking-1", "u1", source="sync-assignee")
            is None
        )
    create_event_log.assert_not_called()


def test_apply_skips_form_sla_tracking():
    """Form SLA stages own routing via FormSLAConfig - assignee changes never flip them."""
    mock_db = MagicMock()
    tracking = _tracking_mock(source_entity_type="purchase_request")
    service = ConversationSLATrackingService(mock_db)

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee") as derive:
        assert (
            service.apply_assignee_team_derivation("tracking-1", "u1", source="sync-assignee")
            is None
        )
    derive.assert_not_called()


def test_apply_skips_resolved_tracking():
    mock_db = MagicMock()
    tracking = _tracking_mock(is_resolved=True)
    service = ConversationSLATrackingService(mock_db)

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee") as derive:
        assert (
            service.apply_assignee_team_derivation("tracking-1", "u1", source="sync-assignee")
            is None
        )
    derive.assert_not_called()


def test_apply_no_derivation_returns_none():
    mock_db = MagicMock()
    tracking = _tracking_mock()
    service = ConversationSLATrackingService(mock_db)

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee", return_value=None):
        assert (
            service.apply_assignee_team_derivation("tracking-1", "u1", source="sync-assignee")
            is None
        )


def test_apply_missing_policy_tier_keeps_clocks_but_fixes_routing():
    mock_db = MagicMock()
    original_due = datetime(2026, 6, 1, tzinfo=timezone.utc)
    tracking = _tracking_mock(due_at=original_due, current_tier_started_at="sentinel")
    # _resolve_tier_with_clamp issues up to three SLAPolicyTier queries before
    # giving up (exact -> clamp-down -> clamp-to-lowest). All None = policy has zero
    # tiers (misconfigured) -> tier_row None -> clocks preserved, routing still fixed.
    mock_db.query.side_effect = [
        _chain(first_result=None),  # SLAPolicyTier exact-level miss
        _chain(first_result=None),  # clamp-down (<= requested) miss
        _chain(first_result=None),  # clamp-to-lowest miss
        _chain(first_result=MagicMock()),  # cursor
    ]
    service = ConversationSLATrackingService(mock_db)
    derived = {"agent_id": "agent-b", "team_set_code": "set_b", "tier": 1, "team_id": "team-b1"}

    with patch.object(service, "get_tracking", return_value=tracking), \
         patch.object(service, "derive_team_for_assignee", return_value=derived), \
         patch.object(service, "create_event_log"):
        result = service.apply_assignee_team_derivation(
            "tracking-1", "u1", source="conversation-assignee"
        )

    assert result["routing_updated"] is True
    assert tracking.agent_id == "agent-b"
    assert tracking.due_at == original_due
    assert tracking.current_tier_started_at == "sentinel"


# ---------------------------------------------------------------------------
# Tier-1 membership invariant - TeamService.add_team_member
# ---------------------------------------------------------------------------

def test_add_member_to_unlinked_team_passes():
    mock_db = MagicMock()
    # form-codes probe, then new-team tier-1 link probe (.first() → None)
    mock_db.query.side_effect = [_form_codes(), _chain(first_result=None)]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-x", "user-1")  # no raise


def test_add_member_already_in_other_tier1_team_rejected():
    mock_db = MagicMock()
    existing_link = _link("agent-a", "set_a", "team-a1")
    user = MagicMock()
    user.name = "Jane Exec"
    user.email = "jane@test.com"
    agent = MagicMock()
    agent.code = "order_enquiries"
    mock_db.query.side_effect = [
        _form_codes(),                                               # form-SLA agent codes
        _chain(first_result=_link("agent-b", "set_b", "team-b1")),  # new team has a conv tier-1 link
        _chain(all_result=[(existing_link, "Team A1")]),            # user's other conv tier-1 links
        _chain(first_result=user),                                   # User
        _chain(first_result=agent),                                  # AccessAgent
    ]
    service = TeamService(mock_db)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_tier1_membership_invariant("team-b1", "user-1")
    assert exc_info.value.status_code == 400
    msg = _http_exception_message(exc_info.value)
    assert "Jane Exec" in msg
    assert "Team A1" in msg
    assert "order_enquiries" in msg
    assert "one tier-1 team" in msg


def test_add_member_same_set_passes():
    """User's only tier-1 set is the same (agent, code) as the new team's - allowed."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(first_result=_link("agent-a", "set_a", "team-a1")),  # new team conv tier-1 link
        _chain(all_result=[]),  # no OTHER tier-1 membership
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-a1", "user-1")  # no raise


def test_add_member_to_shared_pool_team_passes():
    """Same team linked at tier 1 under multiple agents (shared pool) - members allowed."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(first_result=_link("agent-a", "customer_service", "team-x")),  # conv tier-1 link
        _chain(all_result=[]),  # no membership in another tier-1-linked team
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-x", "user-1")  # no raise


def test_add_member_to_form_only_tier1_team_passes():
    """New relaxation: a team linked at tier 1 ONLY under FORM-SLA agents never conflicts.
    The new-team conv-tier-1 probe returns None (filtered out), so we return early."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes("purchase_request", "complaint"),
        _chain(first_result=None),  # no CONVERSATION tier-1 link on this team
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-pr", "user-1")  # no raise


def test_add_member_conv_tier1_allowed_despite_existing_form_tier1(monkeypatch):
    """New relaxation: user already in a FORM-SLA tier-1 team may still join a
    CONVERSATION tier-1 team - the existing-links probe excludes form agents, so
    it finds nothing to conflict with."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes("purchase_request"),
        _chain(first_result=_link("agent-conv", "set_conv", "team-conv")),  # new team conv link
        _chain(all_result=[]),  # existing CONVERSATION tier-1 links (form ones excluded) → none
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-conv", "user-1")  # no raise


def test_add_team_member_runs_invariant_check():
    mock_db = MagicMock()
    service = TeamService(mock_db)
    with patch.object(service, "get_team"), \
         patch.object(service, "_validate_tier1_membership_invariant") as validate:
        # membership-exists check
        mock_db.query.return_value.filter.return_value.first.return_value = None
        service.add_team_member("team-1", "user-1")
    validate.assert_called_once_with("team-1", "user-1")


# ---------------------------------------------------------------------------
# Tier-1 membership invariant - AccessAgentService.set_agent_teams
# ---------------------------------------------------------------------------

def test_set_agent_teams_tier1_conflict_rejected():
    mock_db = MagicMock()
    user = MagicMock()
    user.name = "Jane Exec"
    user.email = "jane@test.com"
    agent = MagicMock()
    agent.code = "general_enquiries"
    mock_db.query.side_effect = [
        _form_codes(),                               # form-SLA agent codes
        _chain(first_result=None),                   # this_agent (conversation → not skipped)
        _chain(all_result=[("team-a1", "user-1")]),  # members of the tier-1 team in payload
        # user's membership in a DIFFERENT tier-1-linked team under another agent
        _chain(all_result=[("user-1", "agent-b", "set_b", "team-b1", "Team B1")]),
        _chain(first_result=user),
        _chain(first_result=agent),
    ]
    service = AccessAgentService(mock_db)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_tier1_invariant_for_assignments(
            "agent-a", [{"code": "set_a", "team_id": "team-a1", "tier": 1}]
        )
    assert exc_info.value.status_code == 400
    msg = _http_exception_message(exc_info.value)
    assert "Jane Exec" in msg
    assert "Team B1" in msg
    assert "general_enquiries" in msg


def test_set_agent_teams_no_tier1_assignments_skips_validation():
    mock_db = MagicMock()
    service = AccessAgentService(mock_db)

    service._validate_tier1_invariant_for_assignments(
        "agent-a", [{"code": "set_a", "team_id": "team-a2", "tier": 2}]
    )
    mock_db.query.assert_not_called()


def test_set_agent_teams_form_agent_skips_validation():
    """New relaxation: linking teams under a FORM-SLA agent never constrains
    membership - the whole check short-circuits after the agent-type probe."""
    mock_db = MagicMock()
    form_agent = MagicMock()
    form_agent.code = "purchase_request"
    mock_db.query.side_effect = [
        _form_codes("purchase_request", "complaint"),
        _chain(first_result=form_agent),  # this_agent IS a form-SLA agent → skip
    ]
    service = AccessAgentService(mock_db)

    service._validate_tier1_invariant_for_assignments(
        "agent-pr", [{"code": "customer_service", "team_id": "team-pr", "tier": 1}]
    )  # no raise, no member/other-link queries


def test_set_agent_teams_clean_config_passes():
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),                               # form-SLA agent codes
        _chain(first_result=None),                   # this_agent (conversation)
        _chain(all_result=[("team-a1", "user-1")]),  # members
        _chain(all_result=[]),                       # no other tier-1 links
        _chain(all_result=[]),                       # no cross-tier reuse
    ]
    service = AccessAgentService(mock_db)

    service._validate_tier1_invariant_for_assignments(
        "agent-a", [{"code": "set_a", "team_id": "team-a1", "tier": 1}]
    )  # no raise


# ---------------------------------------------------------------------------
# /integration/escalate - signal-only auto-increment
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from app.database import get_db as database_get_db
    from app.dependencies import (
        get_db as dependencies_get_db,
        get_current_user_or_api_key,
        get_current_user,
    )
    from app.main import app

    def _user():
        return {"id": "system"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_current_user_or_api_key] = _user
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[database_get_db] = _db
    app.dependency_overrides[dependencies_get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


ASSIGNEE = {"id": "user-2", "email": "b@test.com", "name": "Tier2 B", "respond_user_id": "888"}


def _escalate_tracking_mock(current_tier: int) -> MagicMock:
    tracking = MagicMock()
    tracking.id = "tracking-1"
    tracking.is_resolved = False
    tracking.current_tier = current_tier
    tracking.agent_id = "agent-a"
    tracking.team_set_code = "set_a"
    tracking.source_entity_type = "complaint"
    tracking.message_id = "msg-1"
    tracking.assigned_to_id = "user-1"
    tracking.assigned_to = "777"
    tracking.assigned_user = None
    tracking.due_at = datetime.now(timezone.utc) + timedelta(hours=4)
    tracking.due_at_resolution = datetime.now(timezone.utc) + timedelta(hours=24)
    return tracking


@patch("app.api.v1.sla.sla_tracking.IntegrationLogService")
@patch("app.api.v1.sla.sla_tracking.ConversationSLATrackingService")
def test_escalate_signal_only_increments_tier(mock_service_cls, _mock_log, client):
    svc = mock_service_cls.return_value
    before = _escalate_tracking_mock(current_tier=1)
    after = _escalate_tracking_mock(current_tier=2)
    svc.resolve_internal_respond_contact_id.return_value = "contact-1"
    # get_open_tracking_by_contact is the route's PRIMARY resolver (S2b); an
    # unconfigured auto-mock is truthy (and its auto-mocked .is_resolved is
    # truthy too), so it must return None to fall through to the
    # get_tracking_by_contact_and_policy mock this test actually configures.
    svc.get_open_tracking_by_contact.return_value = None
    svc.get_tracking_by_contact_and_policy.return_value = before
    svc.get_escalation_assignee_for_tier.return_value = ASSIGNEE
    svc.escalate_tracking.return_value = after

    r = client.post(
        "/api/v1/sla-management/conversation-sla-tracking/integration/escalate",
        json={
            "respond_contact_id": "contact-1",
            "policy_id": "policy-1",
            "escalation_reason": "SLA breached",
        },
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["escalated"] is True
    assert data["from_tier"] == 1
    assert data["to_tier"] == 2
    assert data["assigned_to_id"] == "user-2"
    # Server computed target = current + 1 and used the tracking's stored routing
    args, kwargs = svc.get_escalation_assignee_for_tier.call_args
    assert args[1] == 2  # target tier
    assert args[2] == "set_a"
    assert kwargs.get("agent_id_override") == before.agent_id
    assert svc.escalate_tracking.call_args.kwargs["current_tier"] == 2


@patch("app.api.v1.sla.sla_tracking.IntegrationLogService")
@patch("app.api.v1.sla.sla_tracking.ConversationSLATrackingService")
def test_escalate_signal_only_at_max_tier_returns_flag(mock_service_cls, _mock_log, client):
    svc = mock_service_cls.return_value
    svc.resolve_internal_respond_contact_id.return_value = "contact-1"
    svc.get_open_tracking_by_contact.return_value = None
    svc.get_tracking_by_contact_and_policy.return_value = _escalate_tracking_mock(current_tier=3)

    r = client.post(
        "/api/v1/sla-management/conversation-sla-tracking/integration/escalate",
        json={
            "respond_contact_id": "contact-1",
            "policy_id": "policy-1",
            "escalation_reason": "SLA breached",
        },
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["escalated"] is False
    assert data["from_tier"] == 3
    assert data["to_tier"] == 3
    assert "max tier" in data["message"]
    svc.escalate_tracking.assert_not_called()
    svc.get_escalation_assignee_for_tier.assert_not_called()


@patch("app.api.v1.sla.sla_tracking.IntegrationLogService")
@patch("app.api.v1.sla.sla_tracking.ConversationSLATrackingService")
def test_escalate_explicit_target_must_exceed_current(mock_service_cls, _mock_log, client):
    svc = mock_service_cls.return_value
    svc.resolve_internal_respond_contact_id.return_value = "contact-1"
    svc.get_tracking_by_contact_and_policy.return_value = _escalate_tracking_mock(current_tier=2)

    r = client.post(
        "/api/v1/sla-management/conversation-sla-tracking/integration/escalate",
        json={
            "respond_contact_id": "contact-1",
            "policy_id": "policy-1",
            "current_tier": 2,
            "escalation_reason": "SLA breached",
        },
    )

    assert r.status_code == 400
    svc.escalate_tracking.assert_not_called()


@patch("app.api.v1.sla.sla_tracking.IntegrationLogService")
@patch("app.api.v1.sla.sla_tracking.ConversationSLATrackingService")
def test_escalate_explicit_multi_step_jump_still_works(mock_service_cls, _mock_log, client):
    svc = mock_service_cls.return_value
    before = _escalate_tracking_mock(current_tier=1)
    after = _escalate_tracking_mock(current_tier=3)
    svc.resolve_internal_respond_contact_id.return_value = "contact-1"
    svc.get_open_tracking_by_contact.return_value = None
    svc.get_tracking_by_contact_and_policy.return_value = before
    svc.get_escalation_assignee_for_tier.return_value = ASSIGNEE
    svc.escalate_tracking.return_value = after

    r = client.post(
        "/api/v1/sla-management/conversation-sla-tracking/integration/escalate",
        json={
            "respond_contact_id": "contact-1",
            "policy_id": "policy-1",
            "current_tier": 3,
            "escalation_reason": "SLA breached",
        },
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["escalated"] is True
    assert data["from_tier"] == 1
    assert data["to_tier"] == 3
