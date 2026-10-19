"""EVAL-BENCH round 43: answering only the held product when the ask is over a class is a bot fail.

Owner (19 Oct): "answering only the held product when the ask is over a class is a bot fail". The class ask is the gold's (a class
key in its spec, products expected); the answer is read from the tool args, the tool results and the reply's codes. Synthetic rows.
"""
from __future__ import annotations

from scripts.chatbot_eval.targets import grade_turn
from tests.chatbot_eval.test_targets import item
from tests.chatbot_eval.test_targets_v2 import TOOL_A, UA, UB, prod, row2

CLS = {"key": "class", "value": "Water Closet"}
SPEC = [CLS, {"key": "trap_length", "value": "200"}]
EXPECTED = ["SRTA100", "SRTB200", "SRTC300"]
ENTS = [{"hint": "category", "raw": "water closet", "canonical_code": "water closet"},
        {"hint": "specification", "spec_key": "trap_length", "spec_value": 200, "raw": "200mm"}]


def _row(*, tools=(TOOL_A,), reply="SRTA100 has 40 pcs.", held=True, after=None):
    before = [prod("SRTA100", UA)] if held else []
    return row2(message="which water closet 200mm got stock", reply=reply, verdict={"entities": ENTS, "reference_positions": []},
                mem_before=before, mem_after=after if after is not None else [prod("SRTA100", UA), prod("SRTB200", UB)],
                tools=list(tools))


def _check(row, **gold):
    g = {"spec": SPEC, "spec_products": EXPECTED, **gold}
    res = grade_turn(row, item("spec", **g))
    return res["checks"].get("class_set", "absent"), res


def test_red_a_answering_only_the_held_product_over_a_class_ask_fails():
    state, res = _check(_row())
    assert state is False and res["passed"] is False, (state, res["checks"])


def test_guard_b_an_answer_that_reaches_an_expected_member_beyond_the_held_one_passes():
    tool_b = {"name": "crm_inventory_list", "args": {"product_ids": [UB]}}
    state, _ = _check(_row(tools=[TOOL_A, tool_b]))
    assert state is True, state


def test_guard_c_the_held_product_being_the_whole_set_passes():
    state, _ = _check(_row(), spec_products=["SRTA100"])
    assert state is True, state


def test_guard_d_a_reply_listing_the_expected_set_passes():
    state, _ = _check(_row(reply="Water closets with stock: SRTA100, SRTB200, SRTC300"))
    assert state is True, state


def test_red_e_nothing_shows_what_was_answered_is_unknown():
    state, _ = _check(_row(tools=[], reply="Which water closet do you mean?"))
    assert state is None, state


def test_guard_f_no_class_key_none_on_record_or_no_held_product_adds_no_check():
    assert _check(_row(), spec=[{"key": "trap_length", "value": "200"}])[0] == "absent"
    assert _check(_row(), none_on_record=True)[0] == "absent"
    assert _check(_row(held=False))[0] == "absent"
    assert _check(_row(), spec_products=[])[0] == "absent"


def test_guard_g_answering_only_a_variant_of_the_held_product_is_still_held_only():
    tool_v = {"name": "crm_inventory_list", "args": {"product_ids": [UB]}}
    row = _row(tools=[tool_v], reply="SRTA100-BL has 3 pcs.", after=[prod("SRTA100", UA), prod("SRTA100-BL", UB)])
    state, _ = _check(row)
    assert state is False, state
