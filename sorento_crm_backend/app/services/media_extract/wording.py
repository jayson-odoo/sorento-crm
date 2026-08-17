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
   percentage, and always for **one modality** - the allowances are separate
   per modality, so a dealer over the photo limit is told about photos only.

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
    norm_code,
)

# How an attribute kind is said out loud. The customer never sees `box_dimension`.
ATTRIBUTE_LABELS: dict[str, str] = {
    "batch_number": "batch number",
    "barcode": "barcode",
    "box_dimension": "box dimension",
    "product_size": "size",
    "quantity": "quantity",
    "document_number": "document number",
    "document_date": "document date",
}

_ESCAPE_HATCH = "Type the codes and I will look them up straight away."

# The quotas are per modality - separate limits, separate ledger counts, separate
# `warned_period` stamps - so every allowance sentence names ONE of them. Saying
# "photo and voice reads" described an allowance that does not exist and told a
# dealer who had run out of photo reads that they had run out of voice notes too
# (UAC S6-04: a true X of Y).
_MODALITY_NOUNS = {"image": "photo reads", "voice": "voice notes"}
_MODALITY_ESCAPE_HATCHES = {
    "image": _ESCAPE_HATCH,
    "voice": "Type your message and I will help straight away.",
}


def _noun(modality: str) -> str:
    return _MODALITY_NOUNS.get(modality, _MODALITY_NOUNS["image"])


def _escape_hatch(modality: str) -> str:
    return _MODALITY_ESCAPE_HATCHES.get(modality, _ESCAPE_HATCH)


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


def quota_exhausted(limit: int, resets_on: str, modality: str = "image") -> str:
    """The hard refusal: no degraded model is configured for this modality.

    It must say the read **did not happen**. `degraded()` is the message for
    "it happened, worse"; confusing the two would leave a dealer waiting for an
    answer to a photo nobody looked at.
    """
    not_done = (
        "I have not listened to this one"
        if modality == "voice"
        else "I have not read this one"
    )
    return (
        f"You have used all {limit} of this month's {_noun(modality)}, so "
        f"{not_done}. The allowance resets on {resets_on}. "
        f"{_escape_hatch(modality)}"
    )


def warn_threshold(
    remaining: int, limit: int, resets_on: str, modality: str = "image"
) -> str:
    """X of Y left, never a percentage, and for one modality (UAC S6-04)."""
    return (
        f"You have {remaining} of {limit} {_noun(modality)} left this month. "
        f"The allowance resets on {resets_on}."
    )


