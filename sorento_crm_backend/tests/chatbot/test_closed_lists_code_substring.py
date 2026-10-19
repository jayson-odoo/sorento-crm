"""CODE-SUBSTRING (crew a43940036, plan a44428307 ruled (a); PLAN "CODE-SUBSTRING" CS-1 / CS-2).

Ported from CHAT-STATE's xfail(strict) reds (crew/chat-state-r2 929e4135da,
tests/chatbot/test_chat_state_r6_s5b_reconcile_and_answer_ports.py:47-101), here as plain reds: a
class word with no digit ("basin" in "ada basin?" / "basin有货吗") is a category, never a product hit on
the codes that merely contain it (decoys ZZBASINWC1 / ZZMIXERWC1, water closets with stock). The
English "any mixer in stock?" and a whole typed code are the guards. Round 7's world and chat (Leena),
real resolver, class vocabulary, spec registry and brands; the parser verdict is stubbed. The state-on
twin runs the CHAT-STATE path (`state_block`) as CHAT-STATE's `StateChat` does.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_attribute_asks_round3 import _codes_in, _entity
from tests.chatbot.test_attribute_asks_round3 import world as r3world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round4 import world as r4world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round7 import _Leena, _code_ask, _make
from tests.chatbot.test_attribute_asks_round7 import world  # noqa: F401 - fixture used by name
from tests.chatbot.test_chat_state_seam import _op
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import _stock_for
from tests.chatbot.test_reverse_asks_owner_phrasings import _class_category


class StateChat(_Leena):
    """Round 7's chat with the State path on (CHAT-STATE r5's harness, ported as is)."""

    def say(self, text: str, verdict: dict[str, Any]) -> str:
        real_inst = self.stub_parser

        def wrapped(output=None, **kw):
            real_inst(output, **kw)
            real = parser_mod.resolve_config

            def with_state(db, *, current_date, override_version_id=None):
                cfg = real(db, current_date=current_date, override_version_id=override_version_id)
                return dataclasses.replace(cfg, state_block=True)

            parser_mod.resolve_config = with_state

        self.stub_parser = wrapped
        orig = parser_mod.resolve_config
        from app.services.chatbot.turn import chat_state

        real_apply = chat_state.apply_changes
        ran: list[int] = []

        def counted(*a, **k):
            ran.append(1)
            return real_apply(*a, **k)

        chat_state.apply_changes = counted
        try:
            out = super().say(text, verdict)
            assert ran, "state path did NOT run: state_block never reached the engine (harness bug)"
            return out
        finally:
            chat_state.apply_changes = real_apply
            self.stub_parser = real_inst
            parser_mod.resolve_config = orig


def _decoys(db, world) -> set[str]:
    """Two water closets with stock whose CODES hold a class word ("basin", "mixer") and whose
    name and description say only what they are (a water closet)."""
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


def _chat(state_on: bool, session_factory, monkeypatch, stub_parser, stub_access, world):
    cls = StateChat if state_on else _Leena
    return cls(session_factory, monkeypatch, stub_parser, stub_access, world)


def _class_word_ask(message: str, word: str, state_on: bool) -> dict[str, Any]:
    v = _code_ask(message, _entity(word, "category"), attrs=("stock",), intent_hint="check_stock", domain_hint="inventory")
    if state_on:
        v["state_changes"] = [_op("set", "category")]
    return v


STATES = [pytest.param(False, id="state-off"), pytest.param(True, id="state-on")]


@pytest.mark.parametrize("state_on", STATES)
@pytest.mark.parametrize("message,word", [("ada basin?", "basin"), ("basin有货吗", "basin")], ids=["bm", "zh"])
def test_a_class_word_inside_product_codes_stays_a_category_never_a_product_hit(
    session_factory, monkeypatch, stub_parser, stub_access, world, state_on, message, word
):
    """CS-1. Fails on HEAD: the word reaches the decoys through a code-substring row."""
    decoys = _decoys(world["db"], world)
    chat = _chat(state_on, session_factory, monkeypatch, stub_parser, stub_access, world)

    text = chat.say(message, _class_word_ask(message, word, state_on))

    listed = _codes_in(text, world) | {c for c in decoys if c in text}
    assert not listed & decoys, ("a class word became a product hit on codes that merely contain it", sorted(listed), text)


@pytest.mark.parametrize("state_on", STATES)
def test_guard_the_english_mixer_ask_never_lists_a_code_holding_mixer(
    session_factory, monkeypatch, stub_parser, stub_access, world, state_on
):
    decoys = _decoys(world["db"], world)
    chat = _chat(state_on, session_factory, monkeypatch, stub_parser, stub_access, world)

    text = chat.say("any mixer in stock?", _class_word_ask("any mixer in stock?", "mixer", state_on))

    listed = _codes_in(text, world) | {c for c in decoys if c in text}
    assert not listed & decoys, (sorted(listed), text)


@pytest.mark.parametrize("state_on", STATES)
def test_guard_a_whole_typed_code_is_still_a_product_hit_when_hinted_otherwise(
    session_factory, monkeypatch, stub_parser, stub_access, world, state_on
):
    """CS-2: a whole typed code stays a product hit."""
    chat = _chat(state_on, session_factory, monkeypatch, stub_parser, stub_access, world)
    code = world["close_couple"]["sorento"][0].product_code
    v = _code_ask(code, _entity(code, "category"), attrs=("stock",), intent_hint="check_stock", domain_hint="inventory")
    if state_on:
        v["state_changes"] = [_op("set", "product")]

    text = chat.say(code, v)

    assert code in text, text
