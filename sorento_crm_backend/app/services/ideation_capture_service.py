"""The one-message ideation capture turn (IDEATION-CAPTURE, PLAN-ideation-capture-02oct.md 4a).

`POST /external/ideation/turn` calls `handle_capture_turn`. One message becomes one idea:
no draft, no review step, no media lookback. Per turn:

  1. the access gate: the sender must be a linked, active CRM user holding
     `ideation.board.view` (Q2), else nothing is created;
  2. a held similar-list (`session_vars.ideation.status == "similar_offered"`): a bare number
     answers with that idea's link, NEW creates from the HELD message, anything else is a
     fresh message;
  3. a fresh message: the extractor, then ss "similar own ideas"; any hit holds the message and
     offers the numbered list, no hit creates the idea at once and replies with its CRM link and
     the fields it did not catch.

Every reply goes through `ideation_capture_replies.render_reply`; the language is the
extractor's reading of the message (a held list keeps the language of the ORIGINAL message).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.access import RespondContact
from app.models.user import User
from app.services.chat_exchanges import exchange_text, recent_exchanges
from app.services.chatbot_reply_copy import FALLBACK_LANGUAGES
from app.services.conversation_variables_service import overwrite_for_contact
from app.services.ideation_capture_replies import render_reply
from app.services.ideation_gateway_service import upload_idea_attachment, user_for_requester
from app.services.ideation_extractor import (
    IdeateExtraction,
    clean_use_cases,
    extract_ideate_turn,
    normalise_field_value,
    normalise_title,
)
from app.services.ideation_turn_service import (
    IdeationServiceError,
    _TIMEOUT_SECONDS,
    _derive_display_name,
    _get_contact_row,
    _now_iso,
    _parse_iso,
    _resolve_ideation_config,
)
from app.services.submission_types import SUBMISSION_TYPES, normalise_type, ss_fields_for_type
from app.services.user_service import UserPermissionService

logger = logging.getLogger(__name__)

_SIMILAR_OWN_PATH = "/ideation/intake/ideas/similar-own"
_CREATE_PATH = "/ideation/intake/ideas"
_VIEW_PERMISSION = "ideation.board.view"
#: Files through the assistant and opens nothing else (a dealer's own user, WA-COMPLAINT-INTAKE D-1).
SUBMIT_PERMISSION = "ideation.ideas.submit"
#: The one role a dealer's own CRM user gets (D-3): non-staff, so it neither signs in (D-7) nor turns
#: the contact into a staff principal (D-8).
_DEALER_ROLE = "portal_user"
_HOLD_MAX_AGE = timedelta(hours=24)
_MAX_SIMILAR = 3
_PHOTOS = "Photos or files"
#: What the one message may not have given, in the order the reply lists it. The names stay
#: English in every language (owner: "exact"). `use_cases` is a list on the payload; the
#: other two are strings.
_OPTIONAL_FIELDS: tuple[tuple[str, str], ...] = (
    ("desired_outcome", "Desired outcome"),
    ("use_cases", "Use cases"),
    ("current_workaround", "Current workaround"),
)
#: The required field of every type in `submission_types` (today `problem` for idea and issue alike).
_REQUIRED_FIELDS: tuple[str, ...] = tuple(sorted({t.required_field for t in SUBMISSION_TYPES.values()}))
#: Chat photos taken onto a new item (UAC P-1): sent in this window before filing, at most this many.
_PHOTO_WINDOW = timedelta(minutes=30)
_MAX_PHOTOS = 10
#: `entity_attachment_links.entity_type` of a chat photo that landed on an ss item (entity_id = the ss
#: idea id): such a photo is never sent again (P-3).
_SENT_LINK = "ss_idea"
_EDGE = " \t\r\n.,!?;:'\"()[]"


def _post_json(base_url: str, api_key: str, path: str, payload: dict[str, Any], what: str) -> dict[str, Any]:
    """POST `payload` to ss `path` (server-to-server HTTP) and return the JSON object.

    Raises `IdeationServiceError` on any transport/HTTP/parse failure so the caller replies
    gracefully instead of 500ing. ss errors are `{"error": {"code", "message"}}`: the code is
    logged, never shown."""
    url = base_url.rstrip("/") + path
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            resp = client.post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except (ValueError, json.JSONDecodeError):
            detail = exc.response.text
        error = detail.get("error") if isinstance(detail, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        logger.warning("ideation %s refused by ss: status=%s code=%s", what, exc.response.status_code, code)
        raise IdeationServiceError(
            f"{what} request failed: {exc}",
            status_code=exc.response.status_code,
            response_detail=detail,
        ) from exc
    except httpx.HTTPError as exc:
        raise IdeationServiceError(f"{what} request failed: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise IdeationServiceError(f"{what} returned a malformed body: {exc}") from exc
    if not isinstance(data, dict):
        raise IdeationServiceError(f"{what} returned a non-object body")
    return data


def call_similar_own(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST ss `/ideation/intake/ideas/similar-own`; the answer is `{matches: [...]}`."""
    return _post_json(base_url, api_key, _SIMILAR_OWN_PATH, payload, "similar-own")


