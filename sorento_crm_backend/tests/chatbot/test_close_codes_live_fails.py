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
    return reply(demand_qty=3, entities=[{**product(picked), "current_message": False, "quantity": 3}])


# The one-item fill variant (position 1, qty 3) was removed (lead sign-off, round 12): it is structurally the
# partial fill `test_stock_qty_partial_fill` pins to one line; which line "3" is for is the parser's call (lane B).
@pytest.mark.parametrize("variant", ["demand_qty", "demand_qty_and_carried_entity"])
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
        # Lead ruling, round 12 (re-pinned): the offer of the close codes (AC-6) with INLET first, never a bare miss
        # with the refer line; "1" then answers INLET at the typed 2 ("yes" over more than one option asks again, F2).
        assert f"Couldn't find {raw}" in text, f"the miss line does not name {raw!r} as typed: {text!r}"
        assert "Did you mean" in text and INLET in text.split("Did you mean", 1)[1], f"no offer of {INLET}: {text!r}"
        assert R not in text, f"referred while a close code exists: {text!r}"
        assert _position_of(c, INLET) == 1, c.stored_question
        after = c.say("1", _pick_positions(1))
        assert f"{INLET} x 2" in after, f"'1' did not answer {INLET} at 2: {after!r}"
        assert R not in after, after


# --------------------------------------------------------------------------- owner hand test on 820f71cb (F1, live shape)
#
# Turn 1 "<found> and <miss> stock": the how-many for the found code and the offer of three close codes in one reply.
# Turn 2 a pick: "How many units for each? 1. <picked> - 2. <found> -". Turn 3 a number in the LIVE parser shape
# (entities [], no demand_qty, a one-item fill echoing a position and/or a code): the number answers BOTH lines, as
# the owner's "3" did not. Locks, as #2395's t2b/t2f locks in `test_set_codes_owner_fail.py`: a number bound by a
# code the user typed fills only that line; a position and code naming different lines fills only the code's line.

#: (picked position, the number typed): Run 1 picks "2" then "3", Run 2 picks "1" then "4".
RUNS = pytest.mark.parametrize(("pick", "n"), [(2, 3), (1, 4)], ids=["run1_pick2_then_3", "run2_pick1_then_4"])
WITH_DEMAND = pytest.mark.parametrize("with_demand", [False, True], ids=["no_demand_qty", "demand_qty"])


def _owner_turns_1_and_2(session_factory, monkeypatch, stub_access, pick: int) -> tuple[Console, str]:  # noqa: F811
    c = _console(session_factory, monkeypatch, stub_access, CLOSE3, **_facts(HOW_MANY, *CLOSE3))
    first = c.say(f"{HOW_MANY} and {TYPO3} stock", stock(product(HOW_MANY), product(TYPO3)))
    assert f"How many units of {HOW_MANY}?" in first, first
    assert f"Couldn't find {TYPO3}. Did you mean:" in first, first
    offered = [_code_at(c, p) for p in (1, 2, 3)]
    assert set(offered) <= set(CLOSE3), (offered, c.stored_question)
    for p, code in enumerate(offered, 1):
        assert f"{p}. {code}" in first, first
    picked = offered[pick - 1]
    asked = c.say(str(pick), _pick_positions(pick))
    assert "How many units for each?" in asked, asked
    assert f"1. {picked}" in asked and f"2. {HOW_MANY}" in asked, f"not '1. {picked} 2. {HOW_MANY}': {asked!r}"
    return c, picked


def _fill(items: list[tuple[Any, Any, int]], n: int, with_demand: bool) -> dict[str, Any]:
    v = reply(entities=[], demand_qty=n if with_demand else None, open_question_answer=answer("fill", items=items))
    v["open_question_answer"]["qty_for_all"] = None
    return v


@RUNS
@WITH_DEMAND
@pytest.mark.parametrize("shape", ["pos1_picked_code", "pos1_no_code", "pos2_no_code", "pos2_found_code"])
def test_owner_f1_a_number_after_the_pick_answers_both_lines(session_factory, monkeypatch, stub_access, pick, n, with_demand, shape):  # noqa: F811
    c, picked = _owner_turns_1_and_2(session_factory, monkeypatch, stub_access, pick)
    items = {
        "pos1_picked_code": [(1, picked, n)],  # the live shape: position 1 and the picked code echoed
        "pos1_no_code": [(1, None, n)],
        "pos2_no_code": [(2, None, n)],
        "pos2_found_code": [(2, HOW_MANY, n)],
    }[shape]
    text = c.say(str(n), _fill(items, n, with_demand))
    assert f"{picked} x {n}:" in text, f"the picked code was not answered at {n}: {text!r}"
    assert f"{HOW_MANY} x {n}:" in text, f"the found code was not answered at {n}: {text!r}"
    assert "How many units for each?" not in text, f"asked again: {text!r}"
    assert R not in text, text


@WITH_DEMAND
def test_owner_f1_lock_a_number_bound_by_a_typed_code_fills_only_that_line(session_factory, monkeypatch, stub_access, with_demand):  # noqa: F811
    c, picked = _owner_turns_1_and_2(session_factory, monkeypatch, stub_access, 2)
    text = c.say(f"{HOW_MANY} 3", _fill([(None, HOW_MANY, 3)], 3, with_demand))
    assert f"{picked} x 3" not in text, ("the number spread to the other line", text)
    assert f"{HOW_MANY} x 3: {TICK} Got stock." in text, text


@WITH_DEMAND
def test_owner_f1_lock_a_position_and_code_naming_different_lines_fills_only_the_codes_line(session_factory, monkeypatch, stub_access, with_demand):  # noqa: F811
    c, picked = _owner_turns_1_and_2(session_factory, monkeypatch, stub_access, 2)
    text = c.say("3", _fill([(1, HOW_MANY, 3)], 3, with_demand))
    assert f"{picked} x 3" not in text, ("the number spread to the other line", text)
    assert f"{HOW_MANY} x 3: {TICK} Got stock." in text, text
