"""CHATBOT-SET-CODES: the owner's hand test FAIL (13 Nov), frozen.

Sets QWC604-P-RL (QWCX604-P-RL, QWCY604) and QWC604-S-RL (QWCX604-S-RL, QWCY604), stock 100, parts with NO
description. Covers the dealer Console contact and staff where the reply differs.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import text as sql_text

from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _option_codes
from tests.chatbot.test_code_match_sets import _pick
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_set_codes import CISTERN, _who, _world

pytestmark = pytest.mark.usefixtures("stub_access")

P_RL, S_RL = "QWC604-P-RL", "QWC604-S-RL"
SETS = {P_RL: ["QWCX604-P-RL", CISTERN], S_RL: ["QWCX604-S-RL", CISTERN]}
S_PAN = "QWCX604-S-RL"


def _owner_world(session_factory, monkeypatch, stub_access) -> Console:  # noqa: F811
    c = _world(session_factory, monkeypatch, stub_access, SETS)
    db = session_factory()
    try:  # no description at all, the dev catalogue's shape
        db.execute(sql_text("UPDATE products SET description = NULL WHERE product_code = ANY(:c)"), {"c": [m for ms in SETS.values() for m in ms]})
        db.commit()
    finally:
        db.close()
    return c


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_t1_the_owners_four_turns_answer_each_part_at_the_typed_quantity(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    offer = c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    assert "Did you mean" in offer, offer
    offered = _option_codes(c)
    assert {P_RL, S_RL} <= set(offered), offered
    position = offered.index(S_RL) + 1
    text = c.say(str(position), _pick(position))
    assert "How many units for each?" not in text, text
    if who == "dealer":
        for code in (S_PAN, CISTERN):
            assert f"{code} x 2: {TICK} Got stock." in _lines(text), (code, text)
    else:
        assert f"*Set {S_RL}*" in text, text
        for code in (S_PAN, CISTERN):
            assert f"*Product Code:* {code}" in text, (code, text)


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_t2_one_number_after_how_many_units_applies_to_every_part(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    _who(c, who)
    asked = c.say("QWC604-S-RL stock", stock(product(S_RL)))
    if who == "staff":
        assert "How many units for each?" not in asked or c.stored_question, asked
    if "How many units for each?" not in asked:
        pytest.skip("this contact is not asked per part: nothing to answer with one number")
    text = c.say("4", reply(demand_qty=4, open_question_answer=answer("all", qty_for_all=4)))
    for code in (S_PAN, CISTERN):
        assert f"{code} x 4: {TICK} Got stock." in _lines(text), (code, text)


# T3 removed (crew 14 Nov 10:52): the " - " on a "How many units for each?" line is the owner's round-6 fill-in
# blank before the quantity (test_stock_ask_ht26_r9_r6_all_point_form), kept as is.


# A number bound by POSITION to a line of the bot's own question applies to every part it listed.
_POSITION_SHAPES = [([(pos, None, 4)], d) for pos in (1, 2) for d in (True, False)]


@pytest.mark.parametrize(
    "items,with_demand",
    _POSITION_SHAPES,
    ids=[f"pos{i[0][0]}-{'demand_qty' if d else 'no_demand_qty'}" for i, d in _POSITION_SHAPES],
)
def test_t2b_a_one_number_bound_by_position_applies_to_every_part_listed(session_factory, monkeypatch, stub_access, items, with_demand):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    asked = c.say("QWC604-S-RL stock", stock(product(S_RL)))
    assert "How many units for each?" in asked, asked
    extra = {"demand_qty": 4} if with_demand else {}
    text = c.say("4", reply(open_question_answer=answer("fill", items=items), **extra))
    for code in (S_PAN, CISTERN):
        assert f"{code} x 4: {TICK} Got stock." in _lines(text), (code, text)


@pytest.mark.parametrize("with_demand", [False, True], ids=["no_demand_qty", "demand_qty"])
def test_t2b_lock_a_number_bound_by_code_fills_only_that_line(session_factory, monkeypatch, stub_access, with_demand):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    c.say("QWC604-S-RL stock", stock(product(S_RL)))
    extra = {"demand_qty": 4} if with_demand else {}
    text = c.say("QWCY604 4", reply(open_question_answer=answer("fill", items=[(None, CISTERN, 4)]), **extra))
    assert f"{S_PAN} x 4" not in text, ("the number spread to the other part", text)
    assert f"{CISTERN} x 4: {TICK} Got stock." in _lines(text), text


def test_t2c_lock_a_fill_by_code_with_no_entity_fills_only_that_line(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    c.say("QWC604-S-RL stock", stock(product(S_RL)))
    text = c.say("8 for QWCY604", reply(open_question_answer=answer("fill", items=[(None, CISTERN, 8)])))
    assert f"{S_PAN} x 8" not in text, ("the number spread to the other part", text)
    assert any(CISTERN in line and "8" in line for line in _lines(text)), text


@pytest.mark.parametrize("with_demand", [False, True], ids=["no_demand_qty", "demand_qty"])
def test_t2c_t2e_lock_a_code_typed_with_a_number_fills_only_that_line(session_factory, monkeypatch, stub_access, with_demand):  # noqa: F811
    """STOCK-QTY-PARTIAL-FILL R1: the user typed the code (`QWCY604 8`): only that line is filled. The earlier t2c
    shape (a fill with no typed entity) is what t2b now spreads, so these carry the typed product entity."""
    c = _owner_world(session_factory, monkeypatch, stub_access)
    c.say("QWC604-S-RL stock", stock(product(S_RL)))
    extra = {"demand_qty": 8} if with_demand else {}
    text = c.say(
        "8 for QWCY604",
        reply(entities=[product(CISTERN, 8)], open_question_answer=answer("fill", items=[(None, CISTERN, 8)]), **extra),
    )
    assert f"{S_PAN} x 8" not in text, ("the number spread to the other part", text)
    assert any(CISTERN in line and "8" in line for line in _lines(text)), text


def test_t2d_lock_a_number_typed_beside_one_part_fills_only_that_line(session_factory, monkeypatch, stub_access):  # noqa: F811
    """Reviewer 14 Nov: "QWCY604 8" answering the per-part question, read as the part plus demand_qty, fills only the
    QWCY604 line (STOCK-QTY-PARTIAL-FILL owner rule R1); the other part is not answered at 8."""
    c = _owner_world(session_factory, monkeypatch, stub_access)
    asked = c.say("QWC604-S-RL stock", stock(product("QWC604-S-RL")))
    assert "How many units for each?" in asked, asked
    text = c.say("QWCY604 8", stock(product(CISTERN), demand_qty=8))
    assert "QWCX604-S-RL x 8" not in text, text


# --------------------------------------------------------------------------- L1: a code plus its completing word keeps the typed quantity


def test_l1_dealer_code_plus_completing_word_answers_each_part_at_the_typed_quantity(session_factory, monkeypatch, stub_access):  # noqa: F811
    from tests.chatbot._turn_helpers import entity
    from tests.chatbot.test_set_codes import _exact_world

    c = _exact_world(session_factory, monkeypatch, stub_access)
    text = c.say("QWC605-RL soft x 1", stock(product("QWC605-RL", 1), entity("soft", hint="category")))
    assert "How many units for each?" not in text, text
    for code in ("QWCX605-RL-SOFT", CISTERN):
        assert f"{code} x 1: {TICK} Got stock." in _lines(text), (code, text)


# --------------------------------------------------------------------------- reviewer: quantity to the wrong set, mixed list


def test_r1a_a_quantity_typed_for_a_bare_family_word_never_lands_on_another_set(session_factory, monkeypatch, stub_access):  # noqa: F811
    from tests.chatbot.test_set_codes import _exact_world

    c = _exact_world(session_factory, monkeypatch, stub_access)
    text = c.say("QWC605 x 3, QWC605-RL-NEW", stock(product("QWC605", 3), product("QWC605-RL-NEW")))
    assert f"QWCX605-RL-NEW x 3: {TICK} Got stock." not in _lines(text), ("NEW was answered at the other word's x 3", text)


def test_r1b_each_set_on_a_two_set_message_gets_its_own_quantity(session_factory, monkeypatch, stub_access):  # noqa: F811
    """The cistern is shared by the sets, so only the sets' own pans are pinned."""
    from tests.chatbot._turn_helpers import entity
    from tests.chatbot.test_set_codes import _exact_world

    c = _exact_world(session_factory, monkeypatch, stub_access)
    text = c.say(
        "QWC605-RL soft x 1, QWC605-RL-NEW x 2",
        stock(product("QWC605-RL", 1), entity("soft", hint="category"), product("QWC605-RL-NEW", 2)),
    )
    assert "How many units for each?" not in text, text
    assert f"QWCX605-RL-SOFT x 1: {TICK} Got stock." in _lines(text), text
    assert f"QWCX605-RL-NEW x 2: {TICK} Got stock." in _lines(text), text


def test_t3_lock_a_number_bound_to_line_1_of_a_mixed_list_fills_only_line_1(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _world(session_factory, monkeypatch, stub_access, SETS, extra=["QWX7700"])
    asked = c.say("QWC604-S-RL stock, QWX7700 stock", stock(product(S_RL), product("QWX7700")))
    assert "How many units for each?" in asked and "3." in asked, asked
    text = c.say("4", reply(demand_qty=4, open_question_answer=answer("fill", items=[(1, None, 4)])))
    assert f"{S_PAN} x 4: {TICK} Got stock." in _lines(text), text
    assert f"{CISTERN} x 4" not in text and "QWX7700 x 4" not in text, ("the number spread past line 1", text)
