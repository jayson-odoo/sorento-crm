"""EVAL-BENCH round 42: a spec set must be built on the gold's spec KEY, not only its value.

`spec_set` read values only, so "300mm" grounded as another dimension key passed. The key the bot filtered on rides each
specification entity (`spec_key`). There is no key alias table: the only keys that stand in for each other are the gold's own
keys carrying the same value. Synthetic rows only.
"""
from __future__ import annotations

from scripts.chatbot_eval.targets import grade_turn
from tests.chatbot_eval.test_targets import item, row

TRAP = [{"key": "trap_length", "value": "300"}]
TWO = [{"key": "trap_length", "value": "300"}, {"key": "dim_width", "value": "300"}]


def _ent(key, value=300, raw="300mm"):
    return {"hint": "specification", "spec_key": key, "spec_value": value, "raw": raw}


def _spec(entities, gold):
    return grade_turn(row(entities=entities), item("spec", spec=gold))["checks"]["spec_set"]


def test_red_a_a_value_on_another_spec_key_does_not_ground_the_set():
    assert _spec([_ent("dim_length")], TRAP) is False


def test_guard_a_the_gold_key_grounds_the_set():
    assert _spec([_ent("trap_length")], TRAP) is True


def test_red_b_one_of_the_gold_keys_for_the_same_value_stands_for_the_other():
    assert _spec([_ent("dim_width")], TWO) is True
    assert _spec([_ent("trap_length")], TWO) is True
    assert _spec([_ent("dim_length")], TWO) is False


def test_red_c_an_entity_with_the_value_but_no_key_is_unknown():
    assert _spec([_ent(None)], TRAP) is None


def test_guard_d_a_missing_value_still_fails_and_a_class_only_gold_needs_no_key():
    assert _spec([_ent("trap_length", 250, "250mm")], TRAP) is False
    cls = [{"key": "product_type", "value": "water closet"}]
    ents = [{"hint": "category", "raw": "water closet", "canonical_code": "water closet"}]
    assert _spec(ents, cls) is True
