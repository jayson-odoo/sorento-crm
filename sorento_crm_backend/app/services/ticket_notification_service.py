"""Ticket notification fan-out.

Two entry points:

- ``notify_assignee_and_team_on_create`` - fires when a ticket is created via
  the MCP intake (round-robin assignee + remaining tier-1 team members both
  get an in-app + email notification).
- ``notify_submitter_on_status_change(kind='responded'|'resolved')`` - fires
  when the assignee clicks "Update & Reply". Routes the notification to the
  submitter's channel: WhatsApp via Respond.io for respond-contact submitters,
  in-app + email via ``NotificationService`` for system users.

All Respond.io / NotificationService calls are wrapped in try/except so a
delivery failure cannot block the parent transition. Errors are logged and
written to ``integration_logs`` for traceability.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact, TeamMember
from app.models.tickets import Ticket
from app.schemas.integration import IntegrationLogCreate
from app.services.integration_service import IntegrationLogService, RespondClient
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def _ticket_link(ticket: Ticket) -> str:
    return f"/ticket-management/tickets/{ticket.id}"


def _short_summary(ticket: Ticket) -> str:
    text = (ticket.description_text or ticket.title or "").strip()
    if len(text) > 220:
        return text[:217] + "..."
    return text


def notify_assignee_and_team_on_create(
    db: Session,
    *,
    ticket: Ticket,
    assignee_id: str,
    team_id: Optional[str],
) -> None:
    """Send 'assigned' to the round-robin assignee, and 'new in queue' to the
    remaining tier-1 team members. Both receive in-app + email."""
    link = _ticket_link(ticket)
    summary = _short_summary(ticket)
    notif = NotificationService(db)

    try:
        notif.create_with_channel_preferences(
            user_id=str(assignee_id),
            type="ticket_assigned",
            title=f"Ticket assigned to you: {ticket.ticket_number or ticket.id}",
            body=f"{ticket.title}\n\n{summary}" if summary else ticket.title,
            data={
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
                "link": link,
                "priority": ticket.priority,
                "category": ticket.category,
            },
            source_entity_type="ticket",
            source_entity_id=str(ticket.id),
            event_type="assigned",
            send_in_app=True,
            send_email=True,
            send_web_push=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Ticket %s assignee notification failed: %s", ticket.id, e)

    if not team_id:
        return

    try:
        members = (
            db.query(TeamMember)
            .filter(TeamMember.team_id == str(team_id))
            .all()
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Ticket %s team-member lookup failed: %s", ticket.id, e)
        return

    for member in members:
        if str(member.user_id) == str(assignee_id):
            continue
        try:
            notif.create_with_channel_preferences(
                user_id=str(member.user_id),
                type="ticket_team_new",
                title=f"New ticket in your queue: {ticket.ticket_number or ticket.id}",
                body=f"{ticket.title}\n\nAssigned to a teammate; visible to the IT admin tier-1 group.",
                data={
                    "ticket_id": str(ticket.id),
                    "ticket_number": ticket.ticket_number,
                    "link": link,
                    "assignee_id": str(assignee_id),
                },
                source_entity_type="ticket",
                source_entity_id=str(ticket.id),
                event_type="team_created",
                send_in_app=True,
                send_email=True,
                send_web_push=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Ticket %s team-member notification failed for user %s: %s",
                ticket.id,
                member.user_id,
                e,
            )


def _format_status_message(ticket: Ticket, kind: str) -> str:
    number = ticket.ticket_number or str(ticket.id)
    if kind == "responded":
        body = (ticket.response_text or "").strip()
        prefix = f"Update on your IT support ticket {number} ({ticket.title})"
        return f"{prefix}: {body}" if body else prefix
    if kind == "resolved":
        body = (ticket.resolution_text or "").strip()
        prefix = f"Your IT support ticket {number} ({ticket.title}) has been resolved"
        return f"{prefix}: {body}" if body else prefix
    return f"IT support ticket {number} updated."


def notify_submitter_on_status_change(
    db: Session,
    *,
    ticket: Ticket,
    kind: str,
) -> None:
    """Notify the submitter that their ticket moved to ``responded`` or
    ``resolved``. Routes via WhatsApp for respond_contact submitters, via
    in-app + email for user submitters."""
    if kind not in ("responded", "resolved"):
        return
    raised_by = ticket.raised_by
    if not raised_by:
        return

    if ticket.raised_by_kind == "user":
        link = _ticket_link(ticket)
        try:
            NotificationService(db).create_with_channel_preferences(
                user_id=str(raised_by),
                type=f"ticket_{kind}",
                title=(
                    f"Your ticket has been responded: {ticket.ticket_number or ticket.id}"
                    if kind == "responded"
                    else f"Your ticket has been resolved: {ticket.ticket_number or ticket.id}"
                ),
                body=_format_status_message(ticket, kind),
                data={
                    "ticket_id": str(ticket.id),
                    "ticket_number": ticket.ticket_number,
                    "link": link,
                    "kind": kind,
                },
                source_entity_type="ticket",
                source_entity_id=str(ticket.id),
                event_type=f"submitter_{kind}",
                send_in_app=True,
                send_email=True,
                send_web_push=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Ticket %s submitter %s notification failed: %s", ticket.id, kind, e
            )
        return

    contact = (
        db.query(RespondContact).filter(RespondContact.id == str(raised_by)).first()
    )
    if not contact or not contact.respond_io_id:
        logger.info(
            "Ticket %s respond contact missing respond_io_id; skipping WhatsApp notify",
            ticket.id,
        )
        return

    text = _format_status_message(ticket, kind)
    log_service = IntegrationLogService(db)
    try:
        client = RespondClient()
        response = client.send_message(contact.respond_io_id, text)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="tickets",
                business_id=str(ticket.id),
                external_reference=contact.respond_io_id,
                direction="outbound",
                endpoint=f"https://api.respond.io/v2/contact/id:{contact.respond_io_id}/message",
                http_method="POST",
                status="success",
                response_payload=str(response)[:50000] if response else None,
            ),
            request_payload_dict={"message": {"type": "text", "text": text}},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Respond.io send_message failed for ticket %s", ticket.id)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="tickets",
                business_id=str(ticket.id),
                external_reference=contact.respond_io_id or "",
                direction="outbound",
                endpoint=f"https://api.respond.io/v2/contact/id:{contact.respond_io_id or ''}/message",
                http_method="POST",
                status="failed",
                error_message=str(e),
            ),
            request_payload_dict={"message": {"type": "text", "text": text}},
        )


def notify_submitter_text(db: Session, *, ticket: Ticket, title: str, text: str) -> None:
    """Free-text notice to the submitter over the same routing as the status
    notifications: in-app + email for user submitters, WhatsApp (with an outbox
    row on success AND failure) for respond-contact submitters.

    Exists for messages outside the responded/resolved pair - e.g. the form-action
    undo correction, where the submitter was already told "resolved" and that
    message cannot be unsent.
    """
    raised_by = ticket.raised_by
    if not raised_by:
        return

    if ticket.raised_by_kind == "user":
        try:
            NotificationService(db).create_with_channel_preferences(
                user_id=str(raised_by),
                type="ticket_correction",
                title=title,
                body=text,
                data={
                    "ticket_id": str(ticket.id),
                    "ticket_number": ticket.ticket_number,
                    "link": _ticket_link(ticket),
                },
                source_entity_type="ticket",
                source_entity_id=str(ticket.id),
                event_type="submitter_correction",
                send_in_app=True,
                send_email=True,
                send_web_push=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Ticket %s correction notification failed: %s", ticket.id, e)
        return

    contact = (
        db.query(RespondContact).filter(RespondContact.id == str(raised_by)).first()
    )
    if not contact or not contact.respond_io_id:
        logger.info(
            "Ticket %s respond contact missing respond_io_id; skipping WhatsApp correction",
            ticket.id,
        )
        return

    log_service = IntegrationLogService(db)
    try:
        client = RespondClient()
        response = client.send_message(contact.respond_io_id, text)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="tickets",
                business_id=str(ticket.id),
                external_reference=contact.respond_io_id,
                direction="outbound",
                endpoint=f"https://api.respond.io/v2/contact/id:{contact.respond_io_id}/message",
                http_method="POST",
                status="success",
                response_payload=str(response)[:50000] if response else None,
            ),
            request_payload_dict={"message": {"type": "text", "text": text}},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Respond.io correction send failed for ticket %s", ticket.id)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="tickets",
                business_id=str(ticket.id),
                external_reference=contact.respond_io_id or "",
                direction="outbound",
                endpoint=f"https://api.respond.io/v2/contact/id:{contact.respond_io_id or ''}/message",
                http_method="POST",
                status="failed",
                error_message=str(e),
            ),
            request_payload_dict={"message": {"type": "text", "text": text}},
        )
