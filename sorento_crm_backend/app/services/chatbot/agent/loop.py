"""The agent's tool loop (AGENTIC-P1 card sections 1, 5, 6, 7).

Context = system prompt + conversation memory + the user's message. Each round the model
either asks for tools (dispatched through the permission layer) or answers. A budget limit
ends tool use with one last call that offers only the `answer` tool. The `answer` tool ends every
turn, and a verifier (code, not a model) checks its figures and its not-found claims against this
turn's tool results.
"""
from __future__ import annotations

import dataclasses
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
from app.services.chatbot.agent import actions, memory, writes
from app.services.chatbot.agent.formatting import to_whatsapp
from app.services.chatbot.agent.access import build_context, grants_hash, permitted_tools
from app.services.chatbot.agent.tools import (
    ANSWER,
    ANSWER_SCHEMA,
    PLAN,
    PLAN_SCHEMA,
    redact_ids,
    GUARD_PARAMS,
    RESOLVE,
    TOOL_LABELS,
    ToolResult,
    _id_args,
    clip_args,
    dispatch,
    tool_schemas,
)

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_agent"
FEATURE = "chatbot_agent"
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.5-flash"
# The effort the agent thinks at when its label sets none (owner, 31 Oct): without one a flash model gets a
# one-token thinking budget, so it barely thinks and the console has no reasoning to show.
DEFAULT_EFFORT = "low"
MCP_CALL_TIMEOUT = 10.0
NOT_VERIFIED = "(not verified)"
#: Per-call ceilings. Every call also counts against the turn's max_seconds.
ROUND_CALL_CAP = 60.0
# The most of one round's reasoning a turn keeps for the console. Each round is its own trace entry, under the
# trace's 32 KB per-entry cap for any text short of emoji (JSON escapes non-ASCII; an entry over the cap is
# replaced by an "omitted" note, never stored in part).
REASONING_CHARS = 4000
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
# A number that starts a line, after any markdown heading or bullet marks, and is followed by "." or ")"
# and a space: a list number or a section number ("### 3. Stock", "- 3. Stock"), never a figure.
_LIST_MARKER = re.compile(r"(?m)^(\s*(?:#{1,6}\s+)?(?:[-*+]\s+)?)(\d{1,3}[.)])(?=\s|$)")
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


_UUID_TEXT = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
# An identifier: letters and digits joined by "-" or "/" (a product code, an order or packing number).
_IDENTIFIER = re.compile(r"\b[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+\b")


_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|(?-i:May)|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_YEAR = r"(?:19|20)\d{2}"
# Written and numeric dates: "15 Nov 2026", "Nov 15, 2026", "15 November", "Oct 2026",
# "15/11/2026", "15-11-2026", "15.11.2026"; and a bare year 2000 to 2099.
_WRITTEN_DATE = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}(?:,?\s+{_YEAR})?(?![A-Za-z0-9])"
    rf"|\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+{_YEAR})?(?![A-Za-z0-9])"
    rf"|\b{_MONTH}\s+{_YEAR}\b"
    # A lowercase "may" is a month only with a year after it ("5 may 2026"), never "5 may arrive".
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+may\.?,?\s+{_YEAR}\b"
    rf"|\bmay\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+{_YEAR}\b",
    re.I,
)
_NUMERIC_DATE = re.compile(r"(?<![\d.,])\d{1,2}[/.-]\d{1,2}[/.-]\d{4}(?![\d])")
_BARE_YEAR = re.compile(r"(?<![\d.,])20\d{2}(?!\d|[.,]\d)")


def _identifier_blank(m: "re.Match[str]") -> str:
    token = m.group(0)
    return " " * len(token) if re.search(r"[A-Za-z]", token) else token


def _mask(text: str) -> str:
    """`text` with UUIDs, dates, identifiers (a hyphenated code with a letter in it) and list
    markers blanked to spaces of the same length. Dates in every common written form and a bare
    year 2000 to 2099 are blanked too."""
    blank = lambda m: " " * len(m.group(0))  # noqa: E731
    text = _UUID_TEXT.sub(blank, text)
    text = _DATE.sub(blank, text)
    text = _NUMERIC_DATE.sub(blank, text)
    text = _WRITTEN_DATE.sub(blank, text)
    text = _IDENTIFIER.sub(_identifier_blank, text)
    text = _BARE_YEAR.sub(blank, text)
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


