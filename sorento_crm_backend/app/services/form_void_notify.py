"""Best-effort in-app notifications when a form is voided (NTF-1 / NTF-2).

Notifies the form's current SLA assignee and the handling-lock holder
(``handled_by_id``) via the existing in-app notification system only — the
salesperson WhatsApp send (NTF-3) is form-specific and stays in each form
service. Everything here is best-effort and NEVER raises (NTF-5): a notify
failure must not roll back the committed void.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def notify_form_voided_in_app(
    db: Session,
    *,
    source_entity_type: str,
    source_entity_id: str,
    entity_number: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> set[str]:
    """Send in-app notifications to the active tracker's assignee + handling-lock
    holder. Returns the set of user ids actually notified (for telemetry/tests).
    Never raises.
    """
    notified: set[str] = set()
    try:
        from app.models.sla import ConversationSLATracking
        from app.services.sla_scope import open_tracker_scope

        tracker = (
            db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == source_entity_type,
                ConversationSLATracking.source_entity_id == str(source_entity_id),
                # Whoever held a stage voided by an earlier revision was already told.
                *open_tracker_scope(),
            )
            .order_by(ConversationSLATracking.initiated_at.desc())
            .first()
        )
        if tracker is None:
            return notified

        assignee_id = getattr(tracker, "assigned_to_id", None)
        handler_id = getattr(tracker, "handled_by_id", None)

        targets: list[str] = []
        if assignee_id:
            targets.append(str(assignee_id))
        # NTF-2: handling-lock holder (skipped cleanly when unset or == assignee).
        if handler_id and str(handler_id) not in targets:
            targets.append(str(handler_id))
        if not targets:
            return notified

        from app.services.notification_service import NotificationService

        svc = NotificationService(db)
        label = source_entity_type.replace("_", " ")
        title = f"Form voided: {entity_number}" if entity_number else "Form voided"
        body = f"A {label} you were handling has been voided."
        for uid in targets:
            try:
                svc.create_with_channel_preferences(
                    uid,
                    type="form_voided",
                    title=title,
                    body=body,
                    source_entity_type=source_entity_type,
                    source_entity_id=str(source_entity_id),
                    event_type="form_voided",
                    send_in_app=True,
                    send_email=False,
                    send_web_push=False,
                    send_whatsapp=False,  # NTF-4: no WhatsApp to assignee/handler
                )
                notified.add(uid)
            except Exception:
                logger.warning(
                    "Void notify (in-app) failed for user %s on %s/%s",
                    uid,
                    source_entity_type,
                    source_entity_id,
                    exc_info=True,
                )
    except Exception:
        logger.warning(
            "Void in-app notify fan-out failed for %s/%s",
            source_entity_type,
            source_entity_id,
            exc_info=True,
        )
    return notified
