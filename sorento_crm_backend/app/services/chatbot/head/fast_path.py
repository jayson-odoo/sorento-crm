"""Messages the turn can read WITHOUT the semantic parser (PR #1247 round 6).

Owner console test of round 4 (26 Sep 2026): the dealer's "tia" failed with a 429 from
the model, and the parser spends about 25,000 tokens on every turn, so a handful of
turns a minute uses the whole tokens-per-minute budget. A message whose meaning is
fixed by its shape alone needs no model:

* small talk ("tia", "thanks", "ok"): a fixed reply, no parser and no clarifier
  (ruling 4). "ok" is small talk only while nothing is open: under "Did you mean
  ELP3754?" it is a yes, and only the parser may read it.
* a quantity for the open stock question (rulings 1 and 2): one number, which applies
  to every product still owed ("10"), or numbered lines ("1. 10, 2. 5", or the
  question's own lines pasted back filled in). Read only while the stock question is
  the thing being answered, never under an open which-one list, where a number is a
  pick (round 4).

What comes back is a parser emission with every declared key, exactly as if the parser
had said it, so everything after the parser (APPLY, the route, the lanes, the trace)
runs unchanged. A message that does not match is None, and the parser reads it as
before. This reads the message's SHAPE, and it is the only place outside the parser
that does: `turn/` still never reads a word.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.chatbot.turn import task as task_mod

THANKS_REPLY = "You're welcome."
ACK_REPLY = "Noted."

_THANKS = frozenset(
    {
        "tia",
        "thanks",
        "thank you",
        "thankyou",
        "thank u",
        "thanks a lot",
        "thank you very much",
        "many thanks",
        "thx",
        "tq",
        "tqvm",
        "ty",
        "terima kasih",
        "谢谢",
        "多谢",
        "🙏",
    }
)
_ACK = frozenset(
    {"ok", "okay", "okey", "oki", "okie", "k", "noted", "alright", "got it", "sure", "👍", "👌"}
)

_PUNCTUATION_RE = re.compile(r"[.!,~]+")
_SPACE_RE = re.compile(r"\s+")

_UNIT = r"(?:\s*(?:pcs|pc|units?|nos?|sets?))?"
_BARE_NUMBER_RE = re.compile(rf"^\s*(\d{{1,6}}){_UNIT}\s*\.?\s*$", re.IGNORECASE)
# "1. 10", "1) 10", "1: 10", "1 - 10", "1 10", and a pasted line "1. SRTWC286-SH - 10".
_LINE_RE = re.compile(
    rf"""^\s*(?P<pos>\d{{1,2}})\s*(?:[.):=]|\s-\s|\s)\s*
        (?:(?P<code>[A-Za-z][A-Za-z0-9./-]*?)\s*(?:\s-\s|[:=]|\sx\s|\s)\s*)?
        (?P<qty>\d{{1,6}}){_UNIT}\s*$""",
    re.IGNORECASE | re.VERBOSE,
)
_SEGMENT_SPLIT_RE = re.compile(r"[\n,;]+")
# The question's own lines pasted back: its header, and a product line left blank.
_UNFILLED_RE = re.compile(
    r"^\s*(?:how many units for each\??|\d{1,2}\s*[.)]\s*[A-Za-z][A-Za-z0-9./-]*\s*-?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FastRead:
    """`kind` is "small_talk" (then `reply` is what the turn says) or
    "stock_quantity"; `verdict` is the emission the parser would have returned."""

    kind: str
    verdict: dict[str, Any]
    reply: str | None = None


def _said_nothing(schema: dict[str, Any]) -> Any:
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    if "null" in kinds:
        return None
    if "array" in kinds:
        return []
    if "object" in kinds:
        return {key: _said_nothing(sub) for key, sub in (schema.get("properties") or {}).items()}
    if "boolean" in kinds:
        return False
    return None


def said_nothing() -> dict[str, Any]:
    """Every declared key at its "the message said nothing about this" value."""
    from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA

    return _said_nothing(PARSE_OUTPUT_JSON_SCHEMA)


def _words(message: str) -> str:
    return _SPACE_RE.sub(" ", _PUNCTUATION_RE.sub(" ", message.casefold())).strip()


def _small_talk(message: str, state: Any) -> FastRead | None:
    words = _words(message)
    if words.startswith(("ok ", "okay ", "noted ")):
        rest = words.split(" ", 1)[1]
        if rest in _THANKS:
            words = rest
        elif words in ("ok noted", "okay noted", "ok sure", "noted ok"):
            words = "noted"
    if words in _THANKS:
        reply = THANKS_REPLY
    elif words in _ACK and getattr(state, "pending", None) is None:
        reply = ACK_REPLY
    else:
        return None
    verdict = said_nothing()
    verdict["message_type"] = "casual"
    return FastRead(kind="small_talk", verdict=verdict, reply=reply)


def _stock_task(state: Any) -> Any:
    """The stock check the next quantity is for: one still asking, or a one-product
    check just answered (a bare number revises it, round 5)."""
    for task in getattr(getattr(state, "focus", None), "tasks", None) or ():
        if task.kind != "stock_qty":
            continue
        if task.status == task_mod.OPEN and task.slots:
            return task
        if task.status == task_mod.ANSWERED and len(task.slots) == 1:
            return task
    return None


def _lines(message: str, task: Any) -> dict[str, int] | None:
    """{slot key: quantity} for a reply of numbered lines, or None unless EVERY segment
    is one."""
    slots = list(task.slots)
    out: dict[str, int] = {}
    segments = [s for s in _SEGMENT_SPLIT_RE.split(message) if s.strip()]
    if not segments:
        return None
    for segment in segments:
        if _UNFILLED_RE.match(segment):
            continue
        match = _LINE_RE.match(segment)
        if match is None:
            return None
        position = int(match.group("pos"))
        if not 1 <= position <= len(slots):
            return None
        slot = slots[position - 1]
        code = match.group("code")
        if code is not None and code.casefold() != slot.label.casefold():
            named = [s for s in slots if s.label.casefold() == code.casefold()]
            if len(named) != 1:
                return None
            slot = named[0]
        out[slot.key] = int(match.group("qty"))
    return out


def _stock_quantity(message: str, state: Any) -> FastRead | None:
    if getattr(state, "pending", None) is not None:
        return None
    task = _stock_task(state)
    if task is None:
        return None
    verdict = said_nothing()
    verdict["message_type"] = "business_query"
    bare = _BARE_NUMBER_RE.match(message)
    if bare is not None:
        verdict["demand_qty"] = int(bare.group(1))
        return FastRead(kind="stock_quantity", verdict=verdict)
    if task.status != task_mod.OPEN or len(task.slots) < 2:
        return None
    quantities = _lines(message, task)
    if not quantities:
        return None
    verdict[task_mod.SLOT_QUANTITIES] = quantities
    return FastRead(kind="stock_quantity", verdict=verdict)


def read(message: Any, state: Any) -> FastRead | None:
    """The fast reading of this message, or None when only the parser can read it."""
    if not isinstance(message, str) or not message.strip():
        return None
    return _stock_quantity(message, state) or _small_talk(message, state)
