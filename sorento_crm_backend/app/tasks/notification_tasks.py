"""Background tasks for notification delivery (email via outbox, web push direct)."""
import os
import logging
import importlib
from datetime import datetime

from app.database import SessionLocal
from app.models.notification import Notification, NotificationDelivery, PushSubscription

logger = logging.getLogger(__name__)


_NOTIFICATION_TYPE_TO_EVENT_KEY: dict[str, str] = {
    "ticket_assigned": "ticket_assigned",
    "ticket_team_new": "ticket_team_new",
    "ticket_responded": "ticket_responded",
    "ticket_resolved": "ticket_resolved",
    "purchase_request_approved": "purchase_request_approved",
    "purchase_request_rejected": "purchase_request_rejected",
    "stock_inquiry_notification": "stock_inquiry_created",
    "stock_inquiry_notification:external_created": "stock_inquiry_created_external",
    "stock_inquiry_notification:external_resubmitted": "stock_inquiry_created_external",
    "external_promotion_created": "external_promotion_uploader_notice",
    "external_product_attachment_linked": "external_product_attachment",
    "external_form_created": "external_form_created",
    "external_packing_list_created": "external_packing_list_created",
    "complaint_created": "complaint_created_external",
    "complaint_notification": "complaint_created_external",
    "complaint_notification:external_created": "complaint_created_external",
    "form_sla": "form_sla_updated",
    "form_sla:assigned": "form_sla_assigned",
    "form_sla:escalated": "form_sla_escalated",
    "form_sla:responded": "form_sla_updated",
    "form_sla:resolved": "form_sla_updated",
    "form_sla_assigned": "form_sla_assigned",
    "form_sla_escalated": "form_sla_escalated",
    "import_job_finished": "import_job_completed",
    "import_job_failed": "import_job_completed",
    "user_invitation": "user_invitation",
    "daily_sla_summary": "daily_sla_summary",
    "workflow_form_transition": "workflow_form_state_transition",
}


def _resolve_event_key(notification: Notification) -> str:
    """Map a notification's `type` (+ optional `event_type` suffix) to an outbox event_key.

    Falls back to `notification_delivery` for anything not in the map so the guardrail still
    applies (and the row shows up in the admin UI). Add new mappings as new notification
    types are introduced.
    """
    notif_type = str(getattr(notification, "type", "") or "")
    event_type = str(getattr(notification, "event_type", "") or "")
    composite = f"{notif_type}:{event_type}" if event_type else notif_type
    if composite in _NOTIFICATION_TYPE_TO_EVENT_KEY:
        return _NOTIFICATION_TYPE_TO_EVENT_KEY[composite]
    if notif_type in _NOTIFICATION_TYPE_TO_EVENT_KEY:
        return _NOTIFICATION_TYPE_TO_EVENT_KEY[notif_type]
    return "notification_delivery"


def send_notification_deliveries(notification_id: str) -> None:
    """Enqueue pending email deliveries for a notification into the email outbox.

    Web push deliveries still send directly (Browser push has no SMTP server to flood and
    no per-event toggle requirement). Email deliveries flow through `email_outbox_service`
    so the guardrail caps + per-event kill switch apply.
    """
    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notification:
            logger.warning("Notification not found: %s", notification_id)
            return
        from app.models.user import User

        user = db.query(User).filter(User.id == notification.user_id).first()
        if not user:
            logger.warning("User not found for notification %s", notification_id)
            return

        pending = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.notification_id == notification_id,
                NotificationDelivery.status == "pending",
            )
            .all()
        )

        event_key = _resolve_event_key(notification)

        for delivery in pending:
            channel = str(getattr(delivery, "channel", ""))
            if channel == "email":
                _enqueue_email_for_delivery(db, notification, user, delivery, event_key)
            elif channel == "web_push":
                _send_web_push_for_notification(
                    db,
                    notification,
                    str(getattr(notification, "user_id")),
                    delivery,
                )
            elif channel == "whatsapp":
                _send_whatsapp_for_notification(db, notification, user, delivery)
    finally:
        db.close()


