"""Which side answers a console message: today's bot or the agent (AGENTIC-P2-ROUTE).

`decide_route` is the whole decision. State rules come first and never read the wording; only
the last step asks Jev (`jev_client.classify`). A decision that is not the agent means the bot,
so every failure here falls to today's path BEFORE the agent is chosen. After the agent is
chosen the caller never falls back.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.models.ai_assistant import AIAssistantConfig
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import jev_client, session_state
from app.services.chatbot.agent import actions as agent_actions
from app.services.chatbot.agent import memory as agent_memory
from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent import writes as agent_writes
from app.services.chatbot.agent.access import eligible_contact
from app.services.chatbot.jev_client import JevError
from app.services.chatbot.usage import record_turn_llm_usage
from app.services.llm_provider import resolve_typesafe_key

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_router"
FEATURE = "chatbot_router"
#: The business day the daily cap counts in.
BUSINESS_TZ = ZoneInfo("Asia/Kuala_Lumpur")
DEFAULT_MIN_SCORE = 0.7
DEFAULT_DAILY_CAP = 50
#: Exchanges sent to Jev as context, and how much of a bot reply.
RECENT_EXCHANGES = 3
REPLY_CHARS = 300
#: Longer (or empty) messages never go to Jev.
MAX_TEXT_CHARS = 4000
#: A reply this soon after the agent asked the user something stays with the agent.
ASKED_BACK_MINUTES = 60


@dataclass
class RouteDecision:
    side: str  # "chat" | "agent"
    reason: str
    score: float | None = None
    model: str | None = None
    ms: int | None = None
    input_tokens: int | None = None
    #: The class name behind a Jev timeout or transport failure (`JevError.detail`); None otherwise.
    error: str | None = None
    #: The `ai_assistant_usage_logs` row this decision wrote, so the caller can point it at the turn.
    usage_id: str | None = None

    def as_response(self) -> dict[str, Any]:
        return {"side": self.side, "reason": self.reason, "score": self.score, "model": self.model, "ms": self.ms, "error": self.error}


def decide_route(
    db, *, contact_respond_id: str, text: str, session_vars: dict[str, Any] | None, has_media: bool
) -> RouteDecision:
    contact, user, refusal = eligible_contact(db, contact_respond_id)
    if refusal is not None:
        return RouteDecision("chat", f"not_eligible:{refusal}")
    if has_media:
        return RouteDecision("chat", "media")
    if agent_actions.pending_action(db, contact_respond_id, user_id=str(user.id)) is not None:
        return RouteDecision("agent", "pending_action")

    # `None` = the contact's stored session, `{}` = a console Reset (remembers nothing).
    block = {"session_vars": contact.session_vars if session_vars is None else session_vars}
    if session_state.pending_of(block) is not None or _bot_asked(block):
        return RouteDecision("chat", "open_question")

    settings = db.query(SystemSetting).first()
    cap = _daily_cap(contact, settings)
    if cap > 0 and _agent_turns_today(db, contact_respond_id) >= cap:
        return RouteDecision("chat", "daily_cap")

    if not text.strip() or len(text.strip()) > MAX_TEXT_CHARS:
        return RouteDecision("chat", "text_length")

    config = db.query(AIAssistantConfig).first()
    api_key = resolve_typesafe_key(config)
    if not api_key:
        return RouteDecision("chat", "router_failed:no_key")
    prompt = _router_prompt(db)
    if prompt is None:
        return RouteDecision("chat", "router_failed:no_prompt")
    instructions, criteria, model = prompt
    criteria = _with_agent_tools(criteria)

    state = _state(db, contact_respond_id, text)
    started = time.perf_counter()
    try:
        answer = jev_client.classify(
            api_key, model=model, instructions=instructions, criteria=criteria, state=state,
            timeout_s=jev_client.TIMEOUT_S,
        )
    except JevError as exc:
        return RouteDecision("chat", f"router_failed:{exc.kind}", error=exc.detail)
    ms = int((time.perf_counter() - started) * 1000)

    usage_id = str(uuid.uuid4())
    record_turn_llm_usage(
        db,
        feature=FEATURE,
        usage={
            "provider": "typesafe",
            "model": answer.model or model,
            "prompt_tokens": answer.input_tokens,
            "completion_tokens": answer.output_tokens,
            "total_tokens": answer.input_tokens + answer.output_tokens,
        },
        response_time_ms=ms,
        contact_respond_id=contact_respond_id,
        answered=True,
        row_id=usage_id,
    )
    if answer.choice not in ("chat", "agent"):
        return RouteDecision("chat", "router_failed:malformed", ms=ms, usage_id=usage_id)
    floor = settings.chatbot_router_min_score if settings is not None else DEFAULT_MIN_SCORE
    low = answer.confidence < float(floor)
    # The agent's own question is answered on the agent unless Jev is sure it is a new chat question.
    if _agent_asked_back(db, contact_respond_id) and not (answer.choice == "chat" and not low):
        side, reason = "agent", "agent_asked"
    else:
        side, reason = ("chat", "low_confidence") if low else (answer.choice, "classified")
    return RouteDecision(
        side,
        reason,
        score=answer.confidence,
        model=answer.model or model,
        ms=ms,
        input_tokens=answer.input_tokens,
        usage_id=usage_id,
    )


def trace_record(decision: RouteDecision) -> dict[str, Any]:
    """The decision as a stage record of the turn's trace (same keys `TurnTrace.record` writes)."""
    return {
        "stage": "route",
        "status": "ok",
        "started_at": datetime.now(BUSINESS_TZ).isoformat(),
        "ms": decision.ms or 0,
        "summary": f"Routed to the {'agent' if decision.side == 'agent' else 'bot'}: {decision.reason}.",
        "why": "The console picks the bot or the agent for each message; a state rule decides first, then Jev.",
        "facts": decision.as_response(),
        "error": None,
        "raw": None,
    }


