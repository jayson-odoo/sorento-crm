# Tail: persist the five-key session shape (PLAN-chatbot-turn-rearch.md "Tail",
# AC-1532). `pending' = composer.question` exactly (or none); the FOR UPDATE write
# seam is the already-committed `conversation_variables_service.overwrite_for_contact`
# (its own SQL is `SELECT id FROM respond_contacts WHERE respond_io_id = :cid FOR
# UPDATE`). `record_offer`, `team_from_reply`, `_spend_the_answer`, `with_offer`,
# `_re_armed` and the carry helpers this replaces are retired (AC-1532's own grep
# guard).
from __future__ import annotations

from typing import Any

from app.services.conversation_variables_service import overwrite_for_contact
from app.services.chatbot.turn.state import Focus, State


def _pending_to_open_question(pending: Any) -> dict[str, Any] | None:
    if pending is None:
        return None
    return {
        "kind": pending.kind,
        "expects": pending.expects,
        "options": pending.options,
        "team": pending.team,
        "asked_at_turn": pending.asked_at_turn,
        "payload": pending.payload,
    }


def _focus_to_wire(focus: Focus) -> dict[str, Any]:
    def _code(entity: dict[str, Any]) -> Any:
        return entity.get("canonical_code") or entity.get("raw")

    return {
        "products": [_code(p) for p in focus.products],
        "customer": focus.customers[0] if focus.customers else None,
        "domains": list(focus.domains),
        "warehouse": _code(focus.warehouse[0]) if focus.warehouse else None,
        "transporter": None,
        "attachment_type": None,
        "brand": focus.brands[0] if focus.brands else None,
        "tier": focus.tier[0] if focus.tier else None,
        "document": list(focus.document),
        "status": focus.status,
        "date_window": focus.date_window,
    }


def persist(state: State, answer: Any, ctx: Any) -> dict[str, Any]:
    db = getattr(ctx, "db", None)
    respond_io_id = getattr(ctx, "contact_respond_id", None)

    payload = {
        "focus": _focus_to_wire(state.focus),
        "open_question": _pending_to_open_question(answer.question),
        "ideation": getattr(ctx, "ideation", None),
        "access_levels": getattr(ctx, "access_levels", []) or [],
        "contains_flyer": getattr(ctx, "contains_flyer", False),
    }

    return overwrite_for_contact(db, respond_io_id=respond_io_id, state=payload)
