"""Every Respond.io send leaves an outbox row - including the synchronous ones.

Most sends go through `respond_io_tasks._send_and_log`, which writes an
`integration_logs` row on success and failure. Two synchronous paths called
`RespondClient.send_message` directly and logged nothing at all:

  * `PortalService.send_link_via_respond_io` - portal link delivery
  * `ConversationSLATrackingService.send_conversation_reply_for_tracking` - 
    the SLA conversation reply

Local dev runs with deliberately-wrong Respond credentials, so those sends 401
every time. With no outbox row the failure was invisible: the admin saw an
error, and the Respond outbox - the place you go to find out what happened - 
stayed empty.

These tests pin that both paths now log on BOTH outcomes. They assert on the
call to `log_respond_send` rather than on rows, because the two services reach
it through different sessions; `test_log_respond_send_*` covers the row-shaping
itself.

Run: pytest tests/test_respond_outbox_no_bypass.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest


class _Boom(Exception):
    """Stands in for an httpx error carrying Respond's response."""

    def __init__(self):
        super().__init__("401 Unauthorized")
        self.response = MagicMock(status_code=401, text='{"message":"Unauthorized"}')


# --------------------------------------------------------------------------
# log_respond_send itself: does it shape success vs failure rows correctly?
# --------------------------------------------------------------------------

def _capture_log(fn, **kwargs):
    """Run log_respond_send with the log service mocked; return the payload."""
    from app.services import integration_service

    with patch.object(integration_service, "IntegrationLogService") as svc:
        fn(MagicMock(), **kwargs)
        assert svc.return_value.create_integration_log.called
        call = svc.return_value.create_integration_log.call_args
        return call.args[0], call.kwargs.get("request_payload_dict")


def test_log_respond_send_marks_success():
    from app.services.integration_service import log_respond_send

    payload = {"message": {"type": "text", "text": "hi"}}
    log, sent = _capture_log(
        log_respond_send,
        business_table="portal_tokens",
        business_id=str(uuid.uuid4()),
        identifier="12345",
        request_payload=payload,
        response={"id": "m1"},
    )
    assert log.status == "success"
    assert log.integration_channel == "respond_io"
    assert sent == payload


def test_log_respond_send_records_failure_with_status_and_body():
    from app.services.integration_service import log_respond_send

    log, _ = _capture_log(
        log_respond_send,
        business_table="conversation_sla_tracking",
        business_id=str(uuid.uuid4()),
        identifier="12345",
        request_payload={"message": {"type": "text", "text": "hi"}},
        exc=_Boom(),
    )
    assert log.status == "failed"
    assert log.status_code == 401, "Respond's real HTTP status must be captured"
    assert "Unauthorized" in (log.response_payload or ""), "response body must be kept"
    assert "401" in (log.error_message or "")


def test_log_respond_send_prefers_the_payload_actually_attempted():
    """`_attach_send_context` stamps the real attempt (text vs template) on the
    exception. A closed-window failure must log the TEMPLATE it really tried."""
    from app.services.integration_service import log_respond_send

    exc = _Boom()
    exc.request_payload = {"message": {"type": "template", "template": "portal_otp"}}

    _, sent = _capture_log(
        log_respond_send,
        business_table="portal_tokens",
        business_id=str(uuid.uuid4()),
        identifier="12345",
        request_payload={"message": {"type": "text", "text": "default"}},
        exc=exc,
    )
    assert sent["message"]["type"] == "template", (
        "logged the default text payload instead of the template that was "
        "actually attempted"
    )


def test_log_respond_send_never_raises():
    """Outbox logging must not be the reason a send fails."""
    from app.services import integration_service

    with patch.object(
        integration_service, "IntegrationLogService", side_effect=RuntimeError("db down")
    ):
        integration_service.log_respond_send(
            MagicMock(),
            business_table="portal_tokens",
            business_id=str(uuid.uuid4()),
            identifier="1",
            request_payload={},
        )  # must not raise


# --------------------------------------------------------------------------
# The two call sites that used to bypass logging entirely
# --------------------------------------------------------------------------

def _portal_service():
    from app.services.portal_service import PortalService

    svc = PortalService(MagicMock())
    contact = MagicMock(id=str(uuid.uuid4()), respond_io_id="998877", name="Tester")
    token = MagicMock(id=uuid.uuid4(), token="t" * 64)
    token.expires_at.strftime.return_value = "Jul 30, 2026"
    token.expires_at.isoformat.return_value = "2026-07-30T00:00:00"
    svc._resolve_contact = MagicMock(return_value=contact)
    svc.get_or_mint_token = MagicMock(return_value=(token, False))
    svc.build_portal_url = MagicMock(return_value="http://portal/x")
    return svc


@pytest.mark.parametrize("fails", [False, True])
def test_portal_link_send_is_logged(fails):
    from app.services import portal_service as mod

    svc = _portal_service()
    client = MagicMock()
    client.send_message.side_effect = _Boom() if fails else (lambda *a, **k: {"id": "m1"})

    with patch.object(mod, "RespondClient", return_value=client), patch(
        "app.services.integration_service.log_respond_send"
    ) as log:
        if fails:
            with pytest.raises(Exception):
                svc.send_link_via_respond_io("c1", "364817")
        else:
            svc.send_link_via_respond_io("c1", "364817")

    assert log.called, (
        "portal link send wrote no Respond outbox row "
        f"({'failure' if fails else 'success'} path)"
    )
    assert log.call_args.kwargs["business_table"] == "portal_tokens"
    assert (log.call_args.kwargs.get("exc") is not None) is fails


@pytest.mark.parametrize("fails", [False, True])
def test_sla_conversation_reply_is_logged(fails):
    from app.services import sla_service as mod

    svc = mod.ConversationSLATrackingService(MagicMock())
    svc.get_tracking = MagicMock(return_value=MagicMock())
    svc._respond_io_identifier_for_tracking = MagicMock(return_value="998877")

    client = MagicMock()
    client.send_message.side_effect = _Boom() if fails else (lambda *a, **k: {"id": "m1"})
    tid = str(uuid.uuid4())

    with patch("app.services.integration_service.RespondClient", return_value=client), \
            patch("app.services.integration_service.log_respond_send") as log, \
            patch("app.services.crm_chat_outbound_webhook.enqueue_crm_chat_outbound_webhook"), \
            patch(
                "app.services.crm_chat_outbound_webhook.resolve_assignee_respond_user_id_from_tracking",
                return_value=None,
            ):
        if fails:
            with pytest.raises(Exception):
                svc.send_conversation_reply_for_tracking(tid, "hello", respond_user_id="u1")
        else:
            svc.send_conversation_reply_for_tracking(tid, "hello", respond_user_id="u1")

    assert log.called, (
        "SLA conversation reply wrote no Respond outbox row "
        f"({'failure' if fails else 'success'} path)"
    )
    assert log.call_args.kwargs["business_table"] == "conversation_sla_tracking"
    assert (log.call_args.kwargs.get("exc") is not None) is fails
