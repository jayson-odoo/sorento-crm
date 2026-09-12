"""The THREE ways the bot forgets, and the hints it is given instead of raw state.

AC-1003, AC-1004, AC-1020. This module replaces `dialogue/decay.py`, whose whole subject
was a turn counter. Owner decision D9 (12 Sep 2026) reversed growth-r1's D11: a dealer
cannot see a turn count, so nothing may expire on one. Nothing here counts turns, nothing
ages, nothing has a lifetime, and no settings column stands behind any of it.

A focus slot is cleared by exactly three things, and each one is something that HAPPENED:

1. **A current-message entity of the same axis replaces it.** "SRTWT2635" after
   "SRTWT2634 stock" is the same question about a different product, so the products slot
   is emptied here and refilled by `focus.replace_same_axis` a few steps later. The slot
   stays in place with a null value rather than being removed, because this turn is about
   to write it: removing and re-adding it would lose the difference between "the customer
   changed the product" and "the customer stopped naming one".
2. **`topic_reset`.** "another one" / "别的" clears every axis except the tier and the
   brands, which are constraints the customer put on themselves rather than answers to the
   question being asked (AC-1008).
3. **The Respond.io conversation-closed event.** The conversation is over, so everything it
   was about goes, the open question included. `sla_service` clears the contact directly
   when the last open ticket resolves; this arm is what a turn arriving WITH the marker
   does, so the two paths cannot disagree about what "closed" means.

The open question follows the same rule from the other side (AC-1020): a casual or
low-signal message leaves it open, however many of them arrive; a message that carries an
ask and does not answer it clears it with a trace line and is handled as a new ask; a lane
asking a newer question replaces it. It is never answered silently.

Every clear writes one trace line `{slot, reason}`. The reason is a sentence an operator
reads on the trace screen, so "why did the bot forget my product" is answered without
reading any code.
"""
from __future__ import annotations

from typing import Any, Protocol

from app.services.chatbot.contracts import FOCUS_SLOTS
from app.services.chatbot.dialogue import intake
from app.services.chatbot.dialogue.focus import RESET_KEEPS, _SLOT_BY_HINT


class _TraceSink(Protocol):
    def add(self, kind: str, payload: dict[str, Any]) -> None: ...


