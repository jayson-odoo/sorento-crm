"""Brain-path service for `ideate` WhatsApp turns (ideation pipeline, D7/D8, §5.1/§5.2).

Flow per turn (see ``documentation/plans/ideation/PLAN-ideation-ideate-intent.md`` §2c):

  1. resolve the default workspace's ``ideation_product_id`` — fail-closed (no
     ``create_idea`` call) if it or the shared-service config is unset (AC-31);
  2. read the contact's ``session_vars.ideation`` pointer (``draft_id``/``status``);
  3. run the sorento brain extractor → ``{ fields, remove, confirm }`` (D-CONFIRM);
  4. build the §5.1 input deterministically (``product_id`` from the binding,
     ``submitter`` = contact phone E.164, ``draft_id`` omitted on turn 1) and call
     shared-service ``create_idea`` over HTTP (server-to-server httpx — NOT MCP);
  5. read-modify-write ``session_vars``: KEEP ``ideation`` on ``collecting``/``review``,
     DELETE it on ``complete``/``duplicate``, preserving every other CRM key (AC-16);
  6. return ``{ status, reply_text, link?, session_vars }`` (the full updated blob).

Resilience: a shared-service outage returns a graceful ``reply_text`` and NEVER
mutates ``session_vars`` (AC-19) — mirrors the "always fail soft on the send path"
posture. Args are built deterministically, so the LLM UUID-arg coercion used on the
agent path is irrelevant here (AC-18).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status as http_status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.conversation_variables_service import (
    _coerce_to_dict,
    overwrite_for_contact,
)
from app.services.ideation_extractor import IdeateExtraction, extract_ideate_turn
from app.services.respond_workspace_service import RespondWorkspaceService

logger = logging.getLogger(__name__)

_CREATE_IDEA_PATH = "/ideation/intake/create-idea"
_TIMEOUT_SECONDS = 15

# create_idea statuses that CLOSE the draft → clear the pointer (§5.2).
_TERMINAL_STATUSES = {"complete", "duplicate"}


class IdeationServiceError(Exception):
    """Raised when the shared-service ``create_idea`` call cannot be completed
    (outage/timeout/HTTP error/malformed body). The caller degrades to a graceful
    reply — never a 500 on the n8n send sub-flow (AC-19)."""


class _ContactState:
    __slots__ = ("phone_number", "session_vars")

    def __init__(self, phone_number: str, session_vars: dict[str, Any]):
        self.phone_number = phone_number
        self.session_vars = session_vars


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_contact_row(db: Session, respond_io_id: str) -> _ContactState:
    """Load the contact's phone (E.164 submitter) + session_vars by respond_io_id.
    404 when no contact matches (n8n only routes ideate turns for known contacts)."""
    row = db.execute(
        text(
            "SELECT phone_number, session_vars FROM respond_contacts "
            "WHERE respond_io_id = :cid"
        ),
        {"cid": respond_io_id},
    ).first()
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Respond contact not found for respond_io_id={respond_io_id!r}.",
        )
    return _ContactState(row.phone_number, _coerce_to_dict(row.session_vars))


def _resolve_product_id(db: Session) -> str | None:
    """The default workspace's shared-service Product binding, or None (fail-closed)."""
    workspace = RespondWorkspaceService(db).get_default()
    if workspace is None:
        return None
    return getattr(workspace, "ideation_product_id", None) or None


def call_create_idea(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST the §5.1 input to shared-service ``create_idea`` (server-to-server HTTP).

    Raises ``IdeationServiceError`` on any transport/HTTP/parse failure so the
    caller can reply gracefully instead of 500ing (AC-19)."""
    url = base_url.rstrip("/") + _CREATE_IDEA_PATH
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            resp = client.post(url, json=payload, headers={"X-API-Key": api_key})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise IdeationServiceError(f"create_idea request failed: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise IdeationServiceError(f"create_idea returned a malformed body: {exc}") from exc
    if not isinstance(data, dict):
        raise IdeationServiceError("create_idea returned a non-object body")
    return data


def _graceful(reply_text: str, session_vars: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {"status": status, "reply_text": reply_text, "session_vars": session_vars}


def handle_turn(
    db: Session,
    *,
    respond_io_id: str,
    message_text: str,
    audio_attachment_ref: str | None = None,
) -> dict[str, Any]:
    """Handle one `ideate` turn. Returns ``{ status, reply_text, link?, session_vars }``.

    ``session_vars`` in the return is always the FULL, updated blob (AC-10)."""
    contact = _get_contact_row(db, respond_io_id)
    session_vars = contact.session_vars
    ideation_state = session_vars.get("ideation") or {}
    draft_id = ideation_state.get("draft_id")
    prior_status = ideation_state.get("status")
    prior_missing = ideation_state.get("missing") or []

    # (1) fail-closed: no product binding or dormant config → no create_idea call.
    product_id = _resolve_product_id(db)
    base_url = settings.ideation_shared_service_url
    api_key = settings.ideation_intake_api_key
    if not product_id or not base_url or not api_key:
        return _graceful(
            "Idea capture isn't set up here yet, so I couldn't log that — please try "
            "again later or reach out to the team.",
            session_vars,
            status="unconfigured",
        )

    # (3) brain extraction (D-CONFIRM): structured update, never free text.
    extraction: IdeateExtraction = extract_ideate_turn(
        db,
        message_text=message_text,
        status=prior_status,
        missing=prior_missing,
    )

    # (4) build the §5.1 input deterministically.
    payload: dict[str, Any] = {
        "product_id": product_id,
        "submitter": contact.phone_number,
        "message_text": message_text,
        "fields": extraction.fields,
        "remove": extraction.remove,
        "confirm": extraction.confirm,
    }
    if audio_attachment_ref:
        payload["audio_attachment_ref"] = audio_attachment_ref
    if draft_id:  # omitted on turn 1 (AC-12); passed through on continuation (AC-13/17)
        payload["draft_id"] = draft_id

    try:
        result = call_create_idea(base_url, api_key, payload)
    except IdeationServiceError:
        logger.warning("ideation create_idea outage for respond_io_id=%s", respond_io_id, exc_info=True)
        return _graceful(
            "Sorry, I couldn't save that idea just now — please try again in a moment.",
            session_vars,
            status="error",
        )

    status_val = str(result.get("status") or "")
    result_draft_id = result.get("draft_id") or draft_id
    reply_text = result.get("reply_text") or ""
    link = result.get("link")

    # (5) read-modify-write: only touch the `ideation` key, preserve all others.
    new_session_vars = dict(session_vars)
    if status_val in _TERMINAL_STATUSES:
        new_session_vars.pop("ideation", None)  # AC-13c/14/15
    else:  # collecting or review → keep the pointer (AC-12/12b/13b)
        new_session_vars["ideation"] = {
            "draft_id": result_draft_id,
            "status": status_val,
            "missing": list(result.get("missing") or []),
            "updated_at": _now_iso(),
        }
    overwrite_for_contact(db, respond_io_id=respond_io_id, state=new_session_vars)

    response: dict[str, Any] = {
        "status": status_val,
        "reply_text": reply_text,
        "session_vars": new_session_vars,
    }
    if link:
        response["link"] = link
    return response
