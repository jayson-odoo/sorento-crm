"""LEAN: the parser's reasoning effort is a stored setting, off by default, sent only when set.

`system_settings.chatbot_parser_reasoning_effort` = 'off' (default) | 'low' only for now (round 1 review S1: minimal, medium and high are unmeasured
and medium / high risk exhausting max_completion_tokens 2048); anything else reads as 'off'. `parser.resolve_config` reads it on every call (no cache, like
`chatbot_closed_lists_mode`), carries it as `ParserConfig.reasoning_effort`, and `parse` puts it on the
OpenAI request ONLY when it is not 'off'. The SDK kwarg pinned is `reasoning_effort="low"` on
`client.chat.completions.create` (the codebase uses Chat Completions: `_create_chat_completion`,
app/services/llm_provider.py:323-333 hands its kwargs straight to `client.chat.completions.create`;
`OpenAIProvider.chat` builds them at :392-439). No network: the OpenAI client is a recorder.
Assumed names: `SystemSetting.chatbot_parser_reasoning_effort`, `ParserConfig.reasoning_effort`, the
`understood` trace fact `reasoning_effort`, the usage key `reasoning_tokens`.
"""
from __future__ import annotations

import glob
import json
import os
import types
import uuid
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services import ai_prompt_registry
from app.services import chatbot_prompt_vars as pv
from app.services import llm_provider
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access  # noqa: F401

def _full_emission() -> dict[str, Any]:
    """A complete emission for the real `parse`: `_parser_output` plus the top-level keys it lacks."""
    return {**_parser_output(), "asks": None, "topic_reset": False}


TEMPLATE = "Rules for {{current_date}}."


@pytest.fixture(autouse=True)
def _fresh_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _seed_prompt(session_factory, monkeypatch, provider: str = "openai") -> None:
    from app.services import ai_assistant_service

    db = session_factory()
    v = AIPromptVersion(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, version=1, type="text",
                        template=TEMPLATE, variables=["current_date"])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, label="production", version_id=v.id))
    db.commit()
    cfg = types.SimpleNamespace(provider=provider, model="gpt-test")
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: types.SimpleNamespace(get=lambda: cfg))
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")


def _set_effort(session_factory, value: str | None) -> None:
    assert hasattr(SystemSetting, "chatbot_parser_reasoning_effort"), (
        "SystemSetting.chatbot_parser_reasoning_effort does not exist yet")
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    if value is not None:
        row.chatbot_parser_reasoning_effort = value
    db.commit()


def _config(session_factory):
    db = session_factory()
    try:
        return parser_mod.resolve_config(db, current_date="2026-10-21")
    finally:
        db.close()


class _OpenAIRecorder:
    """Stands in for the OpenAI SDK client: records each `chat.completions.create(**kw)`."""

    def __init__(self, reasoning_tokens: int | None = None):
        self.sent: list[dict[str, Any]] = []
        self.reasoning_tokens = reasoning_tokens
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        details = None if self.reasoning_tokens is None else types.SimpleNamespace(reasoning_tokens=self.reasoning_tokens)
        usage = types.SimpleNamespace(prompt_tokens=100, completion_tokens=40, total_tokens=140,
                                      prompt_tokens_details=types.SimpleNamespace(cached_tokens=0),
                                      completion_tokens_details=details)
        message = types.SimpleNamespace(content=json.dumps(_full_emission()), tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)], usage=usage, model="gpt-test")


@pytest.fixture
def openai(monkeypatch):
    rec = _OpenAIRecorder()
    monkeypatch.setattr(llm_provider.OpenAIProvider, "_client", lambda self, **kw: rec)
    return rec


def _parse(session_factory):
    return parser_mod.parse(_config(session_factory), "Current user message: hi")


# ---- default / off ----

def test_default_sends_no_reasoning_key_and_config_says_off(session_factory, monkeypatch, openai):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, None)  # column left at its default
    config = _config(session_factory)
    assert config.reasoning_effort == "off", config
    _parse(session_factory)
    assert openai.sent and all("reasoning_effort" not in kw and "reasoning" not in kw for kw in openai.sent), openai.sent


def test_explicit_off_sends_no_reasoning_key(session_factory, monkeypatch, openai):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, "off")
    assert _config(session_factory).reasoning_effort == "off"
    _parse(session_factory)
    assert openai.sent and all("reasoning_effort" not in kw and "reasoning" not in kw for kw in openai.sent), openai.sent


# ---- set ----

@pytest.mark.parametrize("effort", ["low"])
def test_a_set_effort_rides_the_openai_request(session_factory, monkeypatch, openai, effort):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, effort)
    assert _config(session_factory).reasoning_effort == effort
    _parse(session_factory)
    assert [kw.get("reasoning_effort") for kw in openai.sent] == [effort], openai.sent


