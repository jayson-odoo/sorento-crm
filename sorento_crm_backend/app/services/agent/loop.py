"""The agent's tool loop (AGENTIC-P1 card sections 1, 5, 6, 7).

Context = system prompt + conversation memory + the user's message. Each round the model
either asks for tools (dispatched through the permission layer) or answers. A budget limit
ends tool use with one last call that has no tools. Every number in the final reply must come
from a tool result of this turn or the user's own message.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.models.chatbot_turn import ChatbotTurn
from app.services.agent import memory
from app.services.agent.access import build_context, permitted_tools
from app.services.agent.tools import GUARD_PARAMS, ToolResult, dispatch, tool_schemas

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_agent"
FEATURE = "chatbot_agent"
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.5-flash"
MCP_CALL_TIMEOUT = 10.0
NOT_VERIFIED = "(not verified)"


@dataclass
class Budgets:
    max_rounds: int = 8
    max_seconds: float = 45
    max_input_tokens: int = 150_000
    compact_tokens: int = 40_000
    calls_per_round: int = 4


def budgets_from_settings(db) -> Budgets:
    from app.models.user import SystemSetting

    defaults = Budgets()
    try:
        row = db.query(SystemSetting).first()
    except Exception:  # noqa: BLE001 - budgets must never fail a turn
        logger.warning("agent: budget settings read failed, using defaults", exc_info=True)
        return defaults
    if row is None:
        return defaults

    def pick(column: str, fallback):
        value = getattr(row, column, None)
        return fallback if value is None else value

    return Budgets(
        max_rounds=int(pick("chatbot_agent_max_rounds", defaults.max_rounds)),
        max_seconds=float(pick("chatbot_agent_max_seconds", defaults.max_seconds)),
        max_input_tokens=int(pick("chatbot_agent_max_input_tokens", defaults.max_input_tokens)),
        compact_tokens=int(pick("chatbot_agent_compact_tokens", defaults.compact_tokens)),
    )


# ------------------------------------------------------------------ figure check

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LIST_MARKER = re.compile(r"(?m)^(\s*)\d{1,2}[.)](?=\s)")
# A number is a run of digits (thousands separators allowed, optional decimals) that is not
# glued to a letter or underscore: the digits of a product code are not figures.
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![A-Za-z0-9_])")


def _normal(token: str) -> str:
    plain = token.replace(",", "")
    try:
        return format(Decimal(plain).normalize(), "f")
    except InvalidOperation:
        return plain


def _numbers(text: str) -> list[tuple[str, str]]:
    """(as written, normalised) for each figure in `text`."""
    return [(m.group(0), _normal(m.group(0))) for m in _NUMBER.finditer(text)]


def _reply_figures_text(reply: str) -> str:
    return _LIST_MARKER.sub(r"\1", _DATE.sub(" ", reply))


def unsupported_figures(reply: str, sources: list[str]) -> list[str]:
    supported = {norm for src in sources for _, norm in _numbers(src or "")}
    missing: list[str] = []
    for written, norm in _numbers(_reply_figures_text(reply or "")):
        if norm not in supported and written not in missing:
            missing.append(written)
    return missing


def _redact(reply: str, figures: list[str]) -> str:
    if not figures:
        return reply
    bad = set(figures)
    return _NUMBER.sub(lambda m: NOT_VERIFIED if m.group(0) in bad else m.group(0), reply)


# ------------------------------------------------------------------ result


@dataclass
class AgentTurnResult:
    turn_id: str
    conversation_id: str
    reply_text: str
    status: str  # "answered" | "limited" | "failed"
    limit_hit: str | None
    rounds: int
    usage: dict
    tool_calls: list[dict]


@dataclass
class _Run:
    """Mutable state of one turn."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    calls: int = 0
    rounds: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    digest: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    any_tool_result: bool = False

    def usage(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "calls": self.calls,
        }


class _AgentUnavailable(Exception):
    pass


def _resolve_provider(db) -> tuple[Any, str, str, str | None]:
    """(provider client, provider name, model, reasoning effort). Raises _AgentUnavailable."""
    from app.models.ai_assistant import AIAssistantConfig
    from app.services import ai_prompt_registry
    from app.services.llm_provider import get_provider, resolve_api_key

    name, model = ai_prompt_registry.agent_model(db, PROMPT_KEY)
    if not name:
        name, model = DEFAULT_PROVIDER, DEFAULT_MODEL
    elif not model:
        model = DEFAULT_MODEL if name == DEFAULT_PROVIDER else None
    effort = ai_prompt_registry.agent_reasoning_effort(db, PROMPT_KEY)
    cfg = db.query(AIAssistantConfig).order_by(AIAssistantConfig.created_at.asc()).first()
    key = resolve_api_key(cfg, name)
    if not key:
        raise _AgentUnavailable(f"no API key is configured for {name}")
    try:
        return get_provider(name, key, model), name, model or "", effort
    except ValueError as exc:
        raise _AgentUnavailable(str(exc)) from exc


