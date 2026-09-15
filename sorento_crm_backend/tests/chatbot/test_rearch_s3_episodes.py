"""S3 - episode write on topic switch / conversation close (AC-1546, PLAN-chatbot-
turn-rearch.md "State: three shelves"; the `conversation_frames` table and its
`contact_respond_id` column are already committed, S0/S1 - see
`app/models/conversation_frame.py`).

`turn/memory.py::write_episode(...)` does not exist yet, so every test is RED at
collection with `ModuleNotFoundError: No module named 'app.services.chatbot.turn.
memory'`.

**Ambiguity flagged to the captain**: the brief says "call the SLA close path used
today for the five-key clear" for the conversation-close half of this AC. This tester
could not find such a path (searched `app/services/chatbot/`, `app/api/v1/external/`
and `app/services/sla_service.py` for a session_vars reset keyed to a Respond
conversation-close event; nothing matches). `TestFrameOnConversationClose` below calls
`write_episode(..., close_reason="conversation_close")` directly instead of driving a
named SLA route - it tests the MEMORY seam's own close-reason handling, not the
production trigger wiring, and is flagged rather than silently invented.

**Second ambiguity**: `write_episode`'s parameter names/order are this tester's guess
(`write_episode(db, *, contact_respond_id, domain, intent, entities, tools_used,
turn_ids, summary, close_reason)`), since no S3 module exists yet to read the real
signature off. The engine-level three-topic test (`TestThreeTopicsTwoFrames`) instead
drives the seam through `engine.run_turn` with `topic_reset` on the verdict (S2's own
v3 key, already committed), so it is independent of this tester's parameter-name guess
for `write_episode` and only depends on the ROW COUNT/shape written to
`conversation_frames`.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

# Forces collection failure now - see module docstring.
from app.services.chatbot.turn.memory import write_episode  # noqa: F401

from app.models.conversation_frame import ConversationFrame
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser


def _seed(session_factory) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000003", "sv": json.dumps({"variables": {}})},
    )
    db.commit()


def _frames(session_factory) -> list[ConversationFrame]:
    return (
        session_factory()
        .query(ConversationFrame)
        .filter(ConversationFrame.contact_respond_id == str(CONTACT_ID))
        .order_by(ConversationFrame.started_at)
        .all()
    )


class TestThreeTopicsTwoFrames:
    def test_three_run_turns_topic_reset_on_second_and_third_yield_two_frames(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed(session_factory)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        v1 = verdict(domain_hint="inventory", entities=[entity("A", hint="product")])
        stub_parser(v1)
        e1 = _envelope()
        engine_mod.run_turn(e1, session_factory=session_factory)

        v2 = verdict(domain_hint="order", topic_reset=True, entities=[entity("customer one", hint="customer")])
        stub_parser(v2)
        e2 = _envelope()
        e2.message["message"]["messageId"] = "ZZT-episodes-turn-2"
        engine_mod.run_turn(e2, session_factory=session_factory)

        v3 = verdict(domain_hint="promotion", topic_reset=True)
        stub_parser(v3)
        e3 = _envelope()
        e3.message["message"]["messageId"] = "ZZT-episodes-turn-3"
        engine_mod.run_turn(e3, session_factory=session_factory)

        frames = _frames(session_factory)
        assert len(frames) == 2, (
            f"three topics with topic_reset on turns 2 and 3 must close exactly two "
            f"frames (topic 1 on turn 2's reset, topic 2 on turn 3's reset; topic 3 "
            f"stays open), got {len(frames)}: {[f.domain for f in frames]}"
        )

    def test_no_frame_written_mid_topic(self, session_factory, stub_parser, stub_access) -> None:
        _seed(session_factory)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        v1 = verdict(domain_hint="inventory", entities=[entity("A", hint="product")])
        stub_parser(v1)
        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        v2 = verdict(domain_hint="inventory", entities=[entity("B", hint="product")])
        stub_parser(v2)
        e2 = _envelope()
        e2.message["message"]["messageId"] = "ZZT-episodes-midtopic-2"
        engine_mod.run_turn(e2, session_factory=session_factory)

        assert _frames(session_factory) == [], (
            "no topic_reset was flagged on either turn - no frame must be written"
        )


class TestFrameFieldsAndEmbeddingEnqueue:
    def test_frame_carries_domain_intent_entities_tools_summary_turn_ids(
        self, session_factory
    ) -> None:
        from app.services.chatbot.turn.memory import write_episode

        db = session_factory()
        frame = write_episode(
            db,
            contact_respond_id="ZZT-episodes-fields-1",
            domain="inventory",
            intent="check_stock",
            entities={"product": ["SRTWC287"]},
            tools_used=["crm_inventory_stock_balance_list"],
            turn_ids=["turn-1", "turn-2"],
            summary="Checked stock for SRTWC287.",
            close_reason="topic_switch",
        )

        assert frame.domain == "inventory"
        assert frame.intent == "check_stock"
        assert frame.entities.get("product") == ["SRTWC287"]
        assert "crm_inventory_stock_balance_list" in frame.tools_used
        assert frame.summary
        assert list(frame.turn_ids) == ["turn-1", "turn-2"]

    def test_embedding_enqueued_once_per_frame_with_source_type_conversation_frame(
        self, session_factory, monkeypatch
    ) -> None:
        from app.services import embedding_service as embedding_service_mod
        from app.services.chatbot.turn.memory import write_episode

        calls: list[dict[str, Any]] = []
        original = embedding_service_mod.EmbeddingEventService.queue_event

        def spy(self, **kwargs: Any):
            calls.append(kwargs)
            return original(self, **kwargs)

        monkeypatch.setattr(embedding_service_mod.EmbeddingEventService, "queue_event", spy)

        db = session_factory()
        write_episode(
            db,
            contact_respond_id="ZZT-episodes-embed-1",
            domain="inventory",
            intent="check_stock",
            entities={},
            tools_used=[],
            turn_ids=["turn-1"],
            summary="Checked stock.",
            close_reason="topic_switch",
        )

        frame_calls = [c for c in calls if c.get("source_type") == "conversation_frame"]
        assert len(frame_calls) == 1, f"expected one embedding enqueue per frame, got {frame_calls!r}"


class TestFrameOnConversationClose:
    """See module docstring's ambiguity note - drives `write_episode` directly with
    `close_reason='conversation_close'` rather than a named SLA route."""

    def test_conversation_close_writes_a_frame(self, session_factory) -> None:
        from app.services.chatbot.turn.memory import write_episode

        db = session_factory()
        frame = write_episode(
            db,
            contact_respond_id="ZZT-episodes-close-1",
            domain="order",
            intent="check_outstanding",
            entities={},
            tools_used=[],
            turn_ids=["turn-1"],
            summary="Outstanding DO check for customer one.",
            close_reason="conversation_close",
        )

        assert frame.close_reason == "conversation_close"
        assert frame.status == "closed"
