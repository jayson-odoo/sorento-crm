"""The sales analysis's basis, asked before the run (SALES-TOTAL-ASK, owner ruling 27 Oct 2026).

"Total sales should ask": a sales total (`crm_sales_analysis`, "total sales Jan 2026") whose
message names no basis is asked the sales ranking's own line, "Invoiced, delivered, ordered or
outstanding?" (`ranking_ask.RANKING_BASIS_LINE`, Invoiced first), never run on a default. The
question is a `required_fields` slot like the company question (`sales_company_ask`): the next
turn's parser is shown it with the four options (`turn/question.of_required_ask`) and says whether
the message answers it. Nothing here reads the typed text (owner rule, 28 Oct 2026).

* `settle` (lane): a fresh analysis with no basis is asked; the parser's declared answer (the basis
  it filled, or the option it picked) runs the first message's own ask with it.
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
#: A miss carries no word (only the parser's answer is read), so the give-up line names none.
GIVE_UP = "I still can't tell which basis you mean. Ask for the sales report again with the basis."

#: The answers, in the order the question lists them.
BASES = ("invoiced", "delivered", "ordered", "outstanding")
OPTIONS = tuple((basis, basis.capitalize()) for basis in BASES)

#: The first message's own axes, carried across the question onto the run.
CARRIED = ("sales_channel", "sales_company", "group_by", "top_n", "date_filter_start", "date_filter_end")


def _unread(_db: Any, _word: str, _extras: dict[str, Any]) -> rf.Resolved:
    """Never called with typed words: every answer is the parser's (`_reply`)."""
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
    # Owner rule (28 Oct): only the parser's declared answer answers it; a reply it declared none for drops the
    # question (`required_fields.reply_verdict`), and the typed text is never read here.
    answered_by_parser=True,
    answer_drops=("escalation", "sales_channel", "status", "document"),
))


def named_basis(parse_output: dict[str, Any]) -> str | None:
    """The basis the parser read off the message: the analysis's `sales_basis`, else the report key `basis`."""
    for key in ("sales_basis", "basis"):
        if parse_output.get(key) in BASES:
            return parse_output[key]
    return None


def _reply(parse_output: dict[str, Any]) -> rf.Resolved:
    """An answering turn's basis, from the parser's declared answer only: the one offered option it picked,
    else the basis it filled (`sales_basis` / `basis`). Anything else is a miss, asked again."""
    answer = parse_output.get("required_ask_answer") if isinstance(parse_output.get("required_ask_answer"), dict) else {}
    if answer.get("mode") == "pick":
        picked = [p for p in jsc.array(answer.get("picked")) if isinstance(p, int) and not isinstance(p, bool)]
        if len(picked) == 1 and 1 <= picked[0] <= len(BASES):
            return rf.Resolved("ok", value=BASES[picked[0] - 1], label=BASES[picked[0] - 1])
        return rf.Resolved("unknown", label="")
    basis = named_basis(parse_output)
    return rf.Resolved("ok", value=basis, label=basis) if basis else rf.Resolved("unknown", label="")


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
    totals only a filtered ask (`CATALOGUE_LINE`). No period said reads this calendar year to today, as the
    analysis does (`fetch.py`, the `crm_sales_analysis` builder), never a second question."""
    from app.services.chatbot.lanes.business import report_ask
    from app.services.reports.registry import today_malaysia

    group_by = "month" if parse_output.get("group_by") == "month" else "channel"
    period = {}
    if not parse_output.get("date_filter_start") and not parse_output.get("date_filter_end"):
        today = today_malaysia()
        period = {"date_filter_start": f"{today.year}-01-01", "date_filter_end": today.isoformat()}
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
            **period,
        },
        "",
    )
