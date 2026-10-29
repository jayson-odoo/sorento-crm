"""One continuous conversation per contact, with compaction (AGENTIC-P1 card section 4).

The turns are `chatbot.turns` rows (`ingress = "agent"`) carrying `agent_conversation_id` in
their envelope. `chatbot.agent_conversations` holds the boundary and the running summary.
History is evidence of what the user wants, never of current stock or orders.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from app.models.chatbot_agent import AgentConversation
from app.models.chatbot_turn import ChatbotTurn

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = "Summary of the earlier conversation: "
_ARGS_CLIP = 160


def _now() -> datetime:
    return datetime.now(timezone.utc)


def latest_conversation(db, contact_respond_id: str) -> AgentConversation | None:
    """The contact's newest conversation, or None. Never writes."""
    return (
        db.query(AgentConversation)
        .filter(AgentConversation.contact_respond_id == contact_respond_id)
        .order_by(AgentConversation.created_at.desc())
        .first()
    )


def belongs_to(conv: AgentConversation, user_id: str | None, grants_hash: str | None) -> bool:
    """Was `conv` started for this user and grant set? Both must be given to be checked."""
    if user_id is None and grants_hash is None:
        return True
    return conv.user_id == user_id and conv.grants_hash == grants_hash


def current_conversation(
    db, contact_respond_id: str, *, user_id: str | None = None, grants_hash: str | None = None
) -> AgentConversation:
    """The newest conversation. Given a user and grants digest, a newest row started for a
    different user or grant set is not continued: a new one starts instead."""
    conv = latest_conversation(db, contact_respond_id)
    if conv is not None and belongs_to(conv, user_id, grants_hash):
        return conv
    return new_conversation(db, contact_respond_id, user_id=user_id, grants_hash=grants_hash)


def new_conversation(
    db, contact_respond_id: str, *, user_id: str | None = None, grants_hash: str | None = None
) -> AgentConversation:
    # created_at is set here, not by the column default: two rows made in one transaction
    # would share now() and the "newest" row would be undefined.
    conv = AgentConversation(
        contact_respond_id=contact_respond_id, created_at=_now(), user_id=user_id, grants_hash=grants_hash
    )
    db.add(conv)
    db.flush()
    return conv


def conversation_turns(db, conv: AgentConversation) -> list[ChatbotTurn]:
    return (
        db.query(ChatbotTurn)
        .filter(
            ChatbotTurn.contact_respond_id == conv.contact_respond_id,
            ChatbotTurn.ingress == "agent",
            ChatbotTurn.envelope["agent_conversation_id"].astext == str(conv.id),
        )
        .order_by(ChatbotTurn.created_at, ChatbotTurn.id)
        .all()
    )


def _verbatim_turns(db, conv: AgentConversation) -> list[ChatbotTurn]:
    # A turn still running has no response yet and is not history.
    turns = [t for t in conversation_turns(db, conv) if t.response is not None]
    if conv.summary_through is not None:
        turns = [t for t in turns if t.created_at > conv.summary_through]
    return turns


def digest_line(entry: dict) -> str:
    args = json.dumps(entry.get("args") or {}, ensure_ascii=False, default=str)
    if len(args) > _ARGS_CLIP:
        args = args[:_ARGS_CLIP] + "..."
    return f"{entry.get('name')}({args}) {entry.get('status')}"


def _turn_messages(turn: ChatbotTurn) -> list[dict]:
    envelope = turn.envelope if isinstance(turn.envelope, dict) else {}
    response = turn.response if isinstance(turn.response, dict) else {}
    reply = str(response.get("reply_text") or "")
    digest = [d for d in (response.get("tool_digest") or []) if isinstance(d, dict)]
    if digest:
        reply += "\n[tools: " + "; ".join(digest_line(d) for d in digest) + "]"
    return [
        {"role": "user", "content": str(envelope.get("text") or "")},
        {"role": "assistant", "content": reply},
    ]


def history_messages(db, conv: AgentConversation) -> list[dict]:
    msgs: list[dict] = []
    if conv.summary:
        msgs.append({"role": "user", "content": SUMMARY_PREFIX + conv.summary})
    for turn in _verbatim_turns(db, conv):
        msgs.extend(_turn_messages(turn))
    return msgs


def maybe_compact(
    db,
    conv: AgentConversation,
    *,
    summarize: Callable[[str | None, list[ChatbotTurn]], str],
    threshold_tokens: int,
    keep_last: int = 6,
) -> bool:
    """Fold the older verbatim turns into the running summary when the verbatim part is above
    the threshold (characters / 4). A failing summarizer changes nothing."""
    turns = _verbatim_turns(db, conv)
    chars = sum(len(m["content"]) for t in turns for m in _turn_messages(t))
    if chars // 4 <= threshold_tokens or len(turns) <= keep_last:
        return False
    folded = turns[: len(turns) - keep_last]
    try:
        summary = summarize(conv.summary, folded)
    except Exception:  # noqa: BLE001 - the turn still runs on the verbatim history
        logger.warning("agent: compaction failed for %s", conv.contact_respond_id, exc_info=True)
        return False
    summary = (summary or "").strip()
    if not summary:
        return False
    conv.summary = summary
    conv.summary_through = folded[-1].created_at
    conv.summary_tokens = max(1, len(summary) // 4)
    db.flush()
    return True
