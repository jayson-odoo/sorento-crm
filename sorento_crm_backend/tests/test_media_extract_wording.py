"""`app/services/media_extract/wording.py` - every customer-facing string.

Contract: UAC S6-01..S6-07, plus S4-08/S4-09 (`clarification`/`nothing_read`,
which live in this module because "what the confirmation says" is wording's
job even when the shape of the extraction that triggered it is schema's).

S6-07 requires each notice to be asserted on its FULL rendered string, not a
fragment - "so a partially wrong message cannot pass". Every assertion below
does that: `==` against the exact text, never `in`, except where the test is
explicitly about substring absence (no percentage, no source tag on a lone
value, not double-listed under "not certain").
"""
from __future__ import annotations

from app.services.media_extract import wording
from app.services.media_extract.schema import (
    MediaAttribute,
    MediaConflict,
    MediaConflictValue,
    MediaEntity,
)


# --------------------------------------------------------------------------- #
# Decision notices - full string, per UAC S6-07                              #
# --------------------------------------------------------------------------- #


def test_not_enabled_voice_matches_the_live_voice_sentence_shape():
    """S6-06."""
    assert wording.not_enabled("voice") == (
        "I cannot listen to voice notes on this number yet. Type your message "
        "instead and I will help straight away."
    )


def test_not_enabled_image_mirrors_the_voice_variant_in_shape():
    """S6-06: image and voice must read as one feature - same shape, own
    modality, same escape hatch."""
    assert wording.not_enabled("image") == (
        "I cannot read photos on this number yet. Type the codes instead and "
        "I will look them up straight away."
    )


def test_clip_too_long_names_the_configured_maximum():
    assert wording.clip_too_long(120) == (
        "That voice note is longer than 120 seconds. Please send a shorter "
        "one and I will listen to it."
    )


def test_burst_message_does_not_imply_exhaustion():
    """S6-05: a pacing message, not an allowance message - it must not carry a
    count or the word 'left'."""
    text = wording.burst()
    assert text == (
        "That is a lot at once - give me a moment to catch up, then send the rest."
    )
    assert "left" not in text
    assert not any(ch.isdigit() for ch in text)


def test_quota_exhausted_image_names_photos_only_and_says_it_was_not_read():
    """S6-04 + PLAN 16.2: the quotas are per modality, so the text names one of
    them. And this is the HARD refusal (no degraded model configured), so it
    must say the read did not happen - `degraded()` is the message for 'it
    happened, worse'."""
    text = wording.quota_exhausted(50, "1 September", "image")
    assert text == (
        "You have used all 50 of this month's photo reads, so I have not read "
        "this one. The allowance resets on 1 September. Type the codes and I "
        "will look them up straight away."
    )
    assert "voice" not in text


def test_quota_exhausted_voice_names_voice_only_and_says_it_was_not_heard():
    text = wording.quota_exhausted(100, "1 September", "voice")
    assert text == (
        "You have used all 100 of this month's voice notes, so I have not "
        "listened to this one. The allowance resets on 1 September. Type your "
        "message and I will help straight away."
    )
    assert "photo" not in text


def test_warn_threshold_states_x_of_y_left_never_a_percentage():
    """S6-04."""
    text = wording.warn_threshold(9, 50, "1 September", "image")
    assert text == (
        "You have 9 of 50 photo reads left this month. The allowance resets "
        "on 1 September."
    )
    assert "%" not in text
    assert "left" in text
    assert "voice" not in text


def test_warn_threshold_voice_counts_voice_notes_not_a_shared_allowance():
    """PLAN 16.2: a dealer near the voice limit still has their whole photo
    allowance, so the warning must not describe one pool."""
    assert wording.warn_threshold(20, 100, "1 September", "voice") == (
        "You have 20 of 100 voice notes left this month. The allowance resets "
        "on 1 September."
    )


