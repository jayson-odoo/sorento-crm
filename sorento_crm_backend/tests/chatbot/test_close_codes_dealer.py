"""CHATBOT-CLOSE-CODES: a dealer gets up to 3 close codes for every code it typed that is not found.

UAC: `documentation/plans/chatbot/chatbot-close-codes-acceptance-criteria.md` (AC-1..AC-5, AC-17, AC-18, AC-22);
behaviour card `CARD-chatbot-close-codes-13nov.md` (rules C1, C7). AC-6, AC-9..AC-16 and AC-21 wait on owner answers.

Same harness as `test_code_match_dealer_offers.py`: `engine.run_turn` over seeded Postgres rows in a blank schema
(real engine, real resolver, real stock decision; the parser verdict and the tool reads are stubbed). "Dealer" is the
console's default contact (availability-only). Every code below is a made-up catalogue-shaped code; no customer,
phone or price appears.

Trigram figures in the comments are `similarity()` of the lowercase, separator-stripped forms, measured in Postgres;
the tier-isolating ones are re-measured in the test that relies on them.

Contract assumption for AC-22 (the UAC names the fields in words only): each `code_candidates` entry is
`{"kind": "code_candidates", "typed": <token>, "candidates": [{"code", "tier", "similarity", "all_parts": bool}, ...]
in offered order, "outcome": "offered" | "no_candidate"}`, one entry per missed code and none for a code that was
found. The all-parts flag is assumed to be the per-candidate boolean key `all_parts`. Extra keys are tolerated.
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.services.chatbot.turn.task import REFER_TO_SALESMAN

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot.test_code_match_dealer_offers import (
    TICK,
    Console,
    _console,
    _hide,
    _option_codes,
    _pick_positions,
    _word,
)
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_engine_company_scope import _seed_company, _seed_product

pytestmark = pytest.mark.usefixtures("stub_access")

#: A code typed exactly, answered directly beside the miss.
EXACT = "ZQX5521"

#: Letters-only typo of a letters+digits code: the digits dropped (card example 1 shape). Parts QMR, KX, VB are all
#: held in order by both codes below (trigram 0.43 each).
LT_TYPED = "QMRKXVB"
LT_CODE = "QMR7731-KX-VB"
LT_SIBLING = "QMR4410-KX-VB"

#: Letters-only typo by one letter of a letters-only code (trigram 0.50).
TRI_TYPED, TRI_CODE = "ABCDF", "ABCDE"

#: Letters-only token that is a lone PREFIX of one code / sits INSIDE one longer code. Both codes sit below the
#: resolver's trigram floor (0.30) against the token (0.26 and 0.21), so only a prefix/substring read reaches them.
PS_TYPED = "BRKQM"
PREFIX_CODE = "BRKQM-8354-150-20-NEW"
INSIDE_CODE = "ZXBRKQM-150"

#: Letters-only token with no code anywhere near it.
NONE_TYPED = "QQXZW"

TRIGRAM_FLOOR = 0.30


def _facts(*codes: str) -> dict[str, Stock]:
    return {c.replace("-", "_"): Stock(on_hand=100) for c in codes}


def _sim(session_factory, typed: str, code: str) -> float:
    db = session_factory()
    try:
        return float(
            db.execute(
                sql_text("SELECT similarity(lower(:t), regexp_replace(lower(:c), '[^a-z0-9]', '', 'g'))"),
                {"t": typed, "c": code},
            ).scalar()
        )
    finally:
        db.close()


def _carried_qty(c: Console) -> list[Any]:
    """Every quantity the stored pick carries: its own `stock_qty` and each group's `qty`."""
    payload = (c.stored_question or {}).get("payload") or {}
    return [payload.get("stock_qty"), *[g.get("qty") for g in payload.get("groups") or []]]


def _yes():
    return reply(is_affirmative=True, open_question_answer=answer("yes"))


def _assert_not_answered(text: str) -> None:
    assert TICK not in text and "Got stock" not in text, f"answered on a guess: {text!r}"
    assert "How many units of" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"


# --------------------------------------------------------------------------- AC-1