def _send_whatsapp_for_notification(db, notification: Notification, user, delivery: NotificationDelivery) -> None:
    """Send the notification to the user's WhatsApp contact (TCK-29).

    Window-aware: open -> text, closed -> the use-case's approved template
    (sla_escalation / sla_assignment). Best-effort: marks the delivery sent/failed
    and never raises — the originating escalation/assignment already committed.
    """
    from app.services.respond_link_service import resolve_user_respond_contact
    from app.services.respond_messaging_service import send_text_or_template
    from app.services.integration_service import IntegrationLogService
    from app.schemas.integration import IntegrationLogCreate

    now = datetime.utcnow()
    data = notification.data if isinstance(notification.data, dict) else {}
    # Surface the send (or its failure) in the Respond Outbox, which reads
    # integration_log (channel=respond_io, direction=outbound). Without this the
    # escalation/assignment WhatsApp send is invisible there even though it fired.
    business_table = str(data.get("source_entity_type") or "form_sla_tracking")
    business_id = str(data.get("source_entity_id") or notification.id)
    identifier = ""

    # Resolve the message text + use case up front so the Respond Outbox log shows
    # the attempted message even when the send raises before returning a payload
    # (e.g. a 401). On success this default is replaced by the actual request payload.
    event_type = str(getattr(notification, "event_type", "") or "")
    use_case = data.get("whatsapp_use_case") or (
        "sla_escalation" if event_type == "escalated" else "sla_assignment"
    )
    text = data.get("whatsapp_text") or (
        f"{notification.title}\n\n{notification.body or ''}".strip()
    )
    context_vars = data.get("whatsapp_context_vars") if isinstance(data.get("whatsapp_context_vars"), dict) else None
    attempted_payload = {"message": {"type": "text", "text": text}, "use_case": use_case}

    def _log_outbound(status, *, request_payload=None, response_payload=None, status_code=None):
        try:
            IntegrationLogService(db).create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table=business_table,
                    business_id=business_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier or ''}/message",
                    http_method="POST",
                    status=status,
                    status_code=status_code,
                    response_payload=(str(response_payload)[:50000] if response_payload else None),
                ),
                request_payload_dict=request_payload or {},
            )
        except Exception as log_err:  # logging must never break the delivery
            logger.warning("Failed to write respond outbox log for notification %s: %s", notification.id, log_err)
            db.rollback()

    try:
        contact = resolve_user_respond_contact(db, user)
        if not contact or not contact.respond_io_id:
            delivery.status = "failed"
            delivery.error_message = "No resolvable WhatsApp contact"
            db.commit()
            return
        identifier = str(contact.respond_io_id)
        result = send_text_or_template(
            db,
            identifier=identifier,
            text=text,
            use_case=use_case,
            context_vars=context_vars,
            respond_contact_id=str(contact.id),
        )
        delivery.status = "sent"
        delivery.sent_at = now
        db.commit()
        _log_outbound(
            "success",
            request_payload=(result.get("request_payload") if isinstance(result, dict) else None) or attempted_payload,
            response_payload=result.get("response") if isinstance(result, dict) else None,
        )
    except Exception as e:  # best-effort: degrade, never raise
        logger.warning("WhatsApp delivery failed for notification %s: %s", notification.id, e)
        resp = getattr(e, "response", None)
        resp_code = getattr(resp, "status_code", None) if resp is not None else None
        resp_body = None
        if resp is not None:
            try:
                resp_body = (resp.text or "")[:50000]
            except Exception:
                resp_body = None
        try:
            delivery.status = "failed"
            delivery.error_message = str(e)[:500]
            db.commit()
        except Exception:
            db.rollback()
        # Prefer the real attempted payload the send layer attached (template name
        # + params for a closed-window template send); fall back to the text guess.
        real_payload = getattr(e, "_respond_request_payload", None) or attempted_payload
        _log_outbound(
            "failed",
            request_payload=real_payload,
            response_payload=resp_body or str(e)[:50000],
            status_code=resp_code,
        )


