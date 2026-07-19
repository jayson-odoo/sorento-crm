"""Form void — SLA tracker stop via config, no bespoke code (UAC SLA-1..SLA-3).

SLA-1: a void emits exactly one emit_form_event(..., 'voided') and the void
       service contains NO direct tracker-stop code (an active tracker is left
       untouched when the SLA emit is a no-op).
SLA-2: with 'voided' listed in the form's form_sla_config.resolve_event, voiding
       closes the active conversation_sla_tracking row (existing orchestrator).
SLA-3 (REGRESSION): with a config that does NOT list 'voided', the void still
       succeeds and the tracker is simply not auto-closed (no crash).

Run: venv/bin/pytest tests/test_form_void_sla_stop.py -q
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.sla import ConversationSLATracking
from app.services.procurement_service import PurchaseRequestService
import tests._void_harness as H


@pytest.fixture
def db():
    s = H.make_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _patches(monkeypatch):
    H.ACTOR_GRANTS.clear()
    # notify is out of scope here; keep it from touching notification infra.
    monkeypatch.setattr(PurchaseRequestService, "_notify_request_voided", lambda self, *a, **k: None)
    yield
    H.ACTOR_GRANTS.clear()
    from app.main import app
    app.dependency_overrides.clear()


def _tracker_row(db, tid):
    return db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()


# --------------------------------------------------------------------------- #
# SLA-1 — exactly one 'voided' emit, and no direct tracker-stop code
# --------------------------------------------------------------------------- #
def test_emits_voided_once_and_no_direct_stop(db):
    actor = H.new_user(db)
    policy = H.new_policy(db)
    pid = H.new_pr(db, status="approved")
    tid = H.new_tracker(db, source_entity_type="purchase_request", source_entity_id=pid,
                        policy_id=policy, assigned_to_id=actor, is_resolved=False)

    with patch("app.services.form_sla_service.emit_form_event") as spy:
        PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)

    assert spy.call_count == 1
    args, kwargs = spy.call_args
    assert args[3] == "voided"  # (db, source_entity_type, source_entity_id, event_name)
    assert args[1] == "purchase_request"
    # No bespoke stop: with the SLA emit stubbed out, the tracker is untouched.
    assert _tracker_row(db, tid).is_resolved is False


# --------------------------------------------------------------------------- #
# SLA-2 — config lists 'voided' -> active tracker is closed by the orchestrator
# --------------------------------------------------------------------------- #
def test_config_voided_closes_tracker(db):
    actor = H.new_user(db)
    policy = H.new_policy(db)
    pid = H.new_pr(db, status="approved")
    H.new_config(db, source_entity_type="purchase_request", resolve_event="approved,voided", policy_id=policy)
    tid = H.new_tracker(db, source_entity_type="purchase_request", source_entity_id=pid,
                        policy_id=policy, assigned_to_id=actor, is_resolved=False)

    PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)

    row = _tracker_row(db, tid)
    assert row.is_resolved is True  # tracker closed via config-driven resolve_event


# --------------------------------------------------------------------------- #
# SLA-3 — config does NOT list 'voided' -> void still succeeds, tracker open
# --------------------------------------------------------------------------- #
def test_config_without_voided_still_voids(db):
    actor = H.new_user(db)
    policy = H.new_policy(db)
    pid = H.new_pr(db, status="approved")
    H.new_config(db, source_entity_type="purchase_request", resolve_event="resolved", policy_id=policy)
    tid = H.new_tracker(db, source_entity_type="purchase_request", source_entity_id=pid,
                        policy_id=policy, assigned_to_id=actor, is_resolved=False)

    hdr = PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)

    assert hdr.status == "voided"                       # void itself succeeds
    assert _tracker_row(db, tid).is_resolved is False   # tracker NOT auto-closed
