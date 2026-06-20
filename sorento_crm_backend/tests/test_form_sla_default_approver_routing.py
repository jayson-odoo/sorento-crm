"""Default-approver routing for the PR/SF approval SLA stage.

When a form's configured default approver is a member of the approval team set,
the approval stage routes to them at THEIR tier (e.g. a director at tier 3),
instead of tier-1 round-robin.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.form_sla_service import FormSLAOrchestrator
from app.services.user_service import AccessAgentService


def _orch():
    o = FormSLAOrchestrator.__new__(FormSLAOrchestrator)
    o.db = MagicMock()
    return o


def test_is_approval_stage_only_for_pr_sf_approved_resolve():
    assert FormSLAOrchestrator._is_approval_stage(
        SimpleNamespace(source_entity_type="purchase_request", resolve_event="approved,approval_rejected")
    )
    assert FormSLAOrchestrator._is_approval_stage(
        SimpleNamespace(source_entity_type="sponsorship_form", resolve_event="approved,reject_submitted")
    )
    # CS stage resolves on 'resolved' -> not the approval stage.
    assert not FormSLAOrchestrator._is_approval_stage(
        SimpleNamespace(source_entity_type="purchase_request", resolve_event="resolved")
    )
    # complaint is not a PR/SF approval.
    assert not FormSLAOrchestrator._is_approval_stage(
        SimpleNamespace(source_entity_type="complaint", resolve_event="approved,rejected")
    )


def test_default_approver_user_id_reads_correct_setting():
    o = _orch()
    settings = SimpleNamespace(
        purchase_request_default_approver_user_id="pr-approver",
        sponsorship_form_default_approver_user_id="sf-approver",
    )
    o.db.query.return_value.first.return_value = settings
    assert o._form_default_approver_user_id("purchase_request") == "pr-approver"
    assert o._form_default_approver_user_id("sponsorship_form") == "sf-approver"
    assert o._form_default_approver_user_id("complaint") is None


def test_resolve_team_with_tier_fallback_skips_missing_tiers():
    svc = AccessAgentService.__new__(AccessAgentService)
    svc.db = MagicMock()
    # tier 1 has no team; tier 2 + 3 do.
    svc.get_team_id_by_tier = MagicMock(  # type: ignore[attr-defined]
        side_effect=lambda a, t, team_set_code=None: {2: "teamB", 3: "teamC"}.get(t)
    )
    # assign starting at tier 1 -> falls back to tier 2
    assert svc.resolve_team_with_tier_fallback("a", 1, "set") == ("teamB", 2)
    # escalate to tier 2 -> tier 2 exists
    assert svc.resolve_team_with_tier_fallback("a", 2, "set") == ("teamB", 2)
    # escalate to tier 3 -> tier 3
    assert svc.resolve_team_with_tier_fallback("a", 3, "set") == ("teamC", 3)
    # start below 1 is clamped to 1
    assert svc.resolve_team_with_tier_fallback("a", 0, "set") == ("teamB", 2)


def test_resolve_team_with_tier_fallback_none_when_no_team():
    svc = AccessAgentService.__new__(AccessAgentService)
    svc.db = MagicMock()
    svc.get_team_id_by_tier = MagicMock(return_value=None)  # type: ignore[attr-defined]
    assert svc.resolve_team_with_tier_fallback("a", 1, "set") is None


def test_get_user_tier_in_team_set_finds_member_tier():
    svc = AccessAgentService.__new__(AccessAgentService)
    svc.db = MagicMock()
    # tier 1 -> team A (no member), tier 2 -> team B (member), tier 3 -> team C
    def team_by_tier(agent_id, tier, team_set_code=None):
        return {1: "teamA", 2: "teamB", 3: "teamC"}.get(tier)
    svc.get_team_id_by_tier = MagicMock(side_effect=team_by_tier)  # type: ignore[attr-defined]

    def member_query(team_id, user_id):
        # user is a member of teamB (tier 2) only
        return SimpleNamespace() if team_id == "teamB" else None

    def _query(_model):
        m = MagicMock()
        def _filter(*args, **kwargs):
            # crude: inspect the bound team_id via closure isn't available; emulate
            # by tracking call order through get_team_id_by_tier instead.
            return m
        m.filter.return_value = m
        return m

    # Simpler: patch the membership lookup directly via db.query(...).filter(...).first()
    calls = {"tier": 0}
    def query_side_effect(_model):
        q = MagicMock()
        def filter_side_effect(*a, **k):
            calls["tier"] += 1
            r = MagicMock()
            # 1st filter call = tier1 teamA -> None, 2nd = tier2 teamB -> member
            r.first.return_value = SimpleNamespace() if calls["tier"] == 2 else None
            return r
        q.filter.side_effect = filter_side_effect
        return q
    svc.db.query.side_effect = query_side_effect

    assert svc.get_user_tier_in_team_set("agent", "ck", team_set_code="project_sales_manager") == 2
