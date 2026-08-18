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


def test_derive_multiple_tier1_teams_is_ambiguous(caplog):
    """Invariant-violating config (user in two tier-1-linked TEAMS), NO usable team-set
    context: new contract is a deterministic fallback (first (code, agent_id) link),
    logged as a warning - never a silent None. Aborting derivation entirely would leave
    the tracking unrouted, which is worse than a documented, logged best guess."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_a", "team-a1"),
            _link("agent-b", "set_b", "team-b1"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    with caplog.at_level("WARNING"):
        derived = service.derive_team_for_assignee("user-x")

    assert derived == {
        "agent_id": "agent-a",
        "team_set_code": "set_a",
        "tier": 1,
        "team_id": "team-a1",
    }
    assert any("ambiguous" in r.getMessage() for r in caplog.records)


def test_derive_team_set_context_selects_matching_set():
    """User tier-1 in two DIFFERENT team sets; the tracking's team-set context alone
    (current_agent_id matching neither link) picks the link in that set."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_a", "team-a1"),
            _link("agent-b", "set_b", "team-b1"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee(
        "user-x", current_agent_id="agent-x", current_team_set_code="set_b"
    )

    assert derived == {
        "agent_id": "agent-b",
        "team_set_code": "set_b",
        "tier": 1,
        "team_id": "team-b1",
    }


def test_derive_team_set_context_shared_pool_prefers_current_agent():
    """Within the matched team set there are two agent links for the SAME team (shared
    pool) - current_agent_id disambiguates among them, same as the no-context shared-pool
    case, but scoped by team-set context first."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_b", "team-shared"),
            _link("agent-b", "set_b", "team-shared"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    derived = service.derive_team_for_assignee(
        "user-x", current_agent_id="agent-b", current_team_set_code="set_b"
    )

    assert derived == {
        "agent_id": "agent-b",
        "team_set_code": "set_b",
        "tier": 1,
        "team_id": "team-shared",
    }


def test_derive_fallback_no_context_prefers_current_agent(caplog):
    """Dual-set tier-1 membership, no usable team-set context (code matches nothing):
    fallback prefers the link matching current_agent_id over the deterministic first
    link, and the ambiguity is still logged."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_a", "team-a1"),
            _link("agent-b", "set_b", "team-b1"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    with caplog.at_level("WARNING"):
        derived = service.derive_team_for_assignee(
            "user-x", current_agent_id="agent-b", current_team_set_code="set_x"
        )

    assert derived == {
        "agent_id": "agent-b",
        "team_set_code": "set_b",
        "tier": 1,
        "team_id": "team-b1",
    }
    assert any("ambiguous" in r.getMessage() for r in caplog.records)


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


def test_derive_ambiguous_within_team_set_logs_within_set_wording(caplog):
    """Two DIFFERENT teams share ONE code, and current_team_set_code matches that
    code: restricting to the set still leaves >1 distinct team, which means the
    per-team-set invariant itself is violated (data bug, not missing context) - the
    warning must say so with the 'WITHIN team set' wording, distinct from the
    no-context case below."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_shared", "team-x"),
            _link("agent-b", "set_shared", "team-y"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    with caplog.at_level("WARNING"):
        derived = service.derive_team_for_assignee(
            "user-x", current_team_set_code="set_shared"
        )

    assert derived is not None
    assert derived["team_set_code"] == "set_shared"
    messages = [r.getMessage() for r in caplog.records]
    assert any("WITHIN team set" in m for m in messages)
    assert not any("several team sets" in m for m in messages)


def test_derive_ambiguous_no_context_logs_several_team_sets_wording(caplog):
    """Dual-set tier-1 membership with no team-set context that matches either link:
    the ambiguity is expected (missing/unmatched context, not a data bug), so the
    warning uses the 'several team sets' wording, not 'WITHIN team set'."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[
            _link("agent-a", "set_a", "team-a1"),
            _link("agent-b", "set_b", "team-b1"),
        ]),
    ]
    service = ConversationSLATrackingService(mock_db)

    with caplog.at_level("WARNING"):
        derived = service.derive_team_for_assignee("user-x")

    assert derived is not None
    messages = [r.getMessage() for r in caplog.records]
    assert any("several team sets" in m for m in messages)
    assert not any("WITHIN team set" in m for m in messages)