def _enqueue_email_for_delivery(db, notification: Notification, user, delivery: NotificationDelivery, event_key: str) -> None:
    """Hand the email off to email_outbox_service. Marks delivery as 'queued'."""
    raw_data = getattr(notification, "data", None)
    data = raw_data if isinstance(raw_data, dict) else {}
    notification_title = str(getattr(notification, "title", ""))
    notification_body = getattr(notification, "body", None)
    body_text = str(notification_body) if notification_body is not None else notification_title
    from_name = data.get("from_name")
    body_html = data.get("body_html")

    if data.get("single_email_to_all") and data.get("recipient_emails"):
        recipients = [str(e) for e in data.get("recipient_emails", []) if e]
        if not recipients:
            delivery.status = "failed"
            delivery.error_message = "No recipients"
            db.commit()
            return
        primary = recipients[0]
        cc_rest = recipients[1:] if len(recipients) > 1 else None
        try:
            from app.services.email_outbox_service import enqueue as enqueue_email

            outbox_id = enqueue_email(
                db,
                event_key=event_key,
                to=primary,
                cc=cc_rest,
                subject=notification_title,
                body_text=body_text,
                body_html=body_html,
                from_name=from_name,
                metadata={
                    "notification_id": str(notification.id),
                    "notification_delivery_id": str(delivery.id),
                    "recipients": recipients,
                },
            )
            delivery.status = "queued"
            delivery.error_message = None
            db.commit()
            logger.debug("Enqueued multi-recipient email %s for delivery %s", outbox_id, delivery.id)
        except Exception as e:
            delivery.status = "failed"
            delivery.error_message = f"Enqueue failed: {e}"
            db.commit()
            logger.exception("Failed to enqueue multi-recipient delivery %s", delivery.id)
        return

    recipient = str(getattr(user, "email", "") or "")
    if not recipient:
        delivery.status = "failed"
        delivery.error_message = "User has no email address"
        db.commit()
        return

    coalesce_meta = data.get("email_coalesce") if isinstance(data, dict) else None
    try:
        if isinstance(coalesce_meta, dict) and (coalesce_meta.get("attachment_plain_items") or coalesce_meta.get("attachment_html_items")):
            outbox_id, merged = _enqueue_coalesced_attachment_email(
                db=db,
                event_key=event_key,
                recipient=recipient,
                notification=notification,
                delivery=delivery,
                user=user,
                subject=notification_title,
                from_name=from_name,
                coalesce_meta=coalesce_meta,
            )
            logger.debug(
                "Enqueued coalesced email %s for delivery %s (merged=%s)",
                outbox_id, delivery.id, merged,
            )
        else:
            from app.services.email_outbox_service import enqueue as enqueue_email

            outbox_id = enqueue_email(
                db,
                event_key=event_key,
                to=recipient,
                subject=notification_title,
                body_text=body_text,
                body_html=body_html,
                from_name=from_name,
                metadata={
                    "notification_id": str(notification.id),
                    "notification_delivery_id": str(delivery.id),
                    "user_id": str(getattr(user, "id", "") or ""),
                },
            )
            logger.debug("Enqueued single-recipient email %s for delivery %s", outbox_id, delivery.id)
        delivery.status = "queued"
        delivery.error_message = None
        db.commit()
    except Exception as e:
        delivery.status = "failed"
        delivery.error_message = f"Enqueue failed: {e}"
        db.commit()
        logger.exception("Failed to enqueue single-recipient delivery %s", delivery.id)


