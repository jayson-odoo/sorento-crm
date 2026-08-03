"""The Respond outbox: what we actually told a person, and whether it arrived.

``integration_log`` remains the wire truth. This module is the one place that reads it
EVENT-FIRST (AC-H8, AC-H9):

    Complaint CMP2026-0123 - Visit confirmed - to Mr Vinod (017-3336634)
    WhatsApp template - FAILED 401

Its own module rather than another branch inside
``IntegrationLogService.list_integration_logs``, which is already the generic log list
with eleven filters and would have to carry three joins it must never impose on the
generic caller.

**The query is a LEFT JOIN and that is not a preference (AC-H8a).** AI replies,
n8n-initiated sends and every row `workflow_submission_notify` wrote before S4 carry no
``correlation_id``, so an INNER JOIN onto ``notifications`` loses exactly the traffic
this screen exists to make visible - and loses it silently, as absent rows. The same
goes for the case join: a send about something that is not a complaint still renders,
with an empty case rather than no row.

``sent_as`` is DERIVED from the stamped request payload rather than stored, so a
closed-window failure reads as a template attempt (AC-H14) without a column that a
future caller could forget to set.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.complaints import Complaint
from app.models.integration import IntegrationLog
from app.models.notification import Notification
from app.models.user import User

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

# source_entity_type -> the TABLE its id is a primary key of. `business_table` is a
# table name (AC-H8b); ``source_entity_type`` is an entity type, and stamping one where
# the other belongs produces an outbox row that joins to nothing. Anything not listed
# keeps its entity type verbatim rather than guessing a table into existence.
ENTITY_TABLES: dict[str, str] = {
    "complaint": Complaint.__tablename__,
    "stock_inquiry": "stock_inquiries",
    "purchase_request": "purchase_requests",
    "sponsorship_form": "purchase_requests",
    "ticket": "tickets",
    "workflow_submission": "workflow_submissions",
}

# The tables whose human-readable number the outbox resolves for the case column.
ENTITY_NUMBER_COLUMNS: dict[str, str] = {
    Complaint.__tablename__: "complaint_number",
}


def business_keys_for_notification(notification: Notification) -> tuple[str, str]:
    """``(business_table, business_id)`` for a send made on a notification's behalf.

    ``integration_log.business_id`` is a uuid COLUMN, so it is one row's primary key
    and never a composite string (the recorded lesson from the daily summary's
    ``<user>:<date>:manual:<ts>`` key). ``source_entity_id`` is already guaranteed to
    be a uuid or NULL by ``_split_entity_and_dedup``; when it is NULL there is no
    entity, and the notification itself is the only real uuid available.
    """
    entity_type = str(getattr(notification, "source_entity_type", "") or "")
    entity_id = str(getattr(notification, "source_entity_id", "") or "")
    table = ENTITY_TABLES.get(entity_type) or entity_type or "respond_notification"
    if entity_id and _UUID_RE.match(entity_id):
        return table, entity_id
    # No entity behind this notification (batched alerts, digests): the row is about
    # the notification, so say so rather than pointing a table name at an id that is
    # not in it.
    return (
        ENTITY_TABLES.get(entity_type, entity_type) if entity_type else "respond_notification",
        str(getattr(notification, "id", "")),
    )


def derive_sent_as(request_payload: Optional[str]) -> Optional[str]:
    """``template`` or ``text``, read off what was ACTUALLY attempted.

    The window-aware send stamps the real payload on both the result and the
    exception, so a failure that fell back to a template reads as a template attempt
    (AC-H14). None when nothing was recorded - an unknown attempt is not a text one.
    """
    raw = str(request_payload or "").strip()
    if not raw:
        return None
    message: Any = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            message = parsed.get("message")
    except Exception:  # noqa: BLE001 - legacy rows hold a python repr, not JSON
        message = None
    if isinstance(message, dict):
        kind = str(message.get("type") or "")
        if "template" in kind:
            return "template"
        if kind:
            return "text"
    return "template" if "template" in raw else "text"


def list_outbox(
    db: Session,
    *,
    page: int = 1,
    limit: int = 50,
    business_id: Optional[str] = None,
    business_table: Optional[str] = None,
    status: Optional[str] = None,
    integration_channel: Optional[str] = "respond_io",
    event_type: Optional[str] = None,
) -> dict:
    """Outbound Respond.io sends, newest first, with their event context.

    ``business_id`` scopes to one case, which is how a complaint detail page asks
    "what have we actually told this person".
    """
    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), 200))

    query = (
        db.query(
            IntegrationLog,
            Notification,
            Complaint.complaint_number,
            RespondContact.name,
            RespondContact.phone_number,
            User.name,
        )
        # LEFT joins throughout (AC-H8a). correlation_id and notifications.id are both
        # uuid columns, so the join needs no cast.
        .outerjoin(Notification, Notification.id == IntegrationLog.correlation_id)
        .outerjoin(
            Complaint,
            (IntegrationLog.business_table == Complaint.__tablename__)
            & (cast(Complaint.id, String) == cast(IntegrationLog.business_id, String)),
        )
        .outerjoin(
            RespondContact, RespondContact.id == Notification.respond_contact_id
        )
        .outerjoin(User, User.id == Notification.user_id)
    )
    if integration_channel:
        query = query.filter(IntegrationLog.integration_channel == integration_channel)
    if business_id:
        query = query.filter(
            cast(IntegrationLog.business_id, String) == str(business_id)
        )
    if business_table:
        query = query.filter(IntegrationLog.business_table == business_table)
    if status:
        query = query.filter(IntegrationLog.status == status)
    if event_type:
        query = query.filter(Notification.event_type == event_type)

    total = query.count()
    rows = (
        query.order_by(IntegrationLog.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    data = [
        _serialize(log, notification, case_number, contact_name, contact_phone, user_name)
        for log, notification, case_number, contact_name, contact_phone, user_name in rows
    ]
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if limit else 0,
    }


def _serialize(
    log: IntegrationLog,
    notification: Optional[Notification],
    case_number: Optional[str],
    contact_name: Optional[str],
    contact_phone: Optional[str],
    user_name: Optional[str],
) -> dict:
    """One outbox row. Missing event context is EMPTY, never a crash and never a filter."""
    label = ""
    if notification is not None:
        parts = [str(contact_name or user_name or "").strip()]
        if contact_phone:
            parts.append(f"({str(contact_phone).strip()})")
        label = " ".join(p for p in parts if p).strip()
    if not label:
        # No notification, or a recipient row that has since been deleted: the wire
        # identifier is the only truthful answer, and it is not a uuid.
        label = str(getattr(log, "external_reference", "") or "")

    return {
        "id": str(log.id),
        "created_at": log.created_at,
        "status": log.status,
        "status_code": log.status_code,
        "direction": log.direction,
        "endpoint": log.endpoint,
        "external_reference": log.external_reference,
        "error_message": log.error_message,
        "request_payload": log.request_payload,
        "sent_as": derive_sent_as(log.request_payload),
        "business_table": log.business_table,
        "business_id": str(log.business_id) if log.business_id else None,
        "case_number": case_number,
        "notification_id": str(notification.id) if notification is not None else None,
        "event_type": getattr(notification, "event_type", None),
        "title": getattr(notification, "title", None),
        "recipient_label": label,
    }
