"""Per-slot decay at intake, and the hints the parser is given instead of raw state.

AC-940, AC-941, AC-971. Two things happen here, in this order, at the `received` stage:

1. **Every focus slot the customer has not restated for `ttl_turns` turns is DROPPED**, and
   so is an `open_question` past its own TTL. This runs BEFORE the parser call, deliberately:
   a dead slot must not reach the model as context, or the model re-emits it and the drop
   is undone by the very step it was meant to protect (defect 3 of the growth plan - carry
   decided by two writers).
2. **What is left becomes HINTS.** The parser is handed `focus_hints` and
   `open_question_hint`, not the raw previous state: structured, minimal, and describing
   only what is still alive (D6). The model's job under prompt v3 is to EXTRACT the current
   message and, when a question is open, to say whether this message answers it.

**Turns, never minutes.** Owner decision D11: `age_turns = turn_no - set_at_turn` and
nothing else decides a drop. `set_at` is carried into the trace so an operator can also see
the wall-clock age, and `age_minutes` is computed for the same reason - neither is read by
any branch here, and a reviewer finding one that is has found a defect.

Ageing is INCLUSIVE of the TTL: a slot set at turn N with `ttl_turns = 3` is alive at
N+1, N+2 and N+3 and is dropped at N+4. That is AC-940's own arithmetic ("the same at N+2
carries", "at N+4 does NOT").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.services.chatbot.contracts import FOCUS_SLOTS

# What a slot with no recorded `set_at_turn` is aged from. 0 means "older than any real
# turn", so a slot written by a build that predates this module is dropped on the first
# turn that reads it rather than living forever. That is the safe direction: the customer
# restates what they still mean, and a wrongly-kept scope answers the wrong question
# silently.
_UNKNOWN_SET_AT_TURN = 0


class _TraceSink(Protocol):
    def add(self, kind: str, payload: dict[str, Any]) -> None: ...


@dataclass
class DecayResult:
    """What survived, and what the parser is told about it."""

    focus: dict[str, Any] = field(default_factory=dict)
    open_question: dict[str, Any] | None = None
    focus_hints: dict[str, Any] = field(default_factory=dict)
    open_question_hint: dict[str, Any] | None = None
    # The slots and the question that were dropped, as the same payloads written to the
    # trace. Returned as well as traced so a test can assert the decision without reading
    # the turn row (AC-941).
    dropped: list[dict[str, Any]] = field(default_factory=list)


def age_turns(slot: Any, *, turn_no: int) -> int:
    """How many turns ago this slot was set. Negative is impossible and clamped to 0."""
    set_at_turn = _int(_get(slot, "set_at_turn"), _UNKNOWN_SET_AT_TURN)
    return max(0, int(turn_no) - set_at_turn)


def is_alive(slot: Any, *, turn_no: int, ttl_turns: int) -> bool:
    """Is this slot still on the customer's mind? Turns only (D11)."""
    if not isinstance(slot, dict):
        return False
    if _is_empty(slot.get("value")):
        return False
    return age_turns(slot, turn_no=turn_no) <= max(0, int(ttl_turns))