def test_flipping_the_row_between_two_parses_reaches_the_next_call(session_factory, monkeypatch, openai):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, "off")
    _parse(session_factory)
    _set_effort(session_factory, "low")
    _parse(session_factory)
    _set_effort(session_factory, "off")
    _parse(session_factory)
    assert [kw.get("reasoning_effort") for kw in openai.sent] == [None, "low", None], openai.sent


@pytest.mark.parametrize("junk", ["turbo", "LOW ", "", "none", "xhigh", "minimal", "medium", "high"])
def test_an_unknown_value_reads_as_off(session_factory, monkeypatch, openai, junk):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, junk)
    assert _config(session_factory).reasoning_effort == "off"
    _parse(session_factory)
    assert openai.sent and all("reasoning_effort" not in kw for kw in openai.sent), openai.sent


# ---- providers ----

def test_a_non_openai_provider_never_receives_the_openai_kwarg(session_factory, monkeypatch):
    _seed_prompt(session_factory, monkeypatch, provider="gemini")
    _set_effort(session_factory, "low")
    seen: list[dict[str, Any]] = []

    class _Gemini:
        # the real GeminiProvider.chat signature: no reasoning parameter, no **kwargs
        def chat(self, messages, *, tools=None, temperature=0.0, model=None, max_tokens=None, images=None,
                 response_format=None, json_schema=None, json_schema_name=None, timeout=None,
                 prompt_cache_key=None):
            seen.append({"called": True})
            return types.SimpleNamespace(content=json.dumps(_full_emission()), prompt_tokens=1,
                                         completion_tokens=1, total_tokens=2, cached_tokens=0, tool_calls=[])

    monkeypatch.setattr(llm_provider, "get_provider", lambda provider, api_key, model=None: _Gemini())
    config = _config(session_factory)
    assert config.provider == "gemini"
    assert config.reasoning_effort == "low"  # the setting is read and carried, just never sent here
    parser_mod.parse(config, "Current user message: hi")
    assert seen == [{"called": True}]


# ---- usage ----

def test_usage_records_the_reasoning_tokens_the_provider_reported(session_factory, monkeypatch):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, "low")
    rec = _OpenAIRecorder(reasoning_tokens=37)
    monkeypatch.setattr(llm_provider.OpenAIProvider, "_client", lambda self, **kw: rec)
    out = _parse(session_factory)
    assert out.usage.get("reasoning_tokens") == 37, out.usage


def test_usage_reasoning_tokens_is_none_when_the_provider_reports_none(session_factory, monkeypatch, openai):
    _seed_prompt(session_factory, monkeypatch)
    out = _parse(session_factory)
    assert "reasoning_tokens" in out.usage and out.usage["reasoning_tokens"] is None, out.usage


# ---- the trace ----

def _message(text: str) -> dict[str, Any]:
    return {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-re-{uuid.uuid4().hex[:8]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": text}}}


def _traced_effort(session_factory, stub_access, monkeypatch) -> Any:
    monkeypatch.setattr(parser_mod, "parse", lambda config, block: _parser_output(
        intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[]))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    result = engine_mod.run_turn(_envelope(message=_message("zzqwerty")), session_factory=session_factory)
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    facts = next(r["facts"] for r in (row.trace or []) if isinstance(r, dict) and r.get("stage") == "understood")
    assert "reasoning_effort" in facts, facts
    return facts["reasoning_effort"]


def test_the_trace_records_off_by_default(session_factory, seeded, stub_access, monkeypatch):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, None)
    assert _traced_effort(session_factory, stub_access, monkeypatch) == "off"


def test_the_trace_records_the_effort_that_was_set(session_factory, seeded, stub_access, monkeypatch):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, "low")
    assert _traced_effort(session_factory, stub_access, monkeypatch) == "low"


# ---- the column and its migration ----

def test_the_model_column_defaults_to_off():
    col = getattr(SystemSetting, "chatbot_parser_reasoning_effort", None)
    assert col is not None, "SystemSetting.chatbot_parser_reasoning_effort does not exist yet"
    assert col.property.columns[0].nullable is False
    assert "off" in str(col.property.columns[0].server_default.arg)


