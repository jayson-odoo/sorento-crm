# Tail: persist the five-key session shape (PLAN-chatbot-turn-rearch.md "Tail",
# AC-1532). `pending' = composer.question` exactly (or none); the FOR UPDATE write seam
# is the already-committed `conversation_variables_service.overwrite_for_contact` (its
# own SQL is `SELECT id FROM respond_contacts WHERE respond_io_id = :cid FOR UPDATE`).
#
# The offer carriers, the answer-spending helper and the re-arm markers the old tail
# needed are all gone: a question reaches the next turn ONLY as `open_question`, written
# here from the composer's own question object, so there is nothing left to carry.
from __future__ import annotations

from typing import Any

from app.services.conversation_variables_service import overwrite_for_contact
from app.services.chatbot.turn.pending import to_wire
from app.services.chatbot.turn.state import State, focus_to_wire


def persist(state: State, answer: Any, ctx: Any) -> dict[str, Any]:
    db = getattr(ctx, "db", None)
    respond_io_id = getattr(ctx, "contact_respond_id", None)

    payload = {
        "focus": focus_to_wire(state.focus),
        "open_question": to_wire(getattr(answer, "question", None)),
        "ideation": getattr(ctx, "ideation", None),
        "access_levels": getattr(ctx, "access_levels", []) or [],
        "contains_flyer": bool(getattr(ctx, "contains_flyer", False)),
    }

    return overwrite_for_contact(db, respond_io_id=respond_io_id, state=payload)
