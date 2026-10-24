"""MODEL-PER-CONTACT slice 2 (backend, red): the ladder reaches every chatbot LLM config reader.

UAC AC-M-8 (readers unchanged), 10, 11, 12, 13 and the load_profile / engine wiring. Ladder:
contact override > tag model > that call's own `production` label row > global config.
Contract: `ContactLLMChoice(provider, model, source, tags)`; `llm_choice=` keyword on
`parser.resolve_config`, `casual.resolve_clarifier_config`, `resolver_code_reader._resolve_provider`;
`ParserConfig.model_source`; `Profile.llm_choice`. No live call: provider keys are fake strings and
the provider factory is captured where a reader builds one. Postgres only (`session_factory`).
"""
from __future__ import annotations

import json
import logging
import uuid

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.chatbot_turn import ChatbotTurn
from app.services import ai_prompt_registry
from app.services import chatbot_prompt_vars as pv
from app.services import llm_provider
from app.services import resolver_code_reader as reader_mod
from app.services.ai_assistant_service import AIAssistantConfigService, MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes import casual as casual_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access  # noqa: F401
from tests.chatbot.test_parser_reasoning_setting import _message

GLOBAL_KEY = "sk-ZZT-global-openai-1111"
GEMINI_KEY = "AIzaZZT-gemini-own-2222"
CHOICE_MODEL = "gemini-3.5-flash-lite"


@pytest.fixture(autouse=True)
def _fresh_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _choice(source="tag", provider="gemini", model=CHOICE_MODEL, tags=("ZZT tag",)):
    from app.services.chatbot.contact_model import ContactLLMChoice

    return ContactLLMChoice(provider=provider, model=model, source=source, tags=list(tags))


def _global(db, *, provider="openai", model="gpt-global", generic=GLOBAL_KEY, gemini=""):
    cfg = AIAssistantConfigService(db).get()
    cfg.provider, cfg.model = provider, model
    cfg.api_key_ciphertext = generic
    cfg.gemini_api_key_ciphertext = gemini
    db.commit()


def _label(db, key, *, template="Rules for {{current_date}}.", variables=("current_date",),
           provider=None, model=None, effort=None):
    v = AIPromptVersion(id=str(uuid.uuid4()), name=key, version=1, type="text",
                        template=template, variables=list(variables))
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(id=str(uuid.uuid4()), name=key, label="production", version_id=v.id,
                         provider=provider, model=model, reasoning_effort=effort))
    db.commit()


def _parser_cfg(session_factory, **kw):
    db = session_factory()
    try:
        return parser_mod.resolve_config(db, current_date="2026-10-24", **kw)
    finally:
        db.close()


# ---------------------------------------------------------------- parser (AC-M-8, 10)


def test_ac_m_8_no_choice_is_exactly_today_and_says_global(session_factory):
    db = session_factory()
    _global(db)
    _label(db, parser_mod.PROMPT_KEY, effort="low")
    before = _parser_cfg(session_factory)
    after = _parser_cfg(session_factory, llm_choice=None)
    for field in ("provider", "model", "api_key", "reasoning_effort", "label_reasoning_effort"):
        assert getattr(after, field) == getattr(before, field), field
    assert (after.provider, after.model, after.api_key) == ("openai", "gpt-global", GLOBAL_KEY)
    assert after.label_reasoning_effort == "low"
    assert after.model_source == "global"


def test_ac_m_8_the_label_model_is_reported_as_label(session_factory):
    db = session_factory()
    _global(db)
    _label(db, parser_mod.PROMPT_KEY, provider="openai", model="gpt-label")
    cfg = _parser_cfg(session_factory, llm_choice=None)
    assert (cfg.provider, cfg.model, cfg.model_source) == ("openai", "gpt-label", "label")


@pytest.mark.parametrize("source", ["tag_conflict", "none"])
def test_ac_m_8_a_choice_without_a_model_changes_nothing(session_factory, source):
    db = session_factory()
    _global(db)
    _label(db, parser_mod.PROMPT_KEY)
    cfg = _parser_cfg(session_factory, llm_choice=_choice(source, None, None, ["a", "b"]))
    assert (cfg.provider, cfg.model, cfg.api_key, cfg.model_source) == ("openai", "gpt-global", GLOBAL_KEY, "global")


