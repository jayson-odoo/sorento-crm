"""The sales analysis's basis, asked before the run (SALES-TOTAL-ASK, owner ruling 27 Oct 2026).

"Total sales should ask": a sales total (`crm_sales_analysis`, "total sales Jan 2026") whose
message names no basis is asked the sales ranking's own line, "Invoiced, delivered, ordered or
outstanding?" (`ranking_ask.RANKING_BASIS_LINE`, Invoiced first), never run on a default. The
question is a `required_fields` slot like the company question (`sales_company_ask`), so the next
message is read against it.

* `settle` (lane): a fresh analysis with no basis is asked; the answer (the parser's `basis` or
  `sales_basis`, a position, or the basis word) runs the first message's own ask with it.
* Outstanding is not a basis of `crm_sales_analysis`: that answer runs the report ask's
  outstanding total instead (`as_report_ask`), never a defaulted figure.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot import required_fields as rf
from app.services.chatbot.lanes.business import ranking_ask

ASK_NAME = "sales_basis"
CANCELLED = "Sales report cancelled."
GIVE_UP = "I still can't tell which basis '{word}' is. Ask for the sales report again with the basis."
GIVE_UP_BLANK = "I still can't tell which basis you mean. Ask for the sales report again with the basis."

#: The answers, in the order the question lists them.
BASES = ("invoiced", "delivered", "ordered", "outstanding")
OPTIONS = tuple((basis, basis.capitalize()) for basis in BASES)

#: The first message's own axes, carried across the question onto the run.
CARRIED = ("sales_channel", "sales_company", "group_by", "top_n", "date_filter_start", "date_filter_end")


def _unread(_db: Any, _word: str, _extras: dict[str, Any]) -> rf.Resolved:
    """A typed word is matched against the options by the helper (`_from_pick`); nothing else."""
    return rf.Resolved("unknown")


BASIS = rf.FieldSpec(
    name="basis", noun="basis", question=ranking_ask.RANKING_BASIS_LINE, resolve=_unread, allow_all=False
)

SALES_BASIS_ASK = rf.register(rf.AskType(
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
    answered_by_parser=True,
    # A bare "1" or "invoiced" the parser declared no answer for is still the answer, as the
    # ranking's own basis question reads it (REPORT-SMART-L S3-1).
    shape_fallback=True,
    answer_drops=("escalation", "sales_channel", "status", "document"),
))


def named_basis(parse_output: dict[str, Any]) -> str | None:
    """The basis the parser read off the message: the analysis's `sales_basis`, else the report key `basis`."""
    for key in ("sales_basis", "basis"):
        if parse_output.get(key) in BASES:
            return parse_output[key]
    return None


def _reply(parse_output: dict[str, Any]) -> rf.Resolved | str:
    """An answering turn's basis: the parser's own reading, else its declared pick, else the reply's words
    (a position or an option's name, matched by the helper)."""
    basis = named_basis(parse_output)
    if basis:
        return rf.Resolved("ok", value=basis, label=basis)
    answer = parse_output.get("required_ask_answer") if isinstance(parse_output.get("required_ask_answer"), dict) else {}
    picked = [p for p in jsc.array(answer.get("picked")) if isinstance(p, int) and not isinstance(p, bool)]
    if len(picked) == 1 and 1 <= picked[0] <= len(BASES):
        basis = BASES[picked[0] - 1]
        return rf.Resolved("ok", value=basis, label=basis)
    return jsc.js_string(parse_output.get("required_ask_reply") or "")


def settle(db: Any, parse_output: dict[str, Any]) -> rf.Outcome | None:
    """None when nothing is asked (the message named a basis); otherwise the question to send instead of
    running, or the answered outcome (`run_input`)."""
    slot = parse_output.get("required_ask")
    if isinstance(slot, dict) and slot.get("ask") == ASK_NAME:
        answer = parse_output.get("required_ask_answer")
        cancel = isinstance(answer, dict) and answer.get("mode") == "cancel"
        outcome = rf.collect(db, SALES_BASIS_ASK, slot=slot, reply=_reply(parse_output), cancel=cancel)
        if outcome.slot is not None:
            outcome.reply = ranking_ask.RANKING_BASIS_LINE  # asked again in the same words, never a numbered list
        return outcome
    if named_basis(parse_output):
        return None
    outcome = rf.collect(
        db,
        SALES_BASIS_ASK,
        given={"basis": rf.Resolved("ambiguous", options=OPTIONS)},
        extras={"carry": {key: parse_output.get(key) for key in CARRIED}},
    )
    # The ranking's own line, Invoiced first: one question, one wording.
    outcome.reply = ranking_ask.RANKING_BASIS_LINE
    return outcome


def run_input(outcome: rf.Outcome) -> dict[str, Any]:
    """The answered ask's run: the first message's own axes (the empty ones too) and the basis picked."""
    carried = jsc.get(outcome.extras, "carry") or {}
    out = {key: carried.get(key) for key in CARRIED}
    out["sales_basis"] = (outcome.values.get("basis") or {}).get("value")
    return out


def as_report_ask(parse_output: dict[str, Any]) -> dict[str, Any]:
    """An outstanding answer: the report ask's outstanding orders laid out as the analysis lays its total out,
    one line per channel (or the months, for a month split), in RM, over the first message's channel and period,
    read by `report_ask.settle` like any breakdown (`report_breakdown`). Not an axis-less total: the report ask
    totals only a filtered ask (`CATALOGUE_LINE`)."""
    from app.services.chatbot.lanes.business import report_ask

    group_by = "month" if parse_output.get("group_by") == "month" else "channel"
    return report_ask.take_words(
        {
            **{k: v for k, v in parse_output.items() if k not in ("required_ask", "required_ask_answer", "required_ask_reply", "sales_basis")},
            **report_ask.SALES_RANKING_ASK.reroute,
            "basis": "outstanding",
            "group_by": group_by,
            "measure": "amount",
            "report_breakdown": True,
            "capability_from": "sales_analysis",
            "entities": [],
        },
        "",
    )
