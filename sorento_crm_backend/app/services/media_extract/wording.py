"""Every customer-facing string this feature produces (PLAN section 6).

The far end sends a string and formats nothing. That is the whole point: n8n
does no date arithmetic, no pluralisation and no percentage maths, so there is
exactly one place a message can be wrong and exactly one place to fix it.

The four rules from the captain's `customer-wording.md` are implemented as
behaviour rather than as convention:

1. The 80 percent warning fires once per contact per period per modality -
   enforced by `warned_period` on the limit row, stamped in the same
   transaction as the decision (see `media_access_service`).
2. The degradation notice is a separate kind with its own column, sent when
   degradation first happens in a period.
3. Notices carry `append: true` and are never returned instead of the answer.
4. Dates render as "1 September". Counts render as "X of Y left", never a
   percentage.

Two deliberate changes from the drafts, flagged because the brief requires it:

* the at-limit degradation text **leads with the accuracy warning** rather than
  with the allowance, because the accuracy warning is the part that prevents
  harm. The allowance sentence follows it.
* `not_enabled` has an image variant as well as the live voice one, mirroring it
  in shape so the two features read as one. Every refusal names an action that
  definitely works.

The burst message being suppressed for the remainder of the window is the third
change, and it lives in `media_access_service` because it is a Redis decision,
not a wording one.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from app.services.media_extract.schema import (
    MediaAttribute,
    MediaConflict,
    MediaEntity,
)

# How an attribute kind is said out loud. The customer never sees `box_dimension`.
ATTRIBUTE_LABELS: dict[str, str] = {
    "batch_number": "batch number",
    "barcode": "barcode",
    "box_dimension": "box dimension",
    "product_size": "size",
    "quantity": "quantity",
}

_ESCAPE_HATCH = "Type the codes and I will look them up straight away."


def join_phrase(items: Sequence[str]) -> str:
    """"a", "a and b", "a, b and c". Spoken English, not a JSON array."""
    values = [item for item in items if item]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " and " + values[-1]


# --------------------------------------------------------------------------- #
# Decision notices - one function per notice kind                             #
# --------------------------------------------------------------------------- #


def not_enabled(modality: str) -> str:
    """The gate refusal. One sentence, plus the escape hatch (UAC S6-06)."""
    if modality == "voice":
        return (
            "I cannot listen to voice notes on this number yet. Type your message "
            "instead and I will help straight away."
        )
    return (
        "I cannot read photos on this number yet. Type the codes instead and I "
        "will look them up straight away."
    )


def clip_too_long(max_seconds: int) -> str:
    return (
        f"That voice note is longer than {max_seconds} seconds. Please send a "
        "shorter one and I will listen to it."
    )


def burst() -> str:
    """Pacing, not exhaustion (UAC S6-05). Says nothing about the allowance."""
    return (
        "That is a lot at once - give me a moment to catch up, then send the rest."
    )


def quota_exhausted(limit: int, resets_on: str) -> str:
    return (
        f"You have used all {limit} of this month's photo and voice reads. The "
        f"allowance resets on {resets_on}. {_ESCAPE_HATCH}"
    )


def warn_threshold(remaining: int, limit: int, resets_on: str) -> str:
    """X of Y left, never a percentage (UAC S6-04)."""
    return (
        f"You have {remaining} of {limit} photo and voice reads left this month. "
        f"The allowance resets on {resets_on}."
    )


def degraded(resets_on: str) -> str:
    """Accuracy first, allowance second - the accuracy line prevents the harm."""
    return (
        "I am reading this one with a simpler model and may get it wrong, so "
        "typing the codes is exact. This month's full-accuracy reads are used "
        f"up and the allowance resets on {resets_on}."
    )


# --------------------------------------------------------------------------- #
# Extraction messages                                                         #
# --------------------------------------------------------------------------- #


def _read_phrases(
    entities: Iterable[MediaEntity], attributes: Iterable[MediaAttribute]
) -> list[str]:
    """What was read, in customer words: the raw string, attributes labelled."""
    phrases = [entity.raw for entity in entities]
    phrases += [
        f"{ATTRIBUTE_LABELS.get(attribute.kind, attribute.kind)} {attribute.raw}"
        for attribute in attributes
    ]
    return phrases


def _conflict_sentence(conflict: MediaConflict) -> str:
    """Both values, both sources, and a question. Never a chosen value."""
    rendered = [
        f"{value.value} ({value.source})" if value.source else value.value
        for value in conflict.values
    ]
    if not rendered:
        return f"I am not sure about the {conflict.field}. Which one should I use?"
    return (
        f"On the {conflict.field} I can see {join_phrase(rendered)}. Which one "
        "should I use?"
    )


def nothing_read() -> str:
    """Nothing legible. Says so plainly and names the escape hatch (UAC S4-09)."""
    return f"I could not read anything from that photo. {_ESCAPE_HATCH}"


def confirmation(
    entities: Sequence[MediaEntity],
    attributes: Sequence[MediaAttribute],
    conflicts: Sequence[MediaConflict],
) -> str:
    """"Did I get this right?" - the single decision the dealer has to make.

    Names everything that was read, then raises anything the reading is unsure
    about. A conflict always ends the message with a question, because the
    system genuinely does not know and must not pick.
    """
    if not _read_phrases(entities, attributes):
        return nothing_read()

    # A value already covered by a conflict sentence is neither listed as read
    # nor as "not certain" - the conflict sentence names both of its values, so
    # repeating one of them reads as two separate problems.
    conflicted_raws = {
        (conflict.entity_raw or "").strip().casefold()
        for conflict in conflicts
        if conflict.entity_raw
    }
    conflicted_fields = {conflict.field.strip().casefold() for conflict in conflicts}

    phrases = _read_phrases(
        entities,
        [
            attribute
            for attribute in attributes
            if attribute.kind.casefold() not in conflicted_fields
        ],
    )
    # ... unless that leaves nothing to name, in which case name it all.
    phrases = phrases or _read_phrases(entities, attributes)
    parts = [f"I read {join_phrase(phrases)} from that photo."]

    unsure = [
        entity.raw
        for entity in entities
        if not entity.confident and entity.raw.strip().casefold() not in conflicted_raws
    ]
    unsure += [
        f"{ATTRIBUTE_LABELS.get(attribute.kind, attribute.kind)} {attribute.raw}"
        for attribute in attributes
        if not attribute.confident
        and attribute.kind.casefold() not in conflicted_fields
        and attribute.raw.strip().casefold() not in conflicted_raws
    ]
    if unsure:
        parts.append(f"I am not certain about {join_phrase(unsure)}.")

    parts += [_conflict_sentence(conflict) for conflict in conflicts]

    if not conflicts:
        parts.append("Is that right?")
    return " ".join(parts)


def clarification(
    entities: Sequence[MediaEntity], attributes: Sequence[MediaAttribute]
) -> str:
    """No caption, or an intent we cannot read: say what was read, then ask.

    Guessing the intent on top of an imperfect reading stacks two silent failure
    modes, so the system asks instead (UAC S4-08).
    """
    phrases = _read_phrases(entities, attributes)
    if not phrases:
        return (
            "I could not read anything from that photo. Tell me what you need and "
            "I will look it up."
        )
    return (
        f"I read {join_phrase(phrases)} from that photo. What would you like me "
        "to do with it?"
    )


def truncated_note(max_entities: int) -> str:
    """Said out loud rather than truncating silently (UAC S4-10)."""
    return (
        f"There was more than I can handle in one go, so I have taken the first "
        f"{max_entities}."
    )


# --------------------------------------------------------------------------- #
# Voice                                                                       #
# --------------------------------------------------------------------------- #


def voice_confirmation(transcript: str) -> str:
    """The existing "here is what I heard" confirmation (UAC S5-05)."""
    return f'Here is what I heard: "{transcript.strip()}"'


def voice_unclear() -> str:
    return (
        "I could not make out that voice note. Please send it again or type your "
        "message and I will help straight away."
    )


def voice_language_unsure(transcript: Optional[str] = None) -> str:
    """The model transcribed but could not name the language it heard.

    An empty detected-language list is a valid "unsure" signal, so the customer
    is shown the transcript and asked to confirm rather than told nothing.
    """
    if transcript and transcript.strip():
        return (
            f'Here is what I heard: "{transcript.strip()}" - I am not certain of '
            "the language, so please check it says what you meant."
        )
    return voice_unclear()
