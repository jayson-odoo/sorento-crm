"""CHAT-STATE r6 S5 review (red): reconcile stays on the state path, a substring is never a product hit,
and the clarify / company / count answers reach the turn through the `answer` op (real parser shapes:
`answer` + open_question_answer {mode: position | value}, never a stubbed top_n).
"""
from __future__ import annotations

import pytest

from tests.chatbot._turn_helpers import build_policy, entity, verdict
from tests.chatbot.test_attribute_asks_round3 import _ask, _codes_in, _entity
from tests.chatbot.test_attribute_asks_round3 import small_list  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round7 import _Leena, _code_ask, _make
from tests.chatbot.test_chat_state_r5_set_axis_keeps_held import (  # noqa: F401 - fixtures used by name
    StateChat, chat, r3world, r4world, stub_access, stub_parser, world,
)
from tests.chatbot.test_chat_state_seam import _op
from tests.chatbot.test_reverse_asks_owner_phrasings import _class_category
from tests.chatbot.test_lane_require import _stock_for


# ----------------------------------------------------------------------- 1. reconcile on the state path
def _apply(entities, resolved, *, gate):
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile(), state_gate=gate)
    v = verdict(domain_hint=None, entities=entities, state_changes=[_op("set", "customer")] if gate else None)
    if not gate:
        v.pop("state_changes", None)
    return apply(state, v, build_policy(), resolved=resolved)


@pytest.mark.parametrize("gate", [True, False], ids=["state-on", "state-off-twin"])
def test_r6_s5b_a_single_kind_hit_retypes_a_product_hint_to_the_customer(gate):
    out, plan = _apply([entity("ZZT Acme Trading", hint="product")], {"ZZT Acme Trading": {"customer": 1}}, gate=gate)
    assert [e.get("raw") for e in out.focus.customers] == ["ZZT Acme Trading"], (out.focus.customers, out.focus.products)
    assert not [p for p in out.focus.products if p.get("raw") == "ZZT Acme Trading"], out.focus.products


@pytest.mark.parametrize("gate", [True, False], ids=["state-on", "state-off-twin"])
def test_r6_s5b_a_token_matching_two_kinds_gets_the_numbered_kind_pick(gate):
    out, plan = _apply([entity("Sorento", hint="customer")], {"Sorento": {"customer": 1, "transporter": 1}}, gate=gate)
    assert plan.ask is not None and plan.ask.kind == "kind_pick", plan.ask


# ----------------------------------------------------------------------- 1b. substring is never a product hit
def _decoys(db, world):
    from app.models.product import ProductCategory  # noqa: F401

    uom = world["srt_tubs"][0].base_uom_id
    wc = _class_category(db, "WC")
    made = [
        _make(db, code=code, name=f"Sorento WC {code}", description="CLOSE COUPLED P-TRAP WATER CLOSET",
              brand=world["sorento"], category_id=wc, uom_id=uom)
        for code in ("ZZBASINWC1", "ZZMIXERWC1")
    ]
    for p in made:
        _stock_for(db, product_id=p.id, warehouse_id=world["warehouse"].id)
    db.commit()
    return {p.product_code for p in made}


SUBSTRING_WORDS = [("en", "any mixer in stock?", "mixer"), ("bm", "ada basin?", "basin"), ("zh", "basin有货吗", "basin")]


@pytest.mark.parametrize("state_on", [True, False], ids=["state-on", "state-off"])
@pytest.mark.parametrize("message,word", [c[1:] for c in SUBSTRING_WORDS], ids=[c[0] for c in SUBSTRING_WORDS])
def test_r6_s5b_a_class_word_inside_product_codes_stays_a_category_never_a_product_hit(
    session_factory, monkeypatch, stub_parser, stub_access, world, state_on, message, word
):
    decoys = _decoys(world["db"], world)
    cls = StateChat if state_on else _Leena
    chat = cls(session_factory, monkeypatch, stub_parser, stub_access, world)
    v = _code_ask(message, _entity(word, "category"), attrs=("stock",), intent_hint="check_stock", domain_hint="inventory")
    if state_on:
        v["state_changes"] = [_op("set", "category")]
    text = chat.say(message, v)
    from tests.chatbot.test_attribute_asks_round3 import _codes_in as codes_in

    listed = codes_in(text, world) | {c for c in decoys if c in text}
    assert not listed & decoys, ("a class word became a product hit on codes that merely contain it", sorted(listed))


@pytest.mark.parametrize("state_on", [True, False], ids=["state-on", "state-off"])
def test_r6_s5b_guard_a_whole_product_code_is_still_a_product_hit_when_hinted_otherwise(
    session_factory, monkeypatch, stub_parser, stub_access, world, state_on
):
    cls = StateChat if state_on else _Leena
    chat = cls(session_factory, monkeypatch, stub_parser, stub_access, world)
    code = world["close_couple"]["sorento"][0].product_code
    v = _code_ask(code, _entity(code, "category"), attrs=("stock",), intent_hint="check_stock", domain_hint="inventory")
    if state_on:
        v["state_changes"] = [_op("set", "product")]
    text = chat.say(code, v)
    assert code in text, text


# ----------------------------------------------------------------------- 2a. clarify answer through the answer op
def _oqa(mode, *items, picked=()):
    return {"mode": mode, "picked": list(picked), "items": list(items), "qty_for_all": None}


@pytest.mark.parametrize("reply", ["tap", "the tap one", "tap je"])
def test_r6_s5b_the_clarify_answer_re_runs_the_stored_ask_with_the_picked_option(chat, world, reply):
    from tests.chatbot.test_engine import _parser_output

    first = chat.say("any water tap basin", {**_ask("stock", "water tap basin", "any water tap basin"),
                                             "state_changes": [_op("set", "category")]})
    v = _parser_output(entities=[_entity("tap", "product")], user_goal=reply, match_mode="and")
    v["state_changes"] = [_op("answer")]
    v["open_question_answer"] = _oqa("value", "tap")
    text = chat.say(reply, v)
    taps = {p.product_code for p in world["every"] if "tap" in (p.product_name or "").lower()}
    assert set(_codes_in(text, world)) == taps, ("the stored ask was not re-run with the picked option", text[:300])


# ----------------------------------------------------------------------- 2c. count answer
def test_r6_s5b_the_state_block_shows_the_count_question_as_open():
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import Focus, State

    focus = Focus(domains=["inventory"], set_page={"set_key": {"domain": "inventory", "set_noun": "water closets",
                                                              "total": 9, "shown": 0, "access_levels": []}})
    view = chat_state.view(State(focus=focus, turn_no=3), None)
    assert view["open_question"], ("the count question is not in the State block the parser sees", view)