# ------------------------------------------------------------------ the answer verifier

_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
LIMIT_WORDS = {"rounds": "rounds", "seconds": "time", "input_tokens": "token"}


def _value_forms(value: Any) -> set[str]:
    text = str(value if value is not None else "").strip()
    forms = set()
    for m in _NUMBER.finditer(text):
        forms.add(_normal(m.group("int") + (m.group("dec") or "")))
    return forms


#: Keys that carry bookkeeping or free text, never a figure the user asked about: paging and
#: scoring fields, any `*_id` / `*_ids`, and name-like text ("Basin 600" is not 600 units).
_NOT_FIGURE_KEYS = frozenset(
    {"more", "page", "limit", "offset", "total_count", "score", "has_result", "rank",
     "name", "product_name", "label", "description", "title", "display"}
)


def _figure_key(key: Any) -> bool:
    """May a value under this key back a figure?"""
    k = str(key).lower()
    return k not in _NOT_FIGURE_KEYS and not k.endswith(("_id", "_ids"))


def _number_leaves(data: Any) -> set[str]:
    """Normal forms of every numeric VALUE in `data`: JSON numbers and the numbers inside string
    values. Keys, UUIDs, dates and identifiers never count."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if _figure_key(k):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, bool) or node is None:
            return
        elif isinstance(node, (int, float)):
            found.add(_normal(str(node)))
        elif isinstance(node, str):
            # Numbers inside a formatted string ("51 (O/S: 36)", "RM 12.50", a report's text)
            # back figures; UUIDs, dates and identifiers are masked out by `_figures`.
            for _, _, _, forms in _figures(node):
                found.update(forms)

    walk(data)
    return found


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        plain = value.strip().replace(",", "")
        if _PLAIN_NUMBER.fullmatch(plain):
            return Decimal(plain)
    return None


def _column_totals(data: Any) -> set[str]:
    """Normal forms of the sum of each numeric field across every list of rows in `data`: the
    total a person reads off the rows. Rows are dicts; a presenter row's `fields` ({key, value})
    are summed per key."""
    found: set[str] = set()

    def add(total: Decimal) -> None:
        found.add(_normal(str(total)))

    def walk(node: Any) -> None:
        if isinstance(node, list):
            rows = [r for r in node if isinstance(r, dict)]
            sums: dict[str, Decimal] = {}
            if rows:
                found.add(_normal(str(len(rows))))  # the number of rows is a figure too
            for row in rows:
                for key, value in row.items():
                    if not _figure_key(key):
                        continue
                    number = _as_decimal(value)
                    if number is not None:
                        sums[key] = sums.get(key, Decimal(0)) + number
                fields = row.get("fields")
                if isinstance(fields, list):
                    for f in fields:
                        if isinstance(f, dict) and f.get("key") is not None:
                            number = _as_decimal(f.get("value"))
                            if number is not None:
                                k = f"fields:{f['key']}"
                                sums[k] = sums.get(k, Decimal(0)) + number
            for total in sums.values():
                add(total)
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for k, v in node.items():
                if _figure_key(k):
                    walk(v)

    walk(data)
    return found


def _answer_parts(args: Any) -> tuple[str, list[dict], list[dict], list[str]]:
    args = args if isinstance(args, dict) else {}
    text = args.get("text")
    figures = [f for f in (args.get("figures") or []) if isinstance(f, dict)] if isinstance(args.get("figures"), list) else []
    not_found = [n for n in (args.get("not_found") or []) if isinstance(n, dict)] if isinstance(args.get("not_found"), list) else []
    checked = args.get("not_checked")
    not_checked = [str(x).strip() for x in checked if str(x).strip()] if isinstance(checked, list) else []
    return (text.strip() if isinstance(text, str) else ""), figures, not_found, not_checked


def _found_ids(ledger: dict[str, dict]) -> set[str]:
    ids: set[str] = set()
    for entry in ledger.values():
        if entry["name"] == RESOLVE and entry["status"] == "ok" and isinstance(entry["data"], dict):
            for r in entry["data"].get("results") or []:
                if r.get("status") == "found":
                    ids.update(str(m.get("id")).lower() for m in r.get("matches") or [])
    return ids


def _fold_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _not_found_backed(what: str, call_id: Any, ledger: dict[str, dict], found: set[str]) -> bool:
    entry = ledger.get(str(call_id))
    if not entry:
        return False
    low = _fold_text(what)
    if entry["name"] == RESOLVE and entry["status"] == "ok" and isinstance(entry["data"], dict):
        for r in entry["data"].get("results") or []:
            term = _fold_text(str(r.get("term") or ""))
            if r.get("status") == "not_found" and term and (
                term == low or re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", low)
            ):
                return True
        return False
    if entry["status"] == "empty":
        ids = [str(v).lower() for values in _id_args(entry["args"]).values() for v in values]
        return bool(ids) and all(i in found for i in ids)
    return False


def verify_answer(args: Any, ledger: dict[str, dict], user_text: str) -> tuple[list[str], list[str]]:
    """(numbers in the text no tool result backs, not-found claims no tool call backs)."""
    text, _figures_unused, not_found, _ = _answer_parts(args)
    # A number is backed when any ok result of this turn holds it, or it is the total of a column
    # of returned rows. The figures' citations are informational.
    backed: set[str] = set()
    for entry in ledger.values():
        if entry["status"] == "ok":
            backed |= _number_leaves(entry["data"]) | _column_totals(entry["data"])
    user_forms = _supported_forms([user_text])
    bad_numbers: list[str] = []
    for _, _, written, forms in _figures(text):
        if not forms & (backed | user_forms) and written not in bad_numbers:
            bad_numbers.append(written)
    found = _found_ids(ledger)
    bad_not_found = [
        str(n.get("what") or "").strip()
        for n in not_found
        if not _not_found_backed(str(n.get("what") or ""), n.get("call_id"), ledger, found)
    ]
    return bad_numbers, [w for w in bad_not_found if w]


def _redact_written(text: str, bad: set[str]) -> str:
    out, last = [], 0
    for start, end, written, _ in _figures(text):
        if written in bad:
            out.append(text[last:start])
            out.append(NOT_VERIFIED)
            last = end
    out.append(text[last:])
    return "".join(out)


def _same_part(a: str, b: str) -> bool:
    x, y = _fold_text(a), _fold_text(b)
    return bool(x and y) and (x == y or (len(y) >= 3 and y in x) or (len(x) >= 3 and x in y))


def open_parts(args: Any, plan: list[str], on_limit: bool) -> list[str]:
    """Planned parts the answer neither answered nor (outside a limit) named as not checked."""
    args = args if isinstance(args, dict) else {}
    answered = [str(a) for a in args.get("answered") or []] if isinstance(args.get("answered"), list) else []
    checked = _answer_parts(args)[3]
    return [
        p for p in plan
        if not any(_same_part(p, a) for a in answered)
        and (on_limit or not any(_same_part(p, c) for c in checked))
    ]


def final_reply(
    args: Any, bad_numbers: list[str], bad_not_found: list[str], *, plan: list[str] | None = None,
    on_limit: bool = False,
) -> tuple[str, bool]:
    """The user-facing text of an accepted answer, and whether the model named what it did not check."""
    text, _, _, not_checked = _answer_parts(args)
    if bad_numbers:
        text = _redact_written(text, set(bad_numbers))
    if bad_not_found:
        text = f"I could not confirm that nothing exists for: {'; '.join(bad_not_found)}. {text}".strip()
    if not_checked:
        text = f"{text}\n\nNot checked: {'; '.join(not_checked)}.".strip()
    left = open_parts(args, plan or [], on_limit)
    if left:
        text = f"{text}\n\nI did not get to: {'; '.join(left)}.".strip()
    # No UUIDs in what a person reads.
    return _UUID_TEXT.sub("(id)", text), bool(not_checked)


def violation_message(bad_numbers: list[str], bad_not_found: list[str], empty_text: bool) -> str:
    parts = []
    if empty_text:
        parts.append("text is required")
    if bad_numbers:
        parts.append(
            "these numbers in text are not in any tool result of this turn and are not a column total of the rows returned: "
            + ", ".join(bad_numbers)
        )
    if bad_not_found:
        parts.append(
            "these not_found items are not backed by a crm_resolve not_found term or by an empty "
            "result whose ids came from crm_resolve: " + "; ".join(bad_not_found)
        )
    return "Fix and call answer again. " + "; ".join(parts) + "."


def limit_sentence(word: str, labels: list[str]) -> str:
    what = ", ".join(dict.fromkeys(labels)) if labels else "the rest of your question"
    return f"I stopped at the {word} limit before finishing, so I did not check: {what}."


# ------------------------------------------------------------------ write tools

CONFIRM_ACTION = "confirm_action"
CANCEL_ACTION = "cancel_action"


def _decision_schema(name: str, text: str, action_id: str) -> dict:
    """`action_id` can only be the pending action's id."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": text,
            "parameters": {
                "type": "object",
                "properties": {"action_id": {"type": "string", "enum": [action_id]}},
                "required": ["action_id"],
            },
        },
    }