# ---------------------------------------------------------------------------
# _agent_link_for_user (takeover / reassign tier re-derivation)
# ---------------------------------------------------------------------------


def test_agent_link_for_user_prefers_tracking_team_set():
    """Dual tier-1 membership under one agent (set_p, set_q); passing the tracking's
    own team_set_code='set_q' resolves the code-filtered query directly - no second,
    unfiltered query is needed or issued."""
    mock_db = MagicMock()
    link_q = _link("agent-a", "set_q", "team-q")
    my_teams_chain = _chain(all_result=[("team-p",), ("team-q",)])
    filtered_chain = _chain(first_result=link_q)
    mock_db.query.side_effect = [my_teams_chain, filtered_chain]
    service = ConversationSLATrackingService(mock_db)

    link = service._agent_link_for_user("agent-a", "user-1", team_set_code="set_q")

    assert link is link_q
    assert mock_db.query.call_count == 2  # my_team_ids + the code-filtered query only
    filter_args = [a for call in filtered_chain.filter.call_args_list for a in call.args]
    code_eq = [a for a in filter_args if str(a) == "agent_teams.code = :code_1"]
    assert code_eq and code_eq[0].right.value == "set_q"


def test_agent_link_for_user_falls_back_when_team_set_has_no_link():
    """team_set_code matches none of the user's links (code-filtered query's first()
    is None): falls back to the unfiltered query, and its deterministic result (the
    mock's stand-in for 'lowest code' ordering) is returned."""
    mock_db = MagicMock()
    link_fallback = _link("agent-a", "set_p", "team-p")  # deterministic lowest-code pick
    my_teams_chain = _chain(all_result=[("team-p",), ("team-q",)])
    filtered_chain = _chain(first_result=None)  # 'set_none' matches nothing
    unfiltered_chain = _chain(first_result=link_fallback)
    mock_db.query.side_effect = [my_teams_chain, filtered_chain, unfiltered_chain]
    service = ConversationSLATrackingService(mock_db)

    link = service._agent_link_for_user("agent-a", "user-1", team_set_code="set_none")

    assert link is link_fallback
    assert mock_db.query.call_count == 3  # my_team_ids + filtered miss + unfiltered fallback


def test_agent_link_for_user_no_team_set_code_runs_single_unfiltered_query():
    """team_set_code=None (legacy call shape) runs only the unfiltered query - no
    code-filtered probe at all."""
    mock_db = MagicMock()
    link_fallback = _link("agent-a", "set_p", "team-p")
    my_teams_chain = _chain(all_result=[("team-p",), ("team-q",)])
    unfiltered_chain = _chain(first_result=link_fallback)
    mock_db.query.side_effect = [my_teams_chain, unfiltered_chain]
    service = ConversationSLATrackingService(mock_db)

    link = service._agent_link_for_user("agent-a", "user-1")

    assert link is link_fallback
    assert mock_db.query.call_count == 2  # my_team_ids + the one unfiltered query
    # No code filter reached the query at all.
    filter_args = [a for call in unfiltered_chain.filter.call_args_list for a in call.args]
    assert not any(str(a).startswith("agent_teams.code") for a in filter_args)


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
    # form-codes probe, then new-team tier-1 link probe (.all() → [] → return early)
    mock_db.query.side_effect = [_form_codes(), _chain(all_result=[])]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-x", "user-1")  # no raise


def test_add_member_already_in_other_tier1_team_rejected():
    """New team's own tier-1 link and the user's existing tier-1 link share the SAME
    code (same team set), different team_ids - still a conflict under the per-team-set
    invariant."""
    mock_db = MagicMock()
    new_team_link = _link("agent-b", "set_b", "team-b1")  # new team's own conv tier-1 link
    existing_link = _link("agent-a", "set_b", "team-a1")  # SAME code, different team
    user = MagicMock()
    user.name = "Jane Exec"
    user.email = "jane@test.com"
    agent = MagicMock()
    agent.code = "order_enquiries"
    mock_db.query.side_effect = [
        _form_codes(),                                     # form-SLA agent codes
        _chain(all_result=[new_team_link]),                # new team's conv tier-1 link(s)
        _chain(all_result=[(existing_link, "Team A1")]),    # user's other conv tier-1 links (same code)
        _chain(first_result=user),                          # User
        _chain(first_result=agent),                         # AccessAgent
    ]
    service = TeamService(mock_db)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_tier1_membership_invariant("team-b1", "user-1")
    assert exc_info.value.status_code == 400
    msg = _http_exception_message(exc_info.value)
    assert "Jane Exec" in msg
    assert "Team A1" in msg
    assert "order_enquiries" in msg
    assert "per team set" in msg