@pytest.mark.parametrize("source", ["tag", "contact"])
def test_ac_m_10_the_choice_wins_with_its_own_providers_key(session_factory, source):
    db = session_factory()
    _global(db, gemini=GEMINI_KEY)
    _label(db, parser_mod.PROMPT_KEY, provider="openai", model="gpt-label", effort="low")
    cfg = _parser_cfg(session_factory, llm_choice=_choice(source))
    assert (cfg.provider, cfg.model, cfg.api_key) == ("gemini", CHOICE_MODEL, GEMINI_KEY)
    assert cfg.model_source == source
    # the label's reasoning effort still applies
    assert cfg.label_reasoning_effort == "low"
    assert parser_mod.sent_reasoning_effort(cfg) == "low"


def test_ac_m_12_no_key_for_the_chosen_provider_falls_back_and_warns(session_factory, caplog):
    db = session_factory()
    _global(db, gemini="")
    _label(db, parser_mod.PROMPT_KEY, provider="openai", model="gpt-label")
    with caplog.at_level(logging.WARNING):
        cfg = _parser_cfg(session_factory, llm_choice=_choice("tag"))
    assert (cfg.provider, cfg.model, cfg.api_key) == ("openai", "gpt-label", GLOBAL_KEY)
    assert cfg.model_source == "fallback_no_key"
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING and "gemini" in r.getMessage().lower()]
    assert warned, [r.getMessage() for r in caplog.records]
    for record in caplog.records:
        assert GLOBAL_KEY not in record.getMessage() and GEMINI_KEY not in record.getMessage()


def test_ac_m_12_the_fallback_keeps_the_global_model_when_no_label_names_one(session_factory):
    db = session_factory()
    _global(db, gemini="")
    _label(db, parser_mod.PROMPT_KEY)
    cfg = _parser_cfg(session_factory, llm_choice=_choice("contact"))
    assert (cfg.provider, cfg.model, cfg.model_source) == ("openai", "gpt-global", "fallback_no_key")


# ---------------------------------------------------------------- clarifier (AC-M-11, 12)


@pytest.mark.real_casual_llm
def test_ac_m_11_the_clarifier_follows_the_choice(session_factory):
    db = session_factory()
    _global(db, gemini=GEMINI_KEY)
    cfg = casual_mod.resolve_clarifier_config(db, llm_choice=_choice("tag"))
    assert (cfg.provider, cfg.model, cfg.api_key) == ("gemini", CHOICE_MODEL, GEMINI_KEY)


@pytest.mark.real_casual_llm
def test_ac_m_11_no_choice_is_unchanged(session_factory):
    db = session_factory()
    _global(db, gemini=GEMINI_KEY)
    for kwargs in ({}, {"llm_choice": None}, {"llm_choice": _choice("tag_conflict", None, None, ["a", "b"])}):
        cfg = casual_mod.resolve_clarifier_config(db, **kwargs)
        assert (cfg.provider, cfg.model, cfg.api_key) == ("openai", casual_mod.DEFAULT_MODEL, GLOBAL_KEY), kwargs


