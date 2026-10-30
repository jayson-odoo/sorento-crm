"""AGENTIC-P2: pick, per staff message, the chat bot or the agent (plan "Design" 2 and 3).

State decides first, with no model call: a pending agent proposal, an open bot question, media,
the daily agent-turn cap. Everything else is one Jev `choice` question. Only a contact the agent
may serve is routed (the caller handles `AgentRefused`), and a Jev failure is never retried on
another model: the message goes to today's bot with `reason = router_failed`.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.services.chatbot import jev_client

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_router"
FEATURE = "chatbot_router"
PROVIDER = "jev"
DEFAULT_MODEL = "jev-latest"
DEFAULT_MIN_SCORE = 0.7
DEFAULT_DAILY_TURNS = 50
HISTORY_EXCHANGES = 3
# What Jev receives, cut to the sizes the gold set was extracted at.
MESSAGE_CHARS = 500
EXCHANGE_CHARS = 300

CRITERIA = {
    "chat": (
        "A lookup today's bot already answers: stock of a product, one order or document, a customer "
        "or product detail, a list, a status, or a short reply to the bot's own last question."
    ),
    "agent": (
        "Needs several reads combined, a comparison, a reason, an analysis over periods, agents or "
        "products, or a change to a record. Also a follow up to the agent's own last answer."
    ),
}


@dataclass
class RouteDecision:
    route: str  # "chat" | "agent"
    score: float | None  # P(agent) from Jev, None when Jev was not asked or failed
    reason: str
    provider: str | None = None
    ms: int = 0
    tokens_in: int = 0
    detail: str | None = None  # the refusal behind `not_eligible`, set by the route


def jev_key(db) -> str | None:
    """The key from the AI assistant config, then env `JEV_API_KEY`."""
    from app.models.ai_assistant import AIAssistantConfig

    try:
        row = db.query(AIAssistantConfig).first()
        stored = row.jev_api_key_ciphertext if row is not None else None
    except Exception:  # noqa: BLE001 - a config read must not fail routing; the env key may still serve
        logger.warning("router: key lookup failed", exc_info=True)
        stored = None
    return (stored or "").strip() or (os.environ.get("JEV_API_KEY") or "").strip() or None


def _setting(db, column: str, default):
    from app.models.user import SystemSetting

    try:
        row = db.query(SystemSetting).first()
    except Exception:  # noqa: BLE001 - settings must never fail a turn
        logger.warning("router: settings read failed, using defaults", exc_info=True)
        return default
    value = getattr(row, column, None) if row is not None else None
    return default if value is None else value


def router_enabled(db) -> bool:
    """`system_settings.chatbot_router_enabled`; off when there is no settings row."""
    return bool(_setting(db, "chatbot_router_enabled", False))


def _contact(db, ctx):
    from app.models.access import RespondContact
    from app.models.base import company_scope

    with company_scope(db, None):
        return db.query(RespondContact).filter(RespondContact.id == ctx.contact_pk).first()


def _has_open_question(contact, session_vars: dict | None) -> bool:
    """The bot's open question, read as the turn would load it: the supplied console session when
    one came with the request (`{}` counts), else the stored row; an expired escalation offer is gone."""
    from app.services.chatbot import session_state
    from app.services.chatbot.turn import pending as turn_pending

    raw = session_vars if session_vars is not None else (getattr(contact, "session_vars", None) or {})
    wire = session_state.five_keys({"session_vars": raw}).get("open_question")
    return turn_pending.tick(turn_pending.from_wire(wire)) is not None


def _turns_today(db, contact_respond_id: str, now: datetime) -> int:
    from app.models.chatbot_turn import ChatbotTurn

    myt = now.astimezone(timezone.utc) + timedelta(hours=8)
    start = myt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)
    return (
        db.query(ChatbotTurn)
        .filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.ingress == "agent",
            ChatbotTurn.created_at >= start,
        )
        .count()
    )


def recent_exchanges(db, contact_respond_id: str, limit: int = HISTORY_EXCHANGES) -> list[dict]:
    """The contact's last answered turns, oldest first: `{text, reply, answered_by}`."""
    from app.models.chatbot_turn import ChatbotTurn

    rows = (
        db.query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == contact_respond_id, ChatbotTurn.response.isnot(None))
        .order_by(ChatbotTurn.created_at.desc(), ChatbotTurn.id.desc())
        .limit(limit)
        .all()
    )
    out: list[dict] = []
    for row in reversed(rows):
        envelope = row.envelope if isinstance(row.envelope, dict) else {}
        response = row.response if isinstance(row.response, dict) else {}
        text = envelope.get("text")
        if not isinstance(text, str):  # a bot turn keeps the channel's own envelope
            node: Any = envelope
            for part in ("message", "message", "message", "text"):
                node = node.get(part) if isinstance(node, dict) else None
            text = node if isinstance(node, str) else ""
        out.append(
            {
                "text": text or "",
                "reply": response.get("reply_text") or "",
                "answered_by": "agent" if row.ingress == "agent" else "bot",
            }
        )
    return out


