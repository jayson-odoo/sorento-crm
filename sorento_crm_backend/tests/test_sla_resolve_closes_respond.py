"""Resolve enqueues the Respond.io conversation close (async + outbox-logged).

The actual Respond call + its integration_log now run on the ``respond_io`` worker
queue (see PLAN-respond-sla-actions-async-logged.md). The service helper just
enqueues; the task behaviour (close call + success/failure outbox row) is covered in
test_respond_conversation_tasks.py.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.sla_service import ConversationSLATrackingService


def _service() -> ConversationSLATrackingService:
    svc = ConversationSLATrackingService.__new__(ConversationSLATrackingService)
    svc.db = MagicMock()
    return svc


def test_resolve_enqueues_close_with_tracking_id():
    svc = _service()
    tracking = SimpleNamespace(id="t1", respond_contact_id="internal-uuid")
    with patch("app.services.queue_service.enqueue_job") as enqueue:
        svc._close_respond_conversation_best_effort(tracking)
    enqueue.assert_called_once()
    # task fn + the tracking id, on the respond_io queue.
    assert enqueue.call_args.args[0].__name__ == "close_respond_conversation"
    assert enqueue.call_args.args[1] == "t1"
    assert enqueue.call_args.kwargs["queue_name"] == "respond_io"


def test_resolve_enqueue_failure_is_swallowed():
    svc = _service()
    tracking = SimpleNamespace(id="t2", respond_contact_id="internal-uuid")
    with patch("app.services.queue_service.enqueue_job", side_effect=RuntimeError("redis down")):
        # Must not raise — the resolve already committed.
        svc._close_respond_conversation_best_effort(tracking)
