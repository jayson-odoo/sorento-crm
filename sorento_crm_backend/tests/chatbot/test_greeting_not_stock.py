"""GREETING-NOT-STOCK: a message with no business content never becomes a business ask
from the contact's remembered products alone (prod turns 2bb06537 / 699ce720: a bare "Hi"
from a contact with a tallied usual product got a stock summary for it).

The parser is stubbed to make the prod slip on purpose (a greeting parsed as a stock ask
for the remembered product, `current_message: false`); the guard after the parse
(`turn/no_business.py`) is what must turn it back into a greeting. "eta?" over the same
memory is an ask, and the remembered product still fills it.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.chatbot.turn import no_business
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_memory_s4_fallback_replay import (  # noqa: F401
    _run_turn,
    _seed_contact,
    lane,
    sent_text,
)

USUAL_CODE = "SRTWC286-SH-NEW"
USUAL = [
    {"key": "usual_products", "value": [USUAL_CODE], "source": "tallied", "source_ref": None,
     "first_seen": "2026-10-01", "last_seen": "2026-10-22", "seen_count": 5, "set_by": None},
]
#: What the parser emitted on the prod turn: a stock ask for the remembered product,
#: which the message never named.
SLIPPED_STOCK_ASK = {
    "message_type": "business_query",
    "domain_hint": "inventory",
    "intent_hint": "check_stock",
    "entities": [
        {"raw": USUAL_CODE, "hint": "product", "canonical_code": USUAL_CODE,
         "current_message": False, "confident": True, "hint_confident": True},
    ],
}


class TestIsNoBusiness:
    @pytest.mark.parametrize(
        "text",
        ["Hi", "hi", "Hiii", "Hello boss", "hey there!", "Good morning", "Selamat pagi",
         "thanks", "Thank you very much", "tq", "ok", "Okay noted", "👍", "🙏🙏",
         "ok 👍", "你好", "谢谢", "Assalamualaikum", "bye"],
    )
    def test_no_business_content(self, text: str) -> None:
        assert no_business.is_no_business(text), text

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "eta?", "eta", "stock?", "hi stock 286", "Hi, SRTWC286", "price", "1", "hi 2",
         "more", "all", "same as usual", "any update"],
    )
    def test_business_or_empty(self, text: str) -> None:
        assert not no_business.is_no_business(text), text


class TestWithoutContextAsk:
    def _call(self, v, text="Hi", *, quoted=False, media=False, open_question=None):
        return no_business.without_context_ask(
            v, text=text, quoted=quoted, media=media, open_question=open_question
        )

    def test_a_greeting_parsed_as_a_stock_ask_is_filed_as_casual(self) -> None:
        v = verdict(**SLIPPED_STOCK_ASK)
        cleared, dropped = self._call(v)
        assert dropped is True
        assert cleared["message_type"] == "casual"
        assert cleared["entities"] == [] and cleared["domain_hint"] is None and cleared["intent_hint"] is None
        assert v["entities"], "the parser's own verdict is not mutated"

    def test_an_ask_keeps_the_remembered_product(self) -> None:
        v = verdict(**SLIPPED_STOCK_ASK)
        cleared, dropped = self._call(v, "eta?")
        assert dropped is False and cleared is v

    def test_an_open_question_leaves_the_verdict_alone(self) -> None:
        v = verdict(**SLIPPED_STOCK_ASK)
        _, dropped = self._call(v, "ok", open_question={"kind": "confirm"})
        assert dropped is False

    def test_a_quoted_reply_or_a_photo_leaves_the_verdict_alone(self) -> None:
        v = verdict(**SLIPPED_STOCK_ASK)
        assert self._call(v, quoted=True)[1] is False
        assert self._call(v, media=True)[1] is False

    def test_a_plain_greeting_verdict_is_untouched(self) -> None:
        v = verdict(message_type="casual")
        cleared, dropped = self._call(v)
        assert dropped is False and cleared is v


def _turn_trace(session_factory, turn_id: str) -> list[dict]:
    from app.models.chatbot_turn import ChatbotTurn

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    return [r for r in (row.trace or []) if isinstance(r, dict)]


class TestGreetingWithARememberedProduct:
    def test_hi_with_a_remembered_product_gets_a_greeting_not_a_stock_answer(
        self, session_factory, stub_access, lane
    ) -> None:
        _seed_contact(session_factory, {"profile_facts": USUAL}, level="full")
        result, prompt = _run_turn(
            session_factory, stub_access, message="Hi", verdict_overrides=SLIPPED_STOCK_ASK, n=0, console=False
        )
        assert USUAL_CODE in prompt, "the remembered product still reaches the parser as context"
        assert result.branch_kind == "low_signal", result.branch_kind
        assert lane.tool_calls == [], lane.tool_calls
        assert "Stock summary" not in sent_text(result)
        stages = [r.get("stage") or r.get("kind") for r in _turn_trace(session_factory, result.turn_id)]
        assert "tool" not in stages, stages
        assert "context_ask_dropped" in stages, "the drop is on the trace record"

    def test_eta_with_a_remembered_product_asks_about_that_product(
        self, session_factory, stub_access, lane, monkeypatch
    ) -> None:
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_outstanding_lane import _resolve_services

        match = {"uuid": str(uuid.uuid4()), "entity_type": "product", "canonical_code": USUAL_CODE}
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: _resolve_services({USUAL_CODE: match}),
        )
        _seed_contact(session_factory, {"profile_facts": USUAL}, level="full")
        result, _prompt = _run_turn(
            session_factory, stub_access, message="eta?",
            verdict_overrides={**SLIPPED_STOCK_ASK, "intent_hint": "check_incoming"}, n=0, console=False,
        )
        assert result.branch_kind == "business_query", result.branch_kind
        stages = [r.get("stage") or r.get("kind") for r in _turn_trace(session_factory, result.turn_id)]
        assert "tool" in stages, stages
        assert USUAL_CODE in sent_text(result), "the remembered product fills the ask's slot"


def test_entity_helper_shape_matches() -> None:
    """The slipped verdict's entity is the shape the shared helper builds."""
    assert set(entity(USUAL_CODE, current_message=False)) == set(SLIPPED_STOCK_ASK["entities"][0])
