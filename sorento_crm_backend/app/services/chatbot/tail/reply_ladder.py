"""What a lane's producers SAY, and the three string utilities the tail shares.

This is the half of the retired `compile_state.py` that survives the turn
re-architecture. The other half - the eight state rules, the pending markers, the offer
and picker carriers - is replaced by `turn/apply.py` and `turn/tail.py`: the conversation
state is now written from the `State` the turn actually computed, never re-derived from
the reply on the way out.

The ladder below is that node's own precedence, unchanged, because it is not state logic
at all: it is which producer's sentence wins when several ran. `lanes/canned.py`,
`lanes/escalation.py`, `lanes/casual.py` and the n8n `/complete` path all still produce
exactly these fragments (`tail/outcome.py` builds them), so they all still answer.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.chatbot import jsc

UNDEFINED = jsc.UNDEFINED

# U+2014, written as an escape rather than as the character itself. The repo's own hard
# rule forbids the byte in source (and the pre-push guard enforces it), but the merge arm
# below both EMITS one and FOLDS every one it finds.
EM_DASH = "\u2014"


def strip_undefined(value: Any) -> Any:
    """What `JSON.stringify` does to `undefined`: drop the key, null the array slot."""
    if isinstance(value, dict):
        return {k: strip_undefined(v) for k, v in value.items() if v is not UNDEFINED}
    if isinstance(value, list):
        return [None if v is UNDEFINED else strip_undefined(v) for v in value]
    return value


def sanitize_em_dash(value: Any) -> Any:
    """Deep-walk and fold every U+2014 to a hyphen (captain hard rule, 2026-08-22).

    Dynamic text (LLM, CRM, RAG sourced) must never carry an em-dash to a customer.
    """
    if isinstance(value, dict):
        for key, inner in value.items():
            if isinstance(inner, str):
                value[key] = inner.replace(EM_DASH, "-")
            elif isinstance(inner, (dict, list)):
                sanitize_em_dash(inner)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            if isinstance(inner, str):
                value[index] = inner.replace(EM_DASH, "-")
            elif isinstance(inner, (dict, list)):
                sanitize_em_dash(inner)
    return value


def seal(patch: Mapping[str, Any]) -> dict[str, Any]:
    """The `reply` contract, derived from ONE object, so the two views cannot drift."""
    return {
        "text": _u(patch, "user_response"),
        "quick_replies": _u(patch, "quick_reply"),
        "session_patch": patch,
    }


def _u(obj: Any, key: str) -> Any:
    """`obj.key` keeping `undefined` distinct from `null` (a JSON trip loses the key)."""
    if not jsc.has(obj, key):
        return UNDEFINED
    return obj.get(key)


_ESCALATE_TO_TEAM_RE = re.compile(
    r"(would you like me to escalate to )((?:[a-z0-9-]+ )*[a-z0-9-]+ team\?)", re.IGNORECASE
)


def compose_reply(outcome: Mapping[str, Any]) -> dict[str, Any]:
    """`{text, quick_replies, result_set}` from the 15-key producer map.

    Precedence, unchanged from the node this replaces: the ideate reply, then a
    date-suggest merged with a CS member roster, then either alone, then the canned
    catalog sentence, then the central exchange.
    """
    cat = outcome.get("escalate-catalog")
    mem = outcome.get("build-cs-member-offer")
    suggest_raw = outcome.get("build-suggest-offer")
    sug = (
        suggest_raw
        if (jsc.truthy(suggest_raw) and jsc.get(suggest_raw, "suggest_offer") is True)
        else None
    )
    ideate = outcome.get("build-ideate-reply")
    central = outcome.get("central-exchange")
    merge = bool(jsc.truthy(sug) and jsc.truthy(mem))

    response: Any = UNDEFINED
    include_response = True

    if jsc.truthy(ideate):
        response = _u(ideate, "response")
    elif merge:
        response = _merged_offer(sug, mem)
    elif jsc.truthy(sug):
        response = _u(sug, "suggest_response")
    elif jsc.truthy(mem):
        response = _u(mem, "response")
        include_response = jsc.get(mem, "includeResponse")
    elif jsc.truthy(cat):
        response = _u(cat, "response")
        include_response = jsc.get(cat, "includeResponse")
    elif jsc.truthy(central):
        response = _u(central, "response")

    quick_reply: Any = None
    access_choice = outcome.get("access-level-choice-message")
    if jsc.truthy(access_choice):
        offered = jsc.get(access_choice, "quick_reply")
        quick_reply = offered if len(offered or []) > 0 else None
    if jsc.truthy(sug):
        quick_reply = jsc.get(sug, "suggest_quick_reply")

    text = response if (include_response and response is not UNDEFINED) else None
    if isinstance(text, str):
        text = text.replace(EM_DASH, "-")
    return {
        "text": text,
        "quick_replies": quick_reply,
        "result_set": _result_set(outcome),
    }


def _result_set(outcome: Mapping[str, Any]) -> list[Any]:
    """The roster a bare number answers next turn, when a producer offered one."""
    for key in ("build-cs-member-offer", "build-suggest-offer", "promo-picker", "dym-annotate"):
        producer = outcome.get(key)
        for field in ("cs_last_result_set", "last_result_set", "suggest_result_set"):
            rows = jsc.get(producer, field) if jsc.truthy(producer) else None
            if jsc.is_array(rows) and len(rows) > 0:
                return list(rows)
    return []


def _merged_offer(sug: Any, mem: Any) -> str:
    """A date suggestion AND a CS roster both ran: show both, every row, in roster order."""
    rows = jsc.array(jsc.get(mem, "cs_last_result_set"))
    mem_companies: set[Any] = set()
    for row in rows:
        ids = jsc.get(row, "company_ids")
        ids = ids if (jsc.is_array(ids) and len(ids) > 0) else [jsc.get(row, "company_id") or None]
        for one in ids:
            mem_companies.add(one or None)
    routing_companies = jsc.get(mem, "routing_companies")
    multi_co = jsc.is_array(routing_companies) and len(routing_companies) > 1

    lines: list[str] = []
    for row in rows:
        companies = jsc.get(row, "companies")
        label = (
            companies
            if (jsc.is_array(companies) and len(companies) > 0)
            else ([jsc.get(row, "company_name")] if jsc.truthy(jsc.get(row, "company_name")) else [])
        )
        idx = jsc.js_string(jsc.get(row, "idx"))
        words = jsc.js_string(jsc.get(row, "label"))
        lines.append(
            f"{idx}. {words} ({' / '.join(jsc.js_string(x) for x in label)})"
            if (multi_co and label)
            else f"{idx}. {words}"
        )
    if multi_co:
        for pool in jsc.array(routing_companies):
            if (
                jsc.truthy(pool)
                and jsc.truthy(jsc.get(pool, "company_name"))
                and (jsc.get(pool, "company_id") or None) not in mem_companies
            ):
                lines.append(
                    f"[ {jsc.js_string(jsc.get(pool, 'company_name'))}: no customer-service "
                    f"members are configured {EM_DASH} omitted. ]"
                )
    picker = "\n".join(lines)
    multi_close = jsc.get(mem, "cs_multi_close")
    close = (
        multi_close
        if (multi_co and isinstance(multi_close, str) and multi_close)
        else "Or just reply 'yes' and we'll assign automatically."
    )
    offer_company = jsc.get(mem, "cs_offer_company")
    suggest_response = jsc.get(sug, "suggest_response")
    if isinstance(offer_company, str) and offer_company and isinstance(suggest_response, str):
        words: Any = _ESCALATE_TO_TEAM_RE.sub(
            lambda m: f"{m.group(1)}*{offer_company}* {m.group(2)}", suggest_response, count=1
        )
    else:
        words = suggest_response
    return (
        f"{jsc.js_string(words)}\n\nTo escalate, choose who to route to. "
        f"Reply the number or name:\n{picker}\n\n{jsc.js_string(close)}"
    )
