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
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.models.chatbot_turn import ChatbotTurn
from app.services.agent import memory
from app.services.agent.access import build_context, grants_hash, permitted_tools
from app.services.agent.tools import GUARD_PARAMS, ToolResult, clip_args, dispatch, tool_schemas

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_agent"
FEATURE = "chatbot_agent"
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.5-flash"
MCP_CALL_TIMEOUT = 10.0
NOT_VERIFIED = "(not verified)"
#: Per-call ceilings. Every call also counts against the turn's max_seconds.
ROUND_CALL_CAP = 60.0
SIDE_CALL_CAP = 30.0
#: The final no-tools answer may overrun the turn by this much, so a limit still gets a reply.
FINAL_GRACE = 10.0
#: Below this many seconds left, compaction and the repair round are skipped.
SIDE_CALL_MIN = 10.0
CATALOG_TTL_SECONDS = 300


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
_LIST_MARKER = re.compile(r"(?m)^(\s*)(\d{1,2}[.)])(?=\s)")
_UNITS = r"(?:pcs|pc|units?|ctns?|cartons?|kg|x|k|%)"
_CURRENCY = r"(?:RM|MYR|USD|CNY|SGD)"
# A figure is a run of digits (thousands separators allowed, optional decimals), with an
# optional currency or unit glued to it. A run glued to a letter on the left, or to letters
# that are not a known unit on the right, is part of a product code and not a figure.
_NUMBER = re.compile(
    rf"(?<![A-Za-z0-9_.,])(?:{_CURRENCY}\s?)?(?P<int>\d{{1,3}}(?:,\d{{3}})+|\d+)(?P<dec>\.\d+)?"
    rf"(?:\s?(?P<unit>{_UNITS}))?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def _normal(token: str) -> str:
    plain = token.replace(",", "")
    try:
        return format(Decimal(plain).normalize(), "f")
    except InvalidOperation:
        return plain


def _mask(text: str) -> str:
    """`text` with dates and list markers blanked to spaces of the same length."""
    blank = lambda m: " " * len(m.group(0))  # noqa: E731
    text = _DATE.sub(blank, text)
    return _LIST_MARKER.sub(lambda m: m.group(1) + " " * len(m.group(2)), text)


def _figures(text: str) -> list[tuple[int, int, str, set[str]]]:
    """(start, end, as written, accepted normal forms) for each figure in `text`."""
    out = []
    for m in _NUMBER.finditer(_mask(text)):
        base = _normal(m.group("int") + (m.group("dec") or ""))
        forms = {base}
        if (m.group("unit") or "").lower() == "k":
            forms.add(_normal(str(Decimal(base) * 1000)))
        out.append((m.start(), m.end(), text[m.start():m.end()], forms))
    return out


def _supported_forms(sources: list[str]) -> set[str]:
    found: set[str] = set()
    for src in sources:
        for m in _NUMBER.finditer(src or ""):
            found.add(_normal(m.group("int") + (m.group("dec") or "")))
    return found


def unsupported_figures(reply: str, sources: list[str]) -> list[str]:
    supported = _supported_forms(sources)
    missing: list[str] = []
    for _, _, written, forms in _figures(reply or ""):
        if not forms & supported and written not in missing:
            missing.append(written)
    return missing


def _redact(reply: str, sources: list[str]) -> str:
    supported = _supported_forms(sources)
    out, last = [], 0
    for start, end, _, forms in _figures(reply):
        if not forms & supported:
            out.append(reply[last:start])
            out.append(NOT_VERIFIED)
            last = end
    out.append(reply[last:])
    return "".join(out)


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
    """The agent cannot start; the message is ours and safe to show."""


class _ProviderFailed(Exception):
    """A model call failed. The detail is logged, never shown."""


class AgentBusy(Exception):
    """Another turn for the same contact is still running."""


@contextmanager
def single_flight(contact_respond_id: str):
    """One agent turn at a time per contact: a Postgres advisory lock held on a connection of
    its own (the session's connection goes back to the pool between commits)."""
    from sqlalchemy import text as sql_text

    from app.database import engine

    key = {"k": f"agent:{contact_respond_id}"}
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        if not conn.execute(sql_text("SELECT pg_try_advisory_lock(hashtext(:k))"), key).scalar():
            raise AgentBusy()
        try:
            yield
        finally:
            try:
                conn.execute(sql_text("SELECT pg_advisory_unlock(hashtext(:k))"), key)
            except Exception:  # noqa: BLE001 - a dead connection drops its locks with it
                logger.warning("agent: advisory unlock failed", exc_info=True)
                conn.invalidate()
    finally:
        conn.close()


_CATALOG_CACHE: dict[str, tuple[float, dict]] = {}


def catalog_cached(fetch: Callable[[], dict], *, now: Callable[[], float] = time.monotonic, key: str = "mcp") -> dict:
    """The MCP tool catalogue, fetched at most once per CATALOG_TTL_SECONDS per process."""
    hit = _CATALOG_CACHE.get(key)
    if hit is not None and hit[0] > now():
        return hit[1]
    value = fetch()
    _CATALOG_CACHE[key] = (now() + CATALOG_TTL_SECONDS, value)
    return value


def _fetch_catalog() -> dict:
    from app.config import settings
    from app.services.ai_assistant_service import MCPRuntimeClient

    url = settings.ai_assistant_mcp_url
    return catalog_cached(
        lambda: MCPRuntimeClient(url, timeout_seconds=10).list_tools_with_schema(), key=url
    )


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
        raise _AgentUnavailable("the configured model provider is not supported") from exc


def _system_prompt(db, user_name: str) -> str:
    from app.services import ai_prompt_registry

    text = ai_prompt_registry.get_prompt(db, PROMPT_KEY).text
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{text}\n\nToday's date is {today}. You are working for {user_name}."


def _args_for_digest(args: Any) -> Any:
    if not isinstance(args, dict):
        return {}
    return clip_args({k: v for k, v in args.items() if k not in GUARD_PARAMS})


def run_agent_turn(
    db,
    *,
    contact_respond_id: str,
    text: str,
    provider=None,
    mcp_call=None,
    mcp_builder: Callable[[int], Callable[[str, dict], Any]] | None = None,
    catalog=None,
    clock: Callable[[], float] = time.monotonic,
    operator_user_id: str | None = None,
) -> AgentTurnResult:
    ctx = build_context(db, contact_respond_id)  # AgentRefused propagates
    with single_flight(contact_respond_id):  # AgentBusy propagates
        return _run(
            db, ctx, contact_respond_id=contact_respond_id, text=text, provider=provider,
            mcp_call=mcp_call, mcp_builder=mcp_builder, catalog=catalog, clock=clock,
            operator_user_id=operator_user_id,
        )


def _run(db, ctx, *, contact_respond_id, text, provider, mcp_call, mcp_builder, catalog, clock, operator_user_id):
    from app.services import ai_prompt_registry
    from app.services.chatbot.trace import TurnTrace
    from app.services.chatbot.usage import record_turn_llm_usage

    t0 = clock()
    budgets = budgets_from_settings(db)
    conv = memory.current_conversation(
        db, contact_respond_id, user_id=ctx.user_id, grants_hash=grants_hash(ctx)
    )
    trace = TurnTrace()
    run = _Run()

    envelope = {"text": text, "agent_conversation_id": str(conv.id)}
    if operator_user_id:
        envelope["operator_user_id"] = str(operator_user_id)
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_respond_id,
        ingress="agent",
        is_test=True,
        status="processing",
        envelope=envelope,
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

    def chat(messages: list[dict], tools: list[dict] | None, *, kind: str, cap: float = ROUND_CALL_CAP,
             grace: float = 0.0) -> Any:
        """One model call inside the turn's single deadline. `grace` is the least time the
        call may have (the final answer only)."""
        timeout = min(cap, remaining())
        if grace:
            timeout = max(grace, timeout)
        if timeout < 1:
            raise TimeoutError("the turn ran out of time")
        started = clock()
        try:
            result = provider.chat(
                messages, tools=tools, reasoning_effort=effort, model=model, timeout=timeout
            )
        except Exception as exc:  # noqa: BLE001 - detail is logged, the user sees a fixed reason
            logger.warning("agent: model call failed (%s)", kind, exc_info=True)
            raise _ProviderFailed() from exc
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
            effort = ai_prompt_registry.agent_reasoning_effort(db, PROMPT_KEY)
            name, picked = ai_prompt_registry.agent_model(db, PROMPT_KEY)
            provider_name, model = name or DEFAULT_PROVIDER, picked or DEFAULT_MODEL

        if mcp_call is None and mcp_builder is None:
            from app.services.chatbot.lanes.business.services import _mcp_call

            def mcp_builder(seconds: int):  # noqa: F811 - the production builder
                return _mcp_call(db, timeout_seconds=seconds)
        if catalog is None:
            try:
                catalog = _fetch_catalog()
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent: tool catalogue fetch failed", exc_info=True)
                raise _AgentUnavailable("the CRM tools are not reachable") from exc

        # -- memory: compaction (only with time to spare), then history
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
            res = chat([{"role": "user", "content": prompt}], None, kind="compaction", cap=SIDE_CALL_CAP)
            return res.content or ""

        if remaining() >= SIDE_CALL_MIN:
            memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=budgets.compact_tokens)

        messages: list[dict] = [{"role": "system", "content": _system_prompt(db, ctx.user_name)}]
        messages.extend(memory.history_messages(db, conv))
        messages.append({"role": "user", "content": text})
        schemas = tool_schemas(permitted_tools(db, ctx), catalog) or None
        run.sources.append(text)

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
            return (chat(messages, None, kind="final", grace=FINAL_GRACE).content or "").strip()

        while True:
            try:
                result = chat(messages, schemas, kind="round")
            except (_ProviderFailed, TimeoutError):
                if not run.any_tool_result:
                    raise
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

            skipped = 0
            for idx, call in enumerate(calls):
                name = str(call.get("name") or "")
                args = call.get("arguments")
                started = clock()
                if idx >= budgets.calls_per_round:
                    # A Gemini continuation must be replayed with a reply for every call it
                    # contains, so each extra call gets one; the digest and trace carry one note.
                    skipped += 1
                    out = ToolResult("denied", message="Too many calls this round; ask again next round.")
                    messages.append(
                        {"role": "tool", "tool_call_id": assistant_calls[idx]["id"], "content": out.to_json()}
                    )
                    continue
                # Each call gets what is left of the turn, at most 10 s.
                seconds = max(1, int(min(remaining(), MCP_CALL_TIMEOUT)))
                out = dispatch(
                    db, ctx, name, args,
                    call=mcp_call if mcp_call is not None else mcp_builder(seconds),
                    catalog=catalog, timeout=float(seconds),
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
            if skipped:
                note = {"name": "(extra calls)", "args": {"skipped": skipped}, "status": "denied"}
                run.tool_calls.append({"name": note["name"], "status": "denied", "ms": 0})
                run.digest.append(note)
                trace.add("agent_tool", {**note, "ms": 0, "result_chars": 0, "more": 0})

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

        # -- figure check (one repair round with time to spare, then redaction)
        missing = unsupported_figures(reply, run.sources)
        if missing:
            trace.add("agent_figure_check", {"unsupported": missing})
            if remaining() >= SIDE_CALL_MIN:
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
                    reply = (chat(messages, None, kind="repair", cap=SIDE_CALL_CAP).content or "").strip()
                except (_ProviderFailed, TimeoutError):
                    logger.warning("agent: repair round failed")
            reply = _redact(reply, run.sources)
    except _AgentUnavailable as exc:
        status, error, limit_hit = "failed", str(exc), None
    except _ProviderFailed:
        status, error, limit_hit = "failed", "the model provider failed", None
    except TimeoutError:
        status, error, limit_hit = "failed", "the turn ran out of time", None
    except Exception:  # noqa: BLE001 - the row must never stay in processing
        logger.warning("agent: turn failed", exc_info=True)
        status, error, limit_hit = "failed", "the agent hit an internal error", None
        try:
            db.rollback()  # a failed flush must not block the closing write
        except Exception:  # noqa: BLE001
            pass

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
        "rounds": run.rounds,
    }
    turn.trace = trace.persisted()
    turn.finished_at = datetime.now(timezone.utc)
    if status == "failed":
        # The calls were billed, but the turn did not answer anyone.
        from app.models.ai_assistant import AIAssistantUsageLog

        db.query(AIAssistantUsageLog).filter(
            AIAssistantUsageLog.chatbot_turn_id == turn_id, AIAssistantUsageLog.feature == FEATURE
        ).update({AIAssistantUsageLog.was_answered: False}, synchronize_session=False)
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