def call_create_idea(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST ss `/ideation/intake/ideas` (flat fields). Success is a 2xx with
    `status == "captured"` and a UUID `idea_id`; anything else is an `IdeationServiceError`."""
    data = _post_json(base_url, api_key, _CREATE_PATH, payload, "create idea")
    if data.get("status") != "captured" or _valid_uuid(data.get("idea_id")) is None:
        raise IdeationServiceError(f"create idea returned an unexpected body: status={data.get('status')!r}")
    return data


def _missing_required(fields: dict[str, str]) -> list[str]:
    """The required fields the message did not give. The one seam for the shared
    required-field helper (LOWSTOCK-FILTER-ASK): its call replaces this body."""
    return [key for key in _REQUIRED_FIELDS if not (fields.get(key) or "").strip()]


def _ss_code(exc: IdeationServiceError) -> Any:
    """The `error.code` of an ss error body (`{"error": {"code", "message"}}`), else None."""
    detail = exc.response_detail if isinstance(exc.response_detail, dict) else {}
    err = detail.get("error")
    return err.get("code") if isinstance(err, dict) else None


def is_unknown_type(exc: IdeationServiceError) -> bool:
    """SS #235: a 422 whose body says `unknown_type` is ss refusing the item's type. Any other 422
    (a validation error, another code, no body) is not."""
    return exc.status_code == 422 and _ss_code(exc) == "unknown_type"


def _ss_failure(exc: IdeationServiceError, step: str, respond_io_id: Any) -> str:
    """Log an ss failure and return its reply kind. A 4xx other than 408/429 will not heal on
    a retry (a scope, key or payload fault), so it is `config_error` at ERROR; everything else
    stays `error` at WARNING."""
    status = exc.status_code
    if isinstance(status, int) and 400 <= status < 500 and status not in (408, 429):
        code = _ss_code(exc)
        logger.error(
            "ideation %s rejected by ss (permanent) status=%s code=%s respond_io_id=%s",
            step, status, code, respond_io_id, exc_info=True,
        )
        return "config_error"
    logger.warning("ideation %s failed for respond_io_id=%s", step, respond_io_id, exc_info=True)
    return "error"


def _valid_uuid(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _crm_link(*segments: str) -> str | None:
    base = (settings.frontend_base_url or "").strip().rstrip("/")
    if not base:
        return None
    return "/".join([base, *segments])


def _idea_link(idea_id: Any) -> str | None:
    clean = _valid_uuid(idea_id)
    return _crm_link("ideas", clean) if clean else None


def _language(value: Any) -> str:
    return value if value in FALLBACK_LANGUAGES else "en"


def _held_pointer(ideation_state: dict[str, Any], is_test: bool) -> dict[str, Any] | None:
    """The similar-list pointer this turn may answer: shaped right, same `is_test`, under 24h."""
    if not isinstance(ideation_state, dict) or ideation_state.get("status") != "similar_offered":
        return None
    if bool(ideation_state.get("is_test")) != bool(is_test):
        return None
    similar = ideation_state.get("similar")
    if (
        not isinstance(similar, list)
        or not all(isinstance(item, dict) for item in similar)
        or not ideation_state.get("message_text")
    ):
        return None
    updated = _parse_iso(ideation_state.get("updated_at"))
    if updated is None or datetime.now(timezone.utc) - updated >= _HOLD_MAX_AGE:
        return None
    return ideation_state


def _asked_pointer(ideation_state: dict[str, Any], is_test: bool) -> dict[str, Any]:
    """The ask-back this turn may answer (round 14): the type it asked for and the message it asked
    about, same `is_test`, under 24h; else {}."""
    if not isinstance(ideation_state, dict) or ideation_state.get("status") != "asked":
        return {}
    if bool(ideation_state.get("is_test")) != bool(is_test):
        return {}
    updated = _parse_iso(ideation_state.get("updated_at"))
    if updated is None or datetime.now(timezone.utc) - updated >= _HOLD_MAX_AGE:
        return {}
    return ideation_state


def _with_exchanges(text: str, exchanges: list[tuple[str, str]]) -> str:
    """The transcript of an issue: the exchanges before it (oldest first), then the user's message, so
    whoever reads the issue sees the answer it complains about (round 14)."""
    if not exchanges:
        return text
    lines = [f"User: {exchange_text(said)}\nAssistant: {exchange_text(answered)}" for said, answered in exchanges]
    return "\n".join(lines) + f"\n\n{text}"


def _access_user(db: Session, respond_io_id: str) -> User | None:
    """The active, untrashed CRM user linked to this contact who may file: the Ideas board or the
    submit permission (D-2)."""
    user = (
        db.query(User)
        .join(RespondContact, RespondContact.id == User.respond_contact_id)
        .filter(RespondContact.respond_io_id == respond_io_id)
        .first()
    )
    if user is None or str(user.status or "").upper() != "ACTIVE" or user.is_trashed:
        return None
    if not UserPermissionService(db).check_user_has_any_permission(user.id, [_VIEW_PERMISSION, SUBMIT_PERMISSION]):
        return None
    return user


def _signs_in(db: Session, user: User | None) -> bool:
    """Can this user open a CRM link? Not a dealer's own user, whose roles are all non-staff (D-7)."""
    from app.services.user_service import only_non_staff_roles

    if user is None:
        return False
    return db.query(User.id).filter(User.id == user.id, only_non_staff_roles()).first() is None


def _linked_user(db: Session, contact_id: str) -> User | None:
    return db.query(User).filter(User.respond_contact_id == str(contact_id)).first()


def _dealer_eligible(db: Session, contact: Any) -> bool:
    """May the assistant give this contact its own CRM user (D-3, D-4)? AI access on for its
    respond.io id (`chatbot_allowed_service.is_allowed`, the bot's own gate), exactly one contact
    row for that id, and not a contact the one staff rule covers (`user_service.is_staff_phone`: a staff
    user's phone, a linked staff user, a sales agent's contact)."""
    from app.services import chatbot_allowed_service
    from app.services.user_service import is_staff_phone

    rid = str(getattr(contact, "respond_io_id", None) or "").strip()
    if not rid or not chatbot_allowed_service.is_allowed(db, rid):
        return False
    if db.query(RespondContact).filter(RespondContact.respond_io_id == rid).count() != 1:
        return False
    return not is_staff_phone(db, str(contact.phone_number or ""), str(contact.id))


def _unlinked_dealer(db: Session, respond_io_id: str) -> RespondContact | None:
    """The eligible contact row for this id when no CRM user is linked to it yet, else None."""
    contact = db.query(RespondContact).filter(RespondContact.respond_io_id == respond_io_id).first()
    if contact is None or not _dealer_eligible(db, contact) or _linked_user(db, contact.id) is not None:
        return None
    return contact


def ensure_dealer_user(db: Session, contact: Any) -> User | None:
    """The contact's own CRM user, created when it has none (D-3): through `UserService.create_user`,
    role `portal_user` only, name and phone from the contact, no password. An existing linked user is
    returned, never a second (D-5, D-6); None for an ineligible contact. The audit names the WhatsApp
    assistant acting for the contact (`actor_type` contact, `auth_method` agent, as the agent's dealer
    writes). `create_user` commits the session. A lost race on the one-user-per-contact index returns
    the winner's user (`create_user` rolled the session back); any other refusal (the phone already on
    another user) is logged with its cause and returns None."""
    from sqlalchemy.exc import IntegrityError

    from app.audit_context import AuditActor, actor_scope
    from app.models.user import UserRole
    from app.schemas.user import UserCreate
    from app.services.error_handler import AppException
    from app.services.user_service import UserService

    if contact is None or not _dealer_eligible(db, contact):
        return None
    linked = _linked_user(db, contact.id)
    if linked is not None:
        return linked
    role = db.query(UserRole).filter(UserRole.slug == _DEALER_ROLE).first()
    if role is None:
        logger.error("ideation: role %s is missing, no dealer user created", _DEALER_ROLE)
        return None
    actor = AuditActor(
        actor_type="contact", auth_method="agent", contact_id=str(contact.id), tool_name="whatsapp_assistant"
    )
    try:
        with actor_scope(actor, db=db):
            return UserService(db).create_user(
                UserCreate(name=contact.name, respond_contact_id=str(contact.id), role_ids=[role.id])
            )
    except (AppException, IntegrityError) as exc:
        winner = _linked_user(db, contact.id)
        if winner is None:
            logger.warning(
                "ideation: dealer user not created for contact %s: %s %s",
                contact.id, getattr(exc, "code", type(exc).__name__), getattr(exc, "message", exc),
            )
        return winner


#: How recent the contact's own inbound message must be for its turn to create a dealer user.
_OWN_MESSAGE_WINDOW = timedelta(minutes=10)


def _is_own_latest_message(db: Session, respond_io_id: str, message_text: str) -> bool:
    """Is `message_text` this contact's own latest inbound WhatsApp message (a live chatbot turn of the
    contact in the last 10 minutes, its text the respond.io envelope `message.message.message.text`)?
    A turn with no text (a photo sent after the words) is skipped. A dealer files only then (round 6,
    should-fix 1; round 7): a call naming a contact, with a text that contact never sent, files nothing."""
    from sqlalchemy import func

    from app.models.chatbot_turn import ChatbotTurn

    text = ChatbotTurn.envelope["message"]["message"]["message"]["text"].astext
    latest = (
        db.query(text)
        .filter(
            ChatbotTurn.contact_respond_id == respond_io_id,
            ChatbotTurn.is_test.is_(False),
            ChatbotTurn.ingress != "console",
            ChatbotTurn.created_at >= datetime.now(timezone.utc) - _OWN_MESSAGE_WINDOW,
            func.coalesce(func.btrim(text), "") != "",
        )
        .order_by(ChatbotTurn.created_at.desc())
        .limit(1)
        .scalar()
    )
    return latest is not None and latest.strip() == (message_text or "").strip()


def _missing_list(sent: dict[str, Any], photos: int = 0) -> list[str]:
    """What the CRM did not send, in the reply's order (ss returns no `captured`). Photos are
    missing unless chat photos landed on the item."""
    missing = [label for key, label in _OPTIONAL_FIELDS if not sent.get(key)]
    return missing if photos else [*missing, _PHOTOS]


def item_title(title: str, fields: dict[str, str]) -> str:
    """The item's title: the given one, else the problem statement cut to a label (round 13: a filed item
    always carries a title, owner 14 Nov). "" only while there is no problem statement."""
    return title or normalise_title(fields.get("problem", ""))


def build_create_payload(
    config: Any,
    *,
    user_id: Any,
    contact: Any,
    name: str | None,
    fields: dict[str, str],
    title: str,
    use_cases: list[str],
    source_text: str,
    intake_ref: str,
    is_test: bool,
    submission_type: str | None = "idea",
) -> dict[str, Any]:
    """The ss create payload: the one builder the WhatsApp capture and the agent's idea tool share.
    The type rides on `ss_fields_for_type` (an idea adds nothing, so its payload is unchanged)."""
    payload: dict[str, Any] = {
        "product_id": config.product_id,
        "problem": fields.get("problem", ""),
        "submitter_crm_user_id": user_id,
        "submitter_phone": contact.phone_number,
        "raw_transcript": source_text,
        "is_test": bool(is_test),
        "intake_ref": intake_ref,
    }
    for key in ("desired_outcome", "current_workaround"):
        if fields.get(key):
            payload[key] = fields[key]
    if use_cases:
        payload["use_cases"] = use_cases
    if name:
        payload["submitter_name"] = name
    if title := item_title(title, fields):
        payload["title"] = title
    if contact.submitter_tier:
        payload["submitter_tier"] = contact.submitter_tier
    payload.update(ss_fields_for_type(submission_type))
    return payload


def _naive_utc(value: datetime) -> datetime:
    """`attachments` timestamps are naive UTC."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _chat_photos(db: Session, user_id: Any) -> list[Any]:
    """The images the user's linked contact sent in chat that would go onto a new item now: the media
    lane's (`media_tasks._store_media_bytes`: attachments linked to a `chatbot_turn`, uploaded by the
    contact), sent in the last 30 minutes, not already on an item (`_SENT_LINK` link), newest first, at
    most 10. One selection for the proposal's count and the attach."""
    from sqlalchemy import exists
    from sqlalchemy.orm import aliased

    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    contact_id = db.query(User.respond_contact_id).filter(User.id == str(user_id)).scalar()
    if not contact_id:
        return []
    sent = aliased(EntityAttachmentLink)
    return (
        db.query(Attachment)
        .join(EntityAttachmentLink, EntityAttachmentLink.attachment_id == Attachment.id)
        .filter(
            EntityAttachmentLink.entity_type == "chatbot_turn",
            Attachment.uploaded_by_contact_id == contact_id,
            Attachment.mime_type.like("image/%"),
            Attachment.is_deleted.is_(False),
            Attachment.uploaded_at > _naive_utc(datetime.now(timezone.utc) - _PHOTO_WINDOW),
            ~exists().where(sent.attachment_id == Attachment.id, sent.entity_type == _SENT_LINK),
        )
        .order_by(Attachment.uploaded_at.desc())
        .limit(_MAX_PHOTOS)
        .all()
    )