def _system_prompt(db, user_name: str) -> str:
    from app.services import ai_prompt_registry

    text = ai_prompt_registry.get_prompt(db, PROMPT_KEY).text
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{text}\n\nToday's date is {today}. You are working for {user_name}."


def _args_for_digest(args: Any) -> dict:
    if not isinstance(args, dict):
        return {}
    return {k: v for k, v in args.items() if k not in GUARD_PARAMS}


def run_agent_turn(
    db,
    *,
    contact_respond_id: str,
    text: str,
    provider=None,
    mcp_call=None,
    catalog=None,
    clock: Callable[[], float] = time.monotonic,
) -> AgentTurnResult:
    from app.services.chatbot.trace import TurnTrace
    from app.services.chatbot.usage import record_turn_llm_usage
    from app.services import ai_prompt_registry

    ctx = build_context(db, contact_respond_id)  # AgentRefused propagates
    budgets = budgets_from_settings(db)
    conv = memory.current_conversation(db, contact_respond_id)
    t0 = clock()
    trace = TurnTrace()
    run = _Run()

    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_respond_id,
        ingress="agent",
        is_test=True,
        status="processing",
        envelope={"text": text, "agent_conversation_id": str(conv.id)},
        started_at=datetime.now(timezone.utc),
    )
    db.add(turn)
    # Committed now: the usage writer commits, and rolls back on its own failure.
    db.commit()
    turn_id = str(turn.id)
    conversation_id = str(conv.id)

    provider_name = DEFAULT_PROVIDER
    model = DEFAULT_MODEL
    effort: str | None = None
    status = "answered"
    limit_hit: str | None = None
    error: str | None = None
    reply = ""

    def remaining() -> float:
        return budgets.max_seconds - (clock() - t0)

    def chat(messages: list[dict], tools: list[dict] | None, *, kind: str) -> Any:
        started = clock()
        result = provider.chat(
            messages,
            tools=tools,
            reasoning_effort=effort,
            model=model,
            timeout=max(5.0, min(remaining(), 60.0)),
        )
        ms = int((clock() - started) * 1000)
        run.calls += 1
        run.prompt_tokens += int(result.prompt_tokens or 0)
        run.completion_tokens += int(result.completion_tokens or 0)
        run.cached_tokens += int(result.cached_tokens or 0)
        trace.add(
            "agent_round",
            {
                "kind_of_call": kind,
                "model": result.model or model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "cached_tokens": result.cached_tokens,
                "reasoning_tokens": result.reasoning_tokens,
                "ms": ms,
                "tool_calls": len(result.tool_calls or []),
            },
        )
        record_turn_llm_usage(
            db,
            feature=FEATURE,
            usage={
                "provider": provider_name,
                "model": result.model or model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "cached_tokens": result.cached_tokens,
            },
            response_time_ms=ms,
            contact_respond_id=contact_respond_id,
            answered=True,
            chatbot_turn_id=turn_id,
        )
        return result

    try:
        if provider is None:
            provider, provider_name, model, effort = _resolve_provider(db)
        else:
            _, effort = None, ai_prompt_registry.agent_reasoning_effort(db, PROMPT_KEY)
            name, picked = ai_prompt_registry.agent_model(db, PROMPT_KEY)
            provider_name, model = name or DEFAULT_PROVIDER, picked or DEFAULT_MODEL

        if mcp_call is None:
            from app.services.chatbot.lanes.business.services import _mcp_call

            mcp_call = _mcp_call(db)
        if catalog is None:
            try:
                from app.config import settings
                from app.services.ai_assistant_service import MCPRuntimeClient

                catalog = MCPRuntimeClient(settings.ai_assistant_mcp_url, timeout_seconds=10).list_tools_with_schema()
            except Exception as exc:  # noqa: BLE001
                raise _AgentUnavailable("the CRM tools are not reachable") from exc
    except _AgentUnavailable as exc:
        status, error = "failed", str(exc)
    except Exception as exc:  # noqa: BLE001 - never a crash
        logger.warning("agent: setup failed", exc_info=True)
        status, error = "failed", f"{type(exc).__name__}"

    if status != "failed":
        # -- memory: compaction, then history
        def summarize(old: str | None, folded: list[ChatbotTurn]) -> str:
            lines = []
            for t in folded:
                msgs = memory._turn_messages(t)
                created = t.created_at.date().isoformat() if t.created_at else ""
                lines.append(f"[{created}] User: {msgs[0]['content']}\nAssistant: {msgs[1]['content']}")
            prompt = (
                "Fold the earlier conversation into one running summary. Keep corrections the user made, "
                "open questions, the entities involved and the figures already answered, each with the "
                "date it was read. Plain text, no dashes, no preamble.\n\n"
                f"Running summary so far: {old or '(none)'}\n\nTurns to fold in:\n" + "\n\n".join(lines)
            )
            res = chat([{"role": "user", "content": prompt}], None, kind="compaction")
            return res.content or ""

        memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=budgets.compact_tokens)

        messages: list[dict] = [{"role": "system", "content": _system_prompt(db, ctx.user_name)}]
        messages.extend(memory.history_messages(db, conv))
        messages.append({"role": "user", "content": text})
        schemas = tool_schemas(permitted_tools(db, ctx), catalog) or None
        sources: list[str] = run.sources
        sources.append(text)

        def forced_final(why: str) -> str:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool use has ended for this turn ({why}). Answer now with what you have, "
                        "and say plainly what you could not check."
                    ),
                }
            )
            return (chat(messages, None, kind="final").content or "").strip()

        try:
            while True:
                try:
                    result = chat(messages, schemas, kind="round")
                except Exception as exc:  # noqa: BLE001
                    if not run.any_tool_result:
                        raise
                    logger.warning("agent: provider error after tool results", exc_info=True)
                    status, limit_hit = "limited", "error"
                    reply = forced_final("the model call failed")
                    break
                run.rounds += 1
                calls = list(result.tool_calls or [])
                if not calls:
                    reply = (result.content or "").strip()
                    break

                assistant_calls = [
                    {
                        "id": c.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": c.get("name") or "",
                            "arguments": json.dumps(c.get("arguments") or {}, default=str),
                        },
                    }
                    for c in calls
                ]
                entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": result.content or "",
                    "tool_calls": assistant_calls,
                }
                if result.continuation:
                    entry["continuation"] = result.continuation
                messages.append(entry)

                for idx, call in enumerate(calls):
                    name = str(call.get("name") or "")
                    args = call.get("arguments")
                    started = clock()
                    if idx >= budgets.calls_per_round:
                        out = ToolResult("denied", message="Too many calls this round; ask again next round.")
                    else:
                        out = dispatch(
                            db, ctx, name, args, call=mcp_call, catalog=catalog,
                            timeout=max(1.0, min(remaining(), MCP_CALL_TIMEOUT)),
                        )
                    ms = int((clock() - started) * 1000)
                    payload = out.to_json()
                    if out.status == "ok":
                        run.sources.append(payload)
                    run.any_tool_result = True
                    run.tool_calls.append({"name": name, "status": out.status, "ms": ms})
                    run.digest.append({"name": name, "args": _args_for_digest(args), "status": out.status})
                    trace.add(
                        "agent_tool",
                        {
                            "name": name,
                            "args": _args_for_digest(args),
                            "status": out.status,
                            "ms": ms,
                            "result_chars": len(payload),
                            "more": out.more,
                        },
                    )
                    messages.append({"role": "tool", "tool_call_id": assistant_calls[idx]["id"], "content": payload})

                if run.rounds >= budgets.max_rounds:
                    limit_hit = "rounds"
                elif remaining() <= 0:
                    limit_hit = "seconds"
                elif run.prompt_tokens >= budgets.max_input_tokens:
                    limit_hit = "input_tokens"
                if limit_hit:
                    status = "limited"
                    reply = forced_final(f"limit reached: {limit_hit}")
                    break

            # -- figure check (one repair round, then redaction)
            missing = unsupported_figures(reply, run.sources)
            if missing:
                trace.add("agent_figure_check", {"unsupported": missing})
                try:
                    messages.append({"role": "assistant", "content": reply})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "These figures in your answer do not appear in any tool result of this turn: "
                                + ", ".join(missing)
                                + ". Answer again using only figures from the tool results or from my message, "
                                "and say which figures you could not verify."
                            ),
                        }
                    )
                    reply = (chat(messages, None, kind="repair").content or "").strip()
                except Exception:  # noqa: BLE001
                    logger.warning("agent: repair round failed", exc_info=True)
                reply = _redact(reply, unsupported_figures(reply, run.sources))
        except Exception as exc:  # noqa: BLE001 - before any tool result, or the final call failed
            logger.warning("agent: turn failed", exc_info=True)
            status, error = "failed", (str(exc) or type(exc).__name__)[:200]
            limit_hit = None

    if status == "failed":
        reply = f"The agent could not answer: {error}."
    if not reply:
        reply = "The agent has no answer for this."

    turn = db.get(ChatbotTurn, turn_id) or turn
    turn.status = "failed" if status == "failed" else "done"
    turn.error = error
    turn.response = {
        "reply_text": reply,
        "tool_digest": run.digest,
        "status": status,
        "limit_hit": limit_hit,
    }
    turn.trace = trace.persisted()
    turn.finished_at = datetime.now(timezone.utc)
    db.commit()

    return AgentTurnResult(
        turn_id=turn_id,
        conversation_id=conversation_id,
        reply_text=reply,
        status=status,
        limit_hit=limit_hit,
        rounds=run.rounds,
        usage=run.usage(),
        tool_calls=run.tool_calls,
    )
