"""CHATBOT-CLOSE-CODES round 12: red tests from the crew live pass on 00ac7030 (steps 2, 6, 8, 9).

UAC: `documentation/plans/chatbot/chatbot-close-codes-acceptance-criteria.md` (AC-6, AC-9, AC-10, AC-36, AC-38).
Same harness as `test_close_codes_dealer_round3.py`: `engine.run_turn` over seeded Postgres rows in a blank schema, the
parser verdict and the tool reads stubbed. "Dealer" is the console's default availability-only contact. Codes are
made-up catalogue-shaped codes (the ZZ* families stand in for the live ones); no customer, phone or price appears.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot._turn_helpers import entity
from tests.chatbot.test_close_codes_dealer_round3 import (
    CLOSE3,
    HOW_MANY,
    TYPO3,
    R,
    _facts,
    _position_of,
    _who,
    _yes,
)
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes, _pick_positions

from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")


# --------------------------------------------------------------------------- F1 (live step 2)
#
# One message: a found code with no quantity (the how-many) and a miss with three close codes (the offer). The dealer
# picks "1" from the offer: one "How many units for each?" over the picked code and the found code. "3" then answers
# both at 3, whichever way the parser reads the "3".


def _how_many_and_three_close(session_factory, monkeypatch, stub_access) -> tuple[Console, str]:  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, CLOSE3, **_facts(HOW_MANY, *CLOSE3))
    text = c.say(f"{HOW_MANY} stock, {TYPO3} stock", stock(product(HOW_MANY), product(TYPO3)))
    assert f"How many units of {HOW_MANY}?" in text, text
    assert f"Couldn't find {TYPO3}. Did you mean:" in text, text
    return c, text


def _code_at(c: Console, position: int) -> str:
    for o in (c.stored_question or {}).get("options") or []:
        if int(o.get("position") or 0) == position:
            return str(o.get("code"))
    raise AssertionError(f"no option at {position}: {c.stored_question}")


def _three(variant: str, picked: str) -> dict[str, Any]:
    if variant == "demand_qty":
        return reply(demand_qty=3)
    if variant == "demand_qty_and_carried_entity":
        return reply(demand_qty=3, entities=[{**product(picked), "current_message": False, "quantity": 3}])
    return reply(open_question_answer=answer("fill", items=[(1, None, 3)]))


@pytest.mark.parametrize("variant", ["demand_qty", "demand_qty_and_carried_entity", "fill_answer"])
def test_f1_a_pick_then_a_number_answers_the_picked_code_and_the_found_code(session_factory, monkeypatch, stub_access, variant):  # noqa: F811
    c, _ = _how_many_and_three_close(session_factory, monkeypatch, stub_access)
    picked = _code_at(c, 1)
    assert picked in CLOSE3, (picked, c.stored_question)
    asked = c.say("1", _pick_positions(1))
    assert "How many units for each?" in asked, asked
    assert picked in asked and HOW_MANY in asked, f"the how-many does not list both codes: {asked!r}"
    text = c.say("3", _three(variant, picked))
    assert f"{picked} x 3" in text, f"the picked code was not answered at 3: {text!r}"
    assert f"{HOW_MANY} x 3" in text, f"the found code was not answered at 3: {text!r}"
    assert R not in text, text


# --------------------------------------------------------------------------- F2 (live step 8)
#
# A family of four finishes whose grey row stores its finish as "Matt Gray" (not the word typed). "ZZSH2623 grey stock?"
# with the parser's pick ZZSH2623-GRY is offered with the pick first (AC-36), never "None with finish or colour grey";
# "yes" then answers ZZSH2623-GRY. A plain which-one list answered "yes" is asked again, never referred.

FAMILY = {"ZZSH2623-GRY": "Matt Gray", "ZZSH2623-WH": "White", "ZZSH2623-BK": "Matt Black", "ZZSH2623-GM": "Gun Metal"}
GRY = "ZZSH2623-GRY"


def _family_console(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    from app.models.product_spec import ProductSpecifications

    codes = list(FAMILY)
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(*codes))
    db = session_factory()
    try:
        for code, finish in FAMILY.items():
            db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=c.uuid_of[code],
                                         values={"finish": {"value": finish}}))
        db.commit()
    finally:
        db.close()
    return c


def _grey_spec() -> dict[str, Any]:
    return {**entity("grey", "specification"), "spec_key": "finish", "spec_value": "grey"}


def test_f2_a_colour_word_the_stored_finish_does_not_spell_offers_the_parsers_pick_first(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _family_console(session_factory, monkeypatch, stub_access)
    text = c.say("ZZSH2623 grey stock?", stock({**product("ZZSH2623"), "canonical_code": GRY}, _grey_spec()))
    assert "None with" not in text, f"a 'None with finish or colour' line: {text!r}"
    assert f"Did you mean {GRY}?" in text or f"1. {GRY}" in text, f"{GRY} is not offered first: {text!r}"
    assert TICK not in text and "Got stock" not in text, f"answered on the parser's pick: {text!r}"
    assert _option_codes(c) and _position_of(c, GRY) == 1, c.stored_question
    after = c.say("yes", _yes())
    assert GRY in after, after
    assert f"{GRY} x" in after or f"How many units of {GRY}?" in after, f"'yes' did not answer {GRY}: {after!r}"
    assert R not in after and "Couldn't find" not in after, after
    for other in set(FAMILY) - {GRY}:
        assert other not in after, (other, after)


def test_f2_yes_over_a_plain_which_one_list_asks_it_again_never_refers(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _family_console(session_factory, monkeypatch, stub_access)
    first = c.say("ZZSH2623 stock?", stock({**product("ZZSH2623"), "canonical_code": None}))
    assert "which one?" in first.lower() and set(_option_codes(c)) == set(FAMILY), (first, c.stored_question)
    after = c.say("yes", _yes())
    assert R not in after, f"'yes' over a which-one list was referred: {after!r}"
    assert "which one?" in after.lower(), after
    for code in FAMILY:
        assert code in after, (code, after)
    assert set(_option_codes(c)) == set(FAMILY), c.stored_question


# --------------------------------------------------------------------------- F4 (live steps 6, 9)
#
# A code with a space inside it ("ZZUB668-BACK INLET") typed with a typo in its last word: the miss line names what was
# typed, never the folded token ("ZZUB668BACK"). Parsed with and without the parser's pick.

INLET, OUTLET = "ZZUB668-BACK INLET", "ZZUB668-BACK OUTLET"


@pytest.mark.parametrize("who", ["dealer", "staff"])
@pytest.mark.parametrize("pick", [None, INLET], ids=["no_pick", "inlet_picked"])
def test_f4_a_typo_in_a_spaced_code_names_the_typed_code_in_the_miss_line(session_factory, monkeypatch, stub_access, who, pick):  # noqa: F811
    raw = "ZZUB668-BACK INLT"
    c = _who(session_factory, monkeypatch, stub_access, who, [INLET, OUTLET])
    text = c.say(f"{raw} stock", stock({**product(raw), "canonical_code": pick}))
    assert "Couldn't find" in text and raw in text.upper(), f"the miss line does not name {raw!r}: {text!r}"
    assert "ZZUB668BACK" not in text.upper(), f"the miss line names the folded token: {text!r}"
    if who == "dealer" and pick is None:
        # Lead ruling, round 12: with no parser pick the dealer still gets the offer of the close code (AC-6), never a
        # bare miss with the refer line while a close code exists.
        assert f"Couldn't find {raw}" in text, f"the miss line does not name {raw!r} as typed: {text!r}"
        assert "Did you mean" in text and INLET in text.split("Did you mean", 1)[1], f"no offer of {INLET}: {text!r}"
        assert R not in text, f"referred while a close code exists: {text!r}"


@pytest.mark.parametrize("pick", [None, INLET], ids=["no_pick", "inlet_picked"])
def test_f4_a_letter_added_to_a_spaced_code_with_a_quantity_names_the_typed_code(session_factory, monkeypatch, stub_access, pick):  # noqa: F811
    raw = "ZZUB668-BACK INLETT"
    c = _who(session_factory, monkeypatch, stub_access, "dealer", [INLET, OUTLET])
    text = c.say(f"{raw} x 2 stock", stock({**product(raw, 2), "canonical_code": pick}))
    assert "Couldn't find" in text and raw in text.upper(), f"the miss line does not name {raw!r}: {text!r}"
    assert "ZZUB668BACK" not in text.upper(), f"the miss line names the folded token: {text!r}"
    if pick is None:
        # Lead ruling, round 12: the offer of the close code (AC-6), never a bare miss with the refer line; "yes"
        # then answers INLET at the typed 2.
        assert f"Couldn't find {raw}" in text, f"the miss line does not name {raw!r} as typed: {text!r}"
        assert "Did you mean" in text and INLET in text.split("Did you mean", 1)[1], f"no offer of {INLET}: {text!r}"
        assert R not in text, f"referred while a close code exists: {text!r}"
        after = c.say("yes", _yes())
        assert f"{INLET} x 2" in after, f"'yes' did not answer {INLET} at 2: {after!r}"
        assert R not in after, after
