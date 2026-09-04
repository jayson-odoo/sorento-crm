"""Digits and word boundaries are ASCII, because JavaScript's are (review S3).

Python's `\\d` and `\\b` are Unicode-aware; JavaScript's are not. A full-width digit
(U+FF11 "１", what a Chinese or Japanese IME produces by default) satisfies Python's
`^#?\\s*\\d+$` and NOT JavaScript's, so the port would have read it as a NUMBER where live
reads it as free text.

That is not a cosmetic difference. In a `member_offer` context a bare number is forced to
be a pick (`_forcePick`), and a pick with `preferred_assignee_id` fires a real assignment:
a staff member gets the conversation, the PIC comment and the SLA clock. A customer typing
"１" on an IME keyboard would have been silently assigned to whoever sat at index 1 of a
roster they were not answering.

Same class for `js_number`: `Number("１")` is `NaN` in JS and would have been `1` here.
"""
from __future__ import annotations

import pytest

from app.services.chatbot import jsc
from app.services.chatbot.head import output_exchange as ox

# Built from code points, never pasted: a literal here is invisible in a diff and one
# stray normalisation by an editor would silently retire the test.
FULL_WIDTH_ONE = chr(0xFF11)  # U+FF11 FULLWIDTH DIGIT ONE
ARABIC_INDIC_TWO = chr(0x0662)  # U+0662 ARABIC-INDIC DIGIT TWO
DEVANAGARI_THREE = chr(0x0969)  # U+0969 DEVANAGARI DIGIT THREE

NON_ASCII_DIGITS = [FULL_WIDTH_ONE, ARABIC_INDIC_TWO, DEVANAGARI_THREE]


class TestJsNumber:
    @pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
    def test_a_non_ascii_digit_is_NaN_exactly_as_in_javascript(self, digit: str) -> None:
        assert jsc.is_nan(jsc.js_number(digit))

    def test_an_ascii_digit_is_still_a_number(self) -> None:
        assert jsc.js_number("1") == 1
        assert jsc.js_number(" 42 ") == 42

    def test_a_mixed_string_is_NaN_not_a_partial_parse(self) -> None:
        assert jsc.is_nan(jsc.js_number("1" + FULL_WIDTH_ONE))


class TestBareNumberDetection:
    """`_BARE_NUMBER_RE` is what makes a reply a member PICK rather than a query."""

    @pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
    def test_a_non_ascii_digit_is_not_a_bare_number(self, digit: str) -> None:
        assert ox._BARE_NUMBER_RE.match(digit) is None

    def test_an_ascii_digit_still_is(self) -> None:
        assert ox._BARE_NUMBER_RE.match("1") is not None
        assert ox._BARE_NUMBER_RE.match("#4") is not None


class TestDigitsAndConnectivesReply:
    """`_DIGITS_ONLY_RE` gates the tier-offer digit extraction ("1", "1 and 2", "1,2")."""

    @pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
    def test_a_non_ascii_digit_reply_is_not_treated_as_positions(self, digit: str) -> None:
        assert ox._DIGITS_ONLY_RE.match(digit) is None

    @pytest.mark.parametrize(
        "message", ["1", "1, 2", "1 and 2", "1,2", "#3", "1 & 2", "1+2", "1 , 2 ", "2."]
    )
    def test_the_real_grammars_still_match(self, message: str) -> None:
        assert ox._DIGITS_ONLY_RE.match(message) is not None, message

    def test_whitespace_stays_UNICODE_the_way_javascript_has_it(self) -> None:
        r"""The other half of the ASCII fix, and the easy one to get backwards.

        `re.ASCII` would have narrowed `\s` as well as `\d`, but JavaScript's `\s` DOES
        match Unicode whitespace. A non-breaking space between "1," and "2" is an ordinary
        IME and copy-paste artefact, and live accepts it - narrowing it here would have
        broken a reply that works today, which is the opposite mistake to the one being
        fixed. Hence explicit `[0-9]` classes and no flag.
        """
        nbsp = chr(0x00A0)  # NO-BREAK SPACE
        assert ox._DIGITS_ONLY_RE.match(f"1,{nbsp}2") is not None
        assert ox._BARE_NUMBER_RE.match(f"#{nbsp}4") is not None
        assert ox._OPTION_ANY_RE.search(f"option{nbsp}4") is not None

    def test_a_non_ascii_digit_is_still_refused_around_that_whitespace(self) -> None:
        nbsp = chr(0x00A0)
        assert ox._DIGITS_ONLY_RE.match(f"1,{nbsp}{FULL_WIDTH_ONE}") is None


class TestDateLikeGuard:
    """A did-you-mean pick must never be hijacked by a date; the guard is ASCII too."""

    def test_a_full_width_date_is_not_recognised_as_a_date(self) -> None:
        full_width = "".join(chr(0xFF10 + int(c)) if c.isdigit() else c for c in "2026-09-04")
        assert ox._ISO_DATE_RE.match(full_width) is None

    def test_an_ascii_date_still_is(self) -> None:
        assert ox._ISO_DATE_RE.match("2026-09-04") is not None
        assert ox._SHORT_DATE_RE.match("4/9/2026") is not None


class TestOrdinalWordBoundary:
    """`\\b` is Unicode-aware in Python: without re.ASCII, a boundary can land differently
    around non-ASCII neighbours than it does in JS."""

    def test_the_option_grammar_is_ascii_bounded(self) -> None:
        assert ox._OPTION_ANY_RE.search("option 4") is not None
        assert ox._OPTION_ANY_RE.search("option " + FULL_WIDTH_ONE) is None


class TestEndToEndThroughTheMemberPickArm:
    """The consequence, not just the predicate: a full-width digit must NOT force a pick."""

    def _run(self, message: str) -> dict:
        parent_input = {
            "latest_user_message": message,
            "previous_conversation_state": {
                "selection_context": "member_offer",
                "last_result_set": [
                    {"idx": 1, "uuid": "ZZT-uuid-1", "label": "Aisyah Rahman"},
                    {"idx": 2, "uuid": "ZZT-uuid-2", "label": "Boon Keat"},
                ],
                "routing": {"suggested_team": "customer_service"},
            },
        }
        qf = {
            "message_type": "casual",
            "intent_hint": None,
            "domain_hint": None,
            "entities": [],
            "entity_op": "reuse",
            "reference_positions": [],
            "reference_target": None,
            "person_mention": None,
            "is_affirmative": None,
            "escalation": {"is_escalation_confirmation": False},
            "routing": {"suggested_team": None, "suggested_agent": None, "team_source": None},
        }
        return ox.post_process({"output": qf}, {}, parent_input)["output"]

    def test_an_ascii_digit_resolves_the_pick(self) -> None:
        escalation = self._run("1")["escalation"]
        assert escalation["is_escalation_confirmation"] is True
        assert escalation["preferred_assignee_id"] == "ZZT-uuid-1"

    def test_a_full_width_digit_does_NOT_assign_anybody(self) -> None:
        escalation = self._run(FULL_WIDTH_ONE)["escalation"]
        assert "preferred_assignee_id" not in escalation, (
            "a full-width digit was read as a roster position and would have assigned a "
            "real staff member - JavaScript reads it as free text"
        )
