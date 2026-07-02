"""Regression: form-SLA auto-escalation respects the split-clock rule.

Bug (CMP26-0035): scan_overdue_and_escalate ORed the response clock (due_at) with
no is_responded guard, so a responded-on-time tracker whose response deadline had
since lapsed kept escalating — even after an extend pushed only due_at_resolution
into the future. Fix: post-response, gate on due_at_resolution only (mirrors the
conversation-SLA list_due_escalations rule). Manual escalation stays ungated.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.form_sla_service import FormSLAOrchestrator, _utc_naive_now


def _tracker(*, is_responded, due_off, res_off, tier=1, s_type="complaint"):
    now = _utc_naive_now()
    return SimpleNamespace(
        id="t-1",
        is_resolved=False,
        is_responded=is_responded,
        due_at=(now + timedelta(days=due_off)) if due_off is not None else None,
        due_at_resolution=(now + timedelta(days=res_off)) if res_off is not None else None,
        current_tier=tier,
        source_entity_type=s_type,
    )


def _run_scan(tracker):
    """Drive the real scan loop with one candidate; spy on _escalate_tracker."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [tracker]
    orch = FormSLAOrchestrator(db)
    with patch.object(orch, "_escalate_tracker") as esc_spy:
        orch.scan_overdue_and_escalate()
    return esc_spy


# UAC-1: responded, response due lapsed, resolution still future -> NOT escalated.
def test_responded_response_lapsed_resolution_future_does_not_escalate():
    spy = _run_scan(_tracker(is_responded=True, due_off=-2, res_off=+4))
    assert not spy.called


# UAC-2: responded, resolution due lapsed -> escalates.
def test_responded_resolution_overdue_escalates():
    spy = _run_scan(_tracker(is_responded=True, due_off=-2, res_off=-1))
    assert spy.called


# UAC-3: not responded, response due lapsed -> escalates (unchanged).
def test_not_responded_response_overdue_escalates():
    spy = _run_scan(_tracker(is_responded=False, due_off=-2, res_off=+4))
    assert spy.called


# Negative control: not responded, nothing overdue -> does NOT escalate.
def test_not_responded_nothing_overdue_does_not_escalate():
    spy = _run_scan(_tracker(is_responded=False, due_off=+2, res_off=+4))
    assert not spy.called


# Not responded, resolution already past (response still future) -> escalates.
def test_not_responded_resolution_overdue_escalates():
    spy = _run_scan(_tracker(is_responded=False, due_off=+2, res_off=-1))
    assert spy.called


# UAC-4: gate is type-agnostic — the bug scenario must not escalate for ANY form type.
@pytest.mark.parametrize(
    "s_type",
    ["complaint", "purchase_request", "stock_inquiry", "sponsorship_form", "ticket"],
)
def test_responded_bug_scenario_not_escalated_all_form_types(s_type):
    spy = _run_scan(
        _tracker(is_responded=True, due_off=-2, res_off=+4, s_type=s_type)
    )
    assert not spy.called


# UAC-9: responded, resolution due NULL, response lapsed -> no escalate, no crash.
def test_responded_null_resolution_does_not_escalate_or_crash():
    spy = _run_scan(_tracker(is_responded=True, due_off=-2, res_off=None))
    assert not spy.called


# UAC-10: manual escalation stays ungated — a responded, non-breached tracker still
# force-escalates (pre-breach manual escalate is a feature).
def test_manual_escalate_ungated_for_responded_tracker():
    now = _utc_naive_now()
    tracker = _tracker(is_responded=True, due_off=+2, res_off=+2)  # nothing overdue
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = tracker
    orch = FormSLAOrchestrator(db)
    with patch.object(orch, "_escalate_tracker") as esc_spy, patch(
        "app.services.sla_takeover_service.SlaTakeoverService"
    ):
        orch.escalate_form_tracking("t-1", reason="need eyes now")
    assert esc_spy.called


# --- Fix 2: event-log datetimes must be written as timezone-aware UTC ---
# create_event_log treats NAIVE datetimes as Malaysia time (UTC+8); _write_event_log
# must wrap event_at / due_at in _to_aware_utc or they land shifted -8h.
def _captured_event_log_payload(due_at):
    from datetime import datetime as _dt

    db = MagicMock()
    orch = FormSLAOrchestrator(db)
    with patch(
        "app.services.sla_service.ConversationSLATrackingService"
    ) as svc_cls:
        orch._write_event_log(
            tracker_id="t-1", event_type="escalation", due_at=due_at
        )
    return svc_cls.return_value.create_event_log.call_args.args[0]


def test_write_event_log_event_at_is_aware_utc():
    payload = _captured_event_log_payload(due_at=None)
    assert payload.event_at.tzinfo is not None, "event_at must be tz-aware (else -8h shift)"
    assert payload.event_at.utcoffset().total_seconds() == 0  # true UTC, not MYT


def test_write_event_log_due_at_is_aware_utc_when_present():
    from datetime import datetime as _dt

    payload = _captured_event_log_payload(due_at=_dt(2026, 7, 6, 4, 0, 0))  # naive UTC
    assert payload.due_at.tzinfo is not None
    assert payload.due_at.utcoffset().total_seconds() == 0


def test_write_event_log_due_at_none_passes_through():
    payload = _captured_event_log_payload(due_at=None)
    assert payload.due_at is None  # no crash, stays None
