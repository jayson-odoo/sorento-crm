"""WA-USERNAME-CONTACTS: a WhatsApp username-only contact shares a phone and joins its access.

Core service (never imports `app.services.chatbot`). The engine gate decides WHEN this runs;
this module holds rule 3 (which card is an ownership proof), the phone match and the
Respond.io + CRM writes. Every Respond.io call goes through `RespondClient` for the default
workspace, and the CRM is written only after the Respond.io step succeeded, so a failure
leaves nothing half-linked. Plan: documentation/plans/contacts/PLAN-wa-username-contacts-26oct.md.
"""
from __future__ import annotations

import logging
import re
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

# A phone-shaped run in free text (an exception message); masked before it reaches the outbox.
_PHONE_RE = re.compile(r"\+?\d{8,15}")

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
    card), a non-empty phone, and a PRESENT `channel.meta.wa_id` naming the same number. The
    caller still owes the signed-ingress check (`envelope.ingress == DIRECT_INGRESS`); this
    reads the body only.
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
    if wa_id in (None, "") or normalize_msisdn(wa_id) != phone:
        return None
    return phone


def respond_client(db: Session):
    """The default-workspace client; the one seam the engine tests replace."""
    from app.services.integration_service import RespondClient

    return RespondClient()


def _outbox(
    db: Session,
    *,
    identifier: str,
    business_id: str,
    status: str,
    request_payload: dict,
    response: Any = None,
    error: Optional[Exception] = None,
) -> None:
    """One `integration_logs` row for a customer-facing send (the Respond outbox), written on
    success AND failure like every other Respond.io send. The phone is masked: an exception
    text can carry it."""
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService

    resp = getattr(error, "response", None)
    try:
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="chatbot_turns",
                business_id=business_id,
                external_reference=identifier,
                direction="outbound",
                endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message",
                http_method="POST",
                status=status,
                status_code=getattr(resp, "status_code", None),
                response_payload=str(response)[:50000] if response else None,
                error_message=_PHONE_RE.sub("[phone]", str(error))[:2000] if error else None,
            ),
            request_payload_dict=request_payload,
        )
    except Exception:  # noqa: BLE001 - the send already happened; the row must not undo it
        db.rollback()
        logger.warning("wa_phone_link: could not write the send log", exc_info=True)


def send_ask(db: Session, *, contact_respond_id: str, turn_id: Optional[str] = None) -> bool:
    """Send the `wa_phone_share` template. False when no template is mapped for it (nothing
    was attempted, so no outbox row); any other error is logged to the outbox and raised."""
    business_id = turn_id or contact_respond_id
    try:
        result = respond_messaging_service.send_template_for_use_case(
            db, identifier=contact_respond_id, use_case=WA_PHONE_SHARE_USE_CASE, context_vars={}
        )
    except respond_messaging_service.TemplateSendSkipped:
        return False
    except Exception as e:
        _outbox(
            db,
            identifier=contact_respond_id,
            business_id=business_id,
            status="failed",
            request_payload=getattr(e, "request_payload", None) or {"use_case": WA_PHONE_SHARE_USE_CASE},
            error=e,
        )
        raise
    result = result if isinstance(result, dict) else {}
    _outbox(
        db,
        identifier=contact_respond_id,
        business_id=business_id,
        status="success",
        request_payload=result.get("request_payload") or {"use_case": WA_PHONE_SHARE_USE_CASE},
        response=result.get("response"),
    )
    return True


def send_verified(db: Session, client: Any, *, identifier: str, turn_id: Optional[str] = None) -> bool:
    """The verified line to the surviving contact, with its outbox row. False when the send failed."""
    payload = {"message": {"type": "text", "text": VERIFIED_LINE}}
    business_id = turn_id or identifier
    try:
        response = client.send_message(identifier, VERIFIED_LINE)
    except Exception as e:  # noqa: BLE001 - the link stands; the next message resolves to the row
        logger.warning("wa_phone_link: verified line failed (%s)", _err(e))
        _outbox(db, identifier=identifier, business_id=business_id, status="failed", request_payload=payload, error=e)
        return False
    _outbox(
        db, identifier=identifier, business_id=business_id, status="success", request_payload=payload, response=response
    )
    return True


def _failed(reason: str, survivor: Optional[str] = None, **log_args: Any) -> LinkOutcome:
    """`survivor` is set when the merge already happened: the staff comment must go to the
    contact that still exists."""
    logger.warning("wa_phone_link failed: %s %s", reason, log_args or "")
    return LinkOutcome(status="failed", survivor_respond_id=survivor, reason=reason)


def _merge_survivor(response: Any) -> Optional[str]:
    """The surviving contact id a merge response names (`contactId`, also under `data`), or None."""
    if not isinstance(response, dict):
        return None
    for source in (response, response.get("data")):
        if isinstance(source, dict) and source.get("contactId") not in (None, ""):
            return str(source["contactId"])
    return None


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
        if default_ws is None or str(row.workspace_id) != str(default_ws.id):
            return _failed("the CRM contact for this phone is not on the default workspace", phone=shown)

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
            # Respond.io keeps the OLDER contact whatever the order, so read the survivor.
            survivor = _merge_survivor(client.merge_contacts([int(phone_contact_id), int(contact_respond_id)]))
            if survivor is None:
                again = parse_respond_contact_payload(client.get_contact_by_phone(f"+{num}"))
                survivor = again.get("respond_io_id")
            if survivor is None:
                return _failed("the merge did not name a surviving contact", phone=shown)
            status = "merged"
        elif phone_contact_id is not None:
            status, survivor = "phone_set", str(contact_respond_id)
        else:
            client.update_contact(str(contact_respond_id), {"phone": f"+{num}"})
            status, survivor = "phone_set", str(contact_respond_id)
    except Exception as e:  # noqa: BLE001 - any Respond.io failure is a hand-off, never a half-link
        return _failed(f"Respond.io step failed ({_err(e)})", phone=shown)
    merged_survivor = survivor if status == "merged" else None

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
        return _failed(f"CRM write failed ({_err(e)})", merged_survivor, phone=shown)
    logger.info("wa_phone_link %s phone=%s", status, shown)
    return LinkOutcome(
        status=status,
        survivor_respond_id=survivor,
        contact_pk=str(row.id),
        chatbot_allowed=bool(row.chatbot_allowed),
    )
