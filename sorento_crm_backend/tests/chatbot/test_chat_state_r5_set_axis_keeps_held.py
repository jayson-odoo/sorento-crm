"""CHAT-STATE round 5, F1 (red): setting ONE axis of the held subject keeps the held others.

Card R1 (refine the last answer): when the parser sets one axis (op `set` on axis X), every
other held axis stays; only `new_subject` or an explicit `clear` on an axis drops it.

Seen live (TRAIN-shaped probe): turn 1 "brand + two classes" (set brand, set category; entities
brand, category, category) listed that brand's products. Turn 2, a short refine naming one
class: `set category` + `close_question`, ONE category entity, no brand op. The reply listed
another brand's water closets: the held brand was lost when only the category was set.

Driven as a whole two-turn conversation through `engine.run_turn` (the previous turn's
session is the State the second turn reads), the parse a hand-built verdict, the State path on
(`state_block`), the world round 7's (Sorento, Mocha, Cabana; water closets, basins with
stock). The reply's product codes are the assertion. No live LLM call.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_attribute_asks_round3 import _ask, _codes_in, _entity
from tests.chatbot.test_attribute_asks_round3 import world as r3world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round4 import world as r4world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round7 import _Leena, _brand_word
from tests.chatbot.test_attribute_asks_round7 import world  # noqa: F401 - fixture used by name
from tests.chatbot.test_chat_state_seam import _op
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name


class StateChat(_Leena):
    """Round 7's chat with the State path on, as the live prompt version has it."""

    def say(self, text: str, verdict: dict[str, Any]) -> str:
        inst = self.stub_parser
        real_inst = inst

        def wrapped(output=None, **kw):
            real_inst(output, **kw)
            real = parser_mod.resolve_config

            def with_state(db, *, current_date, override_version_id=None):
                cfg = real(db, current_date=current_date, override_version_id=override_version_id)
                return dataclasses.replace(cfg, state_block=True)

            parser_mod.resolve_config = with_state

        self.stub_parser = wrapped
        orig = parser_mod.resolve_config
        # Guard: the engine's state path runs `chat_state.apply_changes` on a verdict that
        # carries `state_changes`; if state_block never reaches the engine it is never called.
        from app.services.chatbot.turn import chat_state

        real_apply = chat_state.apply_changes
        ran: list[int] = []

        def counted(*a, **k):
            ran.append(1)
            return real_apply(*a, **k)

        chat_state.apply_changes = counted
        from app.services.chatbot import engine as engine_mod

        real_turn_apply = engine_mod.turn_apply
        self.focus_after: list[Any] = []

        def spy(*a, **k):
            res = real_turn_apply(*a, **k)
            self.focus_after.append(res[0].focus)
            return res

        engine_mod.turn_apply = spy
        try:
            out = super().say(text, verdict)
            assert ran, "state path did NOT run: state_block never reached the engine (harness bug), turn ran state-OFF"
            return out
        finally:
            chat_state.apply_changes = real_apply
            engine_mod.turn_apply = real_turn_apply
            self.stub_parser = real_inst
            parser_mod.resolve_config = orig


@pytest.fixture()
def chat(session_factory, monkeypatch, stub_parser, stub_access, world):
    return StateChat(session_factory, monkeypatch, stub_parser, stub_access, world)


def _spec(raw: str, key: str, value: str) -> dict[str, Any]:
    return {**_entity(raw, "specification"), "spec_key": key, "spec_value": value}


def _ask_with(entities: list[dict[str, Any]], changes: list[dict[str, Any]], goal: str) -> dict[str, Any]:
    v = _ask("stock", "x", goal, state_changes=changes)
    v["entities"] = entities
    return v


def _codes(products) -> set[str]:
    return {p.product_code for p in products}


def _groups(world) -> dict[str, set[str]]:
    cc = world["close_couple"]
    return {
        "srt_wc": _codes(cc["sorento"] + world["srt_ptrap"] + world["srt_strap"]),
        "cabana_wc": _codes(cc["cabana"]),
        "mocha_wc": _codes(cc["mocha"] + world["mch_ptrap"]),
        "srt_basin": _codes(world["srt_basins"]),
        "other_basin": _codes(world["mch_basins"] + world["cabana_basins"]),
        "srt_ptrap_wc": _codes(cc["sorento"] + world["srt_ptrap"]),
    }


def _held_set(chat, world, entities, changes, goal) -> str:
    text = chat.say(goal, _ask_with(entities, changes, goal))
    assert _codes_in(text, world), ("the held-set turn listed nothing", text[:300])
    return text


# (id, turn-2 message) fresh paraphrases, never the probe's wording
NARROW_TO_WC = [
    ("en", "just the toilets please"),
    ("bm", "tandas duduk sahaja"),
    ("zh", "只看马桶"),
]


