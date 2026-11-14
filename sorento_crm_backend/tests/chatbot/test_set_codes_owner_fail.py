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


def _shape_fill_code():
    return reply(demand_qty=4, open_question_answer=answer("fill", items=[(None, CISTERN, 4)]))


def _shape_fill_position():
    return reply(demand_qty=4, open_question_answer=answer("fill", items=[(2, None, 4)]))


def _shape_entity():
    return reply(demand_qty=4, entities=[product(CISTERN, 4)])


def _shape_stock_demand():
    return stock(product(CISTERN), demand_qty=4)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "lead 14 Nov: a number the parser binds to ONE part cannot be told apart from a number typed for that part "
        "(\"QWCY604 8\") without reading the message (owner 10:07 ruling); the parser's own reading decides, "
        "recorded for the prompt work (the owner's live turn); the standard qty_for_all reading fills every part (t2)"
    ),
)
@pytest.mark.parametrize(
    "shape",
    [_shape_fill_code, _shape_fill_position, _shape_entity, _shape_stock_demand],
    ids=["fill_by_code", "fill_by_position", "entity_with_qty", "stock_with_demand_qty"],
)
def test_t2b_a_number_the_parser_binds_to_the_last_part_still_applies_to_every_part(session_factory, monkeypatch, stub_access, shape):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    asked = c.say("QWC604-S-RL stock", stock(product(S_RL)))
    assert "How many units for each?" in asked, asked
    text = c.say("4", shape())
    for code in (S_PAN, CISTERN):
        assert f"{code} x 4: {TICK} Got stock." in _lines(text), (code, text)


def test_t2c_lock_a_number_named_for_one_part_without_demand_qty_fills_only_that_line(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _owner_world(session_factory, monkeypatch, stub_access)
    c.say("QWC604-S-RL stock", stock(product(S_RL)))
    text = c.say("8 for QWCY604", reply(open_question_answer=answer("fill", items=[(None, CISTERN, 8)])))
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
