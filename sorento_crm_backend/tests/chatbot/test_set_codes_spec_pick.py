"""CHATBOT-SET-CODES C (PLAN-chatbot-set-codes-c-14nov): a spec word answering a "Did you mean".

Over "Did you mean 1. QWC604-P-RL 2. QWC604-S-RL", the parser is shown each option with the specs
the catalogue records for it, only where the offered options differ, so "S trap" can name option 2
(rule 1). A reply the parser gives no pick and only spec entities asks the same options again,
never a catalogue search (rule 3). Fake codes only.
"""
from __future__ import annotations

import dataclasses
import json
import uuid

import pytest

from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot._r9_engine_console import answer, product, reply, stock
from tests.chatbot._turn_helpers import entity
from tests.chatbot.test_code_match_dealer_offers import Console, _option_codes
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_set_codes_owner_fail import CISTERN, P_RL, S_RL, _owner_world

pytestmark = pytest.mark.usefixtures("stub_access")

P_PAN, S_PAN = "QWCX604-P-RL", "QWCX604-S-RL"


def _trap_world(session_factory, monkeypatch, stub_access, **values) -> Console:  # noqa: F811
    """The owner's two sets with a trap spec on each pan; `values` adds specs on any part."""
    c = _owner_world(session_factory, monkeypatch, stub_access)
    specs = {S_PAN: {"trap_type": "s_trap"}, P_PAN: {"trap_type": "p_trap"}}
    for code, extra in values.items():
        specs[code] = {**specs.get(code, {}), **extra}
    db = session_factory()
    try:
        db.add(ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="trap_type", label="Trap", data_type="enum",
            allowed_values=["s_trap", "p_trap", "f_trap"],
            synonyms={"s_trap": ["s trap"], "p_trap": ["p trap"], "f_trap": ["f trap"]},
        ))
        for code, held in specs.items():
            db.add(ProductSpecifications(
                id=str(uuid.uuid4()), product_id=c.uuid_of[code],
                values={key: {"value": value} for key, value in held.items()},
            ))
        db.commit()
    finally:
        db.close()
    return c


def _state_block_on(monkeypatch) -> None:
    real = parser_mod.resolve_config
    monkeypatch.setattr(
        parser_mod, "resolve_config", lambda db, **k: dataclasses.replace(real(db, **k), state_block=True)
    )


def _shown_options(block: str) -> dict[int, dict]:
    for line in block.splitlines():
        for head in ("- open question: ", "Open question: "):
            if line.startswith(head):
                return {o["position"]: o for o in json.loads(line[len(head):])["options"]}
    raise AssertionError(("no open question in the parser input", block))


def _spec(word: str, value: str) -> dict:
    return entity(word, hint="specification", spec_key="trap_type", spec_value=value)


@pytest.mark.parametrize("state_block", [False, True], ids=["open_question_line", "state_block"])
def test_c_a_did_you_mean_lists_each_option_with_the_spec_that_tells_it_apart(
    session_factory, monkeypatch, stub_access, state_block  # noqa: F811
):
    # The shared cistern's material is held by every offered set: it tells nothing apart.
    c = _trap_world(session_factory, monkeypatch, stub_access, **{CISTERN: {"material": "ceramic"}})
    if state_block:
        _state_block_on(monkeypatch)
    assert "Did you mean" in c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    c.say("S trap", reply(open_question_answer=answer(None)))
    shown = _shown_options(c.blocks[-1])
    assert shown[1]["code"] == P_RL and "P trap" in shown[1].get("label", ""), shown
    assert shown[2]["code"] == S_RL and "S trap" in shown[2].get("label", ""), shown
    assert "S trap" not in shown[1].get("label", "") and "P trap" not in shown[2].get("label", ""), shown
    assert "eramic" not in json.dumps(shown), shown


def test_c_a_spec_only_reply_with_no_pick_asks_the_same_options_again(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _trap_world(session_factory, monkeypatch, stub_access)
    c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    k = len(c.stock_calls)
    text = c.say("S trap", reply(entities=[_spec("S trap", "s_trap")], open_question_answer=answer(None)))
    assert _option_codes(c) == [P_RL, S_RL], (c.stored_question, text)
    assert c.stock_calls[k:] == [], ("a stock read ran while the pick was open", c.stock_calls[k:])
    assert "Got stock" not in text and "How many units for each?" not in text, text


@pytest.mark.parametrize(
    "values,word,value",
    [({CISTERN: {"trap_type": "s_trap"}}, "S trap", "s_trap"), ({}, "F trap", "f_trap")],
    ids=["both_options_hold_it", "no_option_holds_it"],
)
def test_c_a_spec_that_does_not_single_out_one_option_asks_the_same_options_again(
    session_factory, monkeypatch, stub_access, values, word, value  # noqa: F811
):
    c = _trap_world(session_factory, monkeypatch, stub_access, **values)
    c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    k = len(c.stock_calls)
    text = c.say(word, reply(entities=[_spec(word, value)], open_question_answer=answer(None)))
    assert _option_codes(c) == [P_RL, S_RL], (c.stored_question, text)
    assert c.stock_calls[k:] == [], ("a stock read ran while the pick was open", c.stock_calls[k:])
    assert "Got stock" not in text, text


def test_c_lock_a_new_code_typed_while_the_pick_is_open_runs_as_its_own_ask(session_factory, monkeypatch, stub_access):  # noqa: F811
    c = _trap_world(session_factory, monkeypatch, stub_access)
    c.say("qwc604-rl x 2", stock(product("qwc604-rl", 2)))
    text = c.say(f"{CISTERN} stock", stock(product(CISTERN)))
    assert c.stored_question is None, c.stored_question
    assert CISTERN in text and S_RL not in text, text