def decision_schemas(action_id: str) -> list[dict]:
    return [
        _decision_schema(
            CONFIRM_ACTION,
            "Carry out the pending proposed changes, only when the user's latest message clearly says yes to them.",
            action_id,
        ),
        _decision_schema(
            CANCEL_ACTION,
            "Drop the pending proposed changes, when the user's latest message says no or asks to stop.",
            action_id,
        ),
    ]


def waiting_line(action) -> str:
    """The system prompt line that tells a later turn which change is waiting for a decision. Ids and a
    count only: the summary text carries names a third party typed, so it never goes in the system role."""
    n = len(action.steps or [])
    return f"A change is waiting for the user's decision (action {action.id}, {n} change(s))."


def waiting_reference(action) -> str:
    """The waiting change's summary lines, quoted as data in a message of their own."""
    return "Waiting change, for reference only: " + "; ".join(actions.proposal_lines(action))


def proposal_block(lines: list[str]) -> str:
    numbered = "\n".join(f"{n}. {line}" for n, line in enumerate(lines, 1))
    return f"I will make these changes when you confirm:\n{numbered}\nReply yes to go ahead, or tell me what to change."


def _propose(db, ctx, name: str, args: Any, steps: list[dict], seen_ids: set[str], action_id: str) -> ToolResult:
    if len(steps) >= actions.MAX_STEPS:
        return ToolResult("invalid", message=f"At most {actions.MAX_STEPS} changes per confirmation.")
    out, step = writes.propose_step(db, ctx, name, args, seen_ids=seen_ids)
    if step is None:
        return out
    steps.append(step)
    return ToolResult(
        "proposed",
        data={"action_id": action_id, "step": len(steps), "summary": step["summary"]},
        message="Proposed, not done. The user must confirm in a later message.",
    )