def test_degraded_notice_leads_with_the_accuracy_warning_then_the_allowance():
    """PLAN section 6: 'tightened to lead with the accuracy warning rather
    than the allowance, because the accuracy warning is the part that
    prevents harm'."""
    text = wording.degraded("1 September", "image")
    assert text == (
        "I am reading this one with a simpler model and may get it wrong, "
        "so typing the codes is exact. This month's full-accuracy photo reads "
        "are used up and the allowance resets on 1 September."
    )
    assert text.index("simpler model") < text.index("allowance resets")


def test_degraded_notice_voice_keeps_both_halves_of_the_captains_constraint():
    """The accuracy drop AND that typing is exact, said for voice - and about
    voice notes only."""
    text = wording.degraded("1 September", "voice")
    assert text == (
        "I am listening to this one with a simpler model and may get it "
        "wrong, so typing your message is exact. This month's full-accuracy "
        "voice notes are used up and the allowance resets on 1 September."
    )
    assert text.index("simpler model") < text.index("allowance resets")
    assert "photo" not in text


def test_nothing_read_names_the_escape_hatch():
    """S4-09."""
    assert wording.nothing_read() == (
        "I could not read anything from that photo. Type the codes and I "
        "will look them up straight away."
    )


def test_truncated_note_names_the_cap():
    """S4-10."""
    assert wording.truncated_note(10) == (
        "There was more than I can handle in one go, so I have taken the "
        "first 10."
    )


# --------------------------------------------------------------------------- #
# Dates human-readable, counts never a percentage                            #
# --------------------------------------------------------------------------- #


def test_dates_render_human_readable_never_iso():
    for text in (
        wording.quota_exhausted(50, "1 September", "image"),
        wording.warn_threshold(9, 50, "1 September", "image"),
        wording.degraded("1 September", "image"),
        wording.quota_exhausted(100, "1 September", "voice"),
        wording.warn_threshold(20, 100, "1 September", "voice"),
        wording.degraded("1 September", "voice"),
    ):
        assert "1 September" in text
        assert "2026-09-01" not in text


# --------------------------------------------------------------------------- #
# Voice                                                                       #
# --------------------------------------------------------------------------- #


def test_voice_confirmation_quotes_the_trimmed_transcript():
    """S5-05: the existing 'here is what I heard' confirmation."""
    assert wording.voice_confirmation("  hello there  ") == (
        'Here is what I heard: "hello there"'
    )


def test_voice_unclear_full_string():
    assert wording.voice_unclear() == (
        "I could not make out that voice note. Please send it again or type "
        "your message and I will help straight away."
    )


def test_voice_language_unsure_with_a_transcript_shows_it_and_asks_to_confirm():
    """S5-03: an empty detected-language list is a valid 'unsure' signal, not
    silence - the customer still gets the transcript."""
    assert wording.voice_language_unsure("hello there") == (
        'Here is what I heard: "hello there" - I am not certain of the '
        "language, so please check it says what you meant."
    )


def test_voice_language_unsure_with_no_transcript_falls_back_to_voice_unclear():
    assert wording.voice_language_unsure(None) == wording.voice_unclear()
    assert wording.voice_language_unsure("") == wording.voice_unclear()
    assert wording.voice_language_unsure("   ") == wording.voice_unclear()


# --------------------------------------------------------------------------- #
# The two conflict shapes (PLAN Appendix A amendment 1)                       #
# --------------------------------------------------------------------------- #


def test_conflict_sentence_one_value_plus_note_has_no_source_tag():
    """The ambiguous-date shape (S4-04): rule 3 puts ONE printed string in
    `values` and both readings in `note` - the source tag would imply a
    counterpart the customer cannot see, so it must not appear."""
    conflict = MediaConflict(
        field="document_date",
        entity_raw=None,
        values=[MediaConflictValue(value="11/08/2026", source="printed")],
        note="Could be 11 August 2026 or 8 November 2026.",
    )
    sentence = wording._conflict_sentence(conflict)

    assert sentence == (
        "On the document date I can see 11/08/2026 - could be 11 August "
        "2026 or 8 November 2026. Which one should I use?"
    )
    assert "(printed)" not in sentence


