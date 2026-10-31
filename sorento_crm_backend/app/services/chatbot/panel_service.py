"""The AI side panel on the chatbot's brain (AGENTIC-UNIFY PR 3).

One panel message is one live `run_turn`, as the staff member (`principal.StaffPrincipal`): the same
parser and lanes a WhatsApp message gets. `run_turn` executes no action itself, its callers do, and
this caller renders `send_message` and `send_attachments` and drops the rest (AC-11), which is why
nothing reaches WhatsApp or Respond.

Called by `POST /system/ai-assistant/chat` for a holder of `ROLLOUT_SLUG`. `SessionLocal` and
`run_turn` stay module-level names so a test can keep the engine off the shared database.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.chatbot import principal as staff_principal
from app.services.chatbot.console_service import _quick_replies, _stored_attachments
from app.services.chatbot.contracts import PANEL_INGRESS, Envelope
from app.services.chatbot.engine import run_turn, split_marked_message, split_send_actions
from app.services.chatbot_reply_copy import CHATBOT_REPLY_AI_DID_NOT_ANSWER
from app.services.company_scope_resolver import resolve_user_active_company

#: Holding it moves a user's panel onto the chatbot's brain. Granted to nobody by a migration.
ROLLOUT_SLUG = "system.ai_assistant_chat.agent"


@dataclass
class PanelTurnResult:
    reply_text: str
    attachments: list[dict[str, str]] = field(default_factory=list)
    quick_replies: list[str] = field(default_factory=list)
    route: str = "chat"
    turn_id: str | None = None
    status: str | None = None


def run_panel_turn(
    db: Session,
    *,
    user: dict[str, Any],
    conversation: Any,
    text: str,
    page_snapshot: Any = None,
    message_id: str | None = None,
) -> PanelTurnResult:
    """Answer one panel message. `message_id` is the dedup key; left out, every call is its own
    message. `page_snapshot` reaches nothing yet (AC-19)."""
    _ = page_snapshot
    principal = staff_principal.StaffPrincipal(
        user_id=str(user["id"]),
        conversation_id=str(conversation.id),
        active_company_id=resolve_user_active_company(db, str(user["id"])),
    )
    envelope = _envelope(principal, user, text, message_id or f"panel-{uuid.uuid4()}")
    # The turn opens its own sessions around the LLM call; the request's transaction must not sit
    # on a pooled connection for all of it (the same rollback `/chat/turn` does).
    db.rollback()
    # The agent side lands next: until then every panel turn is a chat turn, and Jev is not asked.
    result = run_turn(envelope, session_factory=SessionLocal, offload=False)
    return _rendered(result, route="chat")


def message_metadata(result: Any) -> dict[str, Any]:
    """What the panel message keeps of a turn. `suggestions` is the key the panel's chips read."""
    return {
        "chatbot_turn_id": result.turn_id,
        "route": result.route,
        "status": result.status,
        "attachments": list(result.attachments),
        "suggestions": list(result.quick_replies),
    }


def _envelope(principal: staff_principal.StaffPrincipal, user: dict[str, Any], text: str, message_id: str) -> Envelope:
    """The shape `direct_ingress.envelope_for` builds from Respond's webhook, with no channel a
    WhatsApp flow could recognise."""
    key = principal.key
    return Envelope(
        contact={"id": key, "firstName": str(user.get("name") or "").strip().split(" ")[0]},
        message={
            "event_type": "message.received",
            "contact": {"id": key},
            "channel": {"source": PANEL_INGRESS},
            "message": {
                "messageId": message_id,
                "contactId": key,
                "channelId": PANEL_INGRESS,
                "traffic": "incoming",
                "message": {"type": "text", "text": text},
            },
        },
        ingress=PANEL_INGRESS,
        **staff_principal.envelope_extra(principal),
    )


def _rendered(result: Any, *, route: str) -> PanelTurnResult:
    """AC-11: the replies in order (messages answered ahead first), the files and the chips. The
    assign, comment and contact field actions have no one to act on and are dropped here."""
    actions = split_send_actions(list(result.actions or []))
    reply = result.reply if isinstance(result.reply, dict) else {}
    texts = [
        action["text"]
        for action in actions
        if isinstance(action, dict)
        and action.get("kind") == "send_message"
        and isinstance(action.get("text"), str)
        and action["text"].strip()
    ]
    if not texts and isinstance(reply.get("text"), str):
        texts = split_marked_message(reply["text"]) or [reply["text"]]
    attachments = [
        {"filename": file["filename"], "url": file["url"]}
        for action in actions
        for file in _stored_attachments({"actions": [action]})
    ]
    reply_text = "\n\n".join(text for text in texts if text.strip())
    return PanelTurnResult(
        reply_text=reply_text or ("" if attachments else CHATBOT_REPLY_AI_DID_NOT_ANSWER),
        attachments=attachments,
        quick_replies=_quick_replies({"reply": reply}),
        route=route,
        turn_id=result.turn_id,
        status=result.status,
    )
