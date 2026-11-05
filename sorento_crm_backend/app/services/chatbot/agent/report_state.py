"""AGENT-REPORTS: sales and outstanding report asks on the agent, behind one switch (default off).

Plan: `documentation/plans/chatbot/PLAN-agent-reports-5nov.md`. The agent answers a report ask with
the shared report service (`crm_report_ask`), never its own SQL. What it showed last is the "held
report": the full arguments of the last report call that answered, kept on each agent turn's
response (`report_state`) and handed back to the model every turn as one short block, so a
follow-up ("clear all", "all brands", "by dealer and project") changes it by calling the tool
again with the whole new filter set. Memory's tool digest clips arguments (`memory._ARGS_CLIP`),
which is why the held report is stored on its own.

Nothing here runs while `system_settings.chatbot_agent_reports_enabled` is off.
"""
from __future__ import annotations

import json
from typing import Any

REPORT = "crm_report_ask"
SWITCH_COLUMN = "chatbot_agent_reports_enabled"
#: The most characters of held arguments put in the block (a long id list is cut, never the keys).
ARGS_CHARS = 1500
#: The lines of the card kept as its head (title, filter lines, period): never its rows.
HEAD_LINES = 12
HEAD_CHARS = 800

PROTOCOL = (
    "SALES AND OUTSTANDING REPORTS\n"
    "Every sales or outstanding figure comes from crm_report_ask, never from another tool or your own sums. "
    "The held report below is what the user sees now. Each report call states the WHOLE filter set: start from the "
    "held arguments, change only what the latest message changes, and call again. Plain language decides the "
    "change: 'clear all' or 'remove the filters' drops every filter (company, brand, category, channel, account "
    "type, customer, sales agent, product, location, spec) and the breakdown, keeps the basis and the period, and "
    "calls at once without asking anything; 'all brands' drops brand_ids, 'all categories' drops category_ids; "
    "'by dealer and project' or 'dealer vs project' is group_by channel (no channel filter); a new period, basis "
    "or measure replaces only that argument. Never ask which brand, company or account type a word means when the "
    "held report or the conversation already decides it; a word naming the held company stays the company. Ask "
    "only for what is still unknown: the sales basis is never assumed (offer invoiced first), and a missing period "
    "is asked. Reuse the held ids as they are; resolve only a new name. When a report answers, your answer text "
    "is the tool's response text exactly as returned, with at most one short line before it. Dates dd/mm/yyyy. "
    "No apologies."
)


def switch_on(db) -> bool:
    """The admin switch: `system_settings.chatbot_agent_reports_enabled`. Any read failure is off."""
    from app.models.user import SystemSetting

    try:
        row = db.query(getattr(SystemSetting, SWITCH_COLUMN)).first()
    except Exception:  # noqa: BLE001 - a settings read never fails a turn or a route
        return False
    return bool(row and row[0])


def _clean_args(args: Any) -> dict:
    from app.services.chatbot.agent.tools import GUARD_PARAMS, VIEW_PARAM

    if not isinstance(args, dict):
        return {}
    return {k: v for k, v in args.items() if k not in GUARD_PARAMS and k != VIEW_PARAM and v not in (None, "", [])}


def card_text(data: Any) -> str:
    """The report card a call answered with: the presenter's `response` text, or ""."""
    if isinstance(data, dict) and isinstance(data.get("response"), str):
        return data["response"].strip()
    return ""


def _head(card: str) -> str:
    lines: list[str] = []
    for line in card.splitlines():
        if not line.strip() or line.startswith("Total"):
            break
        lines.append(line)
        if len(lines) >= HEAD_LINES:
            break
    return "\n".join(lines)[:HEAD_CHARS]


def answered_calls(ledger: dict[str, dict]) -> list[dict]:
    """This turn's report calls that answered, in call order."""
    return [e for e in ledger.values() if e.get("name") == REPORT and e.get("status") == "ok"]


def from_ledger(ledger: dict[str, dict]) -> dict | None:
    """The held report after this turn: the last report call that answered, or None when none did."""
    calls = answered_calls(ledger)
    if not calls:
        return None
    last = calls[-1]
    return {"args": _clean_args(last.get("args")), "head": _head(card_text(last.get("data")))}


def held(db, conv) -> dict | None:
    """The conversation's held report: `report_state` of its newest finished turn that carries one."""
    from app.services.chatbot.agent import memory

    for turn in reversed(memory.conversation_turns(db, conv)):
        response = turn.response if isinstance(turn.response, dict) else None
        if response is None:
            continue
        state = response.get("report_state")
        if isinstance(state, dict) and isinstance(state.get("args"), dict):
            return state
    return None


def block(state: dict | None) -> str:
    """The system lines the model reads each turn: the protocol, then the held report (or none)."""
    if not state:
        return f"{PROTOCOL}\n\nHeld report: none yet."
    args = json.dumps(state.get("args") or {}, ensure_ascii=False, default=str, sort_keys=True)
    if len(args) > ARGS_CHARS:
        args = args[:ARGS_CHARS] + "..."
    head = str(state.get("head") or "").strip()
    shown = f"\nWhat the user sees as its head:\n{head}" if head else ""
    return f"{PROTOCOL}\n\nHeld report arguments: {args}{shown}"


def seed_ids(state: dict | None, seen: set[str]) -> None:
    """The held report's ids count as shown this turn: they came from an earlier call that answered for
    this same user and grants (a new grant set starts a new conversation), and the route checks every
    id against the asker's companies again (`report_ask._lookup_pairs`)."""
    from app.services.chatbot.agent.tools import _id_args

    if not state or not isinstance(state.get("args"), dict):
        return
    for values in _id_args(state["args"]).values():
        for value in values:
            if isinstance(value, str):
                seen.add(value.strip().lower())


def with_cards(reply: str, ledger: dict[str, dict]) -> str:
    """The reply in the report card format users already read: when a card this turn answered with is
    missing from the model's text, the reply is the cards themselves (code, not the model)."""
    cards = [c for c in (card_text(e.get("data")) for e in answered_calls(ledger)) if c]
    if not cards or all(c in reply for c in cards):
        return reply
    return "\n\n".join(cards)
