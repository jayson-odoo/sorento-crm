"""PARSER-MAX-TOKENS: the parser's answer budget fits a long stock list, is a stored setting,
and a call that runs out of room still writes its usage row.

Prod turn 5ad8f394 (29 Oct 2026): a stock check for 63 codes stopped on
"Gemini stopped early: MAX_TOKENS (answer 4081 tokens)" at the old 2048 cap (4,097 on
Gemini 3.x with thinking and headroom); ~90 output tokens per item puts 63 items near 5,500.
The codes below are made up (the repo is public). Nothing here calls a provider: Gemini's
`httpx.request` and the OpenAI SDK client are fakes that honour the cap they are sent.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import types
from typing import Any

import pytest

from app.models.user import SystemSetting
from app.services import llm_provider
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_engine import _envelope, stub_access  # noqa: F401
from tests.chatbot.test_memory_trace_and_usage import CONTACT_ID, _seed_contact

#: What the fake model needs to answer the long list (output tokens, thinking excluded).
LONG_ANSWER_TOKENS = 5500
#: Gemini 3.x flash-lite thinking with no effort set (`llm_provider._gemini_thinking_budget`).
FLASH_LITE_THINKING = 1


def _stock_check_block(lines: int = 63) -> str:
    items = "\n".join(f"ZZQ{n:03d}-{(n * 7) % 90 + 10}X{(n * 3) % 50 + 10} x {n % 9 + 1}" for n in range(1, lines + 1))
    return f"Current user message: check stock please\n{items}"


def _emission() -> str:
    return json.dumps({key: None for key in parser_mod.DECLARED_KEYS})


def _config(**overrides: Any) -> parser_mod.ParserConfig:
    base = dict(system_prompt="s", prompt_version=1, provider="gemini", model="gemini-3.5-flash-lite", api_key="k")
    return parser_mod.ParserConfig(**{**base, **overrides})


class _Response:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


def _gemini(monkeypatch, *, needs: int = LONG_ANSWER_TOKENS) -> list[dict]:
    """A Gemini that spends `FLASH_LITE_THINKING` thinking and `needs` answering, out of the
    `maxOutputTokens` it is sent: short of room it stops on MAX_TOKENS, as the real one did."""
    sent: list[dict] = []

    def transport(method, url, **kwargs):
        body = kwargs["json"]
        sent.append(body)
        cap = body["generationConfig"]["maxOutputTokens"]
        if cap < FLASH_LITE_THINKING + needs:
            usage = {"promptTokenCount": 9000, "thoughtsTokenCount": FLASH_LITE_THINKING,
                     "candidatesTokenCount": cap - FLASH_LITE_THINKING, "totalTokenCount": 9000 + cap}
            return _Response({"candidates": [{"content": {"parts": [{"text": _emission()[:40]}]},
                                              "finishReason": "MAX_TOKENS"}], "usageMetadata": usage})
        usage = {"promptTokenCount": 9000, "thoughtsTokenCount": FLASH_LITE_THINKING, "candidatesTokenCount": needs,
                 "totalTokenCount": 9000 + FLASH_LITE_THINKING + needs}
        return _Response({"candidates": [{"content": {"parts": [{"text": _emission()}]}, "finishReason": "STOP"}],
                          "usageMetadata": usage})

    monkeypatch.setattr("httpx.request", transport)
    # No explicit context cache in a unit test: every call goes straight to generateContent.
    monkeypatch.setattr(llm_provider.GeminiProvider, "_cached_content", lambda self, *a, **k: None)
    return sent


class _OpenAI:
    """Stands in for the OpenAI SDK client; answers whole only when the cap leaves room."""

    def __init__(self, needs: int = LONG_ANSWER_TOKENS) -> None:
        self.sent: list[dict[str, Any]] = []
        self.needs = needs
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        cap = kw.get("max_completion_tokens") or kw.get("max_tokens") or 0
        whole = cap >= self.needs
        content = _emission() if whole else _emission()[:40]
        usage = types.SimpleNamespace(prompt_tokens=9000, completion_tokens=min(cap, self.needs),
                                      total_tokens=9000 + min(cap, self.needs),
                                      prompt_tokens_details=types.SimpleNamespace(cached_tokens=0),
                                      completion_tokens_details=None)
        message = types.SimpleNamespace(content=content, tool_calls=None)
        choice = types.SimpleNamespace(message=message, finish_reason="stop" if whole else "length")
        return types.SimpleNamespace(choices=[choice], usage=usage, model="gpt-5.4-mini")


@pytest.fixture
def openai(monkeypatch):
    client = _OpenAI()
    monkeypatch.setattr(llm_provider.OpenAIProvider, "_client", lambda self, **kw: client)
    return client


# --------------------------------------------------------------------------- #
# AC-1 / AC-2: a 63-line stock check fits the default budget on both providers
# --------------------------------------------------------------------------- #


def test_the_default_answer_budget_is_8192():
    assert parser_mod.PARSER_MAX_TOKENS == 8192
    assert _config().max_output_tokens == 8192


def test_a_63_line_stock_check_fits_on_gemini(monkeypatch):
    sent = _gemini(monkeypatch)
    out = parser_mod.parse(_config(), _stock_check_block())
    assert set(out) >= parser_mod.DECLARED_KEYS - parser_mod.TOLERATED_ABSENT
    # The answer budget, plus flash-lite's 1 thinking token and the 3.x answer headroom.
    assert [b["generationConfig"]["maxOutputTokens"] for b in sent] == [
        8192 + FLASH_LITE_THINKING + llm_provider.GEMINI_3_ANSWER_HEADROOM
    ]
    assert out.usage["completion_tokens"] == FLASH_LITE_THINKING + LONG_ANSWER_TOKENS


def test_a_63_line_stock_check_fits_on_openai(openai):
    out = parser_mod.parse(_config(provider="openai", model="gpt-5.4-mini"), _stock_check_block())
    assert set(out) >= parser_mod.DECLARED_KEYS - parser_mod.TOLERATED_ABSENT
    assert [kw.get("max_completion_tokens") for kw in openai.sent] == [8192]


# --------------------------------------------------------------------------- #
# AC-3 / AC-4: system_settings.chatbot_parser_max_output_tokens, read per parse
# --------------------------------------------------------------------------- #


def _set_cap(session_factory, value: int | None) -> None:
    assert hasattr(SystemSetting, "chatbot_parser_max_output_tokens"), (
        "SystemSetting.chatbot_parser_max_output_tokens does not exist yet")
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    if value is not None:
        row.chatbot_parser_max_output_tokens = value
    db.commit()


def _read_cap(session_factory) -> int:
    db = session_factory()
    try:
        return parser_mod.max_output_tokens_setting(db)
    finally:
        db.close()


def test_no_settings_row_reads_the_default(session_factory):
    assert session_factory().query(SystemSetting).count() == 0
    assert _read_cap(session_factory) == 8192


def test_the_column_default_reads_the_default(session_factory):
    _set_cap(session_factory, None)
    assert _read_cap(session_factory) == 8192


@pytest.mark.parametrize("stored", [1024, 4096, 16000, 32768])
def test_a_stored_value_in_range_is_honoured(session_factory, stored):
    _set_cap(session_factory, stored)
    assert _read_cap(session_factory) == stored


@pytest.mark.parametrize("stored, read", [(1, 1024), (0, 1024), (-5, 1024), (1023, 1024), (32769, 32768), (100000, 32768)])
def test_a_stored_value_out_of_range_is_clamped_and_logged(session_factory, caplog, stored, read):
    _set_cap(session_factory, stored)
    with caplog.at_level(logging.WARNING, logger=parser_mod.__name__):
        assert _read_cap(session_factory) == read
    assert any("chatbot_parser_max_output_tokens" in r.getMessage() for r in caplog.records), caplog.records


def test_resolve_config_carries_the_stored_value_to_both_providers(session_factory, monkeypatch, openai):
    """The setting reaches the request on OpenAI as `max_completion_tokens` and on Gemini as the
    answer part of `maxOutputTokens`; a flip reaches the next parse (no cache, like the effort)."""
    from app.services import ai_assistant_service, ai_prompt_registry
    from app.services import chatbot_prompt_vars as pv
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    import uuid

    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    db = session_factory()
    v = AIPromptVersion(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, version=1, type="text",
                        template="Rules for {{current_date}}.", variables=["current_date"])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, label="production", version_id=v.id))
    db.commit()
    provider = {"name": "openai", "model": "gpt-5.4-mini"}
    monkeypatch.setattr(
        ai_assistant_service, "AIAssistantConfigService",
        lambda d: types.SimpleNamespace(get=lambda: types.SimpleNamespace(provider=provider["name"],
                                                                          model=provider["model"])),
    )
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")

    def parse_once():
        cfg_db = session_factory()
        try:
            config = parser_mod.resolve_config(cfg_db, current_date="2026-10-29")
        finally:
            cfg_db.close()
        return config, parser_mod.parse(config, _stock_check_block())

    try:
        _set_cap(session_factory, 16000)
        config, _ = parse_once()
        assert config.max_output_tokens == 16000
        _set_cap(session_factory, 9000)
        config, _ = parse_once()
        assert config.max_output_tokens == 9000
        assert [kw.get("max_completion_tokens") for kw in openai.sent] == [16000, 9000]

        provider.update(name="gemini", model="gemini-3.5-flash-lite")
        sent = _gemini(monkeypatch)
        config, _ = parse_once()
        assert config.provider == "gemini"
        assert [b["generationConfig"]["maxOutputTokens"] for b in sent] == [
            9000 + FLASH_LITE_THINKING + llm_provider.GEMINI_3_ANSWER_HEADROOM
        ]
    finally:
        ai_prompt_registry.bust_cache()
        pv.clear_cache()


def test_the_model_column_defaults_to_8192():
    col = getattr(SystemSetting, "chatbot_parser_max_output_tokens", None)
    assert col is not None, "SystemSetting.chatbot_parser_max_output_tokens does not exist yet"
    assert col.property.columns[0].nullable is False
    assert "8192" in str(col.property.columns[0].server_default.arg)


def test_a_migration_adds_the_column_with_default_8192():
    versions = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions", "*.py")
    hits = [p for p in glob.glob(versions) if "chatbot_parser_max_output_tokens" in open(p, encoding="utf-8").read()]
    assert len(hits) == 1, hits
    text = open(hits[0], encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS chatbot_parser_max_output_tokens" in text, text
    assert "DEFAULT 8192" in text and "NOT NULL" in text, text


# --------------------------------------------------------------------------- #
# AC-5 / AC-6: a call cut short on the cap still bills, and the reply is unchanged
# --------------------------------------------------------------------------- #


def test_a_gemini_answer_cut_short_raises_with_what_it_billed(monkeypatch):
    _gemini(monkeypatch, needs=20000)
    with pytest.raises(llm_provider.ResponseTruncated) as caught:
        llm_provider.GeminiProvider("k").chat(
            [{"role": "user", "content": "hi"}], model="gemini-3.5-flash-lite", max_tokens=8192
        )
    assert isinstance(caught.value, RuntimeError)
    # The operator-facing words are unchanged.
    assert str(caught.value).startswith("Gemini stopped early: MAX_TOKENS (response truncated; thinking 1, answer ")
    result = caught.value.result
    assert result.prompt_tokens == 9000
    assert result.completion_tokens == 8192 + llm_provider.GEMINI_3_ANSWER_HEADROOM + FLASH_LITE_THINKING
    assert result.total_tokens == 9000 + result.completion_tokens


def test_a_parse_cut_short_carries_its_usage(monkeypatch):
    _gemini(monkeypatch, needs=20000)
    with pytest.raises(parser_mod.ParserError) as caught:
        parser_mod.parse(_config(), _stock_check_block(200))
    usage = caught.value.usage
    cap = 8192 + FLASH_LITE_THINKING + llm_provider.GEMINI_3_ANSWER_HEADROOM
    assert usage["provider"] == "gemini" and usage["model"] == "gemini-3.5-flash-lite", usage
    assert usage["prompt_tokens"] == 9000 and usage["completion_tokens"] == cap, usage
    assert usage["total_tokens"] == 9000 + cap, usage
    assert isinstance(usage["latency_ms"], int) and caught.value.latency_ms == usage["latency_ms"]
    assert not caught.value.rate_limited
    assert "MAX_TOKENS" in str(caught.value)


def test_a_turn_cut_short_writes_an_unanswered_usage_row_and_the_same_reply(
    session_factory, stub_access, monkeypatch  # noqa: F811
):
    from app.models.ai_assistant import AIAssistantUsageLog

    _seed_contact(session_factory, str(CONTACT_ID))
    stub_access()
    monkeypatch.delenv("LLM_CASSETTE_MODE", raising=False)
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, *, current_date, override_version_id=None: _config())
    _gemini(monkeypatch, needs=20000)
    envelope = _envelope()
    envelope.message["message"]["messageId"] = "ZZT-pmt-cut-short-1"
    result = engine_mod.run_turn(envelope, session_factory=session_factory)

    from tests.chatbot import fail_triage_texts as FT
    assert result.reply["text"] == FT.H_AI
    rows = (
        session_factory()
        .query(AIAssistantUsageLog)
        .filter(AIAssistantUsageLog.chatbot_turn_id == result.turn_id)
        .all()
    )
    assert [(r.feature, r.was_answered) for r in rows] == [("chatbot_parser", False)], rows
    assert rows[0].provider == "gemini" and rows[0].prompt_tokens == 9000
    assert rows[0].completion_tokens == 8192 + FLASH_LITE_THINKING + llm_provider.GEMINI_3_ANSWER_HEADROOM


# --------------------------------------------------------------------------- #
# Owner addition (29 Oct, option b): the field on Settings > Chatbot, through the settings API
# --------------------------------------------------------------------------- #

SETTINGS = "/api/v1/user-management/settings/"
GENERAL = "/api/v1/user-management/settings/general"


@pytest.fixture
def settings_api(monkeypatch):
    import uuid

    from fastapi.testclient import TestClient

    import app.main  # noqa: F401  isort:skip - registers every model before any query
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.main import app
    from app.services.user_service import UserPermissionService
    from tests._pg_fixture import TEST_PREFIX, blank_session

    allow = {"user_management.settings.view", "user_management.settings.edit"}
    with blank_session() as db:
        db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co"))
        db.commit()

        def _override_db():
            yield db

        actor = {"id": str(uuid.uuid4()), "email": "parser-max-tokens@zzt.test", "name": "ZZT"}
        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: dict(actor)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
        monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)
        monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(allow))
        monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
        try:
            yield TestClient(app, raise_server_exceptions=False), db
        finally:
            app.dependency_overrides.clear()


def _stored(settings_api) -> int:
    api, _db = settings_api
    return api.get(SETTINGS).json()["settings"]["chatbot_parser_max_output_tokens"]


def test_get_settings_reports_the_default(settings_api):
    assert _stored(settings_api) == 8192


@pytest.mark.parametrize("method", ["post", "put"])
def test_a_value_in_range_round_trips_and_the_parser_reads_it(settings_api, method):
    api, db = settings_api
    resp = getattr(api, method)(GENERAL, json={"chatbot_parser_max_output_tokens": 16000})
    assert resp.status_code == 200, resp.text
    assert _stored(settings_api) == 16000
    assert parser_mod.max_output_tokens_setting(db) == 16000


@pytest.mark.parametrize("bad", [1023, 32769, 0, -1, 1.5, "lots"])
def test_a_value_out_of_range_is_refused(settings_api, bad):
    api, _db = settings_api
    resp = api.post(GENERAL, json={"chatbot_parser_max_output_tokens": bad})
    assert resp.status_code == 422, resp.text
    assert _stored(settings_api) == 8192


def test_null_resets_to_the_default(settings_api):
    api, _db = settings_api
    assert api.post(GENERAL, json={"chatbot_parser_max_output_tokens": 20000}).status_code == 200
    resp = api.post(GENERAL, json={"chatbot_parser_max_output_tokens": None})
    assert resp.status_code == 200, resp.text
    assert _stored(settings_api) == 8192


def test_a_cut_short_error_survives_a_pickle_round_trip():
    import pickle

    exc = llm_provider.ResponseTruncated("Gemini stopped early: MAX_TOKENS", llm_provider.ChatResult("", 1, 2, 3))
    back = pickle.loads(pickle.dumps(exc))
    assert str(back) == "Gemini stopped early: MAX_TOKENS" and isinstance(back, RuntimeError)
