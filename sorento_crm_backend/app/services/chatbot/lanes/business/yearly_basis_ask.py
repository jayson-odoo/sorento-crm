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


def _options() -> tuple[tuple[str, str], ...]:
    """The bases offered as a pick (Invoiced, delivered or ordered), in the question's own order."""
    from app.services.chatbot.lanes.business.fetch import SALES_ANALYSIS_BASES

    return tuple((b, b.capitalize()) for b in ("invoiced", "delivered", "ordered") if b in SALES_ANALYSIS_BASES)


def _unread(_db: Any, _word: str, _extras: dict[str, Any]) -> rf.Resolved:
    """The reply's words are never read here: only the parser's declared pick (`settle`)."""
    return rf.Resolved("unknown")


BASIS = rf.FieldSpec(name="basis", noun="basis", question=QUESTION, resolve=_unread, allow_all=False)

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
    # The parser is shown the three options (`turn/question.of_required_ask`) and a reply counts only through its
    # declared answer; no shape fallback (owner rule 28 Oct 2026).
    answered_by_parser=True,
))


def settle(db: Any, parse_output: dict[str, Any]) -> rf.Outcome | None:
    """None when nothing is asked (the message named a basis); otherwise the question to send instead of running, or
    the answered outcome (`run_input`). The answer is the parser's declared pick (or, for a fill, its own `sales_basis`
    reading), resolved against the offered options; never the reply's words."""
    slot = parse_output.get("required_ask")
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME:
        answer = parse_output.get("required_ask_answer")
        answer = answer if isinstance(answer, dict) else {}
        reply = rf.picked_option(slot, answer)
        if reply.status != "ok" and answer.get("mode") == "fill":
            said = jsc.js_string(parse_output.get("sales_basis") or "").strip()
            reply = next((rf.Resolved("ok", value=v, label=l) for v, l in _options() if v == said), reply)
        outcome = rf.collect(db, YEARLY_BASIS_ASK, slot=slot, reply=reply, cancel=answer.get("mode") == "cancel")
        if outcome.slot:
            outcome.reply = QUESTION  # one question, one wording (the pick's numbered list is the parser's, not shown)
        return outcome
    if jsc.js_string(parse_output.get("sales_basis") or "").strip() in dict(_options()):
        return None
    outcome = rf.collect(
        db, YEARLY_BASIS_ASK, given={"basis": rf.Resolved("ambiguous", options=_options())},
        extras={"carry": {key: parse_output.get(key) for key in CARRIED}},
    )
    outcome.reply = QUESTION
    return outcome


def run_input(outcome: rf.Outcome) -> dict[str, Any]:
    """The answered ask's run: the basis chosen, and the first message's own axes."""
    carried = jsc.get(outcome.extras, "carry") or {}
    out = {key: carried.get(key) for key in CARRIED if carried.get(key) is not None}
    out["sales_basis"] = (outcome.values.get("basis") or {}).get("value")
    return out
