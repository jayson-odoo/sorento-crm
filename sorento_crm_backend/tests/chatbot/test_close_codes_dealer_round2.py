"""CHATBOT-CLOSE-CODES round 2: direct answer only for an equal code, misses beside a question, ETA asks, ranking,
and the crew data shapes.

UAC (FINAL, 13 Nov): `documentation/plans/chatbot/chatbot-close-codes-acceptance-criteria.md`, AC-6, AC-9..AC-16,
AC-24..AC-30. Crew answered card questions Q1-Q5 all (a). The S08 update for AC-6 lives in
`test_avail_mode_scenarios.py`.

Same harness as `test_code_match_dealer_offers.py` (`engine.run_turn` over seeded Postgres rows in a blank schema; the
parser verdict and the tool reads are stubbed). "Dealer" is the console's default availability-only contact. The data
shape codes are made-up codes of the same shape as crew's masked rows; no customer, phone or price appears. Trigram
figures are `similarity()` of the lowercase separator-stripped forms, measured in Postgres.

Assumption: a follow-up "yes" / number over an ETA offer is read by the parser with the incoming hints, the way the ETA
ask itself is (`_eta_reply`).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import OWNER_FAMILY, answer, numbered, product, reply, stock
from tests.chatbot.test_code_match_dealer_offers import (
    TICK,
    Console,
    _console,
    _dym_tail,
    _option_codes,
    _pick_positions,
    _word,
)
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_engine_company_scope import _seed_company, _seed_product

pytestmark = pytest.mark.usefixtures("stub_access")

R = REFER_TO_SALESMAN
MALAY_R = "Sila rujuk jurujual anda."  # the refer line as a Malay ask gets it today
ETA = date(2026, 10, 19)
ETA_TEXT = "ETA 19/10/2026"
EXACT = "ZQX5521"
PICK10 = numbered("SRTWC286 x 10: which one?", OWNER_FAMILY)


def _facts(*codes: str, **kw: Any) -> dict[str, Stock]:
    return {c.replace("-", "_"): Stock(on_hand=100, **kw) for c in codes}


def _yes():
    return reply(is_affirmative=True, open_question_answer=answer("yes"))


def _eta_ask(*codes: str):
    return reply(entities=[product(c) for c in codes], domain_hint="incoming", intent_hint="check_incoming")


def _eta_reply(**overrides: Any):
    return reply(domain_hint="incoming", intent_hint="check_incoming", **overrides)


def _position_of(c: Console, code: str) -> int:
    for o in (c.stored_question or {}).get("options") or []:
        if str(o.get("code")) == code:
            return int(o["position"])
    raise AssertionError(f"{code} is not an option of the stored question: {c.stored_question}")


def _as_staff(c: Console) -> None:
    c.as_staff()
    c.stock_on_hand = 12


def _assert_not_answered(text: str) -> None:
    assert TICK not in text and "Got stock" not in text, f"answered on a guess: {text!r}"
    assert "How many units of" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"
    assert "*Product Code:*" not in text, f"answered on a guess: {text!r}"


# --------------------------------------------------------------------------- AC-6

PREFIX_TYPED, PREFIX_ONE = "SRTWC287-S", "SRTWC287-S-150"  # the console's own code; S08 shape


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac6_a_lone_prefix_of_one_digit_code_is_offered_not_answered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [], **_facts(PREFIX_ONE))
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{PREFIX_TYPED} x 3", stock(product(PREFIX_TYPED, 3)))
    _assert_not_answered(text)
    if who == "dealer":
        assert text == f"Couldn't find {PREFIX_TYPED}. Did you mean {PREFIX_ONE}?", text
        assert _option_codes(c) == [PREFIX_ONE], c.stored_question
        assert c.say("yes", _yes()) == f"{PREFIX_ONE} x 3: {TICK} Got stock."
    else:
        assert "Did you mean" in text and PREFIX_ONE in text, text


def test_ac6_a_lone_prefix_beside_an_exact_code_is_offered_not_answered(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [EXACT], **_facts(EXACT, PREFIX_ONE))
    text = c.say(f"{EXACT} x 5, {PREFIX_TYPED} x 3", stock(product(EXACT, 5), product(PREFIX_TYPED, 3)))
    assert f"{EXACT} x 5: {TICK} Got stock." in text, text
    assert f"{PREFIX_ONE} x 3" not in text, f"the prefix was answered directly: {text!r}"
    assert f"Couldn't find {PREFIX_TYPED}. Did you mean {PREFIX_ONE}?" in text, text


# --------------------------------------------------------------------------- AC-9, AC-28

TYPO, TYPO_CLOSE = "ELP3753", "ELP3754"  # the console's own code; S11 shape (one close code)


def test_ac9_a_miss_beside_a_how_many_question_gets_its_offer_in_the_same_reply(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [], **_facts("SRT5674", TYPO_CLOSE))
    text = c.say("SRT5674 stock, ELP3753 stock", stock(product("SRT5674"), product(TYPO)))
    assert "How many units of SRT5674?" in text, text
    assert f"Couldn't find {TYPO}. Did you mean" in text, f"the miss got no offer beside the question: {text!r}"
    assert TYPO_CLOSE in _dym_tail(text), text
    assert R not in text, text
    after = c.say("pick", _pick_positions(_position_of(c, TYPO_CLOSE)))
    assert TYPO_CLOSE in after and "Couldn't find" not in after and R not in after, after


def test_ac28_cb86_shape_how_many_and_the_offer_for_the_miss_in_one_reply(session_factory, monkeypatch, stub_access):  # noqa: F811
    """`Cb86BL and Cb86gm stock`: CB86-BL is found (needs "how many"); CB83-GM is close to Cb86gm (trigram 0.40)."""
    found, close = "CB86-BL", "CB83-GM"
    c = _console(session_factory, monkeypatch, stub_access, [found, close], **_facts(found, close))
    text = c.say("Cb86BL and Cb86gm stock", stock(product("Cb86BL"), product("Cb86gm")))
    assert f"How many units of {found}?" in text, text
    assert "couldn't find cb86gm. did you mean" in text.lower(), text
    assert close in _dym_tail(text), text
    assert R not in text, text
    after = c.say("pick", _pick_positions(_position_of(c, close)))
    assert close in after and "Couldn't find" not in after, after


# --------------------------------------------------------------------------- AC-10


def test_ac10_a_family_which_one_list_then_the_offer_numbered_on_and_a_number_picks_it(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [], **_facts("SRTWC286-SH-150", TYPO_CLOSE))
    text = c.say("srtwc286 x 10, ELP3753 x 2", stock(product("srtwc286", 10), product(TYPO, 2)))
    assert PICK10 in text, text
    at = text.find(f"Couldn't find {TYPO}. Did you mean")
    assert at > text.find(PICK10) >= 0, f"no offer after the which-one options: {text!r}"
    assert f"11. {TYPO_CLOSE}" in text[at:], text
    assert R not in text, text
    assert _position_of(c, TYPO_CLOSE) == 11, c.stored_question
    after = c.say("11", _pick_positions(11))
    assert f"{TYPO_CLOSE} x 2: {TICK} Got stock." in after, after


# --------------------------------------------------------------------------- AC-11, AC-12, AC-13

ETA_TYPO = "SWTWC8354-SH-UF"  # one wrong letter
ETA_TARGET = "SRTWC8354-SH-UF"  # trigram 0.65; the console's SRTWC6022/286-SH-UF families sit at 0.22
ETA_SIBLINGS = ["SRTWC8354-SH-UP", "SRTWC8354-SH-UN"]  # 0.47 each


@pytest.mark.parametrize("message", [f"{ETA_TYPO} bila sampai?", f"ETA {ETA_TYPO}?"])
def test_ac11_dealer_eta_ask_with_one_close_code_is_offered_and_yes_answers_its_incoming(session_factory, monkeypatch, stub_access, message):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [ETA_TARGET], **{ETA_TARGET.replace("-", "_"): Stock(eta=ETA)})
    text = c.say(message, _eta_ask(ETA_TYPO))
    if message.startswith("ETA"):
        assert f"Couldn't find {ETA_TYPO}. Did you mean {ETA_TARGET}?" in text, text
    else:  # a Malay ask is answered in Malay: same path, so the same offer and no refer line in either language
        assert ETA_TARGET in text, text
    assert R not in text and MALAY_R not in text, text
    assert _option_codes(c) == [ETA_TARGET], c.stored_question
    after = c.say("yes", _eta_reply(is_affirmative=True, open_question_answer=answer("yes")))
    assert f"{ETA_TARGET}: {TICK} {ETA_TEXT}" in after, after


def test_ac12_dealer_eta_ask_with_several_close_codes_numbered_and_a_number_answers_that_incoming(session_factory, monkeypatch, stub_access):  # noqa: F811
    codes = [ETA_TARGET, *ETA_SIBLINGS]
    c = _console(session_factory, monkeypatch, stub_access, codes, **{k.replace("-", "_"): Stock(eta=ETA) for k in codes})
    text = c.say(f"ETA {ETA_TYPO}?", _eta_ask(ETA_TYPO))
    assert f"Couldn't find {ETA_TYPO}. Did you mean:" in text, text
    assert R not in text, text
    offered = _option_codes(c)
    assert 2 <= len(offered) <= 3 and set(offered) <= set(codes), offered
    for i, code in enumerate(offered, 1):
        assert f"{i}. {code}" in text, text
    after = c.say("2", _eta_reply(reference_positions=[2], open_question_answer=answer("pick", picked=[2])))
    assert f"{offered[1]}: {TICK} {ETA_TEXT}" in after, after


def test_ac13_dealer_eta_ask_with_no_close_code_keeps_the_refer_line(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [ETA_TARGET])
    text = c.say("ETA QQXZ9917-ZZ?", _eta_ask("QQXZ9917-ZZ"))
    assert "Did you mean" not in text, text
    assert "Couldn't find" in text and "QQXZ9917-ZZ" in text and R in text, text


# --------------------------------------------------------------------------- AC-14, AC-15

#: Typed TWC8354-UF (parts TWC, 8354, UF). Six decoys missing UF score 0.667; the only code holding every part scores
#: 0.47, so it is the 7th trigram row.
RANK_TYPED = "TWC8354-UF"
RANK_DECOYS = ["TWC8354-UP", "TWC8354-UN", "TWC8354-UX", "TWC8354-UA", "TWC8354-UB", "TWC8354-UC"]
RANK_ALL_PARTS = "TWC8354-SH-RD-N-UF"


def _rank_world(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    codes = [EXACT, *RANK_DECOYS, RANK_ALL_PARTS]
    return _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))


def test_ac14_an_all_parts_code_below_the_fifth_trigram_row_is_offered_first(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _rank_world(session_factory, monkeypatch, stub_access)
    text = c.say(f"{RANK_TYPED} x 3", stock(product(RANK_TYPED, 3)))
    offered = _option_codes(c)
    assert len(offered) == 3, (offered, text)
    assert offered[0] == RANK_ALL_PARTS, f"the all-parts code (7th trigram row) was not ranked first: {offered}"


def test_ac15_ranking_is_the_same_for_staff_and_dealers_single_and_multi_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _rank_world(session_factory, monkeypatch, stub_access)
    c.say(f"{RANK_TYPED} x 3", stock(product(RANK_TYPED, 3)))
    dealer_alone = _option_codes(c)
    assert RANK_ALL_PARTS in dealer_alone, dealer_alone
    c.state = None
    c.say(f"{EXACT} x 2, {RANK_TYPED} x 3", stock(product(EXACT, 2), product(RANK_TYPED, 3)))
    assert _option_codes(c) == dealer_alone, ("dealer multi", _option_codes(c), dealer_alone)

    _as_staff(c)
    c.say(f"{RANK_TYPED} x 3", stock(product(RANK_TYPED, 3)))
    assert _option_codes(c) == dealer_alone, ("staff alone", _option_codes(c), dealer_alone)
    c.state = None
    c.say(f"{EXACT} x 2, {RANK_TYPED} x 3", stock(product(EXACT, 2), product(RANK_TYPED, 3)))
    assert _option_codes(c) == dealer_alone, ("staff multi", _option_codes(c), dealer_alone)


# --------------------------------------------------------------------------- AC-16 (guard)


def test_ac16_a_short_token_with_more_than_three_all_parts_matches_keeps_the_which_one_list(session_factory, monkeypatch, stub_access):  # noqa: F811
    codes = ["TWC7713-SH-UF", "TWC7713-SH-UP", "BRC7713-SH", "ELP7713", "MWC7713-RD-UF"]
    c = _console(session_factory, monkeypatch, stub_access, codes)
    text = c.say("7713 stock", stock(product("7713")))
    assert sorted(_option_codes(c)) == sorted(codes), (_option_codes(c), text)
    assert "which one?" in text.lower(), text
    assert "Did you mean" not in text and R not in text, text


# --------------------------------------------------------------------------- AC-24


def test_ac24_srtwt6855_shape_a_same_company_close_code_is_offered(session_factory, monkeypatch, stub_access):  # noqa: F811
    typed, close = "SRTWT6855-GY", "SRTWT6855-GR"  # trigram 0.71
    c = _console(session_factory, monkeypatch, stub_access, [close], **_facts(close))
    text = c.say(f"{typed} got stock?", stock(product(typed)))
    assert f"Couldn't find {typed}. Did you mean" in text, text
    assert close in _dym_tail(text), text
    assert R not in text and "(product)" not in text, text


def test_ac24_the_same_close_code_only_in_another_company_gives_the_refer_line(session_factory, monkeypatch, stub_access):  # noqa: F811
    typed, close = "SRTWT6855-GY", "SRTWT6855-GR"
    c = _console(session_factory, monkeypatch, stub_access, [])
    other = _seed_company(session_factory, name="ZZT Other Co R2")
    _seed_product(session_factory, company_id=other, code=close)
    text = c.say(f"{typed} got stock?", stock(product(typed)))
    assert R in text and "Did you mean" not in text, text
    assert not _word(close, text) and close not in str(c.stored_question), (text, c.stored_question)


# --------------------------------------------------------------------------- AC-25


def test_ac25_srt65_shape_every_missed_code_is_named_with_its_offer_beside_a_which_one_list(session_factory, monkeypatch, stub_access):  # noqa: F811
    """SRT6537-BL and SRT6532-BL are misses (each 0.54 from a catalogue code); SRT6534 opens a which-one list."""
    codes = ["SRT6534-BL", "SRT6534-WH", "SRT6537-GR"]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))
    text = c.say(
        "SRT6537-BL X10 / SRT6532-BL X10 / SRT6534 X10",
        stock(product("SRT6537-BL", 10), product("SRT6532-BL", 10), product("SRT6534", 10)),
    )
    assert "which one?" in text.lower() and "SRT6534-BL" in text and "SRT6534-WH" in text, text
    assert "Couldn't find SRT6537-BL. Did you mean" in text, text
    assert "Couldn't find SRT6532-BL. Did you mean" in text, text
    assert R not in text, text


# --------------------------------------------------------------------------- AC-26


def test_ac26_mwc7627_shape_missing_part_beside_an_answered_code_is_offered_with_qty(session_factory, monkeypatch, stub_access):  # noqa: F811
    found, close = "MBF97513", "MWC7627-SH-S10"  # MWC7627-S10 vs MWC7627-SH-S10: trigram 0.71
    c = _console(session_factory, monkeypatch, stub_access, [found, close], **_facts(found, close))
    text = c.say(
        "MBF97513 X 2 STOCK / MWC7627-S10 X 3 STOCK", stock(product(found, 2), product("MWC7627-S10", 3))
    )
    assert f"{found} x 2: {TICK} Got stock." in text, text
    assert f"Couldn't find MWC7627-S10. Did you mean {close}?" in text, text
    assert c.say("yes", _yes()) == f"{close} x 3: {TICK} Got stock."


# --------------------------------------------------------------------------- AC-27


def test_ac27_srtk39ss_shape_the_miss_among_found_codes_gets_its_offer(session_factory, monkeypatch, stub_access):  # noqa: F811
    codes = ["SRTKT39SS", "SRTKT1631SS", "SRTKT38SS"]  # SRTK39SS vs SRTKT39SS: trigram 0.58
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))
    text = c.say(
        "SRTK39SS / SRTKT1631SS / SRTKT38SS / 5 UNITS",
        stock(product("SRTK39SS", 5), product("SRTKT1631SS", 5), product("SRTKT38SS", 5)),
    )
    assert f"SRTKT1631SS x 5: {TICK} Got stock." in text and f"SRTKT38SS x 5: {TICK} Got stock." in text, text
    assert "Couldn't find SRTK39SS. Did you mean" in text, text
    assert "SRTKT39SS" in _dym_tail(text) and "SRTKT39SS" in _option_codes(c), (text, c.stored_question)
    assert R not in text, text


# --------------------------------------------------------------------------- AC-29


def test_ac29_cb2515ss_shape_eta_ask_offers_close_codes_and_a_number_answers_incoming(session_factory, monkeypatch, stub_access):  # noqa: F811
    codes = ["CB2516SS", "CB2513SS", "CB2515S-GR"]  # 0.50, 0.50, 0.58 against CB2515SS
    c = _console(session_factory, monkeypatch, stub_access, codes, **{k.replace("-", "_"): Stock(eta=ETA) for k in codes})
    text = c.say("CB2515SS check ETA", _eta_ask("CB2515SS"))
    assert "Couldn't find CB2515SS. Did you mean" in text, text
    assert R not in text, text
    offered = _option_codes(c)
    assert 1 <= len(offered) <= 3 and set(offered) <= set(codes), offered
    after = c.say("1", _eta_reply(reference_positions=[1], open_question_answer=answer("pick", picked=[1])))
    assert f"{offered[0]}: {TICK} {ETA_TEXT}" in after, after


# --------------------------------------------------------------------------- AC-30 (guard)


def test_ac30_srtwt1866ss_shape_keeps_the_numbered_list_of_three(session_factory, monkeypatch, stub_access):  # noqa: F811
    """`Srtwt1866ss x ss3 / Have stock`: the typed code is a prefix of three catalogue codes (shape guessed from the
    UAC's "numbered list of 3"; crew's real rows may differ)."""
    codes = ["SRTWT1866SS-CR", "SRTWT1866SS-BL", "SRTWT1866SS-GR"]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))
    text = c.say("Srtwt1866ss x ss3 / Have stock", stock(product("Srtwt1866ss")))
    assert sorted(_option_codes(c)) == sorted(codes), (_option_codes(c), text)
    for i in (1, 2, 3):
        assert f"{i}. " in text, text
    assert "4. " not in text and R not in text, text