def build_state(text: str, history: list[dict]) -> str:
    recent = history[-HISTORY_EXCHANGES:]
    lines: list[str] = []
    for i, ex in enumerate(recent, 1):
        lines.append(f"Exchange {i} ({ex.get('answered_by') or 'bot'} answered)")
        lines.append(f"Staff: {(ex.get('text') or '')[:EXCHANGE_CHARS]}")
        lines.append(f"Reply: {(ex.get('reply') or '')[:EXCHANGE_CHARS]}")
    last = (recent[-1].get("answered_by") or "bot") if recent else "none"
    lines.append(f"last answered by: {last}")
    lines.append(f"New message: {text[:MESSAGE_CHARS]}")
    return "\n".join(lines)


def decide(
    db,
    ctx,
    text: str,
    *,
    history: list[dict],
    has_media: bool,
    now: datetime | None = None,
    session_vars: dict | None = None,
    jev: Callable[..., dict[str, Any]] | None = None,
) -> RouteDecision:
    from app.services import ai_prompt_registry
    from app.services.chatbot.agent import actions
    from app.services.chatbot.usage import record_turn_llm_usage

    if actions.pending_action(db, ctx.contact_respond_id, user_id=ctx.user_id) is not None:
        return RouteDecision("agent", None, "pending_action")
    contact = _contact(db, ctx)
    if (contact is not None or session_vars is not None) and _has_open_question(contact, session_vars):
        return RouteDecision("chat", None, "open_question")
    if has_media:
        return RouteDecision("chat", None, "media")
    limit = getattr(contact, "chatbot_agent_daily_turns", None)
    if limit is None:
        limit = _setting(db, "chatbot_agent_daily_turns", DEFAULT_DAILY_TURNS)
    if limit > 0 and _turns_today(db, ctx.contact_respond_id, now or datetime.now(timezone.utc)) >= limit:
        return RouteDecision("chat", None, "daily_cap")

    key = jev_key(db)
    if not key:
        return RouteDecision("chat", None, "router_failed")
    label_provider, label_model = ai_prompt_registry.agent_model(db, PROMPT_KEY)
    # The label's model is a Jev model only when its provider is empty or jev.
    model = label_model if label_model and (label_provider or PROVIDER) == PROVIDER else DEFAULT_MODEL
    instructions = ai_prompt_registry.get_prompt(db, PROMPT_KEY).text
    started = time.monotonic()
    try:
        answer = (jev or jev_client.choose)(
            key, state=build_state(text, history), instructions=instructions, criteria=CRITERIA, model=model
        )
        score = float(answer["probabilities"]["agent"])
    except Exception as exc:  # noqa: BLE001 - any Jev failure goes to the bot; JevError never carries the key
        logger.warning("router: Jev call failed: %s", type(exc).__name__)
        return RouteDecision("chat", None, "router_failed", PROVIDER, int((time.monotonic() - started) * 1000))
    ms = int((time.monotonic() - started) * 1000)
    tokens_in = int(answer.get("input_tokens") or 0)
    tokens_out = int(answer.get("output_tokens") or 0)
    record_turn_llm_usage(
        db,
        feature=FEATURE,
        usage={
            "provider": PROVIDER,
            "model": model,
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
        response_time_ms=ms,
        contact_respond_id=ctx.contact_respond_id,
        answered=True,
    )
    min_score = float(_setting(db, "chatbot_router_min_score", DEFAULT_MIN_SCORE))
    if score >= min_score:
        return RouteDecision("agent", score, "jev", PROVIDER, ms, tokens_in)
    if score >= float(answer["probabilities"].get("chat", 1 - score)):
        return RouteDecision("chat", score, "low_confidence", PROVIDER, ms, tokens_in)
    return RouteDecision("chat", score, "jev", PROVIDER, ms, tokens_in)
