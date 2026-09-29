"""S3 - episode write on topic switch (AC-1546, PLAN-chatbot-turn-rearch.md "State:
three shelves"; the `conversation_frames` table and its `contact_respond_id` column
are already committed, S0/S1 - see `app/models/conversation_frame.py`).

**Retirement note (coordinator instruction, 26 Sep 2026, chatbot memory lane A):**
this file originally also carried `TestFrameFieldsAndEmbeddingEnqueue` and
`TestFrameOnConversationClose`, both driving `turn/memory.py::write_episode` (the
pre-lane-A writer) DIRECTLY with hand-picked field values and, in one case, a
`close_reason="conversation_close"` this lane's contract never recognises. Both are
removed: the engine no longer calls `write_episode` at all (only
`write_episode_for_reset`, `engine.py`'s sole call site), and their ground is now
covered - inverted, for the embedding case - by the lane A tests named where the old
classes used to be, below `TestThreeTopicsTwoFrames`. That class is UNCHANGED and
still green: it drives the real `engine.run_turn` seam with `topic_reset` on the
verdict, so it exercises whichever writer the engine actually calls, not a direct
signature guess.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

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


# `TestFrameFieldsAndEmbeddingEnqueue` and `TestFrameOnConversationClose` are RETIRED
# (coordinator instruction, 26 Sep 2026, chatbot memory lane A): both drove
# `turn/memory.py::write_episode` (the pre-lane-A writer) DIRECTLY, and the engine no
# longer calls it at all - `engine.py` calls only `write_episode_for_reset` now
# (grepped: the sole `write_episode` call site left in `engine.py` is
# `memory_mod.write_episode_for_reset`). Both classes are superseded by this lane's own
# contract and tests, which drive the SAME ground through the real writer:
#
# - "frame carries domain/intent/entities/tools/summary/turn_ids": superseded by
#   `tests/chatbot/test_memory_episode_digest.py::TestFrameCarriesDigestFields::
#   test_live_reset_frame_carries_summary_entities_tools_domain_intent_last_message`
#   (drives the real engine, not a direct call with hand-picked field values).
# - "embedding enqueued once per frame": INVERTED by the lane A contract (section 3:
#   "No embedding is enqueued for a frame ... S0 already stops calling it from the new
#   writer") - superseded by `tests/chatbot/test_memory_episode_boundaries.py::
#   TestNoEmbeddingEnqueued::test_write_episode_for_reset_never_enqueues_an_embedding`,
#   which asserts the OPPOSITE of what this file's version asserted, against the writer
#   actually in use.
# - "conversation_close writes a frame": superseded outright - `close_reason=
#   "conversation_close"` is not a trigger this lane recognises at all (contract
#   section 5.1's own table: "the parser says `topic_reset` (today's only trigger)" is
#   the ONLY closer; Q2's owner ruling explicitly dropped the round-1 draft's other
#   close triggers). `write_episode_for_reset` has no `close_reason` PARAMETER any
#   more - it always writes `topic_switch` - so there is no equivalent call to make.
