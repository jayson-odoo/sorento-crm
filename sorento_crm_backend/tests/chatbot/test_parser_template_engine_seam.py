"""PARSER-TEMPLATE F1-E: the engine passes `template=parser_config.template` into
`_as_a_stock_ask_by_its_own_words` for a stock_availability_only contact (seam guard)."""
from __future__ import annotations

import json

import pytest

import app.main  # noqa: F401  isort:skip
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import trace as trace_mod
from app.services.chatbot import turn_runtime
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_spec_over_held import _message
from tests.chatbot.test_engine import _envelope, _parser_output, seeded, stub_access  # noqa: F401

CODE = "ZZTPL100"


def _turn(session_factory, stub_access, monkeypatch, *, template: bool) -> list:
    verdict = _parser_output(
        intent_hint="check_incoming", domain_hint="incoming", user_goal="ask",
        entities=[{"raw": CODE, "hint": "product", "canonical_code": CODE, "quantity": 10,
                   "current_message": True, "confident": True}],
    )
    traces: list = []
    real = trace_mod.TurnTrace.persisted

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k",
            closed_lists=True, template=template,
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: verdict)
    monkeypatch.setattr(trace_mod.TurnTrace, "persisted", lambda self: (traces.append(real(self)) or traces[-1]))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: True)
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    engine_mod.run_turn(_envelope(message=_message(f"{CODE} x 10", 0)), session_factory=session_factory)
    return traces[-1] if traces else []


def test_the_regex_stands_down_for_a_dealer_under_the_template(session_factory, seeded, stub_access, monkeypatch):
    records = _turn(session_factory, stub_access, monkeypatch, template=True)
    assert "stock_ask_by_its_own_words" not in json.dumps(records, default=str)


def test_the_regex_still_overrides_to_stock_without_the_template(session_factory, seeded, stub_access, monkeypatch):
    records = _turn(session_factory, stub_access, monkeypatch, template=False)
    assert "stock_ask_by_its_own_words" in json.dumps(records, default=str)
