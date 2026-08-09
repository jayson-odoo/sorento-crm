"""Every WhatsApp notification send writes a respond_io outbox log.

Local testing runs with intentionally-wrong Respond creds, so a 401'd send MUST
still produce an integration_log row (not just flip the delivery to failed) —
same as the complaint / OTP / SLA-escalation paths via `_send_and_log`.

**This file holds the NO-ENTITY branch of the business-key contract.** A batched
or periodic notification (a digest, a daily summary) is about nothing but itself:
`_split_entity_and_dedup` routes its synthetic scope key (`digest:<date>`,
`alert:...`) into `dedup_key` and leaves `source_entity_id` NULL, so
`business_keys_for_notification` falls back to the notification's own id. That
keeps AC-H11 true (`integration_logs.business_id` is a uuid COLUMN, so a real
uuid always goes in it, never a composite string).

The OTHER branch - a notification that DOES name an entity, whose entity is
therefore the business key with the notification only in `correlation_id`
(AC-H8) - is pinned in `tests/test_form_handling_lock_notify_outbox.py` for an
entity type outside `ENTITY_TABLES`, and in
`tests/test_after_sales_notification_spine.py::test_the_outbox_row_points_at_the_notification_and_the_case`
for a mapped one (complaint -> the `complaints` table).

AC-H8b is why the pair reads this way at all: the live code once stamped
`business_id = notification.id` unconditionally, the AC required the entity, and
the AC won. Tests asserting the overruled behaviour were stale, not red.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from app.tasks.notification_tasks import _send_whatsapp_for_notification


def _objs():
    db = MagicMock()
    notification = SimpleNamespace(
        id="632da7e3-a60a-4727-8a71-baa77c2970fd",
        data={
            "whatsapp_use_case": "sla_daily_summary",
            "whatsapp_text": "Daily SLA summary: 1 outstanding",
            "whatsapp_context_vars": {"outstanding": "1"},
        },
        event_type="user_sla_daily_summary",
        title="Summary",
        body="body",
        source_entity_type="scheduled_task_user_sla_daily_summary",
        # NULL on purpose, and reachable: the daily summary's idempotency scope is a
        # synthetic string (`<user>:<date>:manual:<ts>`), which `_split_entity_and_dedup`
        # now puts in `dedup_key` and never in `source_entity_id`. So a digest-style
        # notification genuinely has no entity behind it, and that is the branch this
        # file pins. (A uuid here would be the OTHER branch - see the module docstring.)
        source_entity_id=None,
    )
    user = SimpleNamespace(id="u1")
    delivery = SimpleNamespace(status="pending", error_message=None, sent_at=None)
    contact = SimpleNamespace(id="contact-uuid", respond_io_id="404284985")
    return db, notification, user, delivery, contact


def _patches(contact, send_side_effect=None, send_return=None):
    log_service = MagicMock()
    p_contact = patch(
        "app.services.respond_link_service.resolve_user_respond_contact",
        return_value=contact,
    )
    send = MagicMock(side_effect=send_side_effect, return_value=send_return)
    p_send = patch(
        "app.services.respond_messaging_service.send_text_or_template", send
    )
    p_log = patch(
        "app.services.integration_service.IntegrationLogService",
        return_value=log_service,
    )
    return p_contact, p_send, p_log, log_service


def test_failed_send_with_no_entity_uses_the_notification_as_the_business_key():
    """AC-H8 / AC-H8b / AC-H11, the no-entity branch.

    A notification with no `source_entity_id` is about nothing but itself, so the
    notification id is the only real uuid available and it goes in `business_id`
    as well as `correlation_id`. AC-H11 forbids the alternative anybody reaches
    for - stuffing the composite dedup scope into a uuid column.

    Where the notification DOES name an entity, the entity is the business key and
    the notification appears only in `correlation_id` (AC-H8). That is AC-H8b's
    ruling over the older code, and it is pinned in
    `tests/test_form_handling_lock_notify_outbox.py`.
    """
    db, notification, user, delivery, contact = _objs()
    resp = httpx.Response(401, json={"code": 401, "message": "Token not found"},
                          request=httpx.Request("POST", "https://api.respond.io/x"))
    err = httpx.HTTPStatusError("401", request=resp.request, response=resp)
    # Closed-window send attempts a TEMPLATE; the window-aware send stamps the
    # real attempted payload on the exception (see _attach_send_context).
    err.request_payload = {
        "message": {"type": "whatsapp_template", "use_case": "sla_daily_summary"}
    }
    p_contact, p_send, p_log, log_service = _patches(contact, send_side_effect=err)
    with p_contact, p_send, p_log:
        _send_whatsapp_for_notification(db, notification, user, delivery)

    assert log_service.create_integration_log.call_count == 1
    call = log_service.create_integration_log.call_args
    log_arg = call.args[0]
    assert log_arg.integration_channel == "respond_io"
    assert log_arg.direction == "outbound"
    assert log_arg.status == "failed"
    assert log_arg.status_code == 401
    assert log_arg.external_reference == "404284985"
    # No entity, so the notification is its own business key (AC-H11: a uuid, never
    # the composite dedup scope) and correlation_id names it too (AC-H8).
    assert log_arg.business_id == notification.id
    assert log_arg.correlation_id == notification.id
    # The logged payload reflects the TEMPLATE that was attempted, not a text default.
    assert call.kwargs["request_payload_dict"]["message"]["type"] == "whatsapp_template"
    assert delivery.status == "failed"


def test_successful_send_writes_success_outbox_log():
    db, notification, user, delivery, contact = _objs()
    p_contact, p_send, p_log, log_service = _patches(
        contact,
        send_return={
            "request_payload": {"message": {"type": "text", "text": "x"}},
            "response": {"messageId": 1},
            "sent_as": "template",
        },
    )
    with p_contact, p_send, p_log:
        _send_whatsapp_for_notification(db, notification, user, delivery)

    assert log_service.create_integration_log.call_count == 1
    log_arg = log_service.create_integration_log.call_args.args[0]
    assert log_arg.status == "success"
    assert log_arg.external_reference == "404284985"
    assert delivery.status == "sent"


def test_no_contact_marks_failed_without_outbox_log():
    db, notification, user, delivery, _ = _objs()
    p_contact, p_send, p_log, log_service = _patches(None)
    with p_contact, p_send, p_log:
        _send_whatsapp_for_notification(db, notification, user, delivery)

    # No send attempted => no outbox row; delivery still marked failed.
    assert log_service.create_integration_log.call_count == 0
    assert delivery.status == "failed"