def _assert_code_in_filter(chain: MagicMock, codes) -> None:
    """The existing-membership probe must carry an ``AgentTeam.code.in_(codes)``
    clause - a real DB filters on it (the invariant is now scoped per team set);
    a mock's ``.filter()`` no-ops regardless, so without this the test would still
    pass if the code filter were deleted from the source. SQLAlchemy renders
    ``.in_()`` as ``<col> IN (...)`` (verified: str(AgentTeam.code.in_(codes)) ==
    "agent_teams.code IN (__[POSTCOMPILE_code_1])"), so match on the rendered SQL
    text rather than parameter binding."""
    all_args = [arg for call in chain.filter.call_args_list for arg in call.args]
    in_clauses = [a for a in all_args if "agent_teams.code IN" in str(a)]
    assert in_clauses, (
        f"expected an AgentTeam.code IN (...) filter clause, got: {[str(a) for a in all_args]}"
    )
    bound_values = [set(getattr(getattr(c, "right", None), "value", None) or []) for c in in_clauses]
    assert set(codes) in bound_values, (
        f"expected the code filter bound to {set(codes)}, got {bound_values}"
    )


def test_add_member_same_set_passes():
    """User's only tier-1 set is the same (agent, code) as the new team's - allowed.
    Exercises the real path: new-team probe non-empty, existing-membership probe empty."""
    mock_db = MagicMock()
    existing_probe = _chain(all_result=[])  # no OTHER tier-1 membership
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[_link("agent-a", "set_a", "team-a1")]),  # new team conv tier-1 link
        existing_probe,
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-a1", "user-1")  # no raise
    _assert_code_in_filter(existing_probe, {"set_a"})


def test_add_member_to_shared_pool_team_passes():
    """Same team linked at tier 1 under multiple agents (shared pool) - members allowed.
    Exercises the real path: new-team probe non-empty, existing-membership probe empty."""
    mock_db = MagicMock()
    existing_probe = _chain(all_result=[])  # no membership in another tier-1-linked team
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[_link("agent-a", "customer_service", "team-x")]),  # conv tier-1 link
        existing_probe,
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-x", "user-1")  # no raise
    _assert_code_in_filter(existing_probe, {"customer_service"})


