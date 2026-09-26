"""S0 trace + usage-log RED tests, from the UAC and the lane A contract.

Covers AC-MEM007 (the `memory` trace event's `episodes.written`/`episodes.read` and the
`level` shelf), AC-MEM010 (`understood.facts` carries `prompt_tokens` /
`completion_tokens`), AC-MEM011 (`ai_assistant_usage_logs.chatbot_turn_id`), and the
`trace_detail.compose_trace_detail` shape from contract section 6 (`memory` gains
`level`, `facts_saved`, `open_question`; `compose_trace_detail` gains `order`).

**No implementation exists yet.** `engine.py::_record_memory_trace` writes a `memory`
event with `focus` / `profile` / `episodes` / `open_question` / `written` / `dry_run`
only - no `level`, no `facts_saved`, and `episodes` carries `{before, after, writer}`
lists of frame ids, never the contract's `{read, written, writer}` shape with a
`written` dict describing what THIS turn closed. `trace_detail.compose_trace_detail`
has no `order` key and its own `_memory()` projects only `focus`/`profile`/`episodes`.
`ai_assistant_usage_logs` has no `chatbot_turn_id` column. Every test below fails on a
real assertion or a missing-column/key check, not a fixture bug.

Postgres only (`tests/chatbot/conftest.py::session_factory`, blank scratch schema).
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import (  # noqa: F401
    CONTACT_ID,
    _envelope,
    _parser_output,
    stub_access,
    stub_parser,
)


def _cid() -> str:
    return f"ZZT-memtr-{uuid.uuid4().hex[:10]}"


def _seed_contact(session_factory, contact_respond_id: str) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {
            "cid": contact_respond_id,
            "phone": f"+6011{uuid.uuid4().hex[:8]}",
            "sv": json.dumps({"variables": {}}),
        },
    )
    db.commit()


def _turn_row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _memory_records(row: ChatbotTurn) -> list[dict[str, Any]]:
    return [r for r in (row.trace or []) if isinstance(r, dict) and r.get("kind") == "memory"]


def _run(session_factory, stub_parser, stub_access, *, v: dict[str, Any], message_id: str):
    stub_access()
    stub_parser(v)
    envelope = _envelope()
    envelope.message["message"]["messageId"] = message_id
    return engine_mod.run_turn(envelope, session_factory=session_factory)


# --------------------------------------------------------------------------- #
# AC-MEM007: the `memory` trace event's episode shelf
# --------------------------------------------------------------------------- #


class TestMemoryTraceEpisodesShelf:
    def test_a_reset_turn_records_episodes_written_with_id_turn_count_close_reason_summary(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-memtr7-1")
        r2 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="order", topic_reset=True),
                   message_id="ZZT-memtr7-2")

        row = _turn_row(session_factory, r2.turn_id)
        mem_records = _memory_records(row)
        assert mem_records, "expected a memory trace record on the resetting turn"
        episodes = mem_records[-1].get("episodes") or {}

        written = episodes.get("written")
        assert isinstance(written, dict), (
            f"episodes.written must be a dict with id/turn_count/close_reason/summary "
            f"when this turn wrote a frame, got {written!r}"
        )
        assert set(written) >= {"id", "turn_count", "close_reason", "summary"}, written
        assert written["close_reason"] == "topic_switch"
        assert written["turn_count"] == 1, (
            "today's placeholder writer only ever closes the single resetting turn - "
            "the real range is the turn(s) before it"
        )
        assert isinstance(episodes.get("read"), list)

    def test_a_non_reset_turn_records_episodes_written_as_none(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-memtr7-none-1")

        row = _turn_row(session_factory, r1.turn_id)
        mem_records = _memory_records(row)
        assert mem_records
        episodes = mem_records[-1].get("episodes") or {}
        assert episodes.get("written") is None, episodes


class TestMemoryTraceLevelShelf:
    def test_default_contact_and_settings_read_level_own_none_effective_off(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        """No `respond_contacts.chatbot_memory_level` (own = None) and the system
        `chatbot_memory.enabled` default False -> effective = "off" (contract section
        2)."""
        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-memtr7-level-1")

        row = _turn_row(session_factory, r1.turn_id)
        mem_records = _memory_records(row)
        assert mem_records
        level = mem_records[-1].get("level")
        assert level == {"own": None, "effective": "off"}, level


# --------------------------------------------------------------------------- #
# AC-MEM010: understood.facts carries provider prompt/completion tokens
# --------------------------------------------------------------------------- #


class TestUnderstoodTokenFacts:
    def test_understood_facts_carry_prompt_completion_and_total_tokens(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        stub_access()
        billed_usage = {
            "provider": "openai",
            "model": "gpt-test",
            "prompt_tokens": 1234,
            "completion_tokens": 56,
            "total_tokens": 1290,
        }
        output = parser_mod.ParsedOutput(_parser_output(), usage=billed_usage)
        stub_parser(output)
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-memtr10-1"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        row = _turn_row(session_factory, result.turn_id)
        understood = next(
            r for r in row.trace if r.get("stage") == "understood"
        )
        facts = understood.get("facts") or {}
        assert facts.get("prompt_tokens") == 1234, facts
        assert facts.get("completion_tokens") == 56, facts
        assert facts.get("tokens") == 1290, facts


# --------------------------------------------------------------------------- #
# AC-MEM011: ai_assistant_usage_logs carries the turn id
# --------------------------------------------------------------------------- #


class TestUsageLogCarriesTurnId:
    def test_column_exists_and_is_populated_for_a_live_parser_call(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        column = session_factory().execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'ai_assistant_usage_logs' AND column_name = 'chatbot_turn_id'"
            )
        ).first()
        assert column is not None, (
            "ai_assistant_usage_logs needs a chatbot_turn_id VARCHAR(64) NULL column "
            "(S0 migration, contract section 7)"
        )

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        stub_access()
        billed_usage = {"provider": "openai", "model": "gpt-test", "prompt_tokens": 12, "total_tokens": 20}
        stub_parser(parser_mod.ParsedOutput(_parser_output(), usage=billed_usage))
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-memtr11-1"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        logged_turn_id = session_factory().execute(
            text(
                "SELECT chatbot_turn_id FROM ai_assistant_usage_logs "
                "WHERE feature = 'chatbot_parser' ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar()
        assert logged_turn_id == result.turn_id


# --------------------------------------------------------------------------- #
# trace_detail.compose_trace_detail: memory gains level/facts_saved/open_question;
# the response gains `order` (contract section 6)
# --------------------------------------------------------------------------- #


class TestTraceDetailShape:
    def test_memory_section_carries_level_facts_saved_and_open_question(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from app.services.chatbot.trace_detail import compose_trace_detail

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-memtr-detail-1")

        row = _turn_row(session_factory, r1.turn_id)
        detail = compose_trace_detail(row)
        memory = detail.get("memory") or {}
        assert set(memory) >= {"level", "focus", "profile", "episodes", "facts_saved", "open_question"}, memory

    def test_compose_trace_detail_carries_an_order_key(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from app.services.chatbot.trace_detail import compose_trace_detail

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-memtr-detail-2")

        row = _turn_row(session_factory, r1.turn_id)
        detail = compose_trace_detail(row)
        assert "order" in detail, (
            "compose_trace_detail must carry an 'order' key: "
            "{ticket, waited_ms, previous, next} (contract section 6)"
        )
