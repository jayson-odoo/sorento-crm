"""Collect the REQUIRED fields an ask needs before it runs (LOWSTOCK-FILTER-ASK, owner Q2).

`documentation/plans/chatbot/lowstock-filter-ask-behaviour-card.md`. One helper, shared by
every ask that must not run until some fields are settled (the low stock report today,
IDEATION-CAPTURE #1444 next). It knows nothing about any one ask: an ask type registers its
required fields, and the helper owns the rest.

The rule, per field, in the order the ask type lists them:

1. given in the message and valid -> taken, nothing asked;
2. "all" (the message said "all categories", or the reply is "all") -> settled as `ALL`,
   where the field allows it;
3. otherwise -> asked, ONE field per reply, with the field's own question.

Changing what an ask requires is config: add or remove a `FieldSpec` on its `AskType`.

API
---

* `FieldSpec(name, noun, question, resolve, allow_all=True)` - one required field.
  `resolve(db, word) -> Resolved` reads a typed word: `Resolved("ok", value, label)`,
  `Resolved("ambiguous", options=((value, label), ...))` (the helper lists them with numbers),
  or `Resolved("unknown")`.
* `AskType(name, fields, reroute, cancelled, give_up)` - one ask. `reroute` is laid over the
  parser verdict when a reply answers the open question, so the turn goes back to the same
  ask (for the low stock report: its intent and domain). `give_up` may hold `{word}`.
* `collect(db, ask, *, given=None, slot=None, reply=None, extras=None) -> Outcome`.
  A fresh ask passes `given` (field name -> the raw word the message named, or `ALL`);
  an answering turn passes the `slot` it got back and the `reply` text. `extras` is
  anything the ask wants carried across the question untouched (the low stock report's
  supplier and grouping words). `Outcome.done` -> every required field is settled, run with
  `Outcome.values` (`{name: {"value", "label"}}`). Otherwise send `Outcome.reply` and keep
  `Outcome.slot` (None when nothing stays open: cancelled or given up).
* `reply_verdict(verdict, slot, text, *, asks) -> (verdict, rule)` - the engine seam, read
  before anything routes the message. With a question open, a short reply (or one the
  parser reads as the same ask) is the answer: the verdict is rerouted to the ask, its
  entities cleared, and `required_ask` / `required_ask_reply` carry the slot and the text to
  the lane. A longer message the parser reads as a different ask, or any message with a
  "?", drops the question (`required_ask_dropped`).

The slot is one turn long: the engine consumes it on the next message, and the lane that
asks again hands a fresh one back (`required_ask` on its envelope).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

ALL = "all"

#: Words that settle a field as "all" (lower-cased, whitespace-folded). "all <noun>" and
#: "all <noun>s" are accepted too (`_is_all`).
ALL_WORDS = frozenset({"all", "any", "everything", "every", "semua", "全部", "all of them"})
CANCEL_WORDS = frozenset({"cancel", "stop", "never mind", "nevermind", "forget it", "batal"})
#: A reply longer than this, read by the parser as another ask, leaves the question.
SHORT_REPLY_WORDS = 3
MAX_MISSES = 2


@dataclass(frozen=True)
class Resolved:
    status: str  # "ok" | "ambiguous" | "unknown"
    value: Any = None
    label: str = ""
    options: tuple[tuple[Any, str], ...] = ()


@dataclass(frozen=True)
class FieldSpec:
    name: str
    noun: str
    question: str
    resolve: Callable[[Any, str], Resolved]
    allow_all: bool = True


@dataclass(frozen=True)
class AskType:
    name: str
    fields: tuple[FieldSpec, ...]
    reroute: dict[str, Any]
    cancelled: str
    give_up: str


@dataclass
class Outcome:
    values: dict[str, dict[str, Any]] = field(default_factory=dict)
    reply: str | None = None
    slot: dict[str, Any] | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def done(self) -> bool:
        return self.reply is None and not self.cancelled


def jsc_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(text: str | None) -> str:
    return " ".join((text or "").split()).strip().lower().rstrip(".!")


def _plural(noun: str) -> str:
    return noun[:-1] + "ies" if noun.endswith("y") else noun + "s"


def _is_all(text: str, spec: FieldSpec) -> bool:
    word = _norm(text)
    return word in ALL_WORDS or word in {f"all {spec.noun}", f"all {_plural(spec.noun)}"}


def _miss_line(word: str, spec: FieldSpec) -> str:
    return f"I don't know '{word}' as a {spec.noun}.\n\n{spec.question}"


def _pick_line(spec: FieldSpec, options: list[list[Any]]) -> str:
    head = f"Which {spec.noun} do you mean? Reply with a number" + (' or "all":' if spec.allow_all else ":")
    return "\n".join([head, *[f"{i}. {label}" for i, (_value, label) in enumerate(options, start=1)]])


def _slot(ask: AskType, values: dict, extras: dict, *, asking: str, options=None, misses: int = 0) -> dict:
    return {
        "ask": ask.name,
        "values": values,
        "asking": asking,
        "options": [list(o) for o in options] if options else [],
        "misses": misses,
        "extras": extras,
    }


def _settle(db: Any, spec: FieldSpec, word: str) -> Resolved:
    if _is_all(word, spec):
        return Resolved("ok", value=ALL, label=ALL) if spec.allow_all else Resolved("unknown")
    return spec.resolve(db, word)


def _from_pick(spec: FieldSpec, options: list[list[Any]], word: str) -> Resolved | None:
    """A reply to a numbered list: a number in range, or an option's own label."""
    text = _norm(word)
    if re.fullmatch(r"\d+", text):
        n = int(text)
        if 1 <= n <= len(options):
            value, label = options[n - 1]
            return Resolved("ok", value=value, label=label)
        return Resolved("unknown")
    for value, label in options:
        if _norm(str(label)) == text:
            return Resolved("ok", value=value, label=label)
    return None


