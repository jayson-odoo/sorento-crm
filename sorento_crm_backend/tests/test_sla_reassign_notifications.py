"""Reassign/takeover notification rules: new always; old only when actor differs."""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.notification_service import NotificationService
from app.services.sla_service import ConversationSLATrackingService


def _svc():
    s = ConversationSLATrackingService.__new__(ConversationSLATrackingService)
    s.db = MagicMock()
    return s


def _tracking():
    return SimpleNamespace(id=str(uuid.uuid4()), due_at=datetime(2026, 6, 1, 14, 0, 0))


def _run_notify(actor, new_assignee, old_assignee):
    svc = _svc()
    svc._resolve_my_pending_references = MagicMock(return_value={})  # type: ignore
    recipients = []
    with patch.object(
        NotificationService, "create_with_channel_preferences",
        side_effect=lambda **kw: recipients.append(kw["user_id"]),
    ), patch("app.services.coverage_subscription_service.fan_out_coverage_copies"):
        svc._notify_reassignment(
            _tracking(),
            actor_id=actor,
            new_assignee_id=new_assignee,
            old_assignee_id=old_assignee,
        )
    return recipients


def test_new_assignee_always_notified():
    recips = _run_notify(actor="mgr", new_assignee="tay", old_assignee="charissa")
    assert "tay" in recips


def test_old_assignee_notified_when_actor_differs():
    recips = _run_notify(actor="mgr", new_assignee="tay", old_assignee="charissa")
    assert "charissa" in recips  # someone else moved Charissa's task


def test_self_reassign_no_self_notify():
    # I (me) reassign my own task to tay -> I am old assignee AND actor -> no "moved" notice.
    recips = _run_notify(actor="me", new_assignee="tay", old_assignee="me")
    assert recips.count("me") == 0
    assert "tay" in recips


def test_takeover_old_assignee_notified_new_is_actor():
    # Peer takes over Charissa's task: actor == new assignee (peer), old == charissa.
    recips = _run_notify(actor="peer", new_assignee="peer", old_assignee="charissa")
    assert "peer" in recips  # new assignee always
    assert "charissa" in recips  # old notified (actor != old)