def _decide(db, ctx, name: str, args: Any, turn_id: str) -> ToolResult:
    """`confirm_action` / `cancel_action`: the model read the user's message; the server limits are `actions`."""
    action_id = args.get("action_id") if isinstance(args, dict) else None
    if not isinstance(action_id, str) or not action_id.strip():
        return ToolResult("invalid", message="action_id is required.")
    try:
        if name == CONFIRM_ACTION:
            outcome = actions.confirm(
                db, ctx.contact_respond_id, action_id.strip(), via="chat", turn_id=turn_id,
                operator_user_id=ctx.operator_user_id,
            )
        else:
            outcome = actions.cancel(
                db, ctx.contact_respond_id, action_id.strip(), operator_user_id=ctx.operator_user_id
            )
    except actions.ActionRefused as exc:
        return ToolResult("invalid", message=f"Not done: {exc.reason.replace('_', ' ')}.")
    return ToolResult(
        "ok", data={"status": outcome.status, "reply_text": outcome.reply_text, "steps": outcome.steps}
    )


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
    #: The proposal this turn stored: {"id", "turn_id", "lines", "expires_at"}, or None.
    pending_action: dict | None = None


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
    any_tool_result: bool = False
    #: Labels of tools that were refused, failed, timed out or never ran: what a limit left unchecked.
    unchecked: list[str] = field(default_factory=list)

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
    from app.services.llm_provider import resolve_api_key

    name, model = ai_prompt_registry.agent_model(db, PROMPT_KEY)
    if not name:
        name, model = DEFAULT_PROVIDER, DEFAULT_MODEL
    elif not model:
        model = DEFAULT_MODEL if name == DEFAULT_PROVIDER else None
    effort = ai_prompt_registry.agent_reasoning_effort(db, PROMPT_KEY) or DEFAULT_EFFORT
    cfg = db.query(AIAssistantConfig).order_by(AIAssistantConfig.created_at.asc()).first()
    key = resolve_api_key(cfg, name)
    if not key:
        raise _AgentUnavailable(f"no API key is configured for {name}")
    return _WrappedProvider(name, key, model or ""), name, model or "", effort


