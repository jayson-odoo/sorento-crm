"""Resolve closes the Respond.io conversation (best-effort).

These exercise the helper directly with a mocked DB/client so they don't need a
full SLA tracking DB fixture: resolving a conversation SLA must call
RespondClient.close_conversation with the contact's respond_io_id, and any
Respond failure must be swallowed (the resolve already committed).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.sla_service import ConversationSLATrackingService


def _service() -> ConversationSLATrackingService:
    svc = ConversationSLATrackingService.__new__(ConversationSLATrackingService)
    svc.db = MagicMock()
    return svc


def test_close_uses_contact_respond_io_id():
    svc = _service()
    tracking = SimpleNamespace(
        id="t1",
        respond_contact_id="internal-uuid",
        contact=SimpleNamespace(respond_io_id="888"),
    )
    fake_client = MagicMock()
    with patch(
        "app.services.integration_service.RespondClient.for_contact_id",
        return_value=fake_client,
    ) as for_contact:
        svc._close_respond_conversation_best_effort(tracking)

    for_contact.assert_called_once_with(svc.db, "internal-uuid")
    fake_client.close_conversation.assert_called_once()
    # respond_io_id (not the internal respond_contact_id) is what is sent.
    assert fake_client.close_conversation.call_args.args[0] == "888"


def test_close_failure_is_swallowed():
    svc = _service()
    tracking = SimpleNamespace(
        id="t2",
        respond_contact_id="internal-uuid",
        contact=SimpleNamespace(respond_io_id="888"),
    )
    fake_client = MagicMock()
    fake_client.close_conversation.side_effect = RuntimeError("respond 4xx")
    with patch(
        "app.services.integration_service.RespondClient.for_contact_id",
        return_value=fake_client,
    ):
        # Must not raise.
        svc._close_respond_conversation_best_effort(tracking)


def test_close_skips_when_no_respond_io_id():
    svc = _service()
    svc.db.query.return_value.filter.return_value.first.return_value = None
    tracking = SimpleNamespace(id="t3", respond_contact_id=None, contact=None)
    with patch(
        "app.services.integration_service.RespondClient.for_contact_id",
    ) as for_contact:
        svc._close_respond_conversation_best_effort(tracking)
    for_contact.assert_not_called()
