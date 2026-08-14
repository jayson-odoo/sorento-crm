"""
After CRM sends a WhatsApp/Respond message via API (automation), n8n may not see agent user_id.
POST a Respond.io-shaped payload to a configurable webhook so workflows can run with user + contact context.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid as uuid_module
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.user import User
from app.schemas.integration import IntegrationLogCreate
from app.services.integration_service import IntegrationLogService
from app.services.n8n_webhook_settings import (
    crm_webhook_auth_headers,
    get_n8n_crm_chat_outbound_webhook_url,
)

logger = logging.getLogger(__name__)

# Every human ticket-drawer send is logged and mirrored against the ticket itself,
# never the form entity that happens to host the chat panel.
HUMAN_TICKET_BUSINESS_TABLE = "conversation_sla_tracking"


def send_crm_chat_outbound_webhook_for_log(log_id: str) -> None:
    """POST the integration log payload to the configured webhook (own DB session)."""
    try:
        from app.database import SessionLocal

        bg_db = SessionLocal()
        try:
            bg_service = IntegrationLogService(bg_db)
            bg_service.send_webhook_for_log(log_id)
        finally:
            bg_db.close()
    except Exception as e:
        logger.error("CRM chat outbound webhook failed for log %s: %s", log_id, e, exc_info=True)


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _split_display_name(name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not name or not str(name).strip():
        return None, None
    parts = str(name).strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _contact_first_last(rc: Optional[RespondContact]) -> tuple[Optional[str], Optional[str]]:
    if rc is None:
        return None, None
    fn = (getattr(rc, "first_name", None) or "").strip() or None
    ln = (getattr(rc, "last_name", None) or "").strip() or None
    if fn or ln:
        return fn, ln
    return _split_display_name(getattr(rc, "name", None))


def _message_id_from_respond_response(resp: Optional[dict]) -> Optional[int]:
    if not resp or not isinstance(resp, dict):
        return None
    mid = resp.get("messageId") or resp.get("message_id") or resp.get("id")
    return _int_or_none(mid)


def _is_crm_user_uuid(value: str) -> bool:
    """True if value looks like users.id (UUID) — must not be sent as Respond user id to n8n."""
    s = str(value).strip()
    if len(s) != 36:
        return False
    try:
        uuid_module.UUID(s)
        return True
    except ValueError:
        return False


def resolve_assignee_respond_user_id_from_tracking(db: Session, tracking: Any) -> Optional[str]:
    """Respond.io-style user id for CRM assignee on an SLA tracking row (numeric string)."""
    at = (getattr(tracking, "assigned_to", None) or "").strip()
    if at:
        return at
    aid = getattr(tracking, "assigned_to_id", None)
    if aid:
        u = db.query(User).filter(User.id == str(aid)).first()
        if u and getattr(u, "respond_user_id", None):
            s = str(u.respond_user_id).strip()
            return s or None
    return None


def resolve_sla_assignee_respond_user_id(
    db: Session, source_entity_type: str, source_entity_id: str
) -> Optional[str]:
    """Assignee Respond user id for a business row linked to conversation SLA tracking."""
    from app.services.sla_service import ConversationSLATrackingService

    t = ConversationSLATrackingService(db).get_tracking_by_source_entity(
        source_entity_type, str(source_entity_id)
    )
    if not t:
        return None
    return resolve_assignee_respond_user_id_from_tracking(db, t)


def _webhook_agent_respond_id(
    assignee_respond_user_id: Optional[str],
    sender: Optional[User],
    respond_user_id_for_payload: str,
) -> tuple[Optional[str], Optional[int], Any]:
    """
    Choose Respond / n8n agent user identifier. Priority: explicit assignee (conversation assignee),
    then sender.respond_user_id, then payload fallback only if it is not a CRM users.id UUID.
    Returns (chosen_str, int_if_numeric, value_for_user_id_json).
    """
    chosen: Optional[str] = None
    if assignee_respond_user_id and str(assignee_respond_user_id).strip():
        chosen = str(assignee_respond_user_id).strip()
    elif sender and getattr(sender, "respond_user_id", None):
        rs = str(sender.respond_user_id).strip()
        if rs:
            chosen = rs
    else:
        p = str(respond_user_id_for_payload or "").strip()
        if p and not _is_crm_user_uuid(p):
            chosen = p

    if not chosen:
        return None, None, None

    ru_int = _int_or_none(chosen)
    user_id_json: Any = ru_int if ru_int is not None else chosen
    return chosen, ru_int, user_id_json


def build_crm_chat_outbound_payload(
    *,
    contact_respond_io_id: str,
    message_text: str,
    respond_api_response: Optional[dict],
    space_id: Optional[str],
    business_table: str,
    business_id: str,
    rc: Optional[RespondContact],
    sender: Optional[User],
    respond_user_id_for_payload: str,
    assignee_respond_user_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Single-element array mimicking Respond.io outbound message webhook shape."""
    now_ms = int(time.time() * 1000)
    contact_id_int = _int_or_none(contact_respond_io_id)
    msg_id = _message_id_from_respond_response(respond_api_response) or now_ms

    c_fn, c_ln = _contact_first_last(rc)
    phone = (rc.phone_number if rc else None) or None

    _chosen_str, ru_int, user_id_json = _webhook_agent_respond_id(
        assignee_respond_user_id, sender, respond_user_id_for_payload
    )

    s_fn, s_ln = _split_display_name(getattr(sender, "name", None) if sender else None)
    s_email = (getattr(sender, "email", None) if sender else None) or ""

    message_block: dict[str, Any] = {
        "messageId": msg_id,
        "channelMessageId": None,
        "contactId": contact_id_int if contact_id_int is not None else contact_respond_io_id,
        "channelId": None,
        "traffic": "outgoing",
        "timestamp": now_ms,
        "message": {"type": "text", "text": message_text},
        "status": [{"value": "pending", "timestamp": now_ms}],
    }

    user_block: dict[str, Any] = {
        "id": user_id_json,
        "firstName": s_fn or "",
        "lastName": s_ln or "",
        "email": s_email,
    }

    envelope: dict[str, Any] = {
        "contact": {
            "id": contact_id_int if contact_id_int is not None else contact_respond_io_id,
            "phone": phone,
            "firstName": c_fn or "",
            "lastName": c_ln or "",
        },
        "message": message_block,
        "channel": {
            "id": None,
            "name": "Whatsapp Business",
            "source": "whatsapp_business",
            "meta": None,
            "created_at": None,
            "lastMessageTime": int(time.time()),
            "lastIncomingMessageTime": None,
        },
        "user": user_block,
        "sender": {
            "source": "user",
            "userId": ru_int,
            "teamId": None,
            "workflowId": None,
            "broadcastHistoryId": None,
        },
        "source": "User",
        "crm": {
            "business_table": business_table,
            "business_id": business_id,
            "space_id": space_id,
        },
    }
    return [envelope]


