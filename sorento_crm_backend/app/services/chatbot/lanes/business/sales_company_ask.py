"""The sales analysis's company, asked before the run (CHAT-PICK-QTY-STATE, SALES-COMPANY item 1).

A contact in two companies who names neither is asked which (AC-S1-21, "Sorento or Mocha?").
The ROUTE asked it (`app/api/v1/sales/analysis.py`), as result text: the chat layer stored no
question, so the reply "Sorento" was read against whatever else was open (a stale drill offer,
an escalation company pick, a brand filter) and the analysis never ran. The lane now asks the
same line itself, with the same companies in the same order (`analysis.contact_companies`),
through the shared `required_fields` slot, so the next message is read against THIS question.

* `settle` (lane): a fresh ask with no company and two or more companies is asked; the answer
  (the parser's declared pick) runs the first message's own analysis for that company.
* `as_answer` (engine seam, before `required_fields.reply_verdict`): a reply the parser read as
  naming an OFFERED company without declaring an answer (`sales_company`,
  `escalation.company_pick`, or an entity whose word is the company's name or code) is that
  company's pick. Parser fields only, matched by the pickers' own label rule
  (`turn/decide.picked_positions`); a message with a domain word of its own is its own ask.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot import required_fields as rf

ASK_NAME = "sales_company"
QUESTION = "Which company?"
CANCELLED = "Sales report cancelled."
GIVE_UP = "I still can't tell which company '{word}' is. Ask for the sales report again with the company."
GIVE_UP_BLANK = "I still can't tell which company you mean. Ask for the sales report again with the company."

#: The first message's own axes, carried across the question onto the run.
CARRIED = ("sales_channel", "sales_basis", "group_by", "top_n", "date_filter_start", "date_filter_end")


def _unread(_db: Any, _word: str, _extras: dict[str, Any]) -> rf.Resolved:
    """The reply's words are never read here: only the parser's declared pick (`settle`)."""
    return rf.Resolved("unknown")


COMPANY = rf.FieldSpec(name="company", noun="company", question=QUESTION, resolve=_unread, allow_all=False)

SALES_COMPANY_ASK = rf.register(rf.AskType(
    name=ASK_NAME,
    fields=(COMPANY,),
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
    answered_by_parser=True,
    # A company answer is never a handover: the escalation reading the parser put on it goes.
    answer_drops=("escalation",),
))


def _offered(slot: dict[str, Any]) -> list[dict[str, Any]]:
    """The slot's options as picker options: the company's name is the label, its code an alias."""
    codes = list(jsc.get(slot.get("extras"), "codes") or [])
    return [
        {
            "position": i,
            "label": str(option[1]),
            "payload": {"aliases": [str(codes[i - 1])] if i <= len(codes) and codes[i - 1] else []},
        }
        for i, option in enumerate(slot.get("options") or [], start=1)
        if isinstance(option, (list, tuple)) and len(option) == 2
    ]


def as_answer(verdict: dict[str, Any], slot: dict[str, Any] | None) -> dict[str, Any]:
    """Engine seam, the company question open: the verdict with the offered company it names
    declared as the pick, or the verdict unchanged."""
    from app.services.chatbot.turn import pending as turn_pending
    from app.services.chatbot.turn.decide import domain_in_message, picked_positions

    if not isinstance(slot, dict) or slot.get("ask") != ASK_NAME:
        return verdict
    answer = verdict.get("open_question_answer")
    if (isinstance(answer, dict) and answer.get("mode") in rf.ANSWER_MODES) or domain_in_message(verdict) is True:
        return verdict
    escalation = verdict.get("escalation") if isinstance(verdict.get("escalation"), dict) else {}
    words = [w for w in (verdict.get("sales_company"), escalation.get("company_pick")) if isinstance(w, str) and w.strip()]
    named = {
        **verdict,
        "entities": [
            *[e for e in jsc.array(verdict.get("entities")) if isinstance(e, dict)],
            *[{"raw": w, "current_message": True} for w in words],
        ],
    }
    offered = _offered(slot)
    picked = picked_positions(turn_pending.ask(ASK_NAME, offered), named)
    positions = sorted(set(picked[0])) if picked else []
    if len(positions) != 1 or not 1 <= positions[0] <= len(offered):
        return verdict
    return {**verdict, "open_question_answer": {"mode": "pick", "picked": positions, "items": [], "qty_for_all": None}}


def _companies(db: Any, contact_id: Any, space_id: Any) -> list[tuple[str, str, str]]:
    from app.api.v1.sales.analysis import contact_companies
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    if db is None or not contact_id or not str(contact_id).strip():
        return []
    resolved = resolve_contact_with_null_workspace_fallback(
        db, contact_id=str(contact_id).strip(), space_id=(str(space_id).strip() or None) if space_id else None
    )
    return contact_companies(db, str(resolved)) if resolved else []


def settle(db: Any, parse_output: dict[str, Any], *, contact_id: Any, space_id: Any) -> rf.Outcome | None:
    """None when nothing is asked (the message named a company, or the contact holds one);
    otherwise the line to send instead of running, or the answered outcome (`run_input`)."""
    from app.api.v1.sales.analysis import company_question

    slot = parse_output.get("required_ask")
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME:
        answer = parse_output.get("required_ask_answer")
        answer = answer if isinstance(answer, dict) else {}
        options = list(slot.get("options") or [])
        picked = [p for p in (answer.get("picked") or []) if isinstance(p, int) and not isinstance(p, bool)]
        reply = rf.Resolved("unknown", label="")
        if answer.get("mode") == "pick" and picked and 1 <= picked[0] <= len(options):
            value, label = options[picked[0] - 1]
            reply = rf.Resolved("ok", value=value, label=label)
        return rf.collect(db, SALES_COMPANY_ASK, slot=slot, reply=reply, cancel=answer.get("mode") == "cancel")
    if jsc.truthy(parse_output.get("sales_company")):
        return None
    companies = _companies(db, contact_id, space_id)
    if len(companies) < 2:
        return None
    outcome = rf.collect(
        db,
        SALES_COMPANY_ASK,
        given={"company": rf.Resolved("ambiguous", options=tuple((name, name) for _id, name, _code in companies))},
        extras={
            "codes": [code for _id, _name, code in companies],
            "carry": {key: parse_output.get(key) for key in CARRIED},
        },
    )
    # The route's own line, not the helper's numbered list: one question, one wording.
    outcome.reply = company_question([name for _id, name, _code in companies])
    return outcome


def run_input(outcome: rf.Outcome) -> dict[str, Any]:
    """The answered ask's run: the company picked, and the first message's own axes."""
    carried = jsc.get(outcome.extras, "carry") or {}
    out = {key: carried.get(key) for key in CARRIED if carried.get(key) is not None}
    out["sales_company"] = (outcome.values.get("company") or {}).get("value")
    return out