def degraded(resets_on: str, modality: str = "image") -> str:
    """Accuracy first, allowance second - the accuracy line prevents the harm.

    The captain's constraint, kept intact for both modalities: the contact is
    told accuracy has dropped AND that typing is exact. Only the nouns change,
    because a dealer over the photo limit still has their voice allowance.
    """
    if modality == "voice":
        opening = (
            "I am listening to this one with a simpler model and may get it "
            "wrong, so typing your message is exact."
        )
    else:
        opening = (
            "I am reading this one with a simpler model and may get it wrong, "
            "so typing the codes is exact."
        )
    return (
        f"{opening} This month's full-accuracy {_noun(modality)} are used up "
        f"and the allowance resets on {resets_on}."
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


def _note_clause(note: Optional[str]) -> str:
    """The model's one-clause note, trimmed to sit mid-sentence.

    The note is written by the model, so it arrives as its own little sentence
    ("Could be 11 August 2026 or 8 November 2026.") and has to be lowered into
    the middle of ours. The trailing stop always goes; the leading capital only
    goes when the word is plainly sentence-cased, so "J&Y", "Nov" and any code
    the model quotes keep the shape it read off the document (rule 1).
    """
    clause = (note or "").strip().rstrip(".;,")
    if not clause:
        return ""
    head = clause.split(" ", 1)[0]
    if head[1:].islower():
        clause = clause[0].lower() + clause[1:]
    return clause


def _conflict_sentence(conflict: MediaConflict) -> str:
    """Both values, both sources, the note, and a question.

    Never a chosen value, and never a question the customer cannot answer. Two
    competing values carry their own meaning and the note is context on top of
    them; an ambiguous date has only ONE printed value, because prompt rule 3
    puts both readings in the note instead - so dropping the note would ask
    "I can see 11/08/2026, which one should I use?", which names one value and
    offers nothing to choose between. The note is what makes it answerable.
    """
    # The source tag earns its place only against another source. On a lone
    # value it implies a counterpart the customer cannot see, and sets them
    # wondering what the unnamed other one was.
    with_source = len(conflict.values) > 1
    rendered = [
        f"{value.value} ({value.source})"
        if value.source and with_source
        else value.value
        for value in conflict.values
    ]
    # `field` is the model's own words, so it is usually already spoken English -
    # but it lands on the kind token often enough ("document_date") that the
    # customer would otherwise be shown an underscore.
    field = ATTRIBUTE_LABELS.get(conflict.field.strip().casefold(), conflict.field)
    note = _note_clause(conflict.note)
    if not rendered:
        if not note:
            return f"I am not sure about the {field}. Which one should I use?"
        return f"I am not sure about the {field} - {note}. Which one should I use?"
    seen = f"On the {field} I can see {join_phrase(rendered)}"
    if note:
        seen += f" - {note}"
    return f"{seen}. Which one should I use?"


def _covered_by_conflict(
    attribute: MediaAttribute, conflicts: Sequence[MediaConflict]
) -> bool:
    """Is this exact attribute one of the values a conflict sentence names?

    Scoped by `entity_raw` for the same reason `schema._apply_conflicts` is: one
    line's disputed quantity must not silence the four correct quantities on the
    other lines, or the message stops naming values the dealer can see on the
    photo in front of them.
    """
    kind = attribute.kind.strip().casefold()
    raw = norm_code(attribute.raw)
    for conflict in conflicts:
        target = norm_code(conflict.entity_raw)
        if target and raw == target:
            return True
        on_line = not target or norm_code(attribute.entity_raw) == target
        if on_line and raw and raw in _disputed_values(conflict):
            return True
        if conflict.field.strip().casefold() != kind:
            continue
        if not target or norm_code(attribute.entity_raw) == target:
            return True
    return False


def _disputed_values(conflict: MediaConflict) -> set[str]:
    """The readings a conflict sentence itself names, normalized as codes."""
    return {norm_code(value.value) for value in conflict.values if value.value}


def _entity_is_disputed(
    entity: MediaEntity, conflicts: Sequence[MediaConflict]
) -> bool:
    """Is this entity one of the values a conflict sentence names?

    Distinct from being the LINE a conflict sits on (`entity_raw`): a product
    whose quantity is disputed was still read, and is still listed as read; a
    product code that is itself one of two disagreeing readings is named by the
    conflict sentence already, and naming it a second time as read - or a third
    time as "not certain" - reads as three separate problems.
    """
    raw = norm_code(entity.raw)
    return bool(raw) and any(
        not c.entity_raw and raw in _disputed_values(c) for c in conflicts
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
    # repeating one of them reads as two separate problems. The LINE a conflict
    # sits on (`entity_raw`) is different: it was read, so it stays listed as
    # read, but it is not repeated as "not certain" because the conflict
    # sentence is what says why it is uncertain.
    conflicted_raws = {
        norm_code(conflict.entity_raw) for conflict in conflicts if conflict.entity_raw
    }

    phrases = _read_phrases(
        [entity for entity in entities if not _entity_is_disputed(entity, conflicts)],
        [
            attribute
            for attribute in attributes
            if not _covered_by_conflict(attribute, conflicts)
        ],
    )
    # ... unless that leaves nothing to name, in which case name it all.
    phrases = phrases or _read_phrases(entities, attributes)
    parts = [f"I read {join_phrase(phrases)} from that photo."]

    unsure = [
        entity.raw
        for entity in entities
        if not entity.confident
        and norm_code(entity.raw) not in conflicted_raws
        and not _entity_is_disputed(entity, conflicts)
    ]
    unsure += [
        f"{ATTRIBUTE_LABELS.get(attribute.kind, attribute.kind)} {attribute.raw}"
        for attribute in attributes
        if not attribute.confident and not _covered_by_conflict(attribute, conflicts)
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
