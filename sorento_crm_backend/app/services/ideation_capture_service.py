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
from app.services.chatbot_reply_copy import FALLBACK_LANGUAGES
from app.services.conversation_variables_service import overwrite_for_contact
from app.services.ideation_capture_replies import render_reply
from app.services.ideation_extractor import (
    IdeateExtraction,
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
    call_create_idea,
)
from app.services.user_service import UserPermissionService

logger = logging.getLogger(__name__)

_SIMILAR_OWN_PATH = "/ideation/intake/similar-own"
_VIEW_PERMISSION = "ideation.board.view"
_HOLD_MAX_AGE = timedelta(hours=24)
_MAX_SIMILAR = 3
_PHOTOS = "Photos or files"
#: What the one message may not have given, in the order the reply lists it. The names stay
#: English in every language (owner: "exact").
_OPTIONAL_FIELDS: tuple[tuple[str, str], ...] = (
    ("proposed_solution", "Proposed solution"),
    ("impact", "Impact"),
    ("department", "Department"),
)
_REQUIRED_FIELDS: tuple[str, ...] = ("problem",)
_EDGE = " \t\r\n.,!?;:'\"()[]"


def call_similar_own(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to ss `/ideation/intake/similar-own` (server-to-server HTTP).

    Raises `IdeationServiceError` on any transport/HTTP/parse failure so the caller replies
    gracefully instead of 500ing."""
    url = base_url.rstrip("/") + _SIMILAR_OWN_PATH
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
        raise IdeationServiceError(
            f"similar-own request failed: {exc}",
            status_code=exc.response.status_code,
            response_detail=detail,
        ) from exc
    except httpx.HTTPError as exc:
        raise IdeationServiceError(f"similar-own request failed: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise IdeationServiceError(f"similar-own returned a malformed body: {exc}") from exc
    if not isinstance(data, dict):
        raise IdeationServiceError("similar-own returned a non-object body")
    return data


def _missing_required(fields: dict[str, str]) -> list[str]:
    """The required fields the message did not give. The one seam for the shared
    required-field helper (LOWSTOCK-FILTER-ASK): its call replaces this body."""
    return [key for key in _REQUIRED_FIELDS if not (fields.get(key) or "").strip()]


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
    if not isinstance(ideation_state.get("similar"), list) or not ideation_state.get("message_text"):
        return None
    updated = _parse_iso(ideation_state.get("updated_at"))
    if updated is None or datetime.now(timezone.utc) - updated >= _HOLD_MAX_AGE:
        return None
    return ideation_state


def _access_user(db: Session, respond_io_id: str) -> User | None:
    """The active, untrashed CRM user linked to this contact who holds the Ideas permission."""
    user = (
        db.query(User)
        .join(RespondContact, RespondContact.id == User.respond_contact_id)
        .filter(RespondContact.respond_io_id == respond_io_id)
        .first()
    )
    if user is None or str(user.status or "").upper() != "ACTIVE" or user.is_trashed:
        return None
    if not UserPermissionService(db).check_user_has_permission(user.id, _VIEW_PERMISSION):
        return None
    return user


def _missing_list(captured: dict[str, Any]) -> list[str]:
    missing = [label for key, label in _OPTIONAL_FIELDS if not captured.get(key)]
    return [*missing, _PHOTOS]


def handle_capture_turn(
    db: Session,
    *,
    respond_io_id: str,
    message_text: str,
    submitter_name: str | None = None,
    session_vars_in: dict[str, Any] | None = None,
    is_test: bool = False,
) -> dict[str, Any]:
    """Handle one ideate turn. Returns `{status, reply_text, link?, session_vars, offered_media}`;
    `session_vars` is the full updated blob. A test turn never persists it."""
    contact = _get_contact_row(db, respond_io_id)
    session_vars = contact.session_vars
    caller_sv = session_vars_in or {}
    ideation_state = (
        caller_sv.get("ideation")
        or (caller_sv.get("variables") or {}).get("ideation")
        or session_vars.get("ideation")
        or {}
    )
    held = _held_pointer(ideation_state, is_test)
    text_in = (message_text or "").strip()

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
        new_sv = dict(session_vars)
        new_sv.pop("ideation", None)
        if pointer:
            new_sv["ideation"] = pointer
        if persist and not is_test:
            overwrite_for_contact(db, respond_io_id=respond_io_id, state=new_sv)
        out: dict[str, Any] = {
            "status": status,
            "reply_text": render_reply(kind, facts, user_message=user_message, language=language),
            "session_vars": new_sv,
            "offered_media": [],
        }
        if link:
            out["link"] = link
        return out

    # A bare number or NEW answers the held list; the extractor is not needed for either number.
    choice: str | int | None = None
    if held is not None:
        token = text_in.strip(_EDGE)
        if token.isdigit() and 1 <= int(token) <= len(held["similar"]):
            choice = int(token)
        elif token.lower() == "new":
            choice = "new"

    extraction: IdeateExtraction | None = None
    if choice is None:
        # Fresh message (a held list is dropped). The extractor also reads the language, so it
        # runs before the gates and the gate replies can follow it.
        extraction = extract_ideate_turn(db, message_text=text_in)
        language = _language(extraction.language)
        held = None
    elif choice == "new":
        extraction = extract_ideate_turn(db, message_text=held["message_text"])
        language = _language(held.get("language") or extraction.language)
    else:
        language = _language(held.get("language"))

    config = _resolve_ideation_config(db)
    if not config.is_ready:
        return finish("unconfigured", "unconfigured", {}, language, pointer=held, persist=False)

    user = _access_user(db, respond_io_id)
    if user is None:
        return finish("no_access", "no_access", {}, language)

    if isinstance(choice, int):
        idea = held["similar"][choice - 1]
        facts = {
            "idea_number": idea.get("idea_number"),
            "title": idea.get("title"),
            "link": _idea_link(idea.get("id")),
        }
        return finish("similar_picked", "similar_picked", facts, language)

    assert extraction is not None
    source_text = held["message_text"] if choice == "new" else text_in
    fields = {
        key: cleaned
        for key, value in extraction.fields.items()
        if (cleaned := normalise_field_value(key, value))
    }
    title = normalise_title(extraction.title)
    if _missing_required(fields):
        return finish("ask_idea", "ask_idea", {}, language)

    if choice != "new":
        try:
            found = call_similar_own(
                config.base_url,
                config.api_key,
                {
                    "product_id": config.product_id,
                    "submitter_contact_id": contact.phone_number,
                    "crm_user_id": user.id,
                    "title": title,
                    "problem": fields.get("problem", ""),
                    "is_test": bool(is_test),
                },
            )
        except IdeationServiceError:
            logger.warning("ideation similar-own failed for respond_io_id=%s", respond_io_id, exc_info=True)
            return finish("error", "error", {}, language, persist=False)

        raw = [i for i in (found.get("ideas") or []) if isinstance(i, dict)]
        shown = [
            {
                "id": clean,
                "idea_number": i.get("idea_number"),
                "title": str(i.get("title") or ""),
            }
            for i in raw
            if (clean := _valid_uuid(i.get("id")))
        ][:_MAX_SIMILAR]
        if shown:
            try:
                total = int(found.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            facts = {
                "similar": [
                    {**s, "link": _idea_link(s["id"])} for s in shown
                ],
                "see_all": _crm_link("ideas?view=mine") if total > len(raw) else None,
            }
            pointer: dict[str, Any] = {
                "status": "similar_offered",
                "message_text": text_in,
                "similar": shown,
                "updated_at": _now_iso(),
                "is_test": bool(is_test),
            }
            if extraction.language in FALLBACK_LANGUAGES:
                pointer["language"] = extraction.language
            return finish("similar_offered", "similar_offered", facts, language, pointer=pointer)

    payload: dict[str, Any] = {
        "product_id": config.product_id,
        "capture_now": True,
        "crm_user_id": user.id,
        "submitter_contact_id": contact.phone_number,
        "message_text": source_text,
        "raw_transcript": source_text,
        "fields": fields,
        "is_test": bool(is_test),
    }
    name = contact.display_name or _derive_display_name(submitter_name, None, None)
    if name:
        payload["submitter_name"] = name
    if title:
        payload["title"] = title
    if contact.submitter_tier:
        payload["submitter_tier"] = contact.submitter_tier

    try:
        result = call_create_idea(config.base_url, config.api_key, payload)
    except IdeationServiceError:
        logger.warning("ideation capture create failed for respond_io_id=%s", respond_io_id, exc_info=True)
        return finish("error", "error", {}, language, pointer=held, persist=False)
    if result.get("status") != "complete":
        logger.warning("ideation capture create answered %r", result.get("status"))
        return finish("error", "error", {}, language, pointer=held, persist=False)

    link = _idea_link(result.get("id"))
    facts = {
        "idea_number": result.get("idea_number"),
        "title": result.get("title") or title,
        "link": link,
        "missing": _missing_list(result.get("captured") or {}),
    }
    return finish("complete", "complete", facts, language, link=link)
