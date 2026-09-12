"""AC-1001, AC-1002: the five-key session shape and the `domains` list slot.

RED until lane 1 replaces the 34-key `session_vars` bag with
`{focus, open_question, ideation, access_levels, contains_flyer}` and `Focus.domain`
becomes the list slot `Focus.domains`. Written against the `feat/chatbot-growth-dialogue`
base (HEAD ba13cabbc), which still writes the legacy 34(+3) key shape - see
`app/services/chatbot/contracts.py::SESSION_VAR_KEYS`.

Uses the same engine harness as `tests/chatbot/test_engine.py` /
`tests/chatbot/test_complete_turn.py`: `run_turn` then `complete_turn` against the blank
Postgres schema (`session_factory` fixture, `tests/chatbot/conftest.py`), never sqlite.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Focus, FocusSlot, SessionVars
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_complete_turn import _fragments
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output

FIVE_KEYS = {"focus", "open_question", "ideation", "access_levels", "contains_flyer"}


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


def _stub(monkeypatch, output, *, space_id=None):
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub",
            prompt_version=1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: output)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, **kw: {"allowed": True, "decision": "allow", "agent_name": "General"},
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: space_id)


def _session_of(session_factory) -> dict:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": CONTACT_ID},
    ).first()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _complete(session_factory, message_id: str, fragments: dict) -> dict:
    envelope = _envelope(is_test=False)
    envelope.message["message"]["messageId"] = message_id
    head = engine_mod.run_turn(envelope, session_factory=session_factory)
    assert head.status == "delegated", head.error
    done = engine_mod.complete_turn(head.turn_id, fragments, session_factory=session_factory)
    assert done.status == "done"
    return _session_of(session_factory)["variables"]


class TestFiveKeyShape:
    def test_session_holds_exactly_five_keys(self, seeded, session_factory, monkeypatch):
        """AC-1001: a business turn, a picker turn and a casual turn each leave the
        session with exactly the five keys, none of the 34 legacy ones."""
        # -- a business turn --------------------------------------------------- #
        _stub(monkeypatch, _parser_output(message_type="business_query"))
        stored = _complete(session_factory, "ZZT-shape-biz", _fragments())
        assert set(stored.keys()) == FIVE_KEYS, sorted(stored.keys())

        # -- a picker turn: an ambiguous product offer ------------------------- #
        _stub(monkeypatch, _parser_output(message_type="business_query"))
        stored = _complete(
            session_factory,
            "ZZT-shape-picker",
            _fragments(
                suggest_offer={
                    "suggest_offer": True,
                    "dym_offer": {
                        "candidates": [
                            {"code": "ZZT-A", "label": "ZZT product A"},
                            {"code": "ZZT-B", "label": "ZZT product B"},
                        ]
                    },
                }
            ),
        )
        assert set(stored.keys()) == FIVE_KEYS, sorted(stored.keys())

        # -- a casual turn ------------------------------------------------------ #
        _stub(monkeypatch, _parser_output(message_type="casual"))
        stored = _complete(session_factory, "ZZT-shape-casual", _fragments())
        assert set(stored.keys()) == FIVE_KEYS, sorted(stored.keys())

    def test_session_vars_rejects_legacy_key(self):
        """`SessionVars` is `extra=forbid` over the five keys: a legacy key such as
        `picker_domain` is rejected, not silently accepted."""
        with pytest.raises(Exception):
            SessionVars(picker_domain="master_products")


class TestFocusDomainsList:
    def test_focus_slots_and_domains_list(self):
        """AC-1002: `focus.domains` is a list slot (not `domain`), and every slot is
        `{value, set_at_turn, set_at, source}`."""
        assert "domains" in Focus.model_fields, (
            "Focus has no 'domains' slot yet - still the singular 'domain' "
            f"(fields={sorted(Focus.model_fields)})"
        )
        assert "domain" not in Focus.model_fields
        assert set(FocusSlot.model_fields) == {"value", "set_at_turn", "set_at", "source"}, (
            f"FocusSlot fields are {sorted(FocusSlot.model_fields)}"
        )
