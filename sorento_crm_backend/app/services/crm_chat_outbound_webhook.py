"""
After CRM sends a WhatsApp/Respond message via API (automation), n8n may not see agent user_id.
POST a Respond.io-shaped payload to a configurable webhook so workflows can run with user + contact context.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.user import User
from app.schemas.integration import IntegrationLogCreate
from app.services.integration_service import IntegrationLogService
from app.services.n8n_webhook_settings import get_n8n_crm_chat_outbound_webhook_url

logger = logging.getLogger(__name__)


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
) -> list[dict[str, Any]]:
    """Single-element array mimicking Respond.io outbound message webhook shape."""
    now_ms = int(time.time() * 1000)
    contact_id_int = _int_or_none(contact_respond_io_id)
    msg_id = _message_id_from_respond_response(respond_api_response) or now_ms

    c_fn, c_ln = _contact_first_last(rc)
    phone = (rc.phone_number if rc else None) or None

    # Agent user block: prefer Respond user id (numeric) for n8n
    ru_int = _int_or_none(getattr(sender, "respond_user_id", None) if sender else None)
    if ru_int is None:
        ru_int = _int_or_none(respond_user_id_for_payload)

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
        "id": ru_int if ru_int is not None else respond_user_id_for_payload,
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
            "userId": ru_int if ru_int is not None else None,
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
) -> None:
    """Create integration log + fire webhook in background (same pattern as attachment webhook)."""
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
    )

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
            created_by=str(crm_sender_user_id).strip() if crm_sender_user_id else None,
        ),
        request_payload_dict=payload_list,
    )
    log_id = str(integration_log.id)

    def send_async() -> None:
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

    threading.Thread(target=send_async, daemon=True).start()
