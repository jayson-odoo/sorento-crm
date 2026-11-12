"""CHATBOT-CODE-MATCH slice 2 (R2, R5): all-typed-parts ranking and any code shape.

UAC: AC-8, AC-9, AC-2, AC-19 in `documentation/plans/chatbot/chatbot-code-match-acceptance-criteria.md`
("Slice 2"); behaviour card rules R2 and R5. Same harness as `test_code_match_dealer_offers.py`
(`engine.run_turn` over seeded Postgres rows, real resolver and stock decision; parser and tool read stubbed).

Parts of a typed code are its pieces split at separators and letter/digit boundaries; a candidate "holds"
a part when its code contains it (case and separators ignored), the parts found in order. The seeds are
generic made-up codes; nothing here reads a company's letters. Trigram figures quoted in the comments are
`similarity()` of the dash-stripped lowercase forms, measured in Postgres.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")


def _facts(*codes: str) -> dict[str, Stock]:
    return {c.replace("-", "_"): Stock(on_hand=100) for c in codes}


def _as_staff(c: Console) -> None:
    c.as_staff()
    c.stock_on_hand = 12


# --------------------------------------------------------------------------- AC-8

#: Typed "TWC8354-UF": parts TWC, 8354, UF. Trigram vs the typed form: TWC8354-UP 0.667 (misses UF),
#: TWC8354-SH-UF 0.571 and TWC8354-RD-UF 0.571 (hold every part, in order). Today's order puts the miss first.
TYPED = "TWC8354-UF"
MISSES_A_PART = "TWC8354-UP"
HOLD_ALL = ["TWC8354-SH-UF", "TWC8354-RD-UF"]


def test_ac8_candidates_holding_every_typed_part_are_offered_before_one_missing_a_part(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [MISSES_A_PART, *HOLD_ALL])
    dealer_text = c.say(f"{TYPED} x 3", stock(product(TYPED, 3)))
    dealer = _option_codes(c)
    assert set(dealer[:2]) == set(HOLD_ALL) and dealer[2:] == [MISSES_A_PART], (dealer, dealer_text)

    _as_staff(c)
    c.say(f"{TYPED} x 3", stock(product(TYPED, 3)))
    assert _option_codes(c) == dealer, (_option_codes(c), dealer)


# --------------------------------------------------------------------------- AC-8c

#: Typed "TWC8354-SH-UF": the separators split the letter blocks, so the parts are TWC, 8354, SH, UF.
#: TWC8354-SH-N-UF holds all four, in order, though SH and UF are not adjacent (trigram 0.667 vs the folded
#: typed form); TWC8354-SH-UC misses UF and scores higher (0.714), so today's order puts it first. No
#: catalogue code equals the typed code folded.
SPLIT_TYPED = "TWC8354-SH-UF"
HOLDS_NOT_ADJACENT = "TWC8354-SH-N-UF"
MISSES_UF = "TWC8354-SH-UC"


def test_ac8c_parts_come_from_the_code_as_typed_so_a_separator_splits_letter_blocks(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [MISSES_UF, HOLDS_NOT_ADJACENT])
    dealer_text = c.say(f"{SPLIT_TYPED} x 3", stock(product(SPLIT_TYPED, 3)))
    dealer = _option_codes(c)
    assert dealer == [HOLDS_NOT_ADJACENT, MISSES_UF], (dealer, dealer_text)

    _as_staff(c)
    c.say(f"{SPLIT_TYPED} x 3", stock(product(SPLIT_TYPED, 3)))
    assert _option_codes(c) == [HOLDS_NOT_ADJACENT, MISSES_UF], c.stored_question


# --------------------------------------------------------------------------- AC-8b


def test_ac8b_two_misses_in_one_message_are_each_ranked_as_they_are_alone(session_factory, monkeypatch, stub_access):  # noqa: F811
    other_typed = "MWC9210-UF"
    other = ["MWC9210-UP", "MWC9210-SH-UF", "MWC9210-RD-UF"]
    c = _console(session_factory, monkeypatch, stub_access, [MISSES_A_PART, *HOLD_ALL, *other])
    c.say(f"{TYPED} x 1", stock(product(TYPED, 1)))
    alone_1 = _option_codes(c)
    c.state = None
    c.say(f"{other_typed} x 2", stock(product(other_typed, 2)))
    alone_2 = _option_codes(c)
    assert set(alone_1[:2]) == set(HOLD_ALL) and set(alone_2[:2]) == {"MWC9210-SH-UF", "MWC9210-RD-UF"}, (alone_1, alone_2)

    c.state = None
    text = c.say(f"{TYPED} x 1, {other_typed} x 2", stock(product(TYPED, 1), product(other_typed, 2)))
    assert text.count("Did you mean") == 2, text
    assert _option_codes(c) == alone_1 + alone_2, (_option_codes(c), alone_1, alone_2)


# --------------------------------------------------------------------------- AC-9


def test_ac9_a_short_token_matching_more_than_three_codes_keeps_the_picker_of_all_of_them(session_factory, monkeypatch, stub_access):  # noqa: F811
    codes = ["TWC8152-SH-UF", "TWC8152-SH-UF-N", "TWC8152-SH-UP", "BRC8152-SH", "ELP8152", "MWC8152-RD-UF"]
    c = _console(session_factory, monkeypatch, stub_access, codes)
    text = c.say("8152 stock", stock(product("8152")))
    assert sorted(_option_codes(c)) == sorted(codes), (_option_codes(c), text)
    for i in range(1, len(codes) + 1):
        assert f"{i}. " in text, text
    assert "Which one?" in text or "which one?" in text, text
    assert REFER_TO_SALESMAN not in text, text

    _as_staff(c)
    c.say("8152 stock", stock(product("8152")))
    assert sorted(_option_codes(c)) == sorted(codes), c.stored_question


# --------------------------------------------------------------------------- AC-2


def test_ac2_a_code_typed_with_spaces_is_answered_directly(session_factory, monkeypatch, stub_access):  # noqa: F811
    code = "TWC8354-SH-UF"
    c = _console(session_factory, monkeypatch, stub_access, [code], **_facts(code))
    typed = "twc 8354 sh uf"
    text = c.say(f"{typed} x 2", stock(product(typed, 2)))
    assert text == f"{code} x 2: {TICK} Got stock.", text

    _as_staff(c)
    staff = c.say(f"{typed} x 2", stock(product(typed, 2)))
    assert "Did you mean" not in staff and "Couldn't find" not in staff, staff
    assert code in staff, staff


# --------------------------------------------------------------------------- AC-19


def test_ac19_a_digits_first_token_reaches_its_catalogue_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    code = "TWC8152-SH"
    c = _console(session_factory, monkeypatch, stub_access, [code], **_facts(code))
    text = c.say("8152-SH x 2", stock(product("8152-SH", 2)))
    assert code in text, text
    assert "Couldn't find:" not in text and REFER_TO_SALESMAN not in text, text

    _as_staff(c)
    staff = c.say("8152-SH x 2", stock(product("8152-SH", 2)))
    assert code in staff, staff
    assert "Couldn't find:" not in staff, staff


def test_ac19_a_letters_only_token_reaches_its_catalogue_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    code = "ABCDE"  # typed ABCDF: trigram 0.500
    c = _console(session_factory, monkeypatch, stub_access, [code], **_facts(code))
    text = c.say("ABCDF x 2", stock(product("ABCDF", 2)))
    assert code in text, text
    assert REFER_TO_SALESMAN not in text, text
    assert _option_codes(c) == [code], c.stored_question

    _as_staff(c)
    staff = c.say("ABCDF x 2", stock(product("ABCDF", 2)))
    assert code in staff, staff
