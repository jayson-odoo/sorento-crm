# The open question: every question the bot asks, as ONE object the parser answers
# (PR #1247 round 9, issue #1293).
#
# Owner, 26 Sep 2026 ~14:15Z: "I'm also curious in your methodology in making this work
# because I want to make sure this is as human and as natural as possible and not too
# much hard coding, hard routing." The rule this module serves: the parser READS, the
# code APPLIES. Whatever the bot last asked (a pick, a yes/no, the quantities) is stated
# to the parser as one object with its kind, its options and what is still owed; the
# parser returns one declared answer (`open_question_answer`); `turn/apply.py` acts on
# that answer and falls back to shape rules only when it is absent.
#
# A VIEW, not new state: the object is built from what the turn already stores (the
# pending pick or offer, else the stock task), so nothing here can disagree with it.
# Pure: no I/O, no word of the customer's message is ever read here.
from __future__ import annotations

from typing import Any

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.pending import Pending

PICK_ONE = "pick_one"
CHOOSE_BRAND = "choose_brand"
CONFIRM = "confirm"
QUANTITIES = task_mod.QUANTITIES
LAST_ANSWER = task_mod.LAST_ANSWER
#: Declared so the prompt and the code share one list, and never written: the owner's
#: no-paging, full-counts ruling means the bot never asks how many to show. The first
#: question of that kind is the trigger to build it.
HOW_MANY_TO_SHOW = "how_many_to_show"
FREE = "free"

KINDS: tuple[str, ...] = (
    PICK_ONE,
    CHOOSE_BRAND,
    CONFIRM,
    QUANTITIES,
    LAST_ANSWER,
    HOW_MANY_TO_SHOW,
    FREE,
)


def _options(pending: Pending) -> list[dict[str, Any]]:
    """The options as the parser needs them: the position, the code, and the printed
    label only when it is not the code (a customer's name beside its account code)."""
    out: list[dict[str, Any]] = []
    for option in pending.options:
        position = option.get("position")
        if not isinstance(position, int) or isinstance(position, bool):
            continue
        label = option.get("label")
        code = option.get("code") or label
        row: dict[str, Any] = {"position": position, "code": code}
        if label and label != code:
            row["label"] = label
        out.append(row)
    return out


def _kind(pending: Pending, options: list[dict[str, Any]]) -> str:
    if not options:
        return FREE
    payload = pending.payload or {}
    if pending.expects == "yes_no" or (payload.get("stock_pick") and len(options) == 1):
        # "Couldn't find ELP3753. Did you mean ELP3754?" and a one-team escalation offer
        # are answered by a yes or a no, never by a number.
        return CONFIRM
    if pending.kind == "brand_pick":
        return CHOOSE_BRAND
    return PICK_ONE


def of_pending(pending: Pending | None) -> dict[str, Any] | None:
    """The open pick or offer as the object, or None when nothing is open."""
    if pending is None:
        return None
    options = _options(pending)
    kind = _kind(pending, options)
    payload = pending.payload or {}
    stock = bool(payload.get("stock_pick"))
    qty = task_mod._number(payload.get("stock_qty")) if stock else None
    if kind == FREE:
        owed = ["answer"]
    elif kind == CONFIRM:
        owed = ["yes_no"]
    else:
        # A stock pick needs a quantity too; one given already rides on the pick.
        owed = ["pick", "quantity"] if stock and qty is None else ["pick"]
    obj: dict[str, Any] = {"kind": kind, "options": options, "owed": owed}
    if qty is not None:
        obj["qty"] = qty
    return obj


def open_question(pending: Pending | None, tasks: Any) -> dict[str, Any] | None:
    """The ONE question on the table: the open pick or offer, which is what the next
    message answers, else the stock question (`task.open_question`), else None."""
    obj = of_pending(pending)
    if obj is not None:
        return obj
    return task_mod.open_question(tasks)


def is_the_stock_question(obj: dict[str, Any] | None) -> bool:
    """Does this object state the stock task (so its `Open task:` hint is redundant)?"""
    return bool(obj) and obj.get("kind") in (QUANTITIES, LAST_ANSWER)
