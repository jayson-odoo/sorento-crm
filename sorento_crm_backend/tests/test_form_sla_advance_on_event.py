"""Regression: a stage advances to its next stage only on advance_on_event.

So a complaint stage that resolves on 'approved,rejected' but has
advance_on_event='approved' spawns the customer-service stage on approval only  - 
rejection closes the stage without advancing.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.form_sla_service import FormSLAOrchestrator


def _orch_with_next():
    db = MagicMock()
    orch = FormSLAOrchestrator(db)
    next_cfg = SimpleNamespace(id="next-1", is_active=True, stage_code="customer_service")
    # next_config lookup returns the active next stage.
    db.query.return_value.filter.return_value.first.return_value = next_cfg
    return orch, db


def _config(advance_on_event):
    return SimpleNamespace(
        id="stage-1",
        next_config_id="next-1",
        advance_on_event=advance_on_event,
        resolve_event="approved,rejected",
    )


def _run(advance_on_event, resolve_event):
    orch, _ = _orch_with_next()
    tracker = SimpleNamespace(id="t1", is_resolved=False, is_responded=False, respond_contact_id=None)
    with patch.object(orch, "_active_tracker", return_value=tracker), \
         patch.object(orch, "_start_for_config") as start_spy, \
         patch("app.services.sla_service.ConversationSLATrackingService"):
        orch._resolve_for_active(
            _config(advance_on_event), "entity-1", resolve_event=resolve_event
        )
    return start_spy


def test_advances_on_matching_event():
    spy = _run("approved", "approved")
    assert spy.called  # customer-service stage spawned


def test_does_not_advance_on_other_event():
    spy = _run("approved", "rejected")
    assert not spy.called  # rejected closes stage without advancing


def test_null_advance_spawns_on_any_event():
    spy = _run(None, "rejected")
    assert spy.called  # backward-compatible: no guard -> advance on any resolve
