"""WA-USERNAME-CONTACTS: a WhatsApp username-only contact shares a phone and joins its access.

Core service (never imports `app.services.chatbot`). The engine gate decides WHEN this runs;
this module holds rule 3 (which card is an ownership proof), the phone match and the
Respond.io + CRM writes. Every Respond.io call goes through `RespondClient` for the default
workspace, and the CRM is written only after the Respond.io step succeeded, so a failure
leaves nothing half-linked. Plan: documentation/plans/contacts/PLAN-wa-username-contacts-26oct.md.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.schemas.user import RespondContactCreate
from app.services import respond_messaging_service
from app.services.contact_service import parse_respond_contact_payload
from app.services.phone_signin_service import mask
from app.services.phone_utils import normalize_msisdn

logger = logging.getLogger(__name__)

WA_PHONE_SHARE_USE_CASE = "wa_phone_share"

# The line a contact gets once its phone is linked and the CRM lets the AI answer it. A
# module constant, not the chatbot reply-copy registry: that registry is seeded by a
# migration and this flow ships without one.
VERIFIED_LINE = "Phone number verified, you may start using the AI"


@dataclass
class LinkOutcome:
    status: str  # "merged" | "phone_set" | "failed"
    survivor_respond_id: Optional[str] = None
    contact_pk: Optional[str] = None
    chatbot_allowed: bool = False
    reason: Optional[str] = None


def _card(body: dict) -> dict:
    """The Respond.io message block (`message.message`), or {} for any other shape."""
    outer = body.get("message") if isinstance(body, dict) else None
    inner = outer.get("message") if isinstance(outer, dict) else None
    return inner if isinstance(inner, dict) else {}


def is_contact_card(body: dict) -> bool:
    return _card(body).get("type") == "contact"


def accepted_card_phone(body: dict) -> Optional[str]:
    """E.164 digits (no ``+``) of a card the sender tapped to share, else None.

    Accepted = origin `contact_request` (the Share Contact Info button, not a hand-shared
    card), a non-empty phone, and when `channel.meta.wa_id` is present it names the same number.
    """
    inner = _card(body)
    if inner.get("type") != "contact":
        return None
    card = inner.get("contact")
    if not isinstance(card, dict) or card.get("origin") != "contact_request":
        return None
    phone = normalize_msisdn(card.get("phone"))
    if not phone:
        return None
    channel = body.get("channel")
    meta = channel.get("meta") if isinstance(channel, dict) else None
    wa_id = meta.get("wa_id") if isinstance(meta, dict) else None
    if wa_id not in (None, "") and normalize_msisdn(wa_id) != phone:
        return None
    return phone


def respond_client(db: Session):
    """The default-workspace client; the one seam the engine tests replace."""
    from app.services.integration_service import RespondClient

    return RespondClient()


def send_ask(db: Session, *, contact_respond_id: str) -> bool:
    """Send the `wa_phone_share` template. False when no template is mapped for it."""
    try:
        respond_messaging_service.send_template_for_use_case(
            db, identifier=contact_respond_id, use_case=WA_PHONE_SHARE_USE_CASE, context_vars={}
        )
    except respond_messaging_service.TemplateSendSkipped:
        return False
    return True


def _failed(reason: str, **log_args: Any) -> LinkOutcome:
    logger.warning("wa_phone_link failed: %s %s", reason, log_args or "")
    return LinkOutcome(status="failed", reason=reason)


def _err(exc: Exception) -> str:
    """Class and HTTP status only: an exception message can carry the phone (lookup URL)."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return f"{type(exc).__name__} {status}" if status else type(exc).__name__


def link_phone(db: Session, client: Any, *, contact_respond_id: str, phone: str) -> LinkOutcome:
    num = normalize_msisdn(phone) or ""
    shown = mask(num)
    rows = (
        db.query(RespondContact)
        .filter(RespondContact.phone_number.in_([num, f"+{num}"]))
        .limit(2)
        .all()
    )
    if len(rows) > 1:
        return _failed("more than one CRM contact holds this phone", phone=shown)
    row = rows[0] if rows else None
    if row is not None and row.workspace_id is not None:
        from app.services.respond_workspace_service import RespondWorkspaceService

        default_ws = RespondWorkspaceService(db).get_default()
        if default_ws is not None and str(row.workspace_id) != str(default_ws.id):
            return _failed("the CRM contact for this phone is on another workspace", phone=shown)

    # Respond.io step first; nothing below touches the CRM until it has succeeded.
    try:
        phone_contact_id: Optional[str] = None
        phone_contact: dict = {}
        try:
            phone_contact = parse_respond_contact_payload(client.get_contact_by_phone(f"+{num}"))
            phone_contact_id = phone_contact.get("respond_io_id")
        except httpx.HTTPStatusError as e:
            if e.response is None or e.response.status_code != 404:
                raise
        if phone_contact_id is not None and phone_contact_id != str(contact_respond_id):
            client.merge_contacts([int(phone_contact_id), int(contact_respond_id)])
            status, survivor = "merged", phone_contact_id
        elif phone_contact_id is not None:
            status, survivor = "phone_set", str(contact_respond_id)
        else:
            client.update_contact(str(contact_respond_id), {"phone": f"+{num}"})
            status, survivor = "phone_set", str(contact_respond_id)
    except Exception as e:  # noqa: BLE001 - any Respond.io failure is a hand-off, never a half-link
        return _failed(f"Respond.io step failed ({_err(e)})", phone=shown)

    try:
        if row is not None:
            row.respond_io_id = survivor
            db.commit()
        else:
            from app.services.contact_service import ContactService

            names = {k: phone_contact[k] for k in ("first_name", "last_name", "name") if phone_contact.get(k)}
            row = ContactService(db).create_contact(
                RespondContactCreate(phone_number=f"+{num}", respond_io_id=survivor, **names)
            )
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _failed(f"CRM write failed ({_err(e)})", phone=shown)
    logger.info("wa_phone_link %s phone=%s", status, shown)
    return LinkOutcome(
        status=status,
        survivor_respond_id=survivor,
        contact_pk=str(row.id),
        chatbot_allowed=bool(row.chatbot_allowed),
    )