def test_a_migration_adds_the_column_with_default_off():
    versions = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions", "*.py")
    hits = [p for p in glob.glob(versions) if "chatbot_parser_reasoning_effort" in open(p, encoding="utf-8").read()]
    assert len(hits) == 1, hits
    text = open(hits[0], encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS chatbot_parser_reasoning_effort" in text, text
    assert "DEFAULT 'off'" in text and "NOT NULL" in text, text


# ---- review round: B1 adapter memory, S3 reasoning tokens in the trace, N1 trace = what was sent, N2 cassette ----

class _Refusal(Exception):
    def __init__(self, msg, param, code):
        super().__init__(msg)
        self.param, self.code = param, code


class _Gpt5Client:
    """Refuses `temperature` whenever `reasoning_effort` is present (accepts it otherwise);
    optionally refuses `reasoning_effort` itself."""

    def __init__(self, refuse_effort: bool = False):
        self.sent: list[dict[str, Any]] = []
        self.refuse_effort = refuse_effort
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.sent.append(dict(kw))
        if kw.get("reasoning_effort") and self.refuse_effort:
            raise _Refusal("Error code: 400 - Unsupported parameter: 'reasoning_effort' is not supported with this model.",
                           "reasoning_effort", "unsupported_parameter")
        if kw.get("reasoning_effort") and "temperature" in kw:
            raise _Refusal("Error code: 400 - Unsupported value: 'temperature' does not support 0.0 with this model.",
                           "temperature", "unsupported_value")
        usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2,
                                      prompt_tokens_details=None, completion_tokens_details=None)
        msg = types.SimpleNamespace(content="{}", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=usage)


def _drive(monkeypatch, client, efforts, model="gpt-5.4-mini-zz"):
    monkeypatch.setattr(llm_provider, "_OPENAI_REJECTED_PARAMS", {})
    provider = llm_provider.OpenAIProvider(api_key="sk-x", default_model=model)
    monkeypatch.setattr(provider, "_client", lambda **kw: client)
    finals = []
    for effort in efforts:
        before = len(client.sent)
        provider.chat([{"role": "user", "content": "hi"}], temperature=0.0, model=model, max_tokens=2048,
                      reasoning_effort=None if effort == "off" else effort)
        finals.append(client.sent[-1])
        assert len(client.sent) > before
    return finals


def test_b1_a_refused_temperature_on_a_low_call_does_not_strip_it_from_later_off_calls(monkeypatch):
    finals = _drive(monkeypatch, _Gpt5Client(), ["off", "low", "off"])
    assert [f.get("temperature") for f in finals] == [0.0, None, 0.0], finals
    assert [f.get("reasoning_effort") for f in finals] == [None, "low", None], finals


def test_b1_a_refused_reasoning_effort_does_not_strip_anything_from_later_off_calls(monkeypatch):
    finals = _drive(monkeypatch, _Gpt5Client(refuse_effort=True), ["low", "off"])
    assert "reasoning_effort" not in finals[0], finals
    assert finals[1].get("temperature") == 0.0 and "reasoning_effort" not in finals[1], finals
    assert finals[1].get("max_completion_tokens") == 2048, finals


def _trace_facts(session_factory, stub_access, monkeypatch, output) -> dict[str, Any]:
    monkeypatch.setattr(parser_mod, "parse", lambda config, block: output)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    result = engine_mod.run_turn(_envelope(message=_message("zzqwerty")), session_factory=session_factory)
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    return next(r["facts"] for r in (row.trace or []) if isinstance(r, dict) and r.get("stage") == "understood")


def test_s3_the_trace_records_the_reasoning_tokens_the_provider_reported(session_factory, seeded, stub_access, monkeypatch):
    _seed_prompt(session_factory, monkeypatch)
    _set_effort(session_factory, "low")
    usage = {"provider": "openai", "model": "gpt-test", "prompt_tokens": 100, "completion_tokens": 40,
             "total_tokens": 140, "cached_tokens": 0, "reasoning_tokens": 37}
    output = parser_mod.ParsedOutput(_parser_output(intent_hint="check_stock", domain_hint="inventory",
                                                    user_goal="ask", entities=[]), usage)
    facts = _trace_facts(session_factory, stub_access, monkeypatch, output)
    assert facts.get("reasoning_tokens") == 37, facts


def test_n1_the_trace_says_off_when_the_provider_is_not_openai_even_if_the_row_says_low(session_factory, seeded, stub_access, monkeypatch):
    _seed_prompt(session_factory, monkeypatch, provider="gemini")
    _set_effort(session_factory, "low")
    output = _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[])
    facts = _trace_facts(session_factory, stub_access, monkeypatch, output)
    assert facts.get("reasoning_effort") == "off", facts


def test_n2_the_cassette_key_separates_an_effort_from_none():
    from app.services import llm_cassette

    base = {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]}
    assert llm_cassette.chat_key({**base, "reasoning_effort": "low"}) != llm_cassette.chat_key(base)
    # an off call (no effort, or None) keeps the key every existing recording was made under
    assert llm_cassette.chat_key({**base, "reasoning_effort": None}) == llm_cassette.chat_key(base)