@pytest.mark.real_casual_llm
def test_ac_m_12_the_clarifier_without_a_key_falls_back_and_warns(session_factory, caplog):
    db = session_factory()
    _global(db, gemini="")
    with caplog.at_level(logging.WARNING):
        cfg = casual_mod.resolve_clarifier_config(db, llm_choice=_choice("tag"))
    assert (cfg.provider, cfg.api_key) == ("openai", GLOBAL_KEY)
    assert any(r.levelno >= logging.WARNING and "gemini" in r.getMessage().lower() for r in caplog.records)
    assert all(GLOBAL_KEY not in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- code reader (AC-M-11, 12)


@pytest.fixture
def built(monkeypatch):
    """Captures what the code reader builds instead of constructing a real provider."""
    seen: list[tuple] = []

    def fake_get_provider(name, api_key, model=None):
        seen.append((name, api_key, model))
        return object()

    monkeypatch.setattr(llm_provider, "get_provider", fake_get_provider)
    return seen


def test_ac_m_11_the_code_reader_follows_the_choice(session_factory, built):
    db = session_factory()
    _global(db, gemini=GEMINI_KEY)
    _provider, name, model = reader_mod._resolve_provider(db, llm_choice=_choice("tag"))
    assert (name, model) == ("gemini", CHOICE_MODEL)
    assert built == [("gemini", GEMINI_KEY, CHOICE_MODEL)]


def test_ac_m_11_the_code_reader_without_a_choice_is_unchanged(session_factory, built):
    db = session_factory()
    _global(db, gemini=GEMINI_KEY)
    _p, name, model = reader_mod._resolve_provider(db, llm_choice=None)
    assert (name, model) == ("openai", "gpt-global")
    _p, name2, model2 = reader_mod._resolve_provider(db)
    assert (name2, model2) == (name, model)
    assert built[0][:2] == ("openai", GLOBAL_KEY)


def test_ac_m_12_the_code_reader_without_a_key_falls_back_and_warns(session_factory, built, caplog):
    db = session_factory()
    _global(db, gemini="")
    with caplog.at_level(logging.WARNING):
        _p, name, _model = reader_mod._resolve_provider(db, llm_choice=_choice("contact"))
    assert name == "openai"
    assert built and built[0][:2] == ("openai", GLOBAL_KEY)
    assert any(r.levelno >= logging.WARNING and "gemini" in r.getMessage().lower() for r in caplog.records)
    assert all(GLOBAL_KEY not in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- wiring (load_profile, engine, trace)


def _tag_the_contact(session_factory, llm, name="ZZT wired tag"):
    db = session_factory()
    pk = db.execute(text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}).scalar()
    tid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO contact_tags (id, name, settings) VALUES (:i, :n, CAST(:s AS jsonb))"),
        {"i": tid, "n": name, "s": json.dumps({"chatbot": {"llm": llm}} if llm else {})},
    )
    db.execute(text("INSERT INTO respond_contact_tags (contact_id, tag_id) VALUES (:c, :t)"), {"c": pk, "t": tid})
    db.commit()
    return pk


def test_load_profile_carries_the_choice_for_a_tagged_contact(session_factory, seeded):
    from app.services.chatbot.turn_runtime import load_profile

    _tag_the_contact(session_factory, {"provider": "gemini", "model": CHOICE_MODEL}, name="ZZT lp tag")
    profile, _ = load_profile(session_factory(), str(CONTACT_ID))
    got = profile.llm_choice
    assert (got.provider, got.model, got.source, got.tags) == ("gemini", CHOICE_MODEL, "tag", ["ZZT lp tag"])


def test_load_profile_untagged_contact_has_no_model_choice(session_factory, seeded):
    from app.services.chatbot.turn_runtime import load_profile

    profile, _ = load_profile(session_factory(), str(CONTACT_ID))
    assert profile.llm_choice is None or (profile.llm_choice.source, profile.llm_choice.provider) == ("none", None)


def test_engine_hands_the_choice_to_the_parser_and_the_trace_records_it(session_factory, seeded, stub_access, monkeypatch):
    _tag_the_contact(session_factory, {"provider": "gemini", "model": CHOICE_MODEL}, name="ZZT trace tag")
    captured: dict = {}

    def fake_resolve_config(db, *, current_date, override_version_id=None, llm_choice=None):
        captured["llm_choice"] = llm_choice
        config = parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="gemini", model=CHOICE_MODEL, api_key="g-ZZT",
        )
        config.model_source = getattr(llm_choice, "source", "global")
        return config

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, block: _parser_output(
        intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[]))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    result = engine_mod.run_turn(_envelope(message=_message("zzqwerty")), session_factory=session_factory)

    got = captured.get("llm_choice")
    assert got is not None and (got.provider, got.model, got.source) == ("gemini", CHOICE_MODEL, "tag")
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    facts = next(r["facts"] for r in (row.trace or []) if isinstance(r, dict) and r.get("stage") == "understood")
    assert facts.get("model_source") == "tag", facts
    # AC-M-13: for a tag the trace names the tag(s); the key is the coder's, the value is the tag name
    assert any("ZZT trace tag" in (v if isinstance(v, list) else [v]) for v in facts.values()), facts