@pytest.mark.parametrize("message", [c[1] for c in NARROW_TO_WC], ids=[c[0] for c in NARROW_TO_WC])
def test_r5_f1_setting_the_class_keeps_the_held_brand(chat, world, message):
    """Case 1: held = brand + classes (basin, water closet); the message sets the class to WC."""
    g = _groups(world)
    brand = _brand_word(world, "sorento")
    t1 = _held_set(
        chat, world,
        [_entity(brand, "brand"), _entity("basin", "category"), _entity("water closet", "category")],
        [_op("set", "brand"), _op("set", "category")], f"{brand} basins and water closets",
    )
    first = _codes_in(t1, world)
    assert first and first <= g["srt_wc"] | g["srt_basin"], ("turn 1 left the brand", sorted(first))
    t2 = chat.say(message, _ask_with(
        [_entity("water closet", "category")], [_op("set", "category"), _op("close_question")], message))
    listed = _codes_in(t2, world)
    assert listed, ("no product listed", t2[:300])
    assert not listed & (g["cabana_wc"] | g["mocha_wc"] | g["other_basin"]), (
        "the held brand was lost: other-brand codes listed", sorted(listed & (g["cabana_wc"] | g["mocha_wc"])))
    assert not listed & g["srt_basin"], ("basins listed after the class was set to water closet", sorted(listed))
    assert listed <= g["srt_wc"], sorted(listed)


SET_SPEC = [
    ("en", "the p trap ones"),
    ("bm", "yang p trap sahaja"),
    ("zh", "要P trap的"),
]


@pytest.mark.parametrize("message", [c[1] for c in SET_SPEC], ids=[c[0] for c in SET_SPEC])
def test_r5_f1_setting_a_spec_keeps_the_held_brand_and_class(chat, world, message):
    """Case 2: held = brand + class (water closet); the message sets a spec (trap type)."""
    g = _groups(world)
    brand = _brand_word(world, "sorento")
    _held_set(chat, world, [_entity(brand, "brand"), _entity("water closet", "category")],
              [_op("set", "brand"), _op("set", "category")], f"{brand} water closets")
    t2 = chat.say(message, _ask_with(
        [_spec("p trap", "trap_type", "p_trap")], [_op("set", "specification")], message))
    listed = _codes_in(t2, world)
    assert listed, ("no product listed", t2[:300])
    assert not listed & (g["cabana_wc"] | g["mocha_wc"]), ("the held brand was lost", sorted(listed))
    assert not listed & (g["srt_basin"] | g["other_basin"]), ("the held class was lost", sorted(listed))
    assert listed <= g["srt_ptrap_wc"], sorted(listed)


SET_BRAND = [
    ("en", "cabana ones instead"),
    ("bm", "cabana pula"),
    ("zh", "换成cabana的"),
]


@pytest.mark.parametrize("message", [c[1] for c in SET_BRAND], ids=[c[0] for c in SET_BRAND])
def test_r5_f1_setting_the_brand_keeps_the_held_class_and_spec(chat, world, message):
    """Case 3: held = class (water closet) + spec (p trap); the message sets the brand."""
    g = _groups(world)
    t1 = _held_set(chat, world, [_entity("water closet", "category"), _spec("p trap", "trap_type", "p_trap")],
                   [_op("set", "category"), _op("set", "specification")], "p trap water closets")
    assert _codes_in(t1, world) & g["srt_ptrap_wc"], t1[:300]
    t2 = chat.say(message, _ask_with(
        [_entity(_brand_word(world, "cabana"), "brand")], [_op("set", "brand")], message))
    listed = _codes_in(t2, world)
    assert listed, ("the held class and spec were lost: the brand alone reached the fetch, reply was", t2[:200])
    assert not listed & (g["srt_wc"] | g["mocha_wc"]), ("not the named brand", sorted(listed))
    assert not listed & (g["other_basin"] | g["srt_basin"]), ("the held class was lost", sorted(listed))
    assert listed <= g["cabana_wc"], sorted(listed)


# --------------------------------------------------------------------------- #
# Guards: green before and after
# --------------------------------------------------------------------------- #

CLEAR_BRAND = [
    ("en", "any brand, water closets"),
    ("bm", "mana-mana jenis, tandas duduk"),
    ("zh", "不限品牌的马桶"),
]


@pytest.mark.parametrize("message", [c[1] for c in CLEAR_BRAND], ids=[c[0] for c in CLEAR_BRAND])
def test_r5_f1_guard_an_explicit_clear_on_brand_drops_the_brand(chat, world, message):
    g = _groups(world)
    brand = _brand_word(world, "sorento")
    _held_set(chat, world, [_entity(brand, "brand"), _entity("water closet", "category")],
              [_op("set", "brand"), _op("set", "category")], f"{brand} water closets")
    t2 = chat.say(message, _ask_with(
        [_entity("water closet", "category")], [_op("set", "category"), _op("clear", "brand")], message))
    listed = _codes_in(t2, world)
    assert listed & g["srt_wc"] and listed & (g["cabana_wc"] | g["mocha_wc"]), sorted(listed)


