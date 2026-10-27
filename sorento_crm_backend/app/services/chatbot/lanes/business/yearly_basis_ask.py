"""The Yearly comparison's basis, asked before the run (REPORT-UNIFY phase 3, R3; owner ruling 27 Oct: a sales total
never defaults its basis).

The Yearly comparison (axis year, `crm_sales_analysis`) answers invoiced, delivered or ordered. A ask that names none is
asked "Invoiced, delivered or ordered?" through the shared `required_fields` slot (the `sales_company_ask` pattern), so the
next message is read against THIS question; the answer re-runs the first message's analysis with that basis, its channel,
axis and window riding the slot. `settle` is the lane's call; `run_input` the answered ask's run.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot import required_fields as rf

ASK_NAME = "yearly_basis"
QUESTION = "Invoiced, delivered or ordered?"
CANCELLED = "Sales report cancelled."
GIVE_UP = "I still can't tell which basis '{word}' is. Ask for the yearly comparison again with the basis."
GIVE_UP_BLANK = "I still can't tell which basis you mean. Ask for the yearly comparison again with the basis."

#: The first message's own axes, carried across the question onto the run (`sales_company_ask.CARRIED` plus the company).
CARRIED = ("sales_channel", "group_by", "top_n", "date_filter_start", "date_filter_end", "sales_company")


def _bases() -> tuple[str, ...]:
    from app.services.chatbot.lanes.business.fetch import SALES_ANALYSIS_BASES

    return SALES_ANALYSIS_BASES


def _resolve(_db: Any, word: str, extras: dict[str, Any]) -> rf.Resolved:
    """The reply's basis: the parser's own reading (`sales_basis`), else the word itself when it is one of the bases."""
    said = jsc.js_string(extras.get("reply_basis") or "").strip().lower()
    typed = " ".join(jsc.js_string(word).split()).lower()
    for candidate in (said, typed):
        if candidate in _bases():
            return rf.Resolved("ok", value=candidate, label=candidate)
    return rf.Resolved("unknown")


BASIS = rf.FieldSpec(name="basis", noun="basis", question=QUESTION, resolve=_resolve, allow_all=False)

YEARLY_BASIS_ASK = rf.register(rf.AskType(
    name=ASK_NAME,
    fields=(BASIS,),
    reroute={
        "message_type": "business_query",
        "intent_hint": "check_order",
        "domain_hint": "order",
        "order_status": "sales_analysis",
        "document": None,
        "status": None,
    },
    cancelled=CANCELLED,
    give_up=GIVE_UP,
    give_up_blank=GIVE_UP_BLANK,
    answer_drops=("escalation",),
))


def settle(db: Any, parse_output: dict[str, Any]) -> rf.Outcome | None:
    """None when nothing is asked (the message named a basis); otherwise the question to send instead of running, or
    the answered outcome (`run_input`)."""
    slot = parse_output.get("required_ask")
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME:
        reply = jsc.js_string(parse_output.get("required_ask_reply") or "")
        return rf.collect(
            db, YEARLY_BASIS_ASK, slot=slot, reply=reply, extras={"reply_basis": parse_output.get("sales_basis")}
        )
    if jsc.js_string(parse_output.get("sales_basis") or "").strip().lower() in _bases():
        return None
    return rf.collect(
        db, YEARLY_BASIS_ASK, extras={"carry": {key: parse_output.get(key) for key in CARRIED}}
    )


def run_input(outcome: rf.Outcome) -> dict[str, Any]:
    """The answered ask's run: the basis chosen, and the first message's own axes."""
    carried = jsc.get(outcome.extras, "carry") or {}
    out = {key: carried.get(key) for key in CARRIED if carried.get(key) is not None}
    out["sales_basis"] = (outcome.values.get("basis") or {}).get("value")
    return out
