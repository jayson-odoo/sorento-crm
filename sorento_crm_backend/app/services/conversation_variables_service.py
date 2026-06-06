"""Conversation-state service: plain JSON state on `respond_contacts.session_vars`.

The column holds whatever JSON the caller writes — no turn buffer, no merge,
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