class _WrappedProvider:
    """The production model client: every call goes through `chatbot.llm_call`, the chatbot
    package's one wrapper around the provider (rate limits waited out, one hard deadline)."""

    def __init__(self, name: str, key: str, model: str) -> None:
        self.name, self._key, self.model = name, key, model

    def chat(self, messages: list[dict], *, timeout: float, model: str | None = None, **kwargs: Any) -> Any:
        from app.services.chatbot import llm_call

        return llm_call.chat(
            self.name, self._key, model or self.model, messages, deadline_seconds=timeout, timeout=timeout, **kwargs
        )


def _system_prompt(db, user_name: str) -> str:
    from app.services import ai_prompt_registry

    text = ai_prompt_registry.get_prompt(db, PROMPT_KEY).text
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{text}\n\nToday's date is {today}. You are working for {user_name}."


def _unique_call_id(raw: Any, used: set[str]) -> str:
    """A call id no earlier call of this turn has. Gemini names a call `gemini_<index>_<tool>`, so the
    same tool in two rounds repeats the id; the ledger, the citations and the tool replies all key on it."""
    base = str(raw) if raw else f"call_{uuid.uuid4().hex[:8]}"
    out, n = base, 1
    while out in used:
        n += 1
        out = f"{base}~{n}"
    used.add(out)
    return out


def _collect_names(data: Any, names: dict[str, str]) -> None:
    """id -> the name a result gave it, for the ids a tool call's arguments mention."""
    if isinstance(data, dict):
        label = next((str(data[k]) for k in ("title", "name", "customer_name", "product_code", "code", "label") if data.get(k)), None)
        if label and isinstance(data.get("id"), str):
            names.setdefault(data["id"].lower(), label)
        for v in data.values():
            _collect_names(v, names)
    elif isinstance(data, list):
        for v in data:
            _collect_names(v, names)


def _row_count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return sum(len(v) for v in data.values() if isinstance(v, list))
    return 0


def tool_detail(name: str, args: Any, out: ToolResult, names: dict[str, str]) -> str:
    """One tool call in plain words: what it was for, with what (ids as the names results gave, unknown
    ids left out) and how it ended. Never an id."""
    label = TOOL_LABELS.get(name) or name.replace("crm_", "").replace("_", " ")
    shown = []
    for key, value in (args if isinstance(args, dict) else {}).items():
        if key in GUARD_PARAMS:
            continue
        values = value if isinstance(value, list) else [value]
        if key.endswith(("_id", "_ids")):
            words = [names[str(v).lower()] for v in values if str(v).lower() in names]
        else:
            words = [str(v) for v in values if isinstance(v, (str, int, float)) and not isinstance(v, bool)]
        if words:
            shown.append(f"{key.replace('_', ' ').removesuffix(' ids').removesuffix(' id')}: {', '.join(words)}"[:80])
    head = f"{label} ({'; '.join(shown)})" if shown else label
    if out.status == "proposed":
        ending = f"{(out.data or {}).get('summary', '')} - proposed".strip(" -")
        text = f"{head}: {ending}"
    elif out.status == "empty":
        text = f"{head}: nothing found"
    elif out.status == "ok":
        rows = _row_count(out.data)
        if rows:
            text = f"{head}: {rows} row{'s' if rows != 1 else ''}"
        else:
            text = f"{head}: nothing found" if _is_rows(out.data) else f"{head}: done"
    elif out.status == "timeout":
        text = f"{head}: timed out"
    elif out.status == "error":
        text = f"{head}: failed"
    else:
        text = f"{head}: refused: {out.message}".strip()
    return _UUID_TEXT.sub("", text)


