"""AC-1027: shadow parse - a second `chatbot.turns` row, `ingress = "shadow"`.

When `system_settings.chatbot_parser_shadow_version` is set, every real turn also runs
that registry version of the parser through a SECOND, fake provider and stores a
`chatbot.turns` row with `shadow_of` = the live turn's `message_id`, no reply, no session
write, no send. A shadow failure never touches the live turn. When the setting is null,
nothing extra runs.

RED: nothing in `engine.py` reads `chatbot_parser_shadow_version` or enqueues a shadow
job yet - the column does not exist on `SystemSetting` either, so this test monkeypatches
the CLASS attribute (a plain Python class attribute is a legitimate stand-in for a column
that is not there yet: `getattr(row, "chatbot_parser_shadow_version", None)` reads through
to it) rather than depending on a migration this lane has not written.

Uses the same seam as `tests/chatbot/test_engine.py`: `run_turn` then `complete_turn`
against the blank Postgres schema, with the provider stubbed.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_complete_turn import _fragments
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output

SHADOW_VERSION = "chatbot_semantic_parser@shadow-3"


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    return db


@pytest.fixture()
def shadow_enabled(monkeypatch):
    monkeypatch.setattr(SystemSetting, "chatbot_parser_shadow_version", SHADOW_VERSION, raising=False)
    return SHADOW_VERSION


def _stub(monkeypatch, output):
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: output)
    monkeypatch.setattr(
        engine_mod, "check_access",
        lambda db, **kw: {"allowed": True, "decision": "allow", "agent_name": "General"},
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: None)


class TestShadowParseRunsAlongsideTheLiveTurn:
    def test_a_shadow_row_is_written_when_the_setting_is_on(
        self, seeded, session_factory, monkeypatch, shadow_enabled
    ):
        _stub(monkeypatch, _parser_output(message_type="business_query"))
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = "ZZT-shadow-1"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert head.status == "delegated", head.error
        engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)

        db = session_factory()
        shadow_rows = (
            db.query(ChatbotTurn).filter(ChatbotTurn.ingress == "shadow").all()
        )
        assert len(shadow_rows) == 1, (
            f"expected exactly one shadow row once {shadow_enabled!r} is set, got "
            f"{len(shadow_rows)}"
        )
        shadow = shadow_rows[0]
        assert shadow.shadow_of == "ZZT-shadow-1"
        assert shadow.response is None

        live_row = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.message_id == "ZZT-shadow-1", ChatbotTurn.ingress == "webhook")
            .one()
        )
        assert live_row.id != shadow.id

    def test_no_shadow_row_when_the_setting_is_null(self, seeded, session_factory, monkeypatch):
        _stub(monkeypatch, _parser_output(message_type="business_query"))
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = "ZZT-shadow-off"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)
        engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)

        db = session_factory()
        shadow_rows = db.query(ChatbotTurn).filter(ChatbotTurn.ingress == "shadow").all()
        assert shadow_rows == []

    def test_a_shadow_provider_failure_never_touches_the_live_turn(
        self, seeded, session_factory, monkeypatch, shadow_enabled
    ):
        _stub(monkeypatch, _parser_output(message_type="business_query"))
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = "ZZT-shadow-fail"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)
        done = engine_mod.complete_turn(head.turn_id, _fragments(), session_factory=session_factory)
        assert done.status == "done"

        db = session_factory()
        shadow_rows = db.query(ChatbotTurn).filter(ChatbotTurn.ingress == "shadow").all()
        assert len(shadow_rows) == 1
        assert shadow_rows[0].status == "failed"

        live_row = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.message_id == "ZZT-shadow-fail", ChatbotTurn.ingress == "webhook")
            .one()
        )
        assert live_row.status == "done"