@pytest.mark.parametrize(("typed", "code"), [(LT_TYPED, LT_CODE), (TRI_TYPED, TRI_CODE)])
def test_ac1_dealer_letters_only_typo_beside_an_exact_code_is_offered_with_its_quantity(session_factory, monkeypatch, stub_access, typed, code):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [EXACT, code], **_facts(EXACT, code))
    text = c.say(f"{EXACT} x 2, {typed} x 1", stock(product(EXACT, 2), product(typed, 1)))
    assert f"{EXACT} x 2: {TICK} Got stock." in text, text
    assert f"Couldn't find {typed}. Did you mean {code}?" in text, f"the letters-only miss was dropped: {text!r}"
    assert REFER_TO_SALESMAN not in text, text
    assert _option_codes(c) == [code], c.stored_question
    assert 1 in _carried_qty(c), f"quantity 1 was not carried: {c.stored_question}"

    after = c.say("yes", _yes())
    assert after == f"{code} x 1: {TICK} Got stock.", after


# --------------------------------------------------------------------------- AC-2


def test_ac2_dealer_letters_only_lone_prefix_of_one_code_is_offered_that_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    assert _sim(session_factory, PS_TYPED, PREFIX_CODE) < TRIGRAM_FLOOR  # only a prefix read reaches it
    c = _console(session_factory, monkeypatch, stub_access, [PREFIX_CODE], **_facts(PREFIX_CODE))
    text = c.say(f"{PS_TYPED} x 1", stock(product(PS_TYPED, 1)))
    assert f"Couldn't find {PS_TYPED}. Did you mean {PREFIX_CODE}?" in text, text
    assert REFER_TO_SALESMAN not in text, text
    _assert_not_answered(text)
    assert _option_codes(c) == [PREFIX_CODE], c.stored_question
    assert 1 in _carried_qty(c), c.stored_question


# --------------------------------------------------------------------------- AC-3


def test_ac3_dealer_letters_only_token_inside_one_longer_code_is_offered_that_code(session_factory, monkeypatch, stub_access):  # noqa: F811
    assert _sim(session_factory, PS_TYPED, INSIDE_CODE) < TRIGRAM_FLOOR  # only a substring read reaches it
    c = _console(session_factory, monkeypatch, stub_access, [INSIDE_CODE], **_facts(INSIDE_CODE))
    text = c.say(f"{PS_TYPED} x 1", stock(product(PS_TYPED, 1)))
    assert f"Couldn't find {PS_TYPED}. Did you mean {INSIDE_CODE}?" in text, text
    assert REFER_TO_SALESMAN not in text, text
    _assert_not_answered(text)
    assert _option_codes(c) == [INSIDE_CODE], c.stored_question


# --------------------------------------------------------------------------- AC-4