def count_chat_photos(db: Session, *, user_id: Any) -> int:
    """How many chat photos `attach_chat_photos` would send now (a proposal states it); 0 on any error."""
    try:
        with db.begin_nested():
            return len(_chat_photos(db, user_id))
    except Exception:  # noqa: BLE001 - a count never fails a proposal
        logger.warning("ideation: chat photos could not be counted", exc_info=True)
        return 0


def attach_chat_photos(db: Session, *, user_id: Any, idea_id: Any) -> int:
    """Upload the user's chat photos (`_chat_photos`) onto the new item, as that user (UAC P-1..P-3), and
    return how many landed. The one function the bot lane and the agent tool call after a LIVE create
    (a test item gets none). Each goes through `ideation_gateway_service.upload_idea_attachment`, the
    staff upload route's own function; a photo that landed is linked to the item (`_SENT_LINK`), so it
    is never sent again. Any error is logged and ends the step: the item is already filed (P-2)."""
    from app.services.entity_attachment_service import EntityAttachmentService
    from app.services.resources_service import AttachmentService

    try:
        with db.begin_nested():
            photos = _chat_photos(db, user_id)
            as_user = user_for_requester(db, str(user_id)) if photos else None
    except Exception:  # noqa: BLE001 - a photo never fails the filing (P-2)
        logger.warning("ideation: chat photos not sent to item %s", idea_id, exc_info=True)
        return 0
    landed = 0
    for photo in photos:
        try:
            upload_idea_attachment(
                db,
                as_user,
                str(idea_id),
                photo.original_filename or photo.stored_filename or "photo",
                AttachmentService(db).get_file_content_for(photo),
                photo.mime_type,
            )
        except Exception:  # noqa: BLE001 - a photo never fails the filing (P-2)
            logger.warning("ideation: chat photo %s did not reach item %s", photo.id, idea_id, exc_info=True)
            continue
        landed += 1
        try:
            with db.begin_nested():
                EntityAttachmentService(db).link_existing_attachment(
                    _SENT_LINK, str(idea_id), str(photo.id), created_by=str(user_id)
                )
        except Exception:  # noqa: BLE001
            logger.warning("ideation: chat photo %s landed but was not marked sent", photo.id, exc_info=True)
    return landed


