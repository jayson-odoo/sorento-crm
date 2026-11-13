"""CHATBOT-CLOSE-CODES round 3: red tests from the lane review.

UAC (FINAL): `documentation/plans/chatbot/chatbot-close-codes-acceptance-criteria.md` (AC-6, AC-9, AC-10, AC-20,
AC-22). Same harness as `test_code_match_dealer_offers.py`: `engine.run_turn` over seeded Postgres rows in a blank
schema, the parser verdict and the tool reads stubbed. "Dealer" is the console's default availability-only contact.
Codes are made-up catalogue-shaped codes; no customer, phone or price appears.

ELP3754 (one close code of ELP3753), SRT5674, SRTWC287-S-150 and the SRTWC286 family are the console's own seeds.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import OWNER_FAMILY, answer, numbered, product, reply, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes, _pick_positions

from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

R = REFER_TO_SALESMAN
PICK10 = numbered("SRTWC286 x 10: which one?", OWNER_FAMILY)
HOW_MANY = "SRT5674"
TYPO, CLOSE = "ELP3753", "ELP3754"
#: One wrong letter; three close codes (trigram 0.65 / 0.47 / 0.47), the console's SRTWC6022/286-SH-UF at 0.22.
TYPO3 = "SWTWC8354-SH-UF"
CLOSE3 = ["SRTWC8354-SH-UF", "SRTWC8354-SH-UP", "SRTWC8354-SH-UN"]


def _facts(*codes: str) -> dict[str, Stock]:
    return {c.replace("-", "_"): Stock(on_hand=100) for c in codes}


def _yes():
    return reply(is_affirmative=True, open_question_answer=answer("yes"))


def _qty(n: int):
    return reply(demand_qty=n)


def _position_of(c: Console, code: str) -> int:
    for o in (c.stored_question or {}).get("options") or []:
        if str(o.get("code")) == code:
            return int(o["position"])
    raise AssertionError(f"{code} is not an option of the stored question: {c.stored_question}")


def _how_many_and_offer(session_factory, monkeypatch, stub_access) -> tuple[Console, str]:  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [], **_facts(HOW_MANY, CLOSE))
    text = c.say(f"{HOW_MANY} stock, {TYPO} stock", stock(product(HOW_MANY), product(TYPO)))
    assert f"How many units of {HOW_MANY}?" in text, text
    assert f"Couldn't find {TYPO}. Did you mean" in text and CLOSE in text, text
    return c, text


# --------------------------------------------------------------------------- 1. AC-9 answered in either order


@pytest.mark.parametrize("how", ["yes", "number"])
def test_r3_1_answering_the_offer_first_keeps_the_how_many_question_for_the_found_code(session_factory, monkeypatch, stub_access, how):  # noqa: F811
    c, _ = _how_many_and_offer(session_factory, monkeypatch, stub_access)
    if how == "yes":
        follow = c.say("yes", _yes())
    else:
        pos = _position_of(c, CLOSE)
        follow = c.say(str(pos), _pick_positions(pos))
    assert HOW_MANY in follow, f"the open how-many for {HOW_MANY} was dropped: {follow!r}"
    assert follow.strip() != f"How many units of {CLOSE}?", follow
    later = c.say("7", _qty(7))
    assert f"{HOW_MANY} x 7:" in later, f"the later number did not answer {HOW_MANY}: {later!r}"


def test_r3_1_answering_the_how_many_first_keeps_the_offer_open(session_factory, monkeypatch, stub_access):  # noqa: F811
    c, _ = _how_many_and_offer(session_factory, monkeypatch, stub_access)
    first = c.say("7", _qty(7))
    assert f"{HOW_MANY} x 7: {TICK} Got stock." in first, first
    assert f"{CLOSE} x 7" not in first, f"the number went to the offered code: {first!r}"
    after = c.say("yes", _yes())
    assert CLOSE in after, after
    assert "Couldn't find" not in after and R not in after, after


# --------------------------------------------------------------------------- 2. half-answered which-one + offer


def test_r3_2_picking_only_the_which_one_option_re_asks_the_leftover_offer_in_the_offer_shape(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [], **_facts("SRTWC286-SH-150", CLOSE))
    text = c.say("srtwc286 x 10, ELP3753 x 2", stock(product("srtwc286", 10), product(TYPO, 2)))
    assert PICK10 in text and f"Couldn't find {TYPO}. Did you mean" in text, text
    after = c.say("2", _pick_positions(2))
    assert f"SRTWC286-SH-150 x 10: {TICK} Got stock." in after, after
    assert f"Couldn't find {TYPO}" in after and "Did you mean" in after, after
    assert f"{TYPO} x 2: which one?".lower() not in after.lower(), after
    assert CLOSE in _option_codes(c), c.stored_question


# --------------------------------------------------------------------------- 3. trace of a merged reply


def _assert_trace_marks_only_offered(c: Console, never_offered: set[str]) -> list[dict[str, Any]]:
    entries = c.trace_entries("code_candidates")
    assert entries, "no code_candidates entry"
    for e in entries:
        assert e.get("outcome") != "answered", e
        rows = e.get("candidates") or []
        offered_rows = [r for r in rows if r.get("outcome") == "offered"]
        assert not {str(r.get("code")) for r in offered_rows} & never_offered, (
            f"a which-one option was traced as offered: {e}"
        )
        if not offered_rows:
            assert e.get("outcome") == "no_candidate", f"nothing shown for this miss, yet: {e}"
    return entries


def test_r3_3_merged_which_one_and_offer_traces_only_the_offered_close_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [], **_facts("SRTWC286-SH-150", CLOSE))
    c.say("srtwc286 x 10, ELP3753 x 2", stock(product("srtwc286", 10), product(TYPO, 2)))
    entries = _assert_trace_marks_only_offered(c, set(OWNER_FAMILY))
    mine = [e for e in entries if str(e.get("typed", "")).upper() == TYPO]
    assert len(mine) == 1 and mine[0].get("outcome") == "offered", entries
    offered = [str(r.get("code")) for r in mine[0].get("candidates") or [] if r.get("outcome") == "offered"]
    assert offered == [CLOSE], mine[0]


def test_r3_3_a_miss_whose_close_codes_are_all_shown_elsewhere_reads_no_candidate(session_factory, monkeypatch, stub_access):  # noqa: F811
    """AC-25 shape: SRT6532-BL's close codes are already in the SRT6534 which-one list, so it is named without an offer
    of its own; its trace entry must not read `answered` and must not mark those list options as offered."""
    family = ["SRT6534-BL", "SRT6534-WH"]
    codes = [*family, "SRT6537-GR"]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))
    c.say(
        "SRT6537-BL X10 / SRT6532-BL X10 / SRT6534 X10",
        stock(product("SRT6537-BL", 10), product("SRT6532-BL", 10), product("SRT6534", 10)),
    )
    entries = _assert_trace_marks_only_offered(c, set(family))
    typed = {str(e.get("typed", "")).upper() for e in entries}
    assert {"SRT6537-BL", "SRT6532-BL"} <= typed, entries


# --------------------------------------------------------------------------- 4. AC-9 / AC-10 with 2-3 close codes


def test_r3_4_how_many_beside_a_miss_with_several_close_codes_numbered_list_and_a_number_picks(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, CLOSE3, **_facts(HOW_MANY, *CLOSE3))
    text = c.say(f"{HOW_MANY} stock, {TYPO3} stock", stock(product(HOW_MANY), product(TYPO3)))
    assert f"How many units of {HOW_MANY}?" in text, text
    assert f"Couldn't find {TYPO3}. Did you mean:" in text, text
    offered = [code for code in _option_codes(c) if code in CLOSE3]
    assert 2 <= len(offered) <= 3, c.stored_question
    positions = [_position_of(c, code) for code in offered]
    assert positions == list(range(positions[0], positions[0] + len(offered))), positions
    for pos, code in zip(positions, offered):
        assert f"{pos}. {code}" in text, text
    after = c.say(str(positions[1]), _pick_positions(positions[1]))
    assert offered[1] in after and "Couldn't find" not in after, after


def test_r3_4_which_one_beside_a_miss_with_several_close_codes_numbers_on_from_11(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, CLOSE3, **_facts("SRTWC286-SH-150", *CLOSE3))
    text = c.say("srtwc286 x 10, SWTWC8354-SH-UF x 2", stock(product("srtwc286", 10), product(TYPO3, 2)))
    assert PICK10 in text, text
    at = text.find(f"Couldn't find {TYPO3}. Did you mean:")
    assert at > text.find(PICK10) >= 0, text
    offered = [code for code in _option_codes(c) if code in CLOSE3]
    assert 2 <= len(offered) <= 3, c.stored_question
    for i, code in enumerate(offered, 11):
        assert f"{i}. {code}" in text[at:], text
    after = c.say("12", _pick_positions(12))
    assert f"{offered[1]} x 2: {TICK} Got stock." in after, after


# --------------------------------------------------------------------------- 5. AC-20 greeting


def test_r3_5_a_greeting_first_gets_the_same_offer_as_without_it(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, CLOSE3[:1], **_facts(CLOSE3[0]))
    plain = c.say(f"{TYPO3} x 3 stock?", stock(product(TYPO3, 3)))
    plain_options = _option_codes(c)
    assert f"Couldn't find {TYPO3}. Did you mean {CLOSE3[0]}?" in plain, plain
    c.state = None
    greeted = c.say(f"hi, {TYPO3} x 3 stock?", stock(product(TYPO3, 3)))
    assert f"Couldn't find {TYPO3}. Did you mean {CLOSE3[0]}?" in greeted, greeted
    assert R not in greeted, greeted
    assert _option_codes(c) == plain_options, (c.stored_question, plain_options)


# --------------------------------------------------------------------------- 6. parser-corrected codes (crew (a), 13 Nov)
#
# The parser stub hands `canonical_code` = the catalogue code. Crew ruling (a): the parser's correction does not make a
# direct answer. Only a raw equal to the code but for case, dashes and spaces (R5), or a raw the resolver narrows to the
# code by its own words (R2, the colour words), is answered; a typo in the code or its words (R1, R3) and a lone prefix
# (R4) are offered.

INLET = "SRTUB668-BACK INLET"
GM = "SRTWT8259-GM"
WHO = pytest.mark.parametrize("who", ["dealer", "staff"])


def _corrected(raw: str, canonical: str, qty: int | None = None) -> dict[str, Any]:
    return stock({**product(raw, qty), "canonical_code": canonical})


def _who(session_factory, monkeypatch, stub_access, who: str, codes: list[str]) -> Console:  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))
    if who == "staff":
        c.as_staff()
        c.stock_on_hand = 12
    return c


def _assert_offered_not_answered(c: Console, text: str, who: str, raw: str, code: str) -> None:
    assert TICK not in text and "Got stock" not in text, f"answered on the parser's correction: {text!r}"
    assert "Stock summary" not in text and "*Product Code:*" not in text, f"answered on the parser's correction: {text!r}"
    # Staff keep their own offer shape ("Did you mean:" then "1. <code> - has stock details"), so only the dealer's
    # wording is pinned.
    assert "Did you mean" in text and code in text, text
    if who == "dealer":
        assert f"Couldn't find {raw.upper()}. Did you mean {code}?" in text, text
        assert R not in text, text
        assert _option_codes(c) == [code], c.stored_question


def _assert_answered(text: str, who: str, code: str, qty: int) -> None:
    assert "Did you mean" not in text and "Couldn't find" not in text, text
    if who == "dealer":
        assert text == f"{code} x {qty}: {TICK} Got stock.", text
    else:
        assert f"*Product Code:* {code}" in text, text


@WHO
def test_r3_6_r1_a_typo_word_the_parser_corrected_is_offered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    raw = "SRTUB668-BACK INLT"
    c = _who(session_factory, monkeypatch, stub_access, who, [INLET])
    text = c.say(f"{raw} x 2 stock", _corrected(raw, INLET, 2))
    _assert_offered_not_answered(c, text, who, raw, INLET)


@WHO
def test_r3_6_r2_a_code_with_colour_words_the_parser_mapped_is_answered_directly(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    raw = "SRTWT8259 gun metal"
    c = _who(session_factory, monkeypatch, stub_access, who, [GM])
    text = c.say(f"{raw} x 2 stock", _corrected(raw, GM, 2))
    _assert_answered(text, who, GM, 2)


@WHO
def test_r3_6_r3_a_letter_the_parser_fixed_in_the_code_is_offered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _who(session_factory, monkeypatch, stub_access, who, CLOSE3[:1])
    text = c.say(f"{TYPO3} x 3", _corrected(TYPO3, CLOSE3[0], 3))
    _assert_offered_not_answered(c, text, who, TYPO3, CLOSE3[0])


@WHO
def test_r3_6_r4_a_lone_prefix_the_parser_corrected_to_the_full_code_is_offered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    raw, full = "SRTWC287-S", "SRTWC287-S-150"  # the console's own code
    c = _who(session_factory, monkeypatch, stub_access, who, [])
    text = c.say(f"{raw} x 3", _corrected(raw, full, 3))
    _assert_offered_not_answered(c, text, who, raw, full)


@WHO
def test_r3_6_r5_a_code_typed_with_spaces_the_parser_folded_is_answered_directly(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    raw = "srtwc 8354 sh uf"
    c = _who(session_factory, monkeypatch, stub_access, who, CLOSE3[:1])
    text = c.say(f"{raw} x 3", _corrected(raw, CLOSE3[0], 3))
    _assert_answered(text, who, CLOSE3[0], 3)
