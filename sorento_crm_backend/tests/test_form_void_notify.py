"""Form void — notifications (UAC NTF-1..NTF-5).

NTF-1: current assignee gets an in-app notification.
NTF-2: handling-lock holder (handled_by_id) also gets in-app (skipped when unset).
NTF-3: the salesperson (respond_contact_id) gets a WhatsApp via the existing
       send_text_or_template choke point (which writes integration_log on
       success AND failure — same path as process/close).
NTF-4: NO WhatsApp/comment egress to anyone but the salesperson — assignee +
       handler get in-app ONLY (send_whatsapp=False).
NTF-5: notifications are best-effort — a notify failure never rolls back the void.

Leaf choke points are stubbed so the test does zero real egress; the recorded
calls prove targeting + channel scoping.

Run: venv/bin/pytest tests/test_form_void_notify.py -q
"""
from __future__ import annotations

import pytest

from app.services.procurement_service import PurchaseRequestService
import tests._void_harness as H


@pytest.fixture
def db():
    s = H.make_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def recorder(monkeypatch):
    """Stub the two leaf egress choke points and record every call."""
    rec = {"in_app": [], "wa": []}

    from app.services.notification_service import NotificationService

    def _in_app(self, user_id, **kw):
        rec["in_app"].append({"user_id": str(user_id), **kw})
        return None

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _in_app)

    def _send(self, header, *, message_text, **kw):
        rec["wa"].append({"business_id": str(header.id), "message_text": message_text})
        return None

    monkeypatch.setattr(PurchaseRequestService, "_send_purchase_request_contact_message", _send)
    return rec


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    H.ACTOR_GRANTS.clear()
    from app.main import app
    app.dependency_overrides.clear()


def _seed(db, *, handler=False):
    actor = H.new_user(db, name="Voider")
    assignee = H.new_user(db, name="Assignee")
    handler_id = H.new_user(db, name="Handler") if handler else None
    policy = H.new_policy(db)
    pid = H.new_pr(db, status="approved")
    H.new_tracker(db, source_entity_type="purchase_request", source_entity_id=pid,
                  policy_id=policy, assigned_to_id=assignee, handled_by_id=handler_id,
                  is_resolved=False)
    return actor, assignee, handler_id, pid


# --------------------------------------------------------------------------- #
# NTF-1 / NTF-4 — assignee in-app; no WhatsApp to the assignee
# --------------------------------------------------------------------------- #
def test_assignee_in_app_only(db, recorder):
    actor, assignee, _, pid = _seed(db, handler=False)
    PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)

    in_app_users = {c["user_id"] for c in recorder["in_app"]}
    assert assignee in in_app_users
    # every in-app notify is WhatsApp-off (NTF-4)
    assert all(c.get("send_whatsapp") is False for c in recorder["in_app"])
    # exactly one WhatsApp egress, and it's the salesperson (the form), not the assignee
    assert len(recorder["wa"]) == 1
    assert recorder["wa"][0]["business_id"] == pid


# --------------------------------------------------------------------------- #
# NTF-2 — handling-lock holder also notified (and skipped cleanly when unset)
# --------------------------------------------------------------------------- #
def test_handler_notified_when_set(db, recorder):
    actor, assignee, handler_id, pid = _seed(db, handler=True)
    PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)
    in_app_users = {c["user_id"] for c in recorder["in_app"]}
    assert assignee in in_app_users
    assert handler_id in in_app_users


def test_handler_absent_only_assignee(db, recorder):
    actor, assignee, _, pid = _seed(db, handler=False)
    PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)
    in_app_users = [c["user_id"] for c in recorder["in_app"]]
    assert in_app_users == [assignee]  # only the assignee, no phantom handler entry


# --------------------------------------------------------------------------- #
# NTF-3 / NTF-4 — salesperson WhatsApp fires; it is the ONLY WhatsApp egress
# --------------------------------------------------------------------------- #
def test_salesperson_whatsapp_is_only_egress(db, recorder):
    actor, assignee, handler_id, pid = _seed(db, handler=True)
    PurchaseRequestService(db).void_request(pid, void_reason="created twice", actor_user_id=actor)
    assert len(recorder["wa"]) == 1                       # exactly one WhatsApp send
    assert "voided" in recorder["wa"][0]["message_text"].lower()
    assert "created twice" in recorder["wa"][0]["message_text"]
    # assignee + handler received in-app, never WhatsApp
    assert all(c.get("send_whatsapp") is False for c in recorder["in_app"])


# --------------------------------------------------------------------------- #
# NTF-5 — best-effort: a notify failure does not roll back the void
# --------------------------------------------------------------------------- #
def test_notify_failure_does_not_rollback(db, monkeypatch):
    from app.services.notification_service import NotificationService

    def _boom(self, user_id, **kw):
        raise RuntimeError("notification backend down")

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _boom)
    # also make the salesperson send raise
    monkeypatch.setattr(
        PurchaseRequestService,
        "_send_purchase_request_contact_message",
        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("respond down")),
    )

    actor, assignee, _, pid = _seed(db, handler=False)
    hdr = PurchaseRequestService(db).void_request(pid, void_reason="mistake", actor_user_id=actor)
    assert hdr.status == "voided"  # committed despite notify explosions

    from app.models.procurement import PurchaseRequestHeader as PR
    row = db.query(PR).filter(PR.id == pid).first()
    assert row.status == "voided"
