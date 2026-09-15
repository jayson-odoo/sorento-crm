"""S3 - recall, a re-parse behind two flags (AC-1547, PLAN-chatbot-turn-rearch.md
"Turn order": "Recall is a re-parse: when the verdict says `backward_reference` and
the contact's toggle is on, G's helper fetches frames, B runs once more with the
`Episodes:` block, C runs on the second verdict. Traced as `recall`.").

`turn/memory.py::recall(contact, verdict, ctx) -> list[Frame]` does not exist yet, so
every test is RED at collection with `ModuleNotFoundError: No module named
'app.services.chatbot.turn.memory'`.

The DB-backed negative test (`TestSearchNeverReturnsAnotherContactsFrames`) runs
against the blank scratch schema (`session_factory`, same substrate as every other
`tests/chatbot/` engine test) - `conversation_frames` is an ordinary model table, no
migration-seeded data, so `create_all` already includes it.

**Ambiguity flagged to the captain**: this tester could not find a query-embedding
seam named anywhere in the PLAN/UAC for the NEW `contact_respond_id`-keyed search (the
existing, PARKED `FrameService.search_frames` embeds the query text via
`app.services.embedding_worker._embed_text_chunks`, a local import to avoid a cycle -
measured at `app/services/frame_service.py`). This file stubs THAT seam
(`app.services.embedding_worker._embed_text_chunks`) since it is the only embedding
call site this table's read path has today; if `turn/memory.py::recall` calls a
different function to embed the backward-reference query, the stub needs to move
there instead - the STRUCTURAL assertions (parser called twice, `Episodes:` block
present, `recall` trace record, the contact-id filter, the toggle-off short-circuit)
do not depend on which function embeds the query.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

# Forces collection failure now - see module docstring.
from app.services.chatbot.turn.memory import recall  # noqa: F401

from app.models.conversation_frame import ConversationFrame
from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser


def _seed_contact(session_factory, *, recall_enabled: bool) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, "
            "chatbot_recall_enabled) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :recall)"
        ),
        {
            "cid": str(CONTACT_ID),
            "phone": "+60000000004",
            "sv": json.dumps({"variables": {}}),
            "recall": recall_enabled,
        },
    )
    db.commit()


def _seed_closed_frame(session_factory, *, contact_respond_id: str, summary: str) -> None:
    db = session_factory()
    db.add(
        ConversationFrame(
            contact_id=contact_respond_id,
            contact_respond_id=contact_respond_id,
            space_id="364817",
            channel="whatsapp",
            domain="inventory",
            intent="check_stock",
            summary=summary,
            status="closed",
        )
    )
    db.commit()


class TestRecallOnBackwardReferenceAndToggleOn:
    def test_parser_runs_twice_and_second_block_carries_episodes(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, recall_enabled=True)
        for i in range(3):
            _seed_closed_frame(
                session_factory,
                contact_respond_id=str(CONTACT_ID),
                summary=f"ZZT recall summary {i}",
            )

        from app.services import embedding_worker as embedding_worker_mod

        monkeypatch.setattr(embedding_worker_mod, "_embed_text_chunks", lambda texts: [[0.1] * 8])

        user_blocks: list[str] = []

        def on_call(user_block: str) -> None:
            user_blocks.append(user_block)

        v = verdict(anaphora={"backward_reference": True})
        stub_parser(v, on_call=on_call)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert len(user_blocks) == 2, (
            f"backward_reference + recall toggle ON must re-parse once (two parser "
            f"calls total), got {len(user_blocks)}: {user_blocks!r}"
        )
        assert "Episodes:" in user_blocks[1], user_blocks[1]
        assert any("ZZT recall summary" in user_blocks[1] for _ in [0]), user_blocks[1]

    def test_trace_has_a_recall_record_listing_frame_ids(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, recall_enabled=True)
        _seed_closed_frame(session_factory, contact_respond_id=str(CONTACT_ID), summary="ZZT recall frame")

        from app.services import embedding_worker as embedding_worker_mod
        from app.models.chatbot_turn import ChatbotTurn

        monkeypatch.setattr(embedding_worker_mod, "_embed_text_chunks", lambda texts: [[0.1] * 8])

        v = verdict(anaphora={"backward_reference": True})
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        turn_row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        events = [r for r in (turn_row.trace or []) if r.get("kind") == "recall" or r.get("stage") == "recall"]
        assert events, f"no 'recall' trace record found in {turn_row.trace!r}"


class TestToggleOffNeverRecalls:
    def test_toggle_off_is_one_parse_no_episodes_block(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, recall_enabled=False)
        _seed_closed_frame(session_factory, contact_respond_id=str(CONTACT_ID), summary="ZZT should never surface")

        from app.services import embedding_worker as embedding_worker_mod

        monkeypatch.setattr(embedding_worker_mod, "_embed_text_chunks", lambda texts: [[0.1] * 8])

        user_blocks: list[str] = []

        def on_call(user_block: str) -> None:
            user_blocks.append(user_block)

        v = verdict(anaphora={"backward_reference": True})
        stub_parser(v, on_call=on_call)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert len(user_blocks) == 1, (
            f"recall toggle OFF must never re-parse, got {len(user_blocks)} calls"
        )
        assert "Episodes:" not in user_blocks[0]


class TestSearchNeverReturnsAnotherContactsFrames:
    def test_search_filters_by_this_contacts_id_and_excludes_another_contacts_frame(
        self, session_factory, monkeypatch
    ) -> None:
        from app.services.chatbot.turn.memory import recall
        from app.services import embedding_worker as embedding_worker_mod

        monkeypatch.setattr(embedding_worker_mod, "_embed_text_chunks", lambda texts: [[0.1] * 8])

        _seed_closed_frame(session_factory, contact_respond_id="ZZT-recall-me", summary="ZZT my own frame")
        _seed_closed_frame(session_factory, contact_respond_id="ZZT-recall-other", summary="ZZT someone else's frame")

        db = session_factory()
        v = verdict(anaphora={"backward_reference": True})
        frames = recall("ZZT-recall-me", v, db)

        summaries = [f.get("summary") if isinstance(f, dict) else getattr(f, "summary", None) for f in frames]
        assert any("my own frame" in (s or "") for s in summaries), summaries
        assert not any("someone else's frame" in (s or "") for s in summaries), (
            f"recall() must never return another contact's frame: {summaries!r}"
        )