def collect(
    db: Any,
    ask: AskType,
    *,
    given: dict[str, Any] | None = None,
    slot: dict[str, Any] | None = None,
    reply: str | None = None,
    extras: dict[str, Any] | None = None,
) -> Outcome:
    values: dict[str, dict[str, Any]] = dict((slot or {}).get("values") or {})
    carried = dict((slot or {}).get("extras") or {})
    carried.update(extras or {})
    specs = {s.name: s for s in ask.fields}

    if slot is not None and reply is not None:
        if _norm(reply) in CANCEL_WORDS:
            return Outcome(values=values, reply=ask.cancelled, slot=None, extras=carried, cancelled=True)
        spec = specs.get(jsc_str(slot.get("asking")))
        if spec is not None:
            options = list(slot.get("options") or [])
            got = _from_pick(spec, options, reply) if options else None
            if got is None:
                got = _settle(db, spec, reply)
            if got.status == "ok":
                values[spec.name] = {"value": got.value, "label": got.label}
            elif got.status == "ambiguous":
                opts = [list(o) for o in got.options]
                return Outcome(values=values, reply=_pick_line(spec, opts),
                               slot=_slot(ask, values, carried, asking=spec.name, options=opts), extras=carried)
            else:
                word = " ".join(reply.split())
                misses = int(slot.get("misses") or 0) + 1
                if misses >= MAX_MISSES:
                    return Outcome(values=values, reply=ask.give_up.format(word=word), slot=None, extras=carried)
                return Outcome(values=values, reply=_miss_line(word, spec),
                               slot=_slot(ask, values, carried, asking=spec.name, options=options, misses=misses),
                               extras=carried)

    for spec in ask.fields:
        if spec.name in values:
            continue
        word = (given or {}).get(spec.name)
        if word == ALL and spec.allow_all:
            values[spec.name] = {"value": ALL, "label": ALL}
            continue
        if isinstance(word, str) and word.strip():
            got = _settle(db, spec, word)
            if got.status == "ok":
                values[spec.name] = {"value": got.value, "label": got.label}
                continue
            if got.status == "ambiguous":
                opts = [list(o) for o in got.options]
                return Outcome(values=values, reply=_pick_line(spec, opts),
                               slot=_slot(ask, values, carried, asking=spec.name, options=opts), extras=carried)
            return Outcome(values=values, reply=_miss_line(" ".join(word.split()), spec),
                           slot=_slot(ask, values, carried, asking=spec.name), extras=carried)
        return Outcome(values=values, reply=spec.question,
                       slot=_slot(ask, values, carried, asking=spec.name), extras=carried)
    return Outcome(values=values, extras=carried)


def reply_verdict(
    verdict: dict[str, Any],
    slot: dict[str, Any] | None,
    text: str,
    *,
    asks: dict[str, AskType],
) -> tuple[dict[str, Any], str | None]:
    if not isinstance(slot, dict) or not slot.get("asking"):
        return verdict, None
    ask = asks.get(jsc_str(slot.get("ask")))
    if ask is None:
        return verdict, "required_ask_dropped"
    same_ask = all(verdict.get(k) == v for k, v in ask.reroute.items() if k == "intent_hint")
    short = len((text or "").split()) <= SHORT_REPLY_WORDS
    other_intent = bool(verdict.get("intent_hint")) and not same_ask
    if "?" in (text or "") or (other_intent and not short):
        return verdict, "required_ask_dropped"
    rerouted = {**verdict, **ask.reroute, "entities": [], "required_ask": slot, "required_ask_reply": text}
    return rerouted, "required_ask_answer"
