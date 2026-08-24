"""Deliver an inbound WhatsApp message to the people who asked to hear about it.

PLAN-message-push slice S3. The whole job is: load the committed
``chat_histories`` row, ask ``message_push_service`` who it buzzes, and write one
notification per recipient. **No transport code lives here.**
``NotificationService`` already queues the deliveries and
``notification_tasks._send_web_push_for_notification`` already talks to the browser
push services, prunes dead endpoints and survives a missing VAPID key - an earlier
draft of the plan extracted a ``push_sender`` module for this event to call, and it
was cut for being a new module whose only caller already called the original.

The bell and the phone show the same thing on purpose (UAC AC-M16): one row, two
channels, so a user who missed the buzz finds the same item in the bell. The cost
is bell volume on a chatty day, accepted deliberately - a push the bell cannot
account for is the worse failure.

Idempotent on the Respond ``message_id``: the ingest endpoint is reached TWICE for
the same WhatsApp message (its own AC-J5 dual-lane race), so without a dedup key
every message would double-ring. A row with no ``message_id`` has nothing to dedupe
on and notifies once per ingest, exactly as the row insert does (AC-M16b).
"""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models.chat_history import ChatHistory

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "conversation_message"
EVENT_TYPE = "message_received"
SOURCE_ENTITY_TYPE = "chat_message"


def send_message_push(chat_history_id: int) -> None:
    """RQ entry point on the `notifications` queue."""
    db = SessionLocal()
    try:
        _dispatch(db, chat_history_id)
    except Exception:
        # The message itself is already stored and the drawer already refreshed;
        # a failed alert must not become a retry storm on the ingest lane.
        logger.exception("Message push failed for chat_histories.id=%s", chat_history_id)
    finally:
        db.close()


def _dispatch(db, chat_history_id: int) -> None:
    from app.services.message_push_service import build_message_push
    from app.services.notification_service import NotificationService

    row = db.query(ChatHistory).filter(ChatHistory.id == chat_history_id).first()
    if row is None:
        logger.warning("Message push: chat_histories.id=%s is gone", chat_history_id)
        return

    push = build_message_push(db, row)
    if push is None or not push.recipients:
        return

    service = NotificationService(db)
    for recipient in push.recipients:
        service.create_with_channel_preferences(
            user_id=recipient.user_id,
            type=NOTIFICATION_TYPE,
            title=push.title,
            body=push.body,
            data={
                "link": recipient.link,
                "tag": push.tag,
                "contact_id": push.contact_id,
            },
            source_entity_type=SOURCE_ENTITY_TYPE,
            # `message_id` is the Respond id, not a uuid, so it lands in
            # `dedup_key` alone - `source_entity_id` stays NULL by design (see
            # notification_service._split_entity_and_dedup).
            dedup_key=row.message_id,
            event_type=EVENT_TYPE,
            send_in_app=True,
            # A personal alert, not a workflow event: no email, ever (AC-M16).
            send_email=False,
            # Explicit rather than left to the "upgrade if subscribed" default, so
            # the delivery row records that a push WAS attempted for this recipient
            # even when they have no subscription on any device (AC-M17).
            send_web_push=True,
        )