def enqueue_crm_chat_outbound_webhook(
    db: Session,
    *,
    business_table: str,
    business_id: str,
    contact_respond_io_id: str,
    message_text: str,
    respond_api_response: Optional[dict],
    space_id: Optional[str],
    crm_sender_user_id: Optional[str],
    respond_user_id_fallback: str,
    assignee_respond_user_id: Optional[str] = None,
) -> None:
    """Create integration log and POST the webhook asynchronously (daemon thread; non-blocking)."""
    url = get_n8n_crm_chat_outbound_webhook_url(db)
    if not url:
        return

    sender: Optional[User] = None
    if crm_sender_user_id and str(crm_sender_user_id).strip():
        sender = db.query(User).filter(User.id == str(crm_sender_user_id).strip()).first()
    rc = (
        db.query(RespondContact)
        .filter(RespondContact.respond_io_id == str(contact_respond_io_id).strip())
        .first()
    )

    payload_list = build_crm_chat_outbound_payload(
        contact_respond_io_id=contact_respond_io_id,
        message_text=message_text,
        respond_api_response=respond_api_response,
        space_id=space_id,
        business_table=business_table,
        business_id=business_id,
        rc=rc,
        sender=sender,
        respond_user_id_for_payload=respond_user_id_fallback,
        assignee_respond_user_id=assignee_respond_user_id,
    )

    # AC-J6: the shared secret rides on the log row because that is what the
    # sender (initial POST and any manual resubmit alike) reads its headers
    # from, so every caller of this function emits it uniformly.
    auth_headers = crm_webhook_auth_headers()

    log_service = IntegrationLogService(db)
    integration_log = log_service.create_integration_log(
        IntegrationLogCreate(
            integration_channel="n8n_crm_chat_outbound",
            business_table=business_table,
            business_id=str(business_id),
            external_reference=str(contact_respond_io_id),
            direction="outbound",
            endpoint=url,
            http_method="POST",
            status="pending",
            request_headers=json.dumps(auth_headers) if auth_headers else None,
            created_by=str(crm_sender_user_id).strip() if crm_sender_user_id else None,
        ),
        request_payload_dict=payload_list,
    )
    log_id = str(integration_log.id)

    def send_async() -> None:
        send_crm_chat_outbound_webhook_for_log(log_id)

    threading.Thread(target=send_async, daemon=True).start()