def test_add_member_to_form_only_tier1_team_passes():
    """New relaxation: a team linked at tier 1 ONLY under FORM-SLA agents never conflicts.
    The new-team conv-tier-1 probe returns [] (filtered out), so we return early."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes("purchase_request", "complaint"),
        _chain(all_result=[]),  # no CONVERSATION tier-1 link on this team
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
        _chain(all_result=[_link("agent-conv", "set_conv", "team-conv")]),  # new team conv link
        _chain(all_result=[]),  # existing CONVERSATION tier-1 links (form ones excluded) → none
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-conv", "user-1")  # no raise


def test_add_member_cross_team_set_tier1_allowed():
    """Kia Yee scenario: a user already tier-1 in a 'marketing_promotion' team may join
    a NEW tier-1 team in 'marketing_product' under the same agent. The existing-membership
    query is code-filtered to the NEW team's own code(s) (AgentTeam.code.in_(new_codes)),
    so a real DB never even returns the 'marketing_promotion' link to this query - the
    mock's all_result=[] reflects that filtered result, not a client-side exclusion this
    test is asserting on. What this test proves is "no raise" through the full
    new-team-probe (non-empty) -> existing-probe (empty, by construction of the DB
    filter) path. A mock's ``.filter()`` no-ops regardless of its arguments, so without
    inspecting the actual clause that reached the query, deleting the code filter from
    the source (making this query see the 'marketing_promotion' link too) would not
    fail this test - _assert_code_in_filter closes that gap."""
    mock_db = MagicMock()
    existing_probe = _chain(all_result=[])  # code-filtered to 'marketing_product' -> no match
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(all_result=[_link("agent-x", "marketing_product", "team-product")]),
        existing_probe,
    ]
    service = TeamService(mock_db)

    service._validate_tier1_membership_invariant("team-product", "user-kiayee")  # no raise
    _assert_code_in_filter(existing_probe, {"marketing_product"})


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
    """The other link's code equals the payload's code (same team set) - still a
    conflict; a different code would now be legal (see the cross-team-set test)."""
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
        # user's membership in a DIFFERENT tier-1-linked team, SAME code, under another agent
        _chain(all_result=[("user-1", "agent-b", "set_a", "team-b1", "Team B1")]),
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
    assert "per team set" in msg
    # The conflict tuple lost its redundant code field (user_service.py ~2179) -
    # the team set code shown to the caller must still come through, now sourced
    # from the (uid, code) dict key rather than a third tuple element.
    assert "set_a" in msg


def test_set_agent_teams_cross_team_set_allowed():
    """Cross-team-set tier-1 membership is legal in the bulk path too: the user holds an
    existing tier-1 link under a DIFFERENT code (marketing_promotion) than the payload's
    (marketing_product) - conflict_by_user_code only keys on codes the payload also
    assigns the user to, so this link never becomes a conflict."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(first_result=None),                   # this_agent (conversation)
        _chain(all_result=[("team-p", "user-1")]),    # members of team-p (payload)
        _chain(all_result=[
            ("user-1", "agent-y", "marketing_promotion", "team-promo", "Team Promo"),
        ]),                                            # other tier-1 link, different code
        _chain(all_result=[]),                        # no cross-tier reuse
    ]
    service = AccessAgentService(mock_db)

    service._validate_tier1_invariant_for_assignments(
        "agent-x", [{"code": "marketing_product", "team_id": "team-p", "tier": 1}]
    )  # no raise


def test_set_agent_teams_local_same_code_conflict_rejected():
    """Two tier-1 assignments in ONE payload sharing the same code, with the same user
    a member of both teams, conflicts LOCALLY (no cross-agent link needed)."""
    mock_db = MagicMock()
    user = MagicMock()
    user.name = "Sam Multi"
    user.email = "sam@test.com"
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(first_result=None),  # this_agent (conversation)
        _chain(all_result=[
            ("team-1", "user-1"),
            ("team-2", "user-1"),
        ]),                          # members of both payload teams
        _chain(all_result=[]),       # no OTHER (cross-agent) tier-1 links
        _chain(first_result=user),
    ]
    service = AccessAgentService(mock_db)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_tier1_invariant_for_assignments(
            "agent-a",
            [
                {"code": "set_a", "team_id": "team-1", "tier": 1},
                {"code": "set_a", "team_id": "team-2", "tier": 1},
            ],
        )
    msg = _http_exception_message(exc_info.value)
    assert "Sam Multi" in msg
    assert "set_a" in msg
    assert "per team set" in msg


def test_set_agent_teams_local_cross_code_multi_team_allowed():
    """Same user in two payload teams under DIFFERENT codes: cross-code multi-team
    tier-1 membership is legal (each code's local team set has at most one team)."""
    mock_db = MagicMock()
    mock_db.query.side_effect = [
        _form_codes(),
        _chain(first_result=None),  # this_agent (conversation)
        _chain(all_result=[
            ("team-1", "user-1"),
            ("team-2", "user-1"),
        ]),                          # members of both payload teams
        _chain(all_result=[]),       # no OTHER tier-1 links
        _chain(all_result=[]),       # no cross-tier reuse
    ]
    service = AccessAgentService(mock_db)

    service._validate_tier1_invariant_for_assignments(
        "agent-a",
        [
            {"code": "set_a", "team_id": "team-1", "tier": 1},
            {"code": "set_b", "team_id": "team-2", "tier": 1},
        ],
    )  # no raise


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