NEW_SUBJECT = [
    ("en", "what about wash basins"),
    ("bm", "bagaimana dengan sinki"),
    ("zh", "洗手盆呢"),
]


@pytest.mark.parametrize("message", [c[1] for c in NEW_SUBJECT], ids=[c[0] for c in NEW_SUBJECT])
def test_r5_f1_guard_new_subject_with_a_new_class_drops_the_held_class(chat, world, message):
    g = _groups(world)
    brand = _brand_word(world, "sorento")
    _held_set(chat, world, [_entity(brand, "brand"), _entity("water closet", "category")],
              [_op("set", "brand"), _op("set", "category")], f"{brand} water closets")
    t2 = chat.say(message, _ask_with(
        [_entity("wash basin", "category")], [_op("new_subject")], message))
    listed = _codes_in(t2, world)
    assert listed, t2[:300]
    assert not listed & (g["srt_wc"] | g["cabana_wc"] | g["mocha_wc"]), ("the old class carried", sorted(listed))


# --------------------------------------------------------------------------- #
# Guards from review: the carry is refine-only, off for a product code, never a union,
# and a newly set class replaces the held one whichever bucket it sits in.
# --------------------------------------------------------------------------- #

def _held_srt_wc(chat, world, class_entities=None):
    brand = _brand_word(world, "sorento")
    return _held_set(chat, world, [_entity(brand, "brand"), *(class_entities or [_entity("water closet", "category")])],
                     [_op("set", "brand"), _op("set", "category")], f"{brand} water closets")


@pytest.mark.parametrize("ops", [[_op("keep")], [_op("answer")]], ids=["carry", "answer"])
def test_r5_f1_guard_a_turn_that_is_not_a_refine_does_not_pick_up_the_held_brand(chat, world, ops):
    g = _groups(world)
    _held_srt_wc(chat, world)
    t2 = chat.say("toilets", _ask_with([_entity("water closet", "category")], ops, "toilets"))
    listed = _codes_in(t2, world)
    assert listed & (g["cabana_wc"] | g["mocha_wc"]), ("the held brand was carried on a non-refine turn", sorted(listed), t2[:200])


def test_r5_f1_guard_a_typed_product_code_turn_carries_no_held_brand(chat, world):
    g = _groups(world)
    _held_srt_wc(chat, world)
    code = world["close_couple"]["cabana"][0].product_code
    t2 = chat.say(f"{code} water closet", _ask_with(
        [_entity(code, "product"), _entity("water closet", "category")], [_op("set", "product"), _op("set", "category")],
        f"{code} water closet"))
    listed = _codes_in(t2, world)
    assert code in listed, (sorted(listed), t2[:200])
    assert listed & g["mocha_wc"], ("the held brand was carried beside a typed code (other brands cut)", sorted(listed))


def test_r5_f1_guard_a_typed_brand_is_never_unioned_with_the_held_brand(chat, world):
    g = _groups(world)
    _held_srt_wc(chat, world)
    t2 = chat.say("cabana toilets", _ask_with(
        [_entity(_brand_word(world, "cabana"), "brand"), _entity("water closet", "category")],
        [_op("set", "category")], "cabana toilets"))
    listed = _codes_in(t2, world)
    assert listed, t2[:200]
    assert not listed & (g["srt_wc"] | g["mocha_wc"]), ("held brand unioned with the typed one", sorted(listed))
    assert listed <= g["cabana_wc"], sorted(listed)


def test_r5_f1_a_newly_set_class_replaces_the_held_class_in_the_other_bucket(chat, world):
    """Held class sits as product_type (basin); setting category = water closet replaces it."""
    g = _groups(world)
    _held_srt_wc(chat, world, [_entity("basin", "product_type")])
    t2 = chat.say("toilets only", _ask_with(
        [_entity("water closet", "category")], [_op("set", "category")], "toilets only"))
    listed = _codes_in(t2, world)
    assert listed, t2[:200]
    assert not listed & (g["srt_basin"] | g["other_basin"]), ("the held class (other bucket) was kept", sorted(listed))
    assert listed <= g["srt_wc"], ("brand lost or class wrong", sorted(listed))


def test_r5_f1_a_newly_set_class_replaces_both_class_buckets_in_the_applied_state(chat, world):
    """State level (turn/chat_state.py `_write_set`): no fetch carry needed."""
    _held_srt_wc(chat, world, [_entity("basin", "product_type")])
    chat.say("toilets only", _ask_with(
        [_entity("water closet", "category")], [_op("set", "category")], "toilets only"))
    focus = chat.focus_after[-1]
    names = lambda rows: [str(r.get("raw") or "").lower() for r in rows or []]  # noqa: E731
    extra = focus.extra or {}
    assert not any("basin" in n for n in names(extra.get("product_type"))), ("basin product_type kept", extra)
    assert any("water closet" in n for n in names(extra.get("category"))), ("new category missing", extra)
    assert focus.brands or extra.get("brand"), ("brand lost", focus.brands, extra)
