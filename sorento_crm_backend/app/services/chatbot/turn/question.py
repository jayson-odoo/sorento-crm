# The open question object: whatever the bot has just asked, stated to the parser as one
# structured fact (issue #1293).
#
# The owner, 26 Sep 2026 (after the round 8 console test of PR #1247): "I want to say 'the
# first one I need two' ... not too much hard coding, hard routing." Round 8 stated only the
# stock QUANTITY question as an object; a pick list reached the parser as a flat options
# line, so an answer that picked AND gave a quantity in one breath was read by a shape rule
# and half understood.
#
# The rule this module exists for: the parser READS, the code APPLIES. Every question the
# bot asks is described here, once, with its kind, its options and what is still owed; the
# parser answers it in the declared `open_question_answer` object, and `turn/apply.py`
# acts on that object (`_pick_answer`, `_open_question_answer`). No word of the message is
# read here or there - ordinals, "both", "dua", "第一个" belong to the parser's contract.
#
# Pure: no I/O, no message words.
from __future__ import annotations

from typing import Any

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.pending import ESCALATION_OFFER_KINDS

PICK_ONE = "pick_one"
QUANTITIES = "quantities"
CONFIRM = "confirm"
CHOOSE_BRAND = "choose_brand"
FREE = "free"

#: Every kind of question the bot asks today. "how_many_to_show" is not one: no reply asks
#: how many rows to show (full counts, no "more" paging - standing rulings). The first reply
#: that asks it is the trigger to add it.
QUESTION_KINDS: tuple[str, ...] = (PICK_ONE, QUANTITIES, CONFIRM, CHOOSE_BRAND, FREE)


def _kind(pending: Any) -> str:
    options = list(pending.options or [])
    if not options:
        return FREE
    if pending.expects == "yes_no":
        return CONFIRM
    payload = pending.payload or {}
    if payload.get("did_you_mean") and len(options) == 1:
        # "Couldn't find ELP3753. Did you mean ELP3754?" is answered yes or no.
        return CONFIRM
    if pending.kind == "brand_pick":
        return CHOOSE_BRAND
    return PICK_ONE


def _option(option: dict[str, Any]) -> dict[str, Any]:
    """One option as the parser reads it: its number, the code it resolves to, and the
    printed name when that is not the code (a customer's name)."""
    label = option.get("label")
    # A persisted option's payload may be anything JSON carries (hand pass 11, N-b): only
    # a dict has a value to read.
    payload = option.get("payload") if isinstance(option.get("payload"), dict) else {}
    code = option.get("code") or payload.get("value") or label
    out: dict[str, Any] = {"position": option.get("position"), "code": code}
    if label and str(label) != str(code):
        out["label"] = label
    return out


def pending_question(pending: Any) -> dict[str, Any] | None:
    """The open pending as the object, or None when nothing is pending."""
    if pending is None:
        return None
    kind = _kind(pending)
    payload = pending.payload or {}
    answered = set(pending.answered_positions)
    options = [
        _option(o)
        for o in pending.options or []
        if isinstance(o, dict) and o.get("position") not in answered
    ]
    owed = {PICK_ONE: ["pick"], CHOOSE_BRAND: ["pick"], CONFIRM: ["yes_no"], FREE: ["reply"]}[kind]
    out: dict[str, Any] = {"kind": kind, "options": options, "owed": list(owed)}
    if payload.get("stock_pick") and pending.kind not in ESCALATION_OFFER_KINDS:
        # A dealer's stock pick: the stock check behind it needs a quantity. The one the
        # dealer already gave rides on the pick; else it is owed too.
        qty = task_mod._number(payload.get("stock_qty"))
        if qty is None:
            out["owed"].append("qty")
        else:
            out["qty"] = qty
    return out


def open_question(pending: Any, tasks: Any) -> dict[str, Any] | None:
    """The ONE question on the table: the open pending (a pick, a confirm, a brand roster),
    else the stock quantities question (`task.open_question`), else None."""
    return pending_question(pending) or task_mod.open_question(tasks)
