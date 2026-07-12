"""Rich auto-escalation reason: WHO missed WHICH action by WHEN, stage-aware.

Covers the split-clock → per-stage action verb mapping added so the escalation
banner reads e.g. "CK Lee did not approve or reject by … (resolution overdue)"
instead of the ambiguous "Response/resolution overdue".
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.form_sla_service import (
    FormSLAOrchestrator,
    _stage_action_verb,
)


NOW = datetime(2026, 7, 10, 9, 0, 0)
PAST = NOW - timedelta(hours=2)


def _tracker(entity, team, *, responded, due=PAST, due_reso=PAST):
    # assigned_to_id=None so _build_overdue_reason skips the User lookup (DB-free).
    return SimpleNamespace(
        source_entity_type=entity,
        team_set_code=team,
        is_responded=responded,
        due_at=due,
        due_at_resolution=due_reso,
        assigned_to_id=None,
    )


def _reason(tracker):
    # DB is only touched when assigned_to_id is set; pass None so we can use a plain object.
    svc = FormSLAOrchestrator.__new__(FormSLAOrchestrator)
    svc.db = None
    return svc._build_overdue_reason(tracker, NOW)


def test_stage_action_verb_falls_back_to_resolution_when_no_response_action():
    # PR project_sales has only a resolution action → both clocks map to it.
    assert _stage_action_verb("purchase_request", "project_sales", "response") == (
        "send the request for approval"
    )
    assert _stage_action_verb("purchase_request", "project_sales", "resolution") == (
        "send the request for approval"
    )


def test_stage_action_verb_unknown_stage_is_none():
    assert _stage_action_verb("complaint", "no_such_team", "resolution") is None


def test_complaint_response_breach_names_technical_response():
    r = _reason(_tracker("complaint", "complaint", responded=False))
    assert "submit the technical team response" in r
    assert "(response overdue)" in r
    assert "The assignee did not" in r  # no assigned user → generic subject


def test_complaint_resolution_breach_after_responded_says_approve_or_reject():
    r = _reason(_tracker("complaint", "complaint", responded=True))
    assert "approve or reject" in r
    assert "(resolution overdue)" in r


def test_same_action_stage_maps_any_breach_to_resolution():
    # stock_inquiry project_sales: single action = approve(send to purchasing)/reject.
    r = _reason(_tracker("stock_inquiry", "project_sales", responded=False))
    assert "approve (send to purchasing) or reject" in r
    assert "(resolution overdue)" in r


def test_purchasing_stage_response_breach_says_purchasing_response():
    r = _reason(_tracker("stock_inquiry", "purchasing", responded=False))
    assert "send the purchasing response" in r
    assert "(response overdue)" in r


def test_cs_stage_says_process():
    r = _reason(_tracker("purchase_request", "customer_service", responded=False))
    assert "process the request (CS)" in r


def test_due_timestamp_included():
    # _fmt_due renders the naive-UTC due in KL wall time (+8h); assert the date + "by".
    r = _reason(_tracker("complaint", "complaint", responded=True))
    assert "by 10 Jul 2026," in r


def test_unmapped_stage_uses_generic_verb():
    r = _reason(_tracker("complaint", "mystery_team", responded=True))
    assert "act on this form" in r