def apply(
    session: Any,
    parse: Any,
    conversation_closed: bool = False,
    *,
    trace: _TraceSink | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply the three causes to the stored state, returning `(session, trace_lines)`.

    `session` is `respond_contacts.session_vars.variables` as it was read - a plain dict,
    never a model, because a session written by an older build is legal input and must not
    raise. `parse` is the parser v3 emission. Anything unrecognised is treated as absent.

    The input is not mutated: a caller that traces the before and after (`trace_detail`'s
    `decay` section does) needs both, and a function that edited its argument would leave
    it holding the same object twice.
    """
    stored = dict(session) if isinstance(session, dict) else {}
    emission = parse if isinstance(parse, dict) else {}

    focus_in = stored.get("focus")
    focus = {
        name: dict(slot)
        for name, slot in (focus_in.items() if isinstance(focus_in, dict) else [])
        if isinstance(slot, dict)
    }
    question = stored.get("open_question")
    question = question if isinstance(question, dict) and question.get("kind") else None
    lines: list[dict[str, Any]] = []

    if conversation_closed:
        for name in list(focus):
            if _is_empty(focus[name].get("value")):
                continue
            lines.append(
                _line(
                    name,
                    "the Respond.io conversation was closed, so what it was about is "
                    "cleared before the next message",
                )
            )
            focus.pop(name)
        # Every slot goes, including the ones that were already empty: after a close the
        # state must be indistinguishable from a contact who has never written.
        focus = {}
        if question is not None:
            lines.append(
                _line(
                    "open_question",
                    "the Respond.io conversation was closed, so the question it was "
                    "waiting on is cleared rather than answered by the next message",
                )
            )
            question = None
        _trace(trace, lines)
        return {**stored, "focus": focus, "open_question": question}, lines

    if emission.get("topic_reset") is True:
        for name in list(focus):
            if name in RESET_KEEPS or _is_empty(focus[name].get("value")):
                continue
            lines.append(
                _line(name, "the customer changed the subject (topic_reset)")
            )
            focus.pop(name)

    for name in _axes_named_this_message(emission):
        slot = focus.get(name)
        if not isinstance(slot, dict) or _is_empty(slot.get("value")):
            continue
        lines.append(
            _line(
                name,
                "this message names one of its own, which replaces what was there",
            )
        )
        # Emptied IN PLACE: `focus.replace_same_axis` writes this turn's value into the
        # same slot, and the trace reads better for "changed from X to Y" than for a slot
        # that vanished and reappeared.
        focus[name] = {**slot, "value": None}

    if question is not None and _is_a_new_ask(emission) and not _answers_it(emission):
        lines.append(
            _line(
                "open_question",
                "the customer asked something new instead of answering, so the question "
                "is cleared rather than answered silently by the next reply",
            )
        )
        question = None

    _trace(trace, lines)
    return {**stored, "focus": focus, "open_question": question}, lines


def focus_hints(focus: Any) -> dict[str, Any]:
    """The alive slots as the parser sees them: values only, no bookkeeping.

    Entities keep the three keys the parser already emits and reads (`raw`, `hint`,
    `canonical_code`); `set_at_turn` and `source` are engine bookkeeping and never reach
    the model. A slot with no value is absent rather than null, so the hint block a model
    is shown says only what is true.
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


def _axes_named_this_message(emission: dict[str, Any]) -> list[str]:
    """The focus slots this message named an entity for, in the order it named them.

    Only `current_message` entities count. A parse that re-emits an earlier turn's entity
    is not the customer naming one, and treating it as a replacement would have the state
    overwrite itself with what it already holds.
    """
    out: list[str] = []
    for ask in emission.get("asks") or []:
        if not isinstance(ask, dict):
            continue
        for entity in ask.get("entities") or []:
            if not isinstance(entity, dict) or entity.get("current_message") is not True:
                continue
            name = _slot_of(entity)
            if name is not None and name not in out:
                out.append(name)
    return out


def _slot_of(entity: dict[str, Any]) -> str | None:
    hint = str(entity.get("hint") or "").strip().lower()
    if hint == "product":
        return "products"
    return _SLOT_BY_HINT.get(hint)


def _is_a_new_ask(emission: dict[str, Any]) -> bool:
    """Does this message carry an ask of its own - a domain, or an entity?

    Asked of the FLATTENED emission, never of the raw `asks` key. `asks` is a v3 shape and
    a v1 / v2 emission has none by construction, so keying on it meant every turn under the
    PROMOTED prompt answered "no": a customer who typed "SRTWC8517 stock?" over an open
    escalate offer had their question left armed, and the next bare "yes" - about anything -
    assigned them a human. `intake.flatten` is the one place that reads either shape, and it
    maps a v1 `domain_hint` / `entities` onto the same `domains` / `entities` a v3 ask
    flattens to.

    A CARRIED entity is not an ask. `current_message is False` is the head's own flag for a
    token this turn did not type, and a continuation that merely keeps the prior scope must
    not clear a question the customer can still see. A v3 ask's entities carry no such flag
    - they are what the message named - so the test is "not explicitly carried", not
    "explicitly current".

    A DOMAIN ALONE IS NOT AN ASK OF ITS OWN, and the corpus is what says so: "which one
    has stock" over an open product picker flattens to `{domains: ["inventory"], entities:
    []}` and is a question ABOUT the rows on screen - clearing there leaves the customer's
    very next "1" with nothing to resolve
    (`test_focus_worlds.py::focus-pick-reruns-the-alive-domain`). What makes a message a new
    ask is that it names a SUBJECT of its own, which is the same thing
    `focus.replace_same_axis` treats as replacing a slot.

    A casual or low-signal message names none, which is why the rule can be stated in terms
    of what the customer SAID rather than in terms of `message_type` (a lane could relabel
    that).
    """
    return any(
        isinstance(entity, dict) and entity.get("current_message") is not False
        for entity in intake.flatten(emission)["entities"]
    )


def _answers_it(emission: dict[str, Any]) -> bool:
    answer = emission.get("answers_open_question")
    return isinstance(answer, dict) and answer.get("resolved") is True


def _line(slot: str, reason: str) -> dict[str, Any]:
    return {"slot": slot, "reason": reason}


def _trace(trace: _TraceSink | None, lines: list[dict[str, Any]]) -> None:
    if trace is None:
        return
    for line in lines:
        # The trace key keeps the name `decay` (the drawer's Focus panel and
        # `trace_detail`'s nine keys are written against it); only its entries changed
        # shape, from an age and a lifetime to a slot and a reason.
        trace.add("decay", line)


def _entity_hint(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw": entity.get("raw"),
        "hint": entity.get("hint"),
        "canonical_code": entity.get("canonical_code"),
    }


def _int(value: Any, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _is_empty(value: Any) -> bool:
    return value is None or value == [] or value == {} or value == ""


# `FOCUS_SLOTS` is imported for the module's own contract, not for a loop: a slot name
# that is not in it cannot be cleared here because it cannot be set anywhere else.
_ = FOCUS_SLOTS