def _enqueue_coalesced_attachment_email(
    *,
    db,
    event_key: str,
    recipient: str,
    notification: Notification,
    delivery: NotificationDelivery,
    user,
    subject: str,
    from_name,
    coalesce_meta: dict,
) -> tuple[str, bool]:
    """Coalesce-aware enqueue for attachment-linkage events. Multiple n8n callbacks within the
    event's coalesce window collapse into one outbox row whose body lists every attachment.
    """
    from app.services.email_outbox_service import enqueue_or_merge

    intro_plain = str(coalesce_meta.get("intro_plain") or "")
    intro_html = str(coalesce_meta.get("intro_html") or "")
    footer_plain = str(coalesce_meta.get("footer_plain") or "")
    footer_html = str(coalesce_meta.get("footer_html") or "")
    att_plain_items = list(coalesce_meta.get("attachment_plain_items") or [])
    att_html_items = list(coalesce_meta.get("attachment_html_items") or [])

    def _rebuild(merged_meta: dict) -> tuple[str, str]:
        plain_items = list(merged_meta.get("attachment_plain_items") or [])
        html_items = list(merged_meta.get("attachment_html_items") or [])
        rebuilt_plain = f"{intro_plain}\n" + "\n".join(plain_items) + f"\n\n{footer_plain}"
        rebuilt_html = f"{intro_html}<ul>{''.join(html_items)}</ul>{footer_html}"
        return rebuilt_plain, rebuilt_html

    initial_plain = f"{intro_plain}\n" + "\n".join(att_plain_items) + f"\n\n{footer_plain}"
    initial_html = f"{intro_html}<ul>{''.join(att_html_items)}</ul>{footer_html}"

    coalesce_id = None
    raw_data = getattr(notification, "data", None)
    if isinstance(raw_data, dict):
        coalesce_id = raw_data.get("batch_id") or raw_data.get("promotion_id") or raw_data.get("entity_url")

    outbox_id, merged = enqueue_or_merge(
        db,
        event_key=event_key,
        to=recipient,
        subject=subject,
        body_text=initial_plain,
        body_html=initial_html,
        from_name=from_name,
        coalesce_id=str(coalesce_id) if coalesce_id else None,
        merge_metadata_list_keys=["attachment_plain_items", "attachment_html_items", "attachment_ids", "notification_delivery_ids"],
        rebuild_body=_rebuild,
        metadata={
            "notification_id": str(notification.id),
            "notification_delivery_id": str(delivery.id),
            "notification_delivery_ids": [str(delivery.id)],
            "user_id": str(getattr(user, "id", "") or ""),
            "attachment_plain_items": att_plain_items,
            "attachment_html_items": att_html_items,
            "attachment_ids": list(raw_data.get("attachment_ids", [])) if isinstance(raw_data, dict) else [],
        },
    )
    return outbox_id, merged


def _send_web_push_for_notification(
    db,
    notification: Notification,
    user_id: str,
    delivery: NotificationDelivery,
) -> None:
    """Send web push to all subscriptions for user; update delivery row.

    Web push bypasses the email outbox because (a) it has no SMTP rate-limit concern and
    (b) it talks directly to browser push services per subscription.
    """
    subs = (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == user_id)
        .all()
    )
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    if not vapid_private_key:
        setattr(delivery, "status", "failed")
        setattr(delivery, "error_message", "VAPID not configured")
        db.commit()
        return
    if not subs:
        setattr(delivery, "status", "sent")
        setattr(delivery, "sent_at", datetime.utcnow())
        db.commit()
        return

    try:
        pywebpush_module = importlib.import_module("pywebpush")
        webpush = getattr(pywebpush_module, "webpush")
        WebPushException = getattr(pywebpush_module, "WebPushException")
    except Exception:
        setattr(delivery, "status", "failed")
        setattr(delivery, "error_message", "pywebpush not installed")
        db.commit()
        return

    import json
    payload = json.dumps({
        "title": notification.title,
        "body": notification.body or "",
        "data": notification.data or {},
    })
    last_error = None
    sent_any = False
    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": "mailto:noreply@localhost"},
            )
            sent_any = True
        except WebPushException as e:
            last_error = str(e)
            # Prune dead endpoints (404 Not Found / 410 Gone) so the table stays bounded.
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (404, 410):
                logger.info("Pruning expired push subscription %s (HTTP %s)", sub.id, status_code)
                db.delete(sub)
            else:
                logger.warning("Web push failed for subscription %s: %s", sub.id, e)
    setattr(delivery, "status", "sent" if sent_any else "failed")
    setattr(delivery, "sent_at", datetime.utcnow() if sent_any else None)
    setattr(delivery, "error_message", None if sent_any else (last_error or "No subscription succeeded"))
    db.commit()