def test_conflict_sentence_two_values_plus_note_carries_both_source_tags():
    """The printed-versus-handwritten shape (S4-03): two competing values, so
    the source tag earns its place on both."""
    conflict = MediaConflict(
        field="quantity",
        entity_raw="SRTBF31610",
        values=[
            MediaConflictValue(value="6", source="printed"),
            MediaConflictValue(value="4", source="handwritten"),
        ],
        note="handwritten amendment over the printed quantity",
    )
    sentence = wording._conflict_sentence(conflict)

    assert sentence == (
        "On the quantity I can see 6 (printed) and 4 (handwritten) - "
        "handwritten amendment over the printed quantity. Which one should "
        "I use?"
    )
    assert "(printed)" in sentence and "(handwritten)" in sentence


def test_conflict_sentence_no_note_is_byte_identical_without_the_dash_clause():
    conflict = MediaConflict(
        field="quantity",
        entity_raw="SRTBF31610",
        values=[
            MediaConflictValue(value="6", source="printed"),
            MediaConflictValue(value="4", source="handwritten"),
        ],
        note=None,
    )
    assert wording._conflict_sentence(conflict) == (
        "On the quantity I can see 6 (printed) and 4 (handwritten). Which "
        "one should I use?"
    )


def test_conflict_sentence_degenerate_single_value_no_note():
    """Guard against the shape collapsing badly when there is exactly one
    value and nothing else to say about it."""
    conflict = MediaConflict(
        field="model code",
        entity_raw=None,
        values=[MediaConflictValue(value="SRTKS6647", source=None)],
        note=None,
    )
    assert wording._conflict_sentence(conflict) == (
        "On the model code I can see SRTKS6647. Which one should I use?"
    )


# --------------------------------------------------------------------------- #
# Note case handling                                                          #
# --------------------------------------------------------------------------- #


def test_note_clause_preserves_a_code_leading_note():
    """A note that opens with a printed code such as 'J&Y' must not be
    lowercased - `&Y` is not a plain lowercase-able word, and rule 1 of the
    prompt ('J&Y WORLD HARDWARE is not JAY WORLD HARDWARE') applies to notes
    quoting a code just as much as to entities."""
    assert (
        wording._note_clause("J&Y is the correct customer name.")
        == "J&Y is the correct customer name"
    )


def test_note_clause_de_capitalises_a_sentence_cased_note():
    """A note written as its own sentence ('Could be ...') is lowered so it
    sits mid-sentence in the confirmation."""
    assert (
        wording._note_clause("Could be 11 August 2026 or 8 November 2026.")
        == "could be 11 August 2026 or 8 November 2026"
    )


def test_note_clause_strips_the_trailing_stop():
    clause = wording._note_clause("handwritten amendment over the printed quantity.")
    assert clause == "handwritten amendment over the printed quantity"
    assert not clause.endswith(".")


def test_note_clause_empty_note_is_empty_string():
    assert wording._note_clause(None) == ""
    assert wording._note_clause("   ") == ""


# --------------------------------------------------------------------------- #
# Confirmation message                                                        #
# --------------------------------------------------------------------------- #


def test_confirmation_names_everything_read_when_nothing_is_in_doubt():
    entities = [MediaEntity(raw="SRTKS6647", hint="product", confident=True)]
    attributes = [
        MediaAttribute(kind="batch_number", raw="YG2539", entity_raw=None, confident=True)
    ]
    assert wording.confirmation(entities, attributes, []) == (
        "I read SRTKS6647 and batch number YG2539 from that photo. Is that right?"
    )


def test_confirmation_flags_an_unconfident_value_with_no_conflict():
    entities = [MediaEntity(raw="SRTKS6647", hint="product", confident=False)]
    assert wording.confirmation(entities, [], []) == (
        "I read SRTKS6647 from that photo. I am not certain about SRTKS6647. "
        "Is that right?"
    )