def handle_capture_turn(
    db: Session,
    *,
    respond_io_id: str,
    message_text: str,
    submitter_name: str | None = None,
    session_vars_in: dict[str, Any] | None = None,
    is_test: bool = False,
    ask_reply: bool = False,
) -> dict[str, Any]:
    """Handle one ideate turn. Returns `{status, reply_text, link?, session_vars, offered_media}`;
    `session_vars` is the full updated blob. A test turn never persists it. `language` is the one
    the reply was written in. `ask_reply` marks an answer to the ask-back."""
    contact = _get_contact_row(db, respond_io_id)
    session_vars = contact.session_vars
    if is_test:
        # A dry run carries its own pointer (it is never persisted): the caller's first.
        caller_sv = session_vars_in or {}
        ideation_state = (
            caller_sv.get("ideation")
            or (caller_sv.get("variables") or {}).get("ideation")
            or session_vars.get("ideation")
            or {}
        )
    else:
        # A live turn trusts only what this service persisted, in the contact's own row.
        ideation_state = session_vars.get("ideation") or {}
    held = _held_pointer(ideation_state, is_test)
    asked = _asked_pointer(ideation_state, is_test) if ask_reply else {}
    text_in = (message_text or "").strip()
    exchanges: list[tuple[str, str]] = []

    def finish(
        status: str,
        kind: str,
        facts: dict[str, Any],
        language: str,
        *,
        pointer: dict[str, Any] | None = None,
        persist: bool = True,
        link: str | None = None,
        user_message: str = text_in,
    ) -> dict[str, Any]:
        # A live write re-reads the row first: the extractor and the ss calls run in between, and
        # whatever another writer landed meanwhile must survive. Only `ideation` is this turn's.
        writes = persist and not is_test
        # The raw row, not get_for_contact: that one migrates `focus` on read and must not write it.
        base = _get_contact_row(db, respond_io_id).session_vars if writes else session_vars
        new_sv = dict(base)
        new_sv.pop("ideation", None)
        if pointer:
            new_sv["ideation"] = pointer
        if writes:
            overwrite_for_contact(db, respond_io_id=respond_io_id, state=new_sv)
        out: dict[str, Any] = {
            "status": status,
            "reply_text": render_reply(kind, facts, user_message=user_message, language=language, db=db),
            "session_vars": new_sv,
            "offered_media": [],
            "language": language,
        }
        if link:
            out["link"] = link
        return out

    # A bare number or NEW answers the held list; neither needs the extractor.
    choice: str | int | None = None
    if held is not None:
        token = text_in.strip(_EDGE)
        if token.isdigit() and 1 <= int(token) <= len(held["similar"]):
            choice = int(token)
        elif token.lower() == "new":
            choice = "new"

    extraction: IdeateExtraction | None = None
    kept_pointer: dict[str, Any] | None = None
    if choice is None:
        # Fresh message (a held list is dropped). The extractor also reads the language, so it
        # runs before the gates and the gate replies can follow it.
        # The contact's last exchanges, under the parser's scopes: a complaint about the assistant's
        # last answer is read against that answer (round 14).
        exchanges = recent_exchanges(
            db, contact_respond_id=respond_io_id, ingress="console" if is_test else None, is_test=is_test, limit=2
        )
        try:
            extraction = extract_ideate_turn(db, message_text=text_in, recent_exchanges=exchanges)
        except Exception:  # noqa: BLE001 - a failed read is answered, never a 500
            logger.warning("ideation extractor raised for respond_io_id=%s", respond_io_id, exc_info=True)
            extraction = IdeateExtraction(failed=True)
        # A failed read keeps whatever list was held: nothing about the message is known, so
        # its reply follows the held list's language.
        kept_pointer = held
        language = _language(extraction.language or (held or {}).get("language"))
        held = None
    else:
        language = _language(held.get("language"))

    config = _resolve_ideation_config(db)
    if not config.is_ready:
        return finish("unconfigured", "unconfigured", {}, language, pointer=held, persist=False)

    user = _access_user(db, respond_io_id)
    # An eligible dealer with no CRM user yet gets one, but only once this turn really files (D-4).
    dealer = _unlinked_dealer(db, respond_io_id) if user is None else None
    # An existing dealer-own user (no staff role) is held to the same rules as a new dealer (round 7, 8).
    dealer_own = user is not None and not _signs_in(db, user)
    if (dealer is not None or dealer_own) and is_test:
        return finish("test_turn", "test_turn", {}, language, persist=False)
    if dealer is not None and not _is_own_latest_message(db, respond_io_id, text_in):
        dealer = None
    if dealer_own and not _is_own_latest_message(db, respond_io_id, text_in):
        user = None
    if user is None and dealer is None:
        return finish("no_access", "no_access", {}, language)

    if isinstance(choice, int):
        idea = held["similar"][choice - 1]
        facts = {
            "idea_number": idea.get("idea_number"),
            "title": idea.get("title"),
            "link": _idea_link(idea.get("idea_id")) if _signs_in(db, user) else None,
        }
        return finish("similar_picked", "similar_picked", facts, language)

    if choice == "new":
        # Create from the HELD message: its fields, title and intake_ref ride on the pointer.
        fields = dict(held.get("fields") or {})
        title = str(held.get("title") or "")
        use_cases = clean_use_cases(held.get("use_cases"))
        source_text = held["message_text"]
        intake_ref = _valid_uuid(held.get("intake_ref")) or str(uuid.uuid4())
        submission_type = normalise_type(held.get("type"))
    else:
        assert extraction is not None
        if extraction.failed:
            # AI-KEY-PER-PROVIDER: an extraction that could not run (provider or key error,
            # timeout) says nothing about the message. It is not "no idea": no ask-back, no
            # give-up, the session state is left as it was, and the reply says what happened.
            logger.warning(
                "ideation capture: extraction failed, replying read_failed respond_io_id=%s",
                respond_io_id,
            )
            return finish("read_failed", "read_failed", {}, language, pointer=kept_pointer, persist=False)
        source_text = text_in
        fields = {
            key: cleaned
            for key, value in extraction.fields.items()
            if (cleaned := normalise_field_value(key, value))
        }
        title = normalise_title(extraction.title)
        use_cases = list(extraction.use_cases)
        submission_type = normalise_type(extraction.type)
        if asked.get("type") == "issue":
            # The ask was for an issue: its answer files as that issue, whatever type it reads as (review N4).
            submission_type = "issue"
        issue_answer = ask_reply and "issue" in (submission_type, asked.get("type"))
        if issue_answer and extraction.review_action == "cancel":
            # Review B1: a cancel ends the issue ask. Nothing is filed and the held ask is dropped.
            return finish("cancelled", "cancelled", {"type": "issue"}, language)
        # An intent-only message ("I have an idea") carries no idea whatever the extractor
        # wrote into problem, so problem is not counted when has_idea is False.
        checked = (
            {k: v for k, v in fields.items() if k != "problem"}
            if extraction.has_idea is False
            else fields
        )
        if _missing_required(checked) and issue_answer:
            # Round 14: an issue flow asks once and never gives up. The answer to the ask, with no
            # problem in it, files the issue in the user's own words (this answer and the message asked about).
            said = [t for t in (str(asked.get("message_text") or "").strip(), text_in) if t]
            words = "\n".join(dict.fromkeys(said))
            if not words:
                return finish("ask_idea_gave_up", "ask_idea_gave_up", {"type": "issue"}, language)
            fields = {**fields, "problem": normalise_field_value("problem", words)}
            submission_type = "issue"
            source_text = words
        elif _missing_required(checked):
            if ask_reply:
                # The user answered the ask-back and still gave no idea: end the ask with a
                # statement, never a second identical question.
                return finish("ask_idea_gave_up", "ask_idea_gave_up", {}, language)
            # An issue ask remembers the message it asked about, so the answer files the issue (round 14).
            # An idea ask keeps nothing, as before.
            asking = {
                "status": "asked", "type": "issue", "message_text": text_in,
                "updated_at": _now_iso(), "is_test": bool(is_test),
            } if submission_type == "issue" else None
            return finish("ask_idea", "ask_idea", {"type": submission_type}, language, pointer=asking)
        if submission_type == "issue":
            source_text = _with_exchanges(source_text, exchanges)
        # Minted once the create is decided; a list offer keeps it so NEW (even retried after
        # an ss failure) lands on the same idea.
        intake_ref = str(uuid.uuid4())

        # A dealer with no user yet owns no items in ss: nothing to look up.
        found: dict[str, Any] = {"matches": []}
        if user is not None:
            try:
                found = call_similar_own(
                    config.base_url,
                    config.api_key,
                    {
                        "product_id": config.product_id,
                        "text": text_in,
                        "submitter_crm_user_id": user.id,
                        "submitter_phone": contact.phone_number,
                        "is_test": bool(is_test),
                    },
                )
            except IdeationServiceError as exc:
                kind = _ss_failure(exc, "similar-own", respond_io_id)
                return finish(kind, kind, {}, language, persist=False)

        raw = [m for m in (found.get("matches") or []) if isinstance(m, dict)]
        shown = [
            {
                "idea_id": clean,
                "idea_number": m.get("idea_number"),
                "title": str(m.get("title") or ""),
            }
            for m in raw
            if (clean := _valid_uuid(m.get("idea_id")))
        ][:_MAX_SIMILAR]
        if shown:
            links = _signs_in(db, user)
            facts = {
                "similar": [{**s, "link": _idea_link(s["idea_id"]) if links else None} for s in shown],
                # ss returns no total: a full page of 3 may be hiding more.
                "see_all": _crm_link("ideas?view=mine") if links and len(raw) >= _MAX_SIMILAR else None,
            }
            pointer: dict[str, Any] = {
                "status": "similar_offered",
                "message_text": text_in,
                "fields": fields,
                "title": title,
                "use_cases": use_cases,
                "similar": shown,
                "intake_ref": intake_ref,
                "updated_at": _now_iso(),
                "is_test": bool(is_test),
                "type": submission_type,
            }
            if extraction.language in FALLBACK_LANGUAGES:
                pointer["language"] = extraction.language
            return finish("similar_offered", "similar_offered", facts, language, pointer=pointer)

    if user is None:
        # The dealer's own user, created only now that this turn really files (D-4).
        if ensure_dealer_user(db, dealer) is not None:
            user = _access_user(db, respond_io_id)
        if user is None:
            logger.warning("ideation: dealer %s cannot file (no user or no submit permission)", respond_io_id)
            return finish("account_failed", "account_failed", {}, language, pointer=held, persist=False)

    payload = build_create_payload(
        config,
        user_id=user.id,
        contact=contact,
        name=contact.display_name or _derive_display_name(submitter_name, None, None),
        fields=fields,
        title=title,
        use_cases=use_cases,
        source_text=source_text,
        intake_ref=intake_ref,
        is_test=is_test,
        submission_type=submission_type,
    )

    try:
        result = call_create_idea(config.base_url, config.api_key, payload)
    except IdeationServiceError as exc:
        if is_unknown_type(exc):
            # SS #235: ss refuses the item's type (422 `unknown_type`). Plain words, no retry; never
            # the "set up wrong" reply. Any other 422 is a permanent fault and goes through _ss_failure.
            logger.warning(
                "ideation capture create refused by ss: status=422 code=unknown_type respond_io_id=%s",
                respond_io_id,
            )
            kind = "type_refused"
        else:
            kind = _ss_failure(exc, "capture create", respond_io_id)
        return finish(kind, kind, {}, language, pointer=held, persist=False)

    # The CRM link is built here from the id; ss's public `link` is never relayed. A dealer's own
    # user cannot sign in to the CRM, so its reply carries none.
    link = _idea_link(result.get("idea_id")) if _signs_in(db, user) else None
    # A test item gets no photos (I-5).
    photos = 0 if is_test else attach_chat_photos(db, user_id=user.id, idea_id=result.get("idea_id"))
    facts = {
        "idea_number": result.get("idea_number"),
        # The title the CRM sent (round 13: the reply uses the payload's value), else what ss echoed.
        "title": payload.get("title") or result.get("title"),
        "link": link,
        "missing": _missing_list(payload, photos),
        "type": submission_type,
        "photos": photos,
    }
    return finish("complete", "complete", facts, language, link=link)