def _daily_cap(contact, settings) -> int:
    """Agent turns per day for this contact: its own number, else the global one (0 = no cap)."""
    own = getattr(contact, "chatbot_agent_daily_turns", None)
    if own is not None:
        return int(own)
    return int(settings.chatbot_agent_daily_turns) if settings is not None else DEFAULT_DAILY_CAP


def _agent_turns_today(db, contact_respond_id: str) -> int:
    midnight = datetime.now(BUSINESS_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(ChatbotTurn.id)
        .filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.ingress == "agent",
            ChatbotTurn.created_at >= midnight,
        )
        .count()
    )


def _bot_asked(block: dict[str, Any]) -> bool:
    """Is the bot waiting on this contact: a required ask on the focus, or a fresh held similar list
    (either lane's pointer)? Their next message answers it, whatever Jev would make of it."""
    from app.services.ideation_capture_service import _held_pointer

    keys = session_state.five_keys(block)
    focus = keys.get("focus")
    if isinstance(focus, dict) and focus.get("required_ask"):
        return True
    ideation = keys.get("ideation")
    return isinstance(ideation, dict) and _held_pointer(ideation, bool(ideation.get("is_test"))) is not None


def _agent_asked_back(db, contact_respond_id: str) -> bool:
    """Is the contact's latest done turn an agent turn in their newest conversation that asked the user something, under an hour ago?"""
    row = (
        db.query(ChatbotTurn.ingress, ChatbotTurn.response, ChatbotTurn.created_at, ChatbotTurn.envelope)
        .filter(ChatbotTurn.contact_respond_id == contact_respond_id, ChatbotTurn.status == "done")
        .order_by(ChatbotTurn.created_at.desc(), ChatbotTurn.started_at.desc().nullslast())
        .first()
    )
    if row is None or row[0] != "agent" or not isinstance(row[1], dict) or row[1].get("asked_back") is not True:
        return False
    latest = agent_memory.latest_conversation(db, contact_respond_id)
    if latest is None or not isinstance(row[3], dict) or row[3].get("agent_conversation_id") != str(latest.id):
        return False
    created = row[2]
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created < timedelta(minutes=ASKED_BACK_MINUTES)