def test_conflicted_attribute_is_not_also_listed_under_not_certain():
    """A value covered by a conflict sentence must not be repeated under 'I am
    not certain about' - the conflict sentence already names both of its
    values, so repeating one reads as two separate problems."""
    entities = [MediaEntity(raw="SRTBF31610", hint="product", confident=True)]
    attributes = [
        MediaAttribute(kind="quantity", raw="6", entity_raw="SRTBF31610", confident=False)
    ]
    conflicts = [
        MediaConflict(
            field="quantity",
            entity_raw="SRTBF31610",
            values=[
                MediaConflictValue(value="6", source="printed"),
                MediaConflictValue(value="4", source="handwritten"),
            ],
            note="handwritten amendment over the printed quantity",
        )
    ]

    message = wording.confirmation(entities, attributes, conflicts)

    assert message == (
        "I read SRTBF31610 from that photo. On the quantity I can see 6 "
        "(printed) and 4 (handwritten) - handwritten amendment over the "
        "printed quantity. Which one should I use?"
    )
    assert "not certain" not in message


def test_a_disputed_entity_is_named_once_by_the_conflict_sentence_only():
    """A product code that is itself one of two disagreeing readings is named by
    the conflict sentence; listing it again as read, and a third time as "not
    certain", reads as three separate problems. The other product was read and
    stays listed."""
    entities = [
        MediaEntity(raw="SRTKS6647", hint="product", confident=False),
        MediaEntity(raw="SRTBF31610", hint="product", confident=True),
    ]
    conflicts = [
        MediaConflict(
            field="product code",
            entity_raw=None,
            values=[
                MediaConflictValue(value="SRTKS6647", source="printed"),
                MediaConflictValue(value="SRTKS6641", source="handwritten"),
            ],
        )
    ]

    message = wording.confirmation(entities, [], conflicts)

    assert message == (
        "I read SRTBF31610 from that photo. On the product code I can see "
        "SRTKS6647 (printed) and SRTKS6641 (handwritten). Which one should I use?"
    )
    assert "not certain" not in message


def test_the_line_a_conflict_sits_on_stays_listed_as_read_but_not_as_uncertain():
    """`entity_raw` is the LINE the conflict is about, not the disputed value:
    the product was read, so it is listed, and the conflict sentence is what
    explains the uncertainty."""
    entities = [MediaEntity(raw="SRTBF31610", hint="product", confident=False)]
    conflicts = [
        MediaConflict(
            field="quantity",
            entity_raw="SRTBF31610",
            values=[
                MediaConflictValue(value="6", source="printed"),
                MediaConflictValue(value="4", source="handwritten"),
            ],
        )
    ]

    message = wording.confirmation(entities, [], conflicts)

    assert message.startswith("I read SRTBF31610 from that photo. On the quantity")
    assert "not certain" not in message


def test_confirmation_nothing_read_delegates_to_nothing_read():
    assert wording.confirmation([], [], []) == wording.nothing_read()


# --------------------------------------------------------------------------- #
# Clarification (S4-08)                                                       #
# --------------------------------------------------------------------------- #


def test_clarification_names_what_was_read_then_asks():
    entities = [MediaEntity(raw="SRTKS6647", hint="product", confident=True)]
    attributes = [
        MediaAttribute(kind="batch_number", raw="YG2539", entity_raw=None, confident=True)
    ]
    assert wording.clarification(entities, attributes) == (
        "I read SRTKS6647 and batch number YG2539 from that photo. What "
        "would you like me to do with it?"
    )


def test_clarification_with_nothing_read_still_asks_what_is_needed():
    assert wording.clarification([], []) == (
        "I could not read anything from that photo. Tell me what you need "
        "and I will look it up."
    )


# --------------------------------------------------------------------------- #
# join_phrase - spoken English, not a JSON array                             #
# --------------------------------------------------------------------------- #


def test_join_phrase_shapes():
    assert wording.join_phrase([]) == ""
    assert wording.join_phrase(["a"]) == "a"
    assert wording.join_phrase(["a", "b"]) == "a and b"
    assert wording.join_phrase(["a", "b", "c"]) == "a, b and c"