def reasoning_for_steps(text: Any) -> str:
    """A round's reasoning as the console shows it: no record ids, at most REASONING_CHARS."""
    if not isinstance(text, str):
        return ""
    cleaned = re.sub(r"[ \t]{2,}", " ", _UUID_TEXT.sub("", text)).strip()
    return cleaned if len(cleaned) <= REASONING_CHARS else cleaned[:REASONING_CHARS].rstrip() + "\u2026"


def _is_rows(data: Any) -> bool:
    return isinstance(data, list) or (isinstance(data, dict) and any(isinstance(v, list) for v in data.values()))


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

    steps: list[dict] = []
    action_id = ""
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
            result = send(
                messages, tools=tools, model=model, timeout=timeout,
                # The summary of older turns is a side call: it neither thinks nor shows thoughts.
                reasoning_effort=None if kind == "compaction" else effort,
                include_thoughts=kind != "compaction",
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
        thought = "" if kind == "compaction" else reasoning_for_steps(
            redact_ids(getattr(result, "reasoning_text", "") or "", (str(ctx.contact_respond_id), str(ctx.contact_pk)))
        )
        if thought:
            # For the console's steps only: never the reply, the history or a log line. A round's call
            # comes before its count goes up; the forced final answer is not a round, so it stays in the last one.
            number = max(run.rounds, 1) if kind == "final" else run.rounds + 1
            trace.add("agent_reasoning", {"kind_of_call": kind, "round": number, "text": thought})
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
            effort = ai_prompt_registry.agent_reasoning_effort(db, PROMPT_KEY) or DEFAULT_EFFORT
            name, picked = ai_prompt_registry.agent_model(db, PROMPT_KEY)
            provider_name, model = name or DEFAULT_PROVIDER, picked or DEFAULT_MODEL
        send = provider.chat

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

        if operator_user_id and str(operator_user_id) != str(ctx.user_id):
            ctx = dataclasses.replace(ctx, operator_user_id=str(operator_user_id))
        waiting = actions.pending_action(db, contact_respond_id, user_id=ctx.user_id)
        system = _system_prompt(db, ctx.user_name)
        if waiting is not None:
            system = f"{system}\n\n{waiting_line(waiting)}"
        messages: list[dict] = [{"role": "system", "content": system}]
        messages.extend(memory.history_messages(db, conv))
        if waiting is not None:
            messages.append({"role": "assistant", "content": waiting_reference(waiting)})
        messages.append({"role": "user", "content": text})
        schemas = tool_schemas(permitted_tools(db, ctx), catalog)
        schemas += [r.schema for r in writes.permitted_user_reads(db, ctx)]
        schemas += [w.schema for w in writes.permitted_writes(db, ctx)]
        if waiting is not None and actions.operator_may_decide(db, ctx, waiting):
            schemas += decision_schemas(str(waiting.id))
        schemas += [PLAN_SCHEMA, ANSWER_SCHEMA]
        action_id = str(uuid.uuid4())
        id_names: dict[str, str] = {}
        plan_parts: list[str] = []
        own_ids = (str(ctx.contact_respond_id), str(ctx.contact_pk))

        def scrub(args: dict) -> dict:
            """The answer's text without the contact's own ids, before anything is verified."""
            if isinstance(args.get("text"), str):
                return {**args, "text": redact_ids(args["text"], own_ids)}
            return args
        ledger: dict[str, dict] = {}
        seen_ids: set[str] = set()
        denied_domains: set[str] = set()
        used_call_ids: set[str] = set()
        repaired = False
        final_args: dict | None = None
        nudge = (
            "Finish by calling the answer tool now: put your reply in text, list every number in "
            "figures with the call_id that shows it, and anything you could not find in not_found."
        )

        def answer_of(result_obj: Any) -> dict:
            for c in result_obj.tool_calls or []:
                if c.get("name") == ANSWER:
                    return scrub(c.get("arguments") if isinstance(c.get("arguments"), dict) else {})
            return scrub({"text": (result_obj.content or "").strip()})

        def forced_final(why: str) -> tuple[str, bool]:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool use has ended for this turn ({why}). Call the answer tool now with what you "
                        "have, and name in not_checked what you could not check."
                    ),
                }
            )
            res = chat(messages, [ANSWER_SCHEMA], kind="final", grace=FINAL_GRACE)
            args = answer_of(res)
            bad_numbers, bad_nf = verify_answer(args, ledger, text)
            return final_reply(args, bad_numbers, bad_nf, plan=plan_parts, on_limit=True)

        def add_limit_sentence(reply_text: str, named: bool, word: str) -> str:
            if named:
                return reply_text
            return f"{reply_text}\n\n{limit_sentence(word, run.unchecked)}".strip()

        while True:
            try:
                result = chat(messages, schemas, kind="round")
            except (_ProviderFailed, TimeoutError):
                if not run.any_tool_result:
                    raise
                status, limit_hit = "limited", "error"
                reply, named = forced_final("the model call failed")
                if not named:
                    labels = ", ".join(dict.fromkeys(run.unchecked)) or "the rest of your question"
                    reply = f"{reply}\n\nI stopped because of an error before finishing, so I did not check: {labels}.".strip()
                break
            run.rounds += 1
            calls = list(result.tool_calls or [])
            if not calls:
                content = (result.content or "").strip()
                if not repaired and remaining() >= SIDE_CALL_MIN:
                    repaired = True
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": nudge})
                    continue
                final_args = scrub({"text": content})
                break

            assistant_calls = [
                {
                    "id": _unique_call_id(c.get("id"), used_call_ids),
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

            replies: dict[int, str] = {}
            answer_idx: int | None = None
            skipped = 0
            tool_index = 0
            for idx, call in enumerate(calls):
                name = str(call.get("name") or "")
                args = call.get("arguments")
                call_id = assistant_calls[idx]["id"]
                if name == ANSWER:
                    answer_idx = idx
                    continue
                if name == PLAN:
                    parts = args.get("parts") if isinstance(args, dict) else None
                    if isinstance(parts, list) and 1 <= len(parts) <= 10 and all(isinstance(p, str) and p.strip() for p in parts):
                        plan_parts[:] = [p.strip() for p in parts]
                        replies[idx] = ToolResult("ok", message="Plan recorded.").to_json(call_id)
                        trace.add("agent_plan", {"parts": plan_parts})
                    else:
                        replies[idx] = ToolResult("invalid", message="parts must be 1 to 10 non-empty strings.").to_json(call_id)
                    continue
                started = clock()
                if tool_index >= budgets.calls_per_round:
                    # A Gemini continuation must be replayed with a reply for every call it
                    # contains, so each extra call gets one; the digest and trace carry one note.
                    skipped += 1
                    run.unchecked.append(TOOL_LABELS.get(name, "another lookup"))
                    replies[idx] = ToolResult(
                        "denied", message="Too many calls this round; ask again next round."
                    ).to_json(call_id)
                    continue
                tool_index += 1
                # Each call gets what is left of the turn, at most 10 s.
                seconds = max(1, int(min(remaining(), MCP_CALL_TIMEOUT)))
                if name in writes.WRITES:
                    out = _propose(db, ctx, name, args, steps, seen_ids, action_id)
                elif name in writes.USER_READS:
                    out = writes.run_user_read(db, ctx, name, args, seen_ids)
                elif name in (CONFIRM_ACTION, CANCEL_ACTION):
                    out = _decide(db, ctx, name, args, turn_id)
                else:
                    out = dispatch(
                        db, ctx, name, args,
                        call=mcp_call if mcp_call is not None else mcp_builder(seconds),
                        catalog=catalog, timeout=float(seconds), seen_ids=seen_ids, denied_domains=denied_domains,
                    )
                ms = int((clock() - started) * 1000)
                payload = out.to_json(call_id)
                if out.status in ("ok", "empty"):
                    _collect_names(out.data, id_names)
                detail = tool_detail(name, args, out, id_names)
                run.any_tool_result = True
                ledger[call_id] = {
                    "name": name, "status": out.status,
                    "args": args if isinstance(args, dict) else {}, "data": out.data,
                }
                if out.status in ("denied", "invalid", "error", "timeout"):
                    run.unchecked.append(TOOL_LABELS.get(name, "another lookup"))
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
                        "detail": detail,
                    },
                )
                replies[idx] = payload
            if skipped:
                note = {"name": "(extra calls)", "args": {"skipped": skipped}, "status": "denied"}
                run.tool_calls.append({"name": note["name"], "status": "denied", "ms": 0})
                run.digest.append(note)
                trace.add("agent_tool", {**note, "ms": 0, "result_chars": 0, "more": 0})

            accepted = False
            if answer_idx is not None:
                args = calls[answer_idx].get("arguments")
                args = scrub(args if isinstance(args, dict) else {})
                bad_numbers, bad_nf = verify_answer(args, ledger, text)
                empty_text = not _answer_parts(args)[0]
                trace.add(
                    "agent_answer",
                    {"unbacked_numbers": bad_numbers, "unbacked_not_found": bad_nf, "repaired": repaired},
                )
                if not (bad_numbers or bad_nf or empty_text):
                    replies[answer_idx] = ToolResult("ok", message="Answer accepted.").to_json(assistant_calls[answer_idx]["id"])
                    final_args, accepted = args, True
                elif not repaired and remaining() >= SIDE_CALL_MIN:
                    # One repair round, and only with time to spare; otherwise redact below.
                    repaired = True
                    replies[answer_idx] = ToolResult(
                        "invalid", message=violation_message(bad_numbers, bad_nf, empty_text)
                    ).to_json(assistant_calls[answer_idx]["id"])
                else:
                    final_args, accepted = args, True
            for idx in range(len(calls)):
                messages.append(
                    {"role": "tool", "tool_call_id": assistant_calls[idx]["id"], "content": replies.get(idx, "{}")}
                )
            if accepted:
                break

            if run.rounds >= budgets.max_rounds:
                limit_hit = "rounds"
            elif remaining() <= 0:
                limit_hit = "seconds"
            elif run.prompt_tokens >= budgets.max_input_tokens:
                limit_hit = "input_tokens"
            if limit_hit:
                status = "limited"
                reply, named = forced_final(f"limit reached: {limit_hit}")
                reply = add_limit_sentence(reply, named, LIMIT_WORDS[limit_hit])
                break

        if final_args is not None:
            bad_numbers, bad_nf = verify_answer(final_args, ledger, text)
            reply, _ = final_reply(final_args, bad_numbers, bad_nf, plan=plan_parts)
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
    if status != "failed":
        reply = to_whatsapp(reply)
    pending = None
    if status != "failed" and steps:
        # After verification: the block is built by code from the stored steps, so its figures are not flagged.
        try:
            stored = actions.store_proposal(
                db, ctx, conversation_id=conversation_id, turn_id=turn_id, steps=steps, action_id=action_id
            )
            lines = actions.proposal_lines(stored)
            pending = actions.pending_dict(stored)
            reply = f"{reply}\n\n{proposal_block(lines)}"
        except Exception:  # noqa: BLE001 - the turn still closes
            logger.warning("agent: storing the proposal failed", exc_info=True)
            db.rollback()
            reply = f"{reply}\n\nI could not store the proposed changes, so nothing will be changed."

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
        pending_action=pending,
    )