def _router_prompt(db) -> tuple[str, dict[str, Any], str] | None:
    """(instructions, criteria, Jev model) of the production `chatbot_router` prompt, or None when
    it is missing or unreadable. Read straight from the label: the registry's code fallback would
    hide a missing prompt."""
    row = (
        db.query(AIPromptVersion.template, AIPromptLabel.model)
        .join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
        .filter(AIPromptLabel.name == PROMPT_KEY, AIPromptLabel.label == "production")
        .first()
    )
    if row is None:
        return None
    try:
        body = json.loads(row[0])
        instructions, criteria = str(body["instructions"]), body["criteria"]
    except (ValueError, KeyError, TypeError):
        logger.warning("chatbot_router: the production prompt is not the expected JSON")
        return None
    if not isinstance(criteria, dict) or not criteria:
        return None
    return instructions, criteria, row[1] or jev_client.DEFAULT_MODEL


def agent_tool_labels() -> list[str]:
    """Plain labels of what the agent can do: every write, then every per-user read. `tools.REGISTRY`
    (stock, ETA, cost) is left out on purpose: the bot answers those lookups too and the static
    criteria text already covers them. A tool without a label is skipped (a guard test catches it)."""
    labels: list[str] = []
    for name in [*agent_writes.WRITES, *agent_writes.USER_READS]:
        label = agent_tools.TOOL_LABELS.get(name)
        if label and label not in labels:
            labels.append(label)
    return labels


def _with_agent_tools(criteria: dict[str, Any]) -> dict[str, Any]:
    """A copy of the criteria whose agent entry lists the tools; the stored prompt is never changed."""
    if "agent" not in criteria:
        return criteria
    agent = criteria["agent"]
    agent = dict(agent) if isinstance(agent, dict) else {"what": str(agent)}
    agent["tools"] = agent_tool_labels()
    return {**criteria, "agent": agent}


def _state(db, contact_respond_id: str, text: str) -> dict[str, Any]:
    """What Jev reads: the message, the last exchanges (oldest first) and who answered last."""
    rows = (
        db.query(ChatbotTurn.ingress, ChatbotTurn.envelope, ChatbotTurn.response)
        .filter(ChatbotTurn.contact_respond_id == contact_respond_id, ChatbotTurn.status == "done")
        .order_by(ChatbotTurn.created_at.desc(), ChatbotTurn.started_at.desc().nullslast())
        .limit(RECENT_EXCHANGES * 2)
        .all()
    )
    exchanges: list[dict[str, Any]] = []
    for ingress, envelope, response in rows:
        reply = _reply_text(response)
        if not reply:
            continue
        by_agent = ingress == "agent"
        exchanges.append(
            {
                "user": _user_text(envelope),
                "reply": reply[:REPLY_CHARS],
                "answered_by": "agent" if by_agent else "bot",
            }
        )
        if len(exchanges) == RECENT_EXCHANGES:
            break
    exchanges.reverse()
    return {
        "latest_message": text,
        "recent_exchanges": exchanges,
        "last_answered_by": exchanges[-1]["answered_by"] if exchanges else None,
    }


def _user_text(envelope: Any) -> str:
    from app.services.chatbot.turn_runtime import _envelope_text

    if isinstance(envelope, dict) and isinstance(envelope.get("text"), str):
        return envelope["text"]
    return _envelope_text(envelope) or ""


def _reply_text(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    if isinstance(response.get("reply_text"), str):
        return response["reply_text"].strip()
    reply = response.get("reply")
    text = reply.get("text") if isinstance(reply, dict) else None
    return text.strip() if isinstance(text, str) else ""