def apply(
    variables: Any,
    *,
    turn_no: int,
    ttl_turns: int,
    trace: _TraceSink | None = None,
) -> DecayResult:
    """Age the stored dialogue state and build the parser's hints.

    `variables` is `respond_contacts.session_vars.variables` as it was read - a plain dict,
    never a model, because a session written by an older build (or by n8n) is legal input
    and must not raise. Anything unrecognised is treated as absent.
    """
    stored = variables if isinstance(variables, dict) else {}
    result = DecayResult()

    focus_in = stored.get("focus")
    focus_in = focus_in if isinstance(focus_in, dict) else {}
    for name in FOCUS_SLOTS:
        slot = focus_in.get(name)
        if not isinstance(slot, dict) or _is_empty(slot.get("value")):
            continue
        if is_alive(slot, turn_no=turn_no, ttl_turns=ttl_turns):
            result.focus[name] = slot
            continue
        entry = _drop_entry(
            slot=name,
            value=slot.get("value"),
            set_at_turn=_int(slot.get("set_at_turn"), _UNKNOWN_SET_AT_TURN),
            set_at=slot.get("set_at"),
            age=age_turns(slot, turn_no=turn_no),
            reason=(
                f"not restated for {age_turns(slot, turn_no=turn_no)} turns; the focus TTL "
                f"is {ttl_turns}"
            ),
        )
        result.dropped.append(entry)
        if trace is not None:
            trace.add("decay", entry)

    question = stored.get("open_question")
    if isinstance(question, dict) and question.get("kind"):
        asked_at = _int(question.get("asked_at_turn"), _UNKNOWN_SET_AT_TURN)
        # The question carries its OWN lifetime rather than reading the focus TTL: a member
        # offer is on the customer's screen for 3 turns (AC-816 rule 1) and a team clarify
        # is answered on the very next turn or not at all. One number per kind, written
        # when the question is asked.
        life = max(0, _int(question.get("ttl_turns"), 1))
        age = max(0, int(turn_no) - asked_at)
        if age <= life:
            result.open_question = question
        else:
            entry = _drop_entry(
                slot="open_question",
                value=question.get("kind"),
                set_at_turn=asked_at,
                set_at=question.get("asked_at"),
                age=age,
                reason=(
                    f"unanswered for {age} turns; this question's TTL is {life}. It is "
                    "cleared rather than answered silently by a later reply"
                ),
            )
            result.dropped.append(entry)
            if trace is not None:
                trace.add("decay", entry)

    result.focus_hints = focus_hints(result.focus)
    result.open_question_hint = open_question_hint(result.open_question)
    return result


def focus_hints(focus: Any) -> dict[str, Any]:
    """The alive slots as the parser sees them: values only, no bookkeeping.

    Entities keep the three keys the parser already emits and reads (`raw`, `hint`,
    `canonical_code`); `set_at_turn`, `set_at` and `source` are engine bookkeeping and
    never reach the model. A slot with no value is absent rather than null, so the hint
    block a model is shown says only what is true.
    """
    out: dict[str, Any] = {}
    for name, slot in (focus or {}).items():
        if not isinstance(slot, dict):
            continue
        value = slot.get("value")
        if _is_empty(value):
            continue
        if name == "products":
            out[name] = [_entity_hint(e) for e in value if isinstance(e, dict)]
        elif name in ("customer", "transporter", "warehouse"):
            out[name] = _entity_hint(value) if isinstance(value, dict) else value
        else:
            out[name] = value
    return out


def open_question_hint(question: Any) -> dict[str, Any] | None:
    """`{kind, expects, options}` - the LABELS the customer was shown, nothing else.

    Never the uuids and never the payload: the model's whole job here is to say whether
    this message answers the question and which row it picked, and a uuid on the prompt is
    a value it could hallucinate back. The engine resolves a position against the frozen
    rows itself (`open_question.resolve`).
    """
    if not isinstance(question, dict) or not question.get("kind"):
        return None
    options = question.get("options")
    labels = []
    if isinstance(options, list):
        for index, row in enumerate(options, start=1):
            if not isinstance(row, dict):
                continue
            label = row.get("label") or row.get("code") or row.get("value")
            if label is None:
                continue
            labels.append({"idx": _int(row.get("idx"), index), "label": str(label)})
    return {
        "kind": question.get("kind"),
        "expects": question.get("expects"),
        "options": labels,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _drop_entry(
    *,
    slot: str,
    value: Any,
    set_at_turn: int,
    set_at: Any,
    age: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "slot": slot,
        "value": value,
        "set_at_turn": set_at_turn,
        "age_turns": age,
        "age_minutes": _age_minutes(set_at),
        "reason": reason,
    }


def _entity_hint(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw": entity.get("raw"),
        "hint": entity.get("hint"),
        "canonical_code": entity.get("canonical_code"),
    }


def _get(slot: Any, key: str) -> Any:
    return slot.get(key) if isinstance(slot, dict) else None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _is_empty(value: Any) -> bool:
    return value is None or value == [] or value == {} or value == ""


def _age_minutes(set_at: Any) -> int | None:
    """Wall-clock age, for the TRACE only. Never read by a branch (D11)."""
    if not isinstance(set_at, str) or not set_at:
        return None
    try:
        stamp = datetime.fromisoformat(set_at)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - stamp).total_seconds() // 60)
