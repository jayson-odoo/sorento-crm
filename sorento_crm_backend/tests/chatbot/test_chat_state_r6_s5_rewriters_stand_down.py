"""CHAT-STATE round 6, S5 (red): the legacy text rewriters stand down under the state gate (AC-S5-1).

Each rewriter is spied at its real call site: turn_runtime.{with_set_count_from_text, with_brand_from_offer,
with_company_pick, with_new_set_words, with_clarify_answer}, engine._as_a_stock_ask_by_its_own_words (the
stock-ask regex), engine._top_selling_verdict, order_list.order_list_verdict, turn.reconcile.apply_reconciliation.
decide.py's refine-of-standing-subject branch has no isolated function to spy (it lives inside `decide`);
it is reported as not pinnable here. State-off twin: the same spies DO fire off the state path.
"""
from __future__ import annotations

import pytest

from tests.chatbot.test_chat_state_r6_subject import (  # noqa: F401 - fixtures used by name
    Focus, _ask_with, _entity, _op, json, seam, tchat, world,
)
from tests.chatbot.test_chat_state_r5_set_axis_keeps_held import r3world, r4world, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_attribute_asks_round7 import _brand_word
from tests.chatbot.test_chat_state_seam import _emit

TARGETS = [
    ("with_set_count_from_text", "app.services.chatbot.turn_runtime"),
    ("with_brand_from_offer", "app.services.chatbot.turn_runtime"),
    ("with_company_pick", "app.services.chatbot.turn_runtime"),
    ("with_new_set_words", "app.services.chatbot.turn_runtime"),
    ("with_clarify_answer", "app.services.chatbot.turn_runtime"),
    ("_as_a_stock_ask_by_its_own_words", "app.services.chatbot.engine"),
    ("_top_selling_verdict", "app.services.chatbot.engine"),
    ("order_list_verdict", "app.services.chatbot.order_list"),
    ("apply_reconciliation", "app.services.chatbot.turn.apply"),
]


def _spy_all(monkeypatch):
    import importlib

    seen = {name: 0 for name, _m in TARGETS}
    for name, mod_name in TARGETS:
        mod = importlib.import_module(mod_name)
        real = getattr(mod, name)

        def make(name=name, real=real):
            def spy(*a, **k):
                seen[name] += 1
                return real(*a, **k)
            return spy

        monkeypatch.setattr(mod, name, make())
    return seen


def _held(tchat, world):
    brand = _brand_word(world, "sorento")
    tchat.say("t1", _ask_with([_entity(brand, "brand"), _entity("water closet", "category")],
                              [_op("set", "brand"), _op("set", "category")], "t1"))


def _turn2(world):
    wc = lambda: _entity("water closet", "category")  # noqa: E731
    return {
        "refine": ([wc()], [_op("set", "category")]),
        "keep": ([wc()], [_op("keep")]),
        "answer": ([wc()], [_op("answer")]),
        "new_subject": ([_entity(_brand_word(world, "cabana"), "brand"), wc()], [_op("new_subject")]),
        "reject": ([wc()], [_op("set", "no_such_axis")]),
    }


@pytest.mark.parametrize("variant", ["refine", "keep", "answer", "new_subject", "reject"])
def test_r6_s5_no_legacy_rewriter_runs_on_a_state_turn_of_any_op_or_a_reject(tchat, world, monkeypatch, variant):
    _held(tchat, world)
    seen = _spy_all(monkeypatch)
    entities, ops = _turn2(world)[variant]
    tchat.say("t2", _ask_with(entities, ops, "t2"))
    ran = {k: v for k, v in seen.items() if v}
    assert not ran, (variant, ran)


def test_r6_s5_state_off_twin_the_rewriters_still_run_off_the_state_path(session_factory, monkeypatch, stub_parser, stub_access, world):
    from tests.chatbot.test_attribute_asks_round7 import _Leena

    plain = _Leena(session_factory, monkeypatch, stub_parser, stub_access, world)
    seen = _spy_all(monkeypatch)
    brand = _brand_word(world, "sorento")
    plain.say("t1", _ask_with([_entity(brand, "brand"), _entity("water closet", "category")], None, "t1"))
    plain.say("t2", _ask_with([_entity("water closet", "category")], None, "t2"))
    for name in ("with_company_pick", "with_clarify_answer", "with_set_count_from_text", "with_brand_from_offer", "with_new_set_words"):
        assert seen[name] >= 1, (name, seen)


# ----------------------------------------------------------------------- behaviour pins on the state path
def test_r6_s5_a_count_said_through_the_parse_field_limits_the_set_without_the_text_rewriter(tchat, world):
    _held(tchat, world)
    v = _ask_with([], [_op("keep")], "ten")
    v["top_n"] = 2
    text = tchat.say("show me 2", v)
    from tests.chatbot.test_attribute_asks_round3 import _codes_in

    assert 0 < len(_codes_in(text, world)) <= 2, text[:300]


def test_r6_s5_the_brand_from_the_offer_comes_from_the_r4a_offer_pick_op(seam, monkeypatch):
    from tests.chatbot.test_chat_state_r4a_brand_offer import E9, _brand_pick, _held_state, _ids_in_calls

    prev = _held_state(seam, E9)
    seam.say("bravat only", _brand_pick("bravat", changes=[_op("answer")]), previous=prev)
    assert "set_brand_chosen" in seam.rules_fired or _ids_in_calls(seam.turn_calls[-1]) <= {
        seam.uuid_of[c] for c in E9["held"]["Bravat"]}, (seam.rules_fired, seam.turn_calls[-1])


def test_r6_s5_an_offered_brand_typed_under_keep_on_a_held_brand_axis_is_not_an_offer_pick(seam):
    from tests.chatbot.test_chat_state_r4a_brand_offer import E9, _brand_pick, _held_state

    prev = _held_state(seam, E9)
    prev["focus"]["brands"] = ["SORENTO"]  # the brand axis is held, so a brand typed under keep is set aside
    out = seam.say("bravat", _brand_pick("bravat", changes=[_op("keep")]), previous=prev)
    assert "set_brand_chosen" not in seam.rules_fired, ("a kept-aside word counted as an offer pick", seam.rules_fired)
    subject = seam.memory(out).get("state", {}).get("subject") or {}
    assert subject.get("provenance", {}).get("brand") != "offer", subject