def test_ac4_dealer_two_letters_only_typos_each_get_an_offer_numbered_on_and_1_and_2_answers_both(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(
        session_factory, monkeypatch, stub_access, [EXACT, TRI_CODE, LT_CODE], **_facts(EXACT, TRI_CODE, LT_CODE)
    )
    text = c.say(
        f"{EXACT} x 2, {TRI_TYPED} x 1, {LT_TYPED} x 3",
        stock(product(EXACT, 2), product(TRI_TYPED, 1), product(LT_TYPED, 3)),
    )
    assert f"{EXACT} x 2: {TICK} Got stock." in text, text
    assert text.count("Did you mean") == 2, text
    assert f"Couldn't find {TRI_TYPED}. Did you mean" in text, text
    assert f"Couldn't find {LT_TYPED}. Did you mean" in text, text
    assert f"1. {TRI_CODE}" in text and f"2. {LT_CODE}" in text, text
    assert REFER_TO_SALESMAN not in text, text
    assert _option_codes(c) == [TRI_CODE, LT_CODE], c.stored_question
    assert [o["position"] for o in c.stored_question["options"]] == [1, 2], c.stored_question

    both = c.say("1 and 2", _pick_positions(1, 2))
    assert f"{TRI_CODE} x 1: {TICK} Got stock." in both, both
    assert f"{LT_CODE} x 3: {TICK} Got stock." in both, both


# --------------------------------------------------------------------------- AC-5


def test_ac5_the_offer_inside_a_multi_code_ask_equals_the_offer_alone(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(
        session_factory, monkeypatch, stub_access, [EXACT, LT_CODE, LT_SIBLING], **_facts(EXACT, LT_CODE, LT_SIBLING)
    )
    alone_text = c.say(f"{LT_TYPED} x 1", stock(product(LT_TYPED, 1)))
    alone = _option_codes(c)
    assert set(alone) == {LT_CODE, LT_SIBLING}, (alone, alone_text)

    c.state = None
    text = c.say(f"{EXACT} x 2, {LT_TYPED} x 1", stock(product(EXACT, 2), product(LT_TYPED, 1)))
    assert f"{EXACT} x 2: {TICK} Got stock." in text, text
    assert f"Couldn't find {LT_TYPED}. Did you mean" in text, text
    assert _option_codes(c) == alone, (_option_codes(c), alone, text)


# --------------------------------------------------------------------------- AC-17

#: tier -> (typed, a close code that tier reaches). Trigram: one wrong letter (0.50). Prefix / substring: below the
#: trigram floor, so only that read reaches them. All-parts: holds every typed part in order (QMR, KX, VB).
TIERS = {
    "trigram": (TRI_TYPED, TRI_CODE),
    "prefix": (PS_TYPED, PREFIX_CODE),
    "substring": (PS_TYPED, INSIDE_CODE),
    "all_parts": (LT_TYPED, LT_CODE),
}


@pytest.mark.parametrize("shape", ["alone", "multi"])
@pytest.mark.parametrize("tier", list(TIERS))
def test_ac17_a_close_code_only_in_another_company_is_never_offered_to_a_dealer(session_factory, monkeypatch, stub_access, tier, shape):  # noqa: F811
    typed, code = TIERS[tier]
    c = _console(session_factory, monkeypatch, stub_access, [EXACT], **_facts(EXACT))
    other = _seed_company(session_factory, name=f"ZZT Other Co Close {tier}")
    _seed_product(session_factory, company_id=other, code=code)
    if shape == "alone":
        text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    else:
        text = c.say(f"{EXACT} x 2, {typed} x 1", stock(product(EXACT, 2), product(typed, 1)))
        assert f"{EXACT} x 2: {TICK} Got stock." in text, text
    assert "Did you mean" not in text, text
    assert not _word(code, text), text
    assert code not in str(c.stored_question), c.stored_question


# --------------------------------------------------------------------------- AC-18


def _make_unofferable(session_factory, code: str, how: str) -> None:
    if how == "discontinued":
        db = session_factory()
        try:
            db.execute(sql_text("UPDATE products SET is_discontinued = true WHERE product_code = :c"), {"c": code})
            db.commit()
        finally:
            db.close()
    elif how == "placeholder":
        _hide(session_factory, code, "product_not_searchable")  # `is_searchable` false is the placeholder flag
    else:
        _hide(session_factory, code, "inactive")


#: path -> (typed, the only close code, whether an exact code rides along).
PATHS = {
    "letters_only": (LT_TYPED, LT_CODE, False),
    "letters_only_multi": (LT_TYPED, LT_CODE, True),
    "prefix": (PS_TYPED, PREFIX_CODE, False),
    "substring_multi": (PS_TYPED, INSIDE_CODE, True),
}


@pytest.mark.parametrize("path", list(PATHS))
@pytest.mark.parametrize("how", ["inactive", "discontinued", "placeholder"])
def test_ac18_an_inactive_discontinued_or_placeholder_code_is_never_offered(session_factory, monkeypatch, stub_access, how, path):  # noqa: F811
    typed, code, multi = PATHS[path]
    facts = {**_facts(EXACT), code.replace("-", "_"): Stock(on_hand=100, discontinued=how == "discontinued")}
    c = _console(session_factory, monkeypatch, stub_access, [EXACT, code], **facts)
    _make_unofferable(session_factory, code, how)
    if multi:
        text = c.say(f"{EXACT} x 2, {typed} x 1", stock(product(EXACT, 2), product(typed, 1)))
        assert f"{EXACT} x 2: {TICK} Got stock." in text, text
    else:
        text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert "Did you mean" not in text, text
    assert not _word(code, text), text
    assert code not in str(c.stored_question), c.stored_question


# --------------------------------------------------------------------------- AC-22


def _by_typed(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        out.setdefault(str(e.get("typed", "")).upper(), []).append(e)
    return out


def _assert_offered_entry(entry: dict[str, Any], offered: list[str]) -> list[dict[str, Any]]:
    assert entry.get("outcome") == "offered", entry
    rows = entry.get("candidates")
    assert isinstance(rows, list) and rows, entry
    assert [str(r.get("code")) for r in rows][: len(offered)] == offered, (rows, offered)
    for r in rows:
        assert r.get("tier"), r
        assert isinstance(r.get("similarity"), (int, float)), r
        assert isinstance(r.get("all_parts"), bool), f"no all-parts flag on the candidate: {r}"
    return rows


def test_ac22_a_letters_only_miss_alone_writes_one_offered_entry_with_the_all_parts_flag(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [LT_CODE], **_facts(LT_CODE))
    c.say(f"{LT_TYPED} x 1", stock(product(LT_TYPED, 1)))
    entries = c.trace_entries("code_candidates")
    assert len(entries) == 1, entries
    assert str(entries[0].get("typed", "")).upper() == LT_TYPED, entries
    rows = _assert_offered_entry(entries[0], [LT_CODE])
    assert rows[0]["all_parts"] is True, rows


def test_ac22_a_multi_code_ask_writes_one_entry_per_missed_code_and_none_for_the_found_one(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [EXACT, LT_CODE], **_facts(EXACT, LT_CODE))
    c.say(
        f"{EXACT} x 2, {LT_TYPED} x 1, {NONE_TYPED} x 1",
        stock(product(EXACT, 2), product(LT_TYPED, 1), product(NONE_TYPED, 1)),
    )
    by_typed = _by_typed(c.trace_entries("code_candidates"))
    assert EXACT not in by_typed, by_typed
    assert len(by_typed.get(LT_TYPED, [])) == 1, f"the letters-only miss wrote no single entry: {by_typed}"
    assert len(by_typed.get(NONE_TYPED, [])) == 1, f"the no-candidate miss wrote no single entry: {by_typed}"
    _assert_offered_entry(by_typed[LT_TYPED][0], [LT_CODE])
    none = by_typed[NONE_TYPED][0]
    assert none.get("outcome") == "no_candidate", none
    assert not none.get("candidates"), none


@pytest.mark.parametrize("typed", ["QQXZ9917-ZZ", NONE_TYPED])
def test_ac22_a_miss_with_no_candidate_traces_no_candidate_never_answered(session_factory, monkeypatch, stub_access, typed):  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, [LT_CODE])
    c.say(f"{typed} x 1", stock(product(typed, 1)))
    entries = c.trace_entries("code_candidates")
    assert len(entries) == 1, entries
    assert str(entries[0].get("typed", "")).upper() == typed, entries
    assert entries[0].get("outcome") == "no_candidate", entries[0]
    assert not entries[0].get("candidates"), entries[0]


def test_ac22_the_all_parts_flag_is_true_for_a_code_holding_every_part_and_false_otherwise(session_factory, monkeypatch, stub_access):  # noqa: F811
    """Typed TWC8354-UF (parts TWC, 8354, UF): TWC8354-SH-UF holds every part in order, TWC8354-UP misses UF."""
    holds, misses, typed = "TWC8354-SH-UF", "TWC8354-UP", "TWC8354-UF"
    c = _console(session_factory, monkeypatch, stub_access, [holds, misses])
    c.say(f"{typed} x 3", stock(product(typed, 3)))
    offered = _option_codes(c)
    entries = c.trace_entries("code_candidates")
    assert len(entries) == 1, entries
    rows = _assert_offered_entry(entries[0], offered)
    flags = {str(r["code"]): r["all_parts"] for r in rows}
    assert flags.get(holds) is True and flags.get(misses) is False, flags
