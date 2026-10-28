"""GREETING-NOT-STOCK: a message with no business content never becomes a business ask
from the contact's remembered products alone (prod turns 2bb06537 / 699ce720: a bare "Hi"
from a contact with a tallied usual product got a stock summary for it).

The parser is stubbed to make the prod slip on purpose (a greeting parsed as a stock ask
for the remembered product, `current_message: false`); the guard after the parse
(`no_business.py`) is what must turn it back into a greeting. "eta?" over the same
memory is an ask, and the remembered product still fills it.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.chatbot import no_business
from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_engine import seeded, stub_access, stub_parser  # noqa: F401
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
        ["Hi", "hi", "Hii", "Hiii", "okk", "Hello boss", "hey there!", "Good morning", "Selamat pagi",
         "thanks", "Thank you very much", "tq", "ok", "Okay noted", "👍", "🙏🙏",
         "ok 👍", "你好", "谢谢", "Assalamualaikum", "bye", "Terima kasih boss", "got it", "ok got it thanks", "okkk",
         "Helloooo"],
    )
    def test_no_business_content(self, text: str) -> None:
        assert no_business.is_no_business(text), text

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "eta?", "eta", "stock?", "hi stock 286", "Hi, SRTWC286", "price", "1", "hi 2",
         "more", "all", "same as usual", "any update",
         # Reviewer S1: Manglish / Malay asks and chases built from greeting-list words.
         "got?", "boss got?", "got ah", "u got it?", "terima?", "terima", "kasih", "??", "?", "...",
         "afternoon?", "malam?", "ok?", "好？", "forgot item"],
    )
    def test_business_or_empty(self, text: str) -> None:
        assert not no_business.is_no_business(text), text


class TestWithoutContextAsk:
    def _call(self, v, text="Hi", *, quoted=False, media=False, held=False):
        return no_business.without_context_ask(v, text=text, quoted=quoted, media=media, held=held)

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

    def test_a_held_question_leaves_the_verdict_alone(self) -> None:
        v = verdict(**SLIPPED_STOCK_ASK)
        _, dropped = self._call(v, "ok", held=True)
        assert dropped is False

    def test_a_declared_state_change_is_dropped_with_the_ask(self) -> None:
        """Reviewer S2: a parsed "new subject" would rebuild the focus the greeting leaves alone."""
        v = verdict(**SLIPPED_STOCK_ASK, state_changes=[{"op": "new_subject"}])
        cleared, dropped = self._call(v)
        assert dropped is True and cleared["state_changes"] == []

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


class TestAQuestionTheBotIsWaitingOn:
    """Reviewer B1 / K2: "ok" to something the bot is waiting on is the live conversation's,
    so the engine passes the guard every kind of held question, not only `open_question`."""

    def test_ok_to_an_open_idea_draft_still_reaches_the_ideation_lane(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ) -> None:
        from tests.chatbot.test_ideation_draft_keeps_lane import _run
        from tests.chatbot.test_engine import _parser_output

        result, captured = _run(
            session_factory, system_settings_row, stub_parser, stub_access, monkeypatch,
            text="ok",
            parser=_parser_output(
                message_type="business_query", intent_hint="submit_idea", domain_hint="ideate",
                scope_intent=None, is_affirmative=True, user_goal="confirming", entities=[], entity_op=None,
            ),
        )
        assert result.branch_kind == "ideate", result.branch_kind
        assert len(captured) == 1
        assert "context_ask_dropped" not in [
            r.get("stage") or r.get("kind") for r in _turn_trace(session_factory, result.turn_id)
        ]

    def test_ok_over_an_open_pick_is_not_dropped(self, session_factory, stub_access, lane) -> None:
        from app.services.chatbot.turn import pending as turn_pending
        from tests.chatbot.test_ideation_draft_keeps_lane import ROSTER_PENDING
        from tests.chatbot.test_s3_canned_and_ideate import _seed_session_variables

        _seed_contact(session_factory, {"profile_facts": USUAL}, level="full")
        _seed_session_variables(
            session_factory,
            {"focus": {"domains": ["inventory"]}, "open_question": turn_pending.to_wire(ROSTER_PENDING)},
        )
        result, _prompt = _run_turn(
            session_factory, stub_access, message="ok", verdict_overrides=SLIPPED_STOCK_ASK, n=0, console=False
        )
        assert "context_ask_dropped" not in [
            r.get("stage") or r.get("kind") for r in _turn_trace(session_factory, result.turn_id)
        ]



class TestGreetGreetOkThenEta:
    """Crew hand test step 5 (copy :8107): "Hi", "Hi", "Hello boss", "ok 👍", then "eta?".
    Whatever the guard did to the small-talk turns (left them, or dropped a slipped ask on
    "ok"), "eta?" whose parse carries the remembered product is answered for it, opening
    with the carried line. The guard holds nothing that "eta?" needs."""

    @pytest.mark.parametrize("ok_parse", ["casual", "slipped"])
    def test_eta_after_small_talk_still_carries_the_usual_product(
        self, session_factory, stub_access, lane, monkeypatch, ok_parse
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
        casual = {"message_type": "casual"}
        turns = [
            ("Hi", casual),
            ("Hi", casual),
            ("Hello boss", casual),
            ("ok 👍", casual if ok_parse == "casual" else SLIPPED_STOCK_ASK),
        ]
        for n, (text, parsed) in enumerate(turns):
            result, _ = _run_turn(session_factory, stub_access, message=text, verdict_overrides=parsed, n=n, console=False)
            assert result.branch_kind == "low_signal", (text, result.branch_kind)
        dropped = [r.get("kind") for r in _turn_trace(session_factory, result.turn_id)].count("context_ask_dropped")
        assert dropped == (1 if ok_parse == "slipped" else 0)

        result, prompt = _run_turn(
            session_factory, stub_access, message="eta?",
            verdict_overrides={**SLIPPED_STOCK_ASK, "intent_hint": "check_incoming"}, n=4, console=False,
        )
        assert USUAL_CODE in prompt, "the remembered product reaches the eta? parse"
        assert result.branch_kind == "business_query", result.branch_kind
        assert "Your usual: " + USUAL_CODE in sent_text(result), sent_text(result)
