"""Conversation-state service: plain JSON state on `respond_contacts.session_vars`.

The column holds whatever JSON the caller writes - no turn buffer, no merge,
no sliding window. Reads return the stored dict; writes overwrite it whole.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def _coerce_to_dict(raw: Any) -> dict[str, Any]:
    """Coerce a stored JSONB value into a dict (empty dict on null / malformed)."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def get_for_contact(db: Session, *, respond_io_id: str) -> dict[str, Any]:
    """Return `session_vars` dict for the contact. 404 when no row matches."""
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": respond_io_id},
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Respond contact not found for respond_io_id={respond_io_id!r}.",
        )

    return _coerce_to_dict(row.session_vars)


def overwrite_for_contact(
    db: Session,
    *,
    respond_io_id: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Replace `session_vars` for the contact with `state`. 404 when no row matches."""
    row = db.execute(
        text(
            "SELECT id FROM respond_contacts WHERE respond_io_id = :cid FOR UPDATE"
        ),
        {"cid": respond_io_id},
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Respond contact not found for respond_io_id={respond_io_id!r}.",
        )

    db.execute(
        text(
            "UPDATE respond_contacts SET session_vars = CAST(:s AS jsonb), updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"s": json.dumps(state), "id": row.id},
    )
    db.commit()
    return state


_REFERENCED_STATE_SQL = """
WITH anchor AS (
    SELECT turn_id
    FROM   chat_histories
    WHERE  contact_id = :cid
      AND  message_id = :mid
    ORDER BY sent_at DESC, id DESC
    LIMIT 1
)
SELECT ch.state_trace -> 'after' AS after_state
FROM   chat_histories ch
JOIN   anchor a ON a.turn_id IS NOT NULL AND ch.turn_id = a.turn_id
WHERE  ch.contact_id = :cid
  AND  ch.type = 'incoming'
  AND  ch.state_trace IS NOT NULL
ORDER BY ch.sent_at DESC, ch.id DESC
LIMIT 1
"""


def get_referenced_state(
    db: Session,
    *,
    respond_io_id: str,
    message_id: str,
) -> dict[str, Any] | None:
    """Return a 4-key projection of the quoted turn's post-turn conversation state.

    Resolution: the chat-history row with this (contact, message_id) identifies a TURN
    via `turn_id`; that turn's INCOMING row carries `state_trace`, whose `after` member
    is the state the turn wrote. Returns None on any miss so the caller degrades to the
    immediately-previous state rather than to a stateless baseline.

    Deliberately a PROJECTION, never the raw trace: `before` / `parser_raw` /
    `parser_applied` stay internal, and `last_result_set` / `selection_context` /
    `response` / `access_levels` / `routing` are withheld. Two of those exclusions are
    safety properties, not tidiness: `selection_context` without `last_result_set`
    would resolve a bare pick against the wrong roster (wrong-member assign), and
    `access_levels` must never be re-granted by quoting an older turn.
    """
    row = db.execute(
        text(_REFERENCED_STATE_SQL),
        {"cid": respond_io_id, "mid": message_id},
    ).first()
    if row is None:
        return None
    raw = row.after_state
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    # `after: null` means the turn wrote no state (no-access refusal, LLM fallback).
    # That is a MISS, never `{}` - an empty baseline would WIPE continuity, which is
    # strictly worse than the pre-pointer behaviour.
    if not isinstance(raw, dict):
        return None
    # All four keys are ALWAYS present when non-None: the n8n rebase uses object
    # spread, whose semantics are only exact when `undefined` can never appear.
    return {
        "domain_hint": raw.get("domain_hint"),
        "intent_hint": raw.get("intent_hint"),
        "entities": raw["entities"] if isinstance(raw.get("entities"), list) else [],
        "dym_offer": raw["dym_offer"] if isinstance(raw.get("dym_offer"), dict) else None,
    }


def get_referenced_result_set(
    db: Session,
    *,
    respond_io_id: str,
    message_id: str,
) -> list[Any] | None:
    """Return the `result` set stored on the chat-history message with this
    Respond.io message id for the contact, or None when no match / no result.

    `chat_histories.contact_id` stores the Respond.io contact id, so it joins
    directly against the conversation-variables path param.
    """
    row = db.execute(
        text(
            """
            SELECT result FROM chat_histories
            WHERE contact_id = :cid AND message_id = :mid
            ORDER BY sent_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"cid": respond_io_id, "mid": message_id},
    ).first()
    if row is None:
        return None
    raw = row.result
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    return raw if isinstance(raw, list) else None
