"""Engine findings of the reviewer pass on PR #1304 at d89110c0: B1, S1, S15, S22.

* B1: a message that only states something about the dealer has no domain, routes to
  `low_signal`, and its `profile_statements` must still be applied (Q6 "anything said
  is remembered"); an invalid value is traced as `profile_statement_dropped`.
* S22: the `memory` event's profile before is the intake snapshot, not the post-write
  one, and the casual arm records a `memory` event too.
* S1: the current message never fills an "Earlier in this conversation" slot.
* S15: a dry run from another ingress (Prompts screen, API) is not part of the console's
  range: not read as an earlier message, not swept into a console episode.

Postgres only (`tests/chatbot/conftest.py::session_factory`).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401


def _seed_contact(session_factory, *, memory_level: str | None = None) -> str:
    cid = str(CONTACT_ID)
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_memory_level) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :lvl)"
        ),
        {
            "cid": cid,
            "phone": f"+6011{uuid.uuid4().hex[:8]}",
            "sv": json.dumps({"variables": {}}),
            "lvl": memory_level,
        },
    )
    db.commit()
    return cid


def _facts(session_factory, cid: str) -> list[dict]:
    stored = session_factory().execute(
        text("SELECT chatbot_profile FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid}
    ).scalar()
    return list((stored or {}).get("facts") or [])


def _trace(session_factory, turn_id: str) -> list[dict]:
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    return [r for r in (row.trace or []) if isinstance(r, dict)]


@pytest.fixture()
def casual_lane(session_factory, system_settings_row, monkeypatch):
    """The `low_signal` lane completes in the CRM with a stubbed clarifier, exactly as
    `test_completed_lanes_switch.py` drives it."""
    from sqlalchemy.orm import object_session

    from app.services.chatbot.lanes import casual

    system_settings_row.chatbot_completed_lanes = ["low_signal"]
    object_session(system_settings_row).commit()
    monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
    monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db, **_: object())
    monkeypatch.setattr(casual, "call_clarifier", lambda config, prompt: '{"response": "Noted."}')


class TestB1StatementOnlyTurnIsRemembered:
    @pytest.mark.parametrize("message_type", ["business_query", "greeting", "other"])
    def test_a_statement_on_a_low_signal_turn_is_saved(
        self, session_factory, stub_parser, stub_access, casual_lane, message_type
    ) -> None:
        cid = _seed_contact(session_factory)
        stub_access()
        stub_parser(
            verdict(
                message_type=message_type,
                domain_hint=None,
                intent_hint=None,
                entities=[],
                profile_statements=[{"key": "role", "value": "purchaser"}],
            )
        )
        envelope = _envelope()
        envelope.message["message"]["message"]["text"] = "I'm the purchaser here"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.branch_kind == "low_signal"
        facts = _facts(session_factory, cid)
        assert any(f.get("key") == "role" and f.get("value") == "purchaser" for f in facts), facts

    def test_an_invalid_value_is_traced_as_dropped(
        self, session_factory, stub_parser, stub_access, casual_lane
    ) -> None:
        cid = _seed_contact(session_factory)
        stub_access()
        stub_parser(
            verdict(
                message_type="other",
                domain_hint=None,
                intent_hint=None,
                entities=[],
                profile_statements=[{"key": "role", "value": "astronaut"}],
            )
        )
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert not any(f.get("key") == "role" for f in _facts(session_factory, cid))
        dropped = [r for r in _trace(session_factory, result.turn_id) if r.get("kind") == "profile_statement_dropped"]
        assert dropped and dropped[0].get("key") == "role", dropped
        assert dropped[0].get("reason") == "invalid value", dropped


class TestS22MemoryEvent:
    def test_the_casual_arm_records_a_memory_event_with_the_intake_snapshot(
        self, session_factory, stub_parser, stub_access, casual_lane
    ) -> None:
        _seed_contact(session_factory)
        stub_access()
        stub_parser(
            verdict(
                message_type="other",
                domain_hint=None,
                intent_hint=None,
                entities=[],
                profile_statements=[{"key": "role", "value": "purchaser"}],
            )
        )
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        events = [r for r in _trace(session_factory, result.turn_id) if r.get("kind") == "memory"]
        assert len(events) == 1, events
        profile = events[0]["profile"]
        assert profile["before"]["facts_count"] == 0, profile
        assert profile["after"]["facts_count"] == 1, profile
        assert {"key": "role", "source": "stated"} in events[0]["facts_saved"]


def _block_capture(stub_parser, output):
    seen: list[str] = []
    stub_parser(output, on_call=seen.append)
    return seen


class TestS1CurrentMessageIsNotEarlier:
    def test_the_second_turn_lists_only_the_first_as_earlier(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, memory_level="conversation")
        stub_access()
        out = verdict(domain_hint="inventory", entities=[entity("SRTWB1455")])
        first = _envelope()
        first.message["message"]["messageId"] = "ZZT-r2-s1-a"
        first.message["message"]["message"]["text"] = "first message aaa"
        stub_parser(out)
        engine_mod.run_turn(first, session_factory=session_factory)

        seen = _block_capture(stub_parser, out)
        second = _envelope()
        second.message["message"]["messageId"] = "ZZT-r2-s1-b"
        second.message["message"]["message"]["text"] = "second message bbb"
        engine_mod.run_turn(second, session_factory=session_factory)

        block = seen[-1]
        before_current = block.split("Current user message:", 1)[0]
        # The first message is printed once (as an exchange, which the L3 layer does
        # not repeat as an earlier message); the current one only as the current one.
        assert "first message aaa" in before_current, block
        assert "second message bbb" not in before_current, block


class TestS15ConsoleRangeIsConsoleOnly:
    def _seed_turn(self, session_factory, cid: str, *, ingress: str, text_value: str, minutes_ago: int) -> str:
        db = session_factory()
        turn_id = str(uuid.uuid4())
        when = datetime.now() - timedelta(minutes=minutes_ago)
        db.add(
            ChatbotTurn(
                id=turn_id,
                contact_respond_id=cid,
                message_id=f"ZZT-r2-s15-{uuid.uuid4().hex[:8]}",
                is_test=True,
                ingress=ingress,
                status="done",
                stage="sent",
                branch_kind="business_query",
                envelope={"message": {"message": {"message": {"type": "text", "text": text_value}}}},
                created_at=when,
            )
        )
        db.commit()
        return turn_id

    def test_a_prompts_screen_dry_run_is_not_swept_into_a_console_episode(self, session_factory) -> None:
        from app.services.chatbot.turn import memory as memory_mod

        cid = _seed_contact(session_factory)
        console_turn = self._seed_turn(session_factory, cid, ingress="console", text_value="console aaa", minutes_ago=5)
        other_turn = self._seed_turn(session_factory, cid, ingress="webhook", text_value="prompts bbb", minutes_ago=4)
        reset = self._seed_turn(session_factory, cid, ingress="console", text_value="console reset", minutes_ago=1)

        db = session_factory()
        frame = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=True, resetting_turn_id=reset
        )
        assert frame is not None
        assert console_turn in frame.turn_ids
        assert other_turn not in frame.turn_ids, frame.turn_ids

    def test_a_console_turn_does_not_read_another_ingress_dry_run_as_earlier(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        cid = _seed_contact(session_factory, memory_level="conversation")
        self._seed_turn(session_factory, cid, ingress="webhook", text_value="prompts screen ccc", minutes_ago=3)
        self._seed_turn(session_factory, cid, ingress="console", text_value="console ddd", minutes_ago=2)
        stub_access()
        seen = _block_capture(stub_parser, verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]))
        envelope = _envelope(is_test=True, ingress="console")
        envelope.message["message"]["message"]["text"] = "console now"
        engine_mod.run_turn(envelope, session_factory=session_factory)

        block = seen[-1]
        assert "console ddd" in block, block
        assert "prompts screen ccc" not in block, block