def resolve_sender_respond_user_id(
    db: Session, crm_sender_user_id: Optional[str]
) -> Optional[str]:
    """Respond user id mapped to the CRM staff member who pressed Send.

    None when the staff member has no mapping, or when the mapping was filled
    with a CRM ``users.id`` UUID - which is not a Respond user id and must never
    reach n8n (it evaluates ``user.id.toString()`` against Respond's own users).
    """
    if not crm_sender_user_id or not str(crm_sender_user_id).strip():
        return None
    user = db.query(User).filter(User.id == str(crm_sender_user_id).strip()).first()
    respond_id = str(getattr(user, "respond_user_id", None) or "").strip() if user else ""
    if not respond_id or _is_crm_user_uuid(respond_id):
        return None
    return respond_id


def notify_human_ticket_send(
    db: Session,
    *,
    tracking_id: str,
    contact_respond_io_id: str,
    message_text: str,
    respond_api_response: Optional[dict],
    sender_user_id: Optional[str],
) -> bool:
    """Signal n8n that a HUMAN replied from a ticket drawer (UAC AC-J1/J2/J3).

    A CRM API send and a bot send are indistinguishable in Respond's own webhook
    payload (both ``source: "Developer API"``, ``user: null``), so the
    Respond-trigger route can never carry this signal. ``respond-send-user``
    already has a second, plain-webhook trigger with a ``source == "User"`` gate;
    this is the CRM half of it - the drawer send path just never wired in. n8n
    uses it to set ``is_human_intervened`` and arm the ht timeout lane, exactly
    as a manual reply from the Respond app does.

    Called ONCE per drawer send (one staff action = one intervention signal),
    only from the human ticket paths - never from bot flows, notification tasks
    or the shared chat-panel send, which carry no human-reply meaning.

    Best-effort post-commit: the message has ALREADY reached the contact, so
    every failure here is caught and warned. Returns True when the webhook was
    handed off, False when it was skipped (AC-J3: an unmapped sender is skipped
    rather than sent with a null/fake ``user.id``, which throws inside n8n).
    """
    try:
        respond_user_id = resolve_sender_respond_user_id(db, sender_user_id)
        if not respond_user_id:
            logger.warning(
                "respond-send-user webhook skipped for ticket %s: sender %s has no "
                "mapped Respond user id",
                tracking_id,
                sender_user_id,
            )
            return False
        enqueue_crm_chat_outbound_webhook(
            db,
            business_table=HUMAN_TICKET_BUSINESS_TABLE,
            business_id=str(tracking_id),
            contact_respond_io_id=str(contact_respond_io_id),
            message_text=message_text or "",
            respond_api_response=(
                respond_api_response if isinstance(respond_api_response, dict) else None
            ),
            space_id=None,
            crm_sender_user_id=str(sender_user_id) if sender_user_id else None,
            # The acting agent on a drawer send is the SENDER, not necessarily the
            # ticket's assignee (a colleague can answer). Pin it on both inputs so
            # the payload cannot fall back to anything else.
            respond_user_id_fallback=respond_user_id,
            assignee_respond_user_id=respond_user_id,
        )
        return True
    except Exception:  # noqa: BLE001 - the contact already has the message
        logger.warning(
            "respond-send-user webhook failed for ticket %s", tracking_id, exc_info=True
        )
        return False
