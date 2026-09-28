"""Fix lane round 3 on PR #1304: the owner's hand test of 28 Sep 2026, replayed.

The record (shared hand-test DB, console contact, memory On at Full, own level Full):
`check stock srtwc286`, `how about srtwc287` (inventory), `what did i ask` (the
clarify menu), `what products do i usually ask about` (`message_type:
history_question`, low_signal), then `incoming srtwc286` (domain incoming). No row
reached `conversation_frames`, and the Chatbot tab showed one open conversation with
Topic "-".

* R1: the inventory to incoming switch closes the open conversation into an episode
  (the parser's `topic_reset` stays false there: the product is the same), with its
  summary and Topic, on the contact's Conversations list and in the turn's `memory`
  trace event (what the Chat History drawer reads).
* R2: the open conversation's Topic is its current domain.
* R3: a history question with memory on gets the fallback naming what memory holds,
  not the clarifier.

Postgres only (`tests/chatbot/conftest.py::session_factory`).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import object_session

from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn import episode_digest
from app.services.chatbot_reply_copy import CHATBOT_REPLY_HISTORY_LEAD, CHATBOT_REPLY_HISTORY_NOTHING
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401

CLARIFIER_TEXT = "Noted."


def _seed_contact(session_factory, *, level: str | None = "full") -> str:
    db = session_factory()
    pk = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_memory_level) "
            "VALUES (:pk, :cid, :phone, CAST(:sv AS jsonb), :lvl)"
        ),
        {
            "pk": pk,
            "cid": str(CONTACT_ID),
            "phone": f"+6011{uuid.uuid4().hex[:8]}",
            "sv": json.dumps({"variables": {}}),
            "lvl": level,
        },
    )
    db.commit()
    return pk


@pytest.fixture()
def memory_on(session_factory, system_settings_row, monkeypatch):
    """Memory switched On at Full, and the `low_signal` lane completing in the CRM with a
    stubbed clarifier (`test_memory_fix_round2_engine.py::casual_lane`)."""
    from app.services.chatbot.lanes import casual

    system_settings_row.chatbot_memory = {"enabled": True, "default_level": "full"}
    system_settings_row.chatbot_completed_lanes = ["low_signal"]
    object_session(system_settings_row).commit()
    monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
    monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db, **_: object())
    monkeypatch.setattr(
        casual, "call_clarifier", lambda config, prompt: json.dumps({"response": CLARIFIER_TEXT})
    )
    # The incoming lookup answers "nothing", no network reached
    # (`test_escalation_agent_carry.py::_stub_incoming_probe_empty`).
    from app.services.ai_assistant_service import MCPRuntimeClient

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, arguments: json.dumps({"answers": []}))


#: The five messages of the owner's record, with the verdicts the parser gave them.
FIVE = [
    ("check stock srtwc286", verdict(domain_hint="inventory", entities=[entity("SRTWC286")])),
    ("how about srtwc287", verdict(domain_hint="inventory", entities=[entity("SRTWC287")])),
    (
        "what did i ask",
        verdict(message_type="clarification", domain_hint=None, intent_hint=None, entities=[]),
    ),
    (
        "what products do i usually ask about",
        verdict(message_type="history_question", domain_hint=None, intent_hint=None, entities=[]),
    ),
    ("incoming srtwc286", verdict(domain_hint="incoming", entities=[entity("SRTWC286")])),
]


def _say(session_factory, stub_parser, stub_access, message: str, v: dict[str, Any], *, n: int, console: bool):
    stub_access()
    stub_parser(v)
    overrides: dict[str, Any] = {"is_test": True, "ingress": "console"} if console else {}
    envelope = _envelope(**overrides)
    envelope.message["message"]["messageId"] = f"ZZT-r3-{uuid.uuid4().hex[:8]}-{n}"
    envelope.message["message"]["message"]["text"] = message
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    # One minute apart, in order: created_at decides every range.
    db = session_factory()
    db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).update(
        {"created_at": datetime(2026, 9, 28, 3, 1, tzinfo=timezone.utc) + timedelta(minutes=n)}
    )
    db.commit()
    return result


def _frames(session_factory, *, is_test: bool) -> list[ConversationFrame]:
    return (
        session_factory()
        .query(ConversationFrame)
        .filter(
            ConversationFrame.contact_respond_id == str(CONTACT_ID),
            ConversationFrame.is_test.is_(is_test),
        )
        .all()
    )


def _memory_event(session_factory, turn_id: str) -> dict:
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    events = [r for r in (row.trace or []) if isinstance(r, dict) and r.get("kind") == "memory"]
    assert events, "the turn recorded no memory event"
    return events[-1]


def _reply_text(result) -> str:
    reply = getattr(result, "reply", None) or {}
    return str(reply.get("text") or "")


class TestOwnerHandTestReplay:
    @pytest.mark.parametrize("console", [True, False], ids=["console", "live"])
    def test_the_incoming_switch_writes_the_inventory_episode(
        self, session_factory, stub_parser, stub_access, memory_on, console
    ) -> None:
        contact_pk = _seed_contact(session_factory)
        results = [
            _say(session_factory, stub_parser, stub_access, msg, v, n=i, console=console)
            for i, (msg, v) in enumerate(FIVE)
        ]

        frames = _frames(session_factory, is_test=console)
        assert len(frames) == 1, f"the inventory to incoming switch wrote {len(frames)} frames"
        frame = frames[0]
        assert list(frame.turn_ids) == [r.turn_id for r in results[:4]]
        assert frame.domain == "inventory"
        assert frame.close_reason == "topic_switch"
        assert "stock for SRTWC286" in (frame.summary or ""), frame.summary
        assert "SRTWC287" in (frame.summary or ""), frame.summary
        # The world stays apart: a console episode is never a live one, and back.
        assert _frames(session_factory, is_test=not console) == []

        # The turn drawer's Memory panel reads the switch turn's `memory` event.
        written = _memory_event(session_factory, results[4].turn_id)["episodes"]["written"]
        assert written is not None
        assert written["summary"] == frame.summary
        assert written["domain"] == "inventory"
        assert written["trigger"] == "domain_switch"

        # The contact's Conversations list: the episode, and (R2) the open incoming
        # conversation with its Topic.
        from app.services.contact_service import ContactService

        episodes = ContactService(session_factory()).get_chatbot_memory(contact_pk, include_episodes=True)[
            "episodes"
        ]
        rows = episodes["rows"]
        assert [r["id"] for r in rows] == [frame.id]
        assert rows[0]["domains"] == ["inventory"]
        assert rows[0]["console"] is console
        current = episodes["console_current" if console else "current"]
        assert current is not None
        assert current["domains"] == ["incoming"]
        assert current["turn_count"] == 1
        assert current["first_turn_id"] == results[4].turn_id
        assert episodes["console_current" if not console else "current"] is None
        assert episodes["console_kept" if console else "kept"] == 1

    def test_the_history_question_names_what_memory_holds(
        self, session_factory, stub_parser, stub_access, memory_on
    ) -> None:
        _seed_contact(session_factory)
        results = [
            _say(session_factory, stub_parser, stub_access, msg, v, n=i, console=True)
            for i, (msg, v) in enumerate(FIVE[:4])
        ]
        history = results[3]
        text_value = _reply_text(history)
        assert history.branch_kind == "low_signal"
        assert text_value != CLARIFIER_TEXT
        # Round 4 (S4) replaced this round's "Here is what I remember" block with the
        # numbered list and its re-run offer; what is pinned is unchanged: memory names
        # the open inventory conversation, not the clarifier.
        assert CHATBOT_REPLY_HISTORY_LEAD["en"] in text_value, text_value
        assert "1. " in text_value and "Stock: Asked about stock for SRTWC286" in text_value, text_value
        assert "SRTWC287" in text_value, text_value


class TestOpenTopicIsTheCurrentDomain:
    def test_the_open_conversation_topic_is_never_blank_once_a_domain_was_planned(
        self, session_factory, stub_parser, stub_access, memory_on
    ) -> None:
        contact_pk = _seed_contact(session_factory)
        for i, (msg, v) in enumerate(FIVE[:2]):
            _say(session_factory, stub_parser, stub_access, msg, v, n=i, console=False)

        from app.services.contact_service import ContactService

        current = ContactService(session_factory()).get_chatbot_memory(contact_pk, include_episodes=True)[
            "episodes"
        ]["current"]
        assert current["domains"] == ["inventory"]
        assert "stock for SRTWC286" in current["summary"], current["summary"]


class TestHistoryFallbackGates:
    def test_memory_off_keeps_the_clarifier(
        self, session_factory, stub_parser, stub_access, memory_on, system_settings_row
    ) -> None:
        system_settings_row.chatbot_memory = {"enabled": False, "default_level": "full"}
        object_session(system_settings_row).commit()
        _seed_contact(session_factory, level=None)
        result = _say(session_factory, stub_parser, stub_access, *FIVE[3], n=0, console=True)
        assert _reply_text(result) == CLARIFIER_TEXT

    def test_nothing_held_says_so(self, session_factory, stub_parser, stub_access, memory_on) -> None:
        _seed_contact(session_factory)
        result = _say(session_factory, stub_parser, stub_access, *FIVE[3], n=0, console=True)
        assert CHATBOT_REPLY_HISTORY_NOTHING["en"] in _reply_text(result)

    def test_closed_episodes_are_named_as_earlier(
        self, session_factory, stub_parser, stub_access, memory_on
    ) -> None:
        _seed_contact(session_factory)
        for i, (msg, v) in enumerate(FIVE):
            _say(session_factory, stub_parser, stub_access, msg, v, n=i, console=True)
        result = _say(session_factory, stub_parser, stub_access, *FIVE[3], n=9, console=True)
        text_value = _reply_text(result)
        # Round 4 (S4): numbered newest first, the open incoming conversation, then
        # the closed inventory one.
        assert "1. " in text_value and "2. " in text_value, text_value
        incoming, stock = "Incoming stock: Asked about incoming stock for SRTWC286", ", Stock: Asked about stock for SRTWC286"
        assert incoming in text_value and stock in text_value, text_value
        assert text_value.index(incoming) < text_value.index(stock), text_value


class TestCloseTrigger:
    """The pure rule the engine and the backfill share."""

    def test_a_new_domain_switches(self) -> None:
        assert episode_digest.close_trigger({"topic_reset": False}, "incoming", "inventory") == "domain_switch"

    def test_the_same_domain_does_not(self) -> None:
        assert episode_digest.close_trigger({}, "inventory", "inventory") is None

    def test_no_planned_domain_never_switches(self) -> None:
        assert episode_digest.close_trigger({"domain_hint": "product"}, None, "inventory") is None

    def test_nothing_open_to_switch_from(self) -> None:
        assert episode_digest.close_trigger({}, "incoming", None) is None

    def test_the_parser_reset_still_closes(self) -> None:
        assert episode_digest.close_trigger({"topic_reset": True}, None, None) == "topic_reset"


class TestBackfillUsesTheSameRule:
    def test_the_backfill_rebuilds_the_live_switch_episode_identically(
        self, session_factory, stub_parser, stub_access, memory_on
    ) -> None:
        _seed_contact(session_factory)
        for i, (msg, v) in enumerate(FIVE):
            _say(session_factory, stub_parser, stub_access, msg, v, n=i, console=False)
        live = _frames(session_factory, is_test=False)
        assert len(live) == 1
        live_ids, live_summary = list(live[0].turn_ids), live[0].summary

        db = session_factory()
        db.query(ConversationFrame).filter(ConversationFrame.contact_respond_id == str(CONTACT_ID)).delete()
        db.commit()

        from scripts.backfill_chatbot_episodes import backfill

        counts = backfill(session_factory())
        assert counts["frames_written"] == 1, counts
        rebuilt = _frames(session_factory, is_test=False)
        assert [list(f.turn_ids) for f in rebuilt] == [live_ids]
        assert rebuilt[0].summary == live_summary
        # Idempotent: a second run writes nothing.
        assert backfill(session_factory())["frames_written"] == 0
