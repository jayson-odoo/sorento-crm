"""One continuous conversation per contact, with compaction (AGENTIC-P1 card section 4).

The turns are `chatbot.turns` rows (`ingress = "agent"`) carrying `agent_conversation_id` in
their envelope. `chatbot.agent_conversations` holds the boundary and the running summary.
History is evidence of what the user wants, never of current stock or orders.
"""
from __future__ import annotations

import json
import logging
import uuid
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


def conversation_turns(db, conv: AgentConversation, *, limit: int | None = None) -> list[ChatbotTurn]:
    """The conversation's turns, oldest first. With `limit`, the newest that many."""
    query = db.query(ChatbotTurn).filter(
        ChatbotTurn.contact_respond_id == conv.contact_respond_id,
        ChatbotTurn.ingress == "agent",
        ChatbotTurn.envelope["agent_conversation_id"].astext == str(conv.id),
    )
    if limit is None:
        return query.order_by(ChatbotTurn.created_at, ChatbotTurn.id).all()
    return list(reversed(query.order_by(ChatbotTurn.created_at.desc(), ChatbotTurn.id.desc()).limit(limit).all()))


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


#: Calls that are the loop's own plumbing, never a lookup a person asked about.
_HIDDEN_STEP_TOOLS = frozenset({"answer", "plan"})


def steps_from_trace(trace: object) -> dict:
    """What one turn did, read from its stored trace: model rounds, tokens, each tool call (with the round it
    ran in) and the model's reasoning per round (`agent_reasoning`, AGENTIC-REASONING-VIS).
    `agent_round` events carry the tokens of every model call (a final or repair call adds tokens,
    not a round); `agent_tool` events are the tool calls, minus the hidden `answer` / `plan` calls
    and the note that stands for calls past the per-round cap."""
    steps: dict = {
        "rounds": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "tool_calls": [], "reasoning": [],
    }
    if not isinstance(trace, list):
        return steps
    for event in trace:
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        if kind == "agent_round":
            if event.get("kind_of_call") == "round":
                steps["rounds"] += 1
            for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
                value = event.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    steps[key] += int(value)
        elif kind == "agent_tool":
            name = str(event.get("name") or "")
            if not name or name in _HIDDEN_STEP_TOOLS or name.startswith("("):
                continue
            ms = event.get("ms")
            call = {
                "name": name,
                "status": str(event.get("status") or ""),
                "ms": int(ms) if isinstance(ms, (int, float)) and not isinstance(ms, bool) else 0,
            }
            if event.get("detail"):  # a turn stored before slice 6 has none
                call["detail"] = str(event["detail"])
            call["round"] = max(steps["rounds"], 1)
            steps["tool_calls"].append(call)
        elif kind == "agent_reasoning":
            text = event.get("text")
            number = event.get("round")
            if isinstance(text, str) and text.strip():
                ok = isinstance(number, int) and not isinstance(number, bool) and number > 0
                steps["reasoning"].append({
                    "round": number if ok else max(steps["rounds"], 1),
                    "text": text,
                    "final": event.get("kind_of_call") == "final",
                })
    return steps


def steps_for_turn(db, turn_id: str) -> dict:
    try:
        uuid.UUID(str(turn_id))
    except ValueError:
        return steps_from_trace(None)
    row = db.get(ChatbotTurn, turn_id)
    return steps_from_trace(row.trace if row is not None else None)
