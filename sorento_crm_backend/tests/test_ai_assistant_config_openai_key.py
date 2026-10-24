"""MODEL-PER-CONTACT R4: a per-provider OpenAI key slot (AC-R4-1..8).

Red-first. `openai_api_key_ciphertext` does not exist yet; the resolver order for
OpenAI becomes own column > generic (while cfg.provider == "openai") > env > "".
Postgres only, via tests/_pg_fixture. Every key is fake.
"""
from __future__ import annotations

import types

import pytest
from sqlalchemy import text

from app.models.ai_assistant import AIAssistantConfig
from app.schemas.ai_assistant import AIAssistantConfigResponse, AIAssistantConfigUpdate
from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.llm_provider import resolve_api_key
from tests._pg_fixture import blank_session

OWN = "sk-ZZT-own-openai-9999"


def _cfg(provider, *, openai="", generic="", gemini="", anthropic=""):
    return types.SimpleNamespace(
        provider=provider,
        api_key_ciphertext=generic,
        openai_api_key_ciphertext=openai,
        gemini_api_key_ciphertext=gemini,
        anthropic_api_key_ciphertext=anthropic,
    )


@pytest.fixture
def env(monkeypatch):
    from app.config import settings as app_settings

    def _set(openai="", gemini="", anthropic=""):
        monkeypatch.setattr(app_settings, "openai_api_key", openai, raising=False)
        monkeypatch.setattr(app_settings, "gemini_api_key", gemini, raising=False)
        monkeypatch.setattr(app_settings, "anthropic_api_key", anthropic, raising=False)

    _set()
    return _set


# ---- resolver ---------------------------------------------------------


def test_ac_r4_3_openai_own_column_wins_when_assistant_runs_on_gemini(env):
    cfg = _cfg("gemini", openai="sk-own", generic="g-generic", gemini="g-own")
    assert resolve_api_key(cfg, "openai") == "sk-own"
    assert resolve_api_key(cfg, "gemini") == "g-own"


def test_ac_r4_3_openai_own_column_wins_when_assistant_runs_on_anthropic(env):
    cfg = _cfg("anthropic", openai="sk-own", generic="a-generic", anthropic="a-own")
    assert resolve_api_key(cfg, "openai") == "sk-own"
    assert resolve_api_key(cfg, "anthropic") == "a-own"


def test_ac_r4_2_own_column_beats_generic_on_openai(env):
    cfg = _cfg("openai", openai="sk-own", generic="sk-gen")
    assert resolve_api_key(cfg, "openai") == "sk-own"


def test_ac_r4_5_generic_still_serves_openai_when_own_column_empty(env):
    # Pins today's behaviour; passes before the change.
    for empty in ("", None):
        cfg = _cfg("openai", openai=empty, generic="sk-gen", gemini="g-own", anthropic="a-own")
        assert resolve_api_key(cfg, "openai") == "sk-gen"
        assert resolve_api_key(cfg, "gemini") == "g-own"
        assert resolve_api_key(cfg, "anthropic") == "a-own"


def test_ac_r4_4_env_key_when_no_openai_slot_and_assistant_on_gemini(env):
    cfg = _cfg("gemini", openai="", generic="g-generic")
    env(openai="sk-env")
    assert resolve_api_key(cfg, "openai") == "sk-env"
    env(openai="")
    assert resolve_api_key(cfg, "openai") == ""  # never the Gemini generic key


# ---- model / storage ----------------------------------------------------


def test_ac_r4_1_7_column_exists_and_is_encrypted_at_rest():
    from app.utils.field_encryption import decrypt_secret

    assert hasattr(AIAssistantConfig, "openai_api_key_ciphertext")
    with blank_session() as db:
        row = AIAssistantConfigService(db).get()
        row.openai_api_key_ciphertext = OWN
        db.flush()
        db.expire_all()
        assert db.get(AIAssistantConfig, row.id).openai_api_key_ciphertext == OWN
        raw = db.execute(
            text("SELECT openai_api_key_ciphertext FROM ai_assistant_configs WHERE id = :i"),
            {"i": row.id},
        ).scalar_one()
        assert raw and raw != OWN and OWN not in raw
        assert raw.startswith("gAAAAA")
        assert decrypt_secret(raw) == OWN


def test_ac_r4_7_reencrypt_script_covers_the_column():
    from scripts.reencrypt_field_secrets import COLUMNS

    assert ("ai_assistant_configs", "openai_api_key_ciphertext", True) in COLUMNS


# ---- write path / response ----------------------------------------------


def _payload(**overrides) -> AIAssistantConfigUpdate:
    fields = {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "temperature": 0,
        "system_prompt": "",
        "enabled_tools": [],
        "rag_enabled": True,
        "is_enabled": True,
    }
    fields.update(overrides)
    return AIAssistantConfigUpdate(**fields)


def test_ac_r4_6_set_then_blank_or_absent_leaves_it_alone_and_response_is_masked():
    with blank_session() as db:
        service = AIAssistantConfigService(db)
        row = service.update(_payload(openai_api_key="sk-new-ZZT-5678"), user_id=None)
        assert row.openai_api_key_ciphertext == "sk-new-ZZT-5678"

        body = service.to_response_dict(row)
        assert body["openai_api_key_masked"] == "****5678"
        resp = AIAssistantConfigResponse(**body)
        assert resp.openai_api_key_masked == "****5678"

        dumped = resp.model_dump_json()
        assert "sk-new-ZZT-5678" not in dumped
        assert "sk-new-ZZT-5678" not in str(body)
        for forbidden in ("openai_api_key", "openai_api_key_ciphertext"):
            assert forbidden not in body
            assert forbidden not in resp.model_dump()

        row = service.update(_payload(openai_api_key="   "), user_id=None)
        assert row.openai_api_key_ciphertext == "sk-new-ZZT-5678"
        row = service.update(_payload(), user_id=None)
        assert row.openai_api_key_ciphertext == "sk-new-ZZT-5678"


def test_ac_r4_6_openai_slot_is_independent_of_the_generic_key():
    with blank_session() as db:
        service = AIAssistantConfigService(db)
        row = service.update(
            _payload(provider="openai", model="gpt-4o-mini",
                     api_key="sk-ZZT-generic-1111", openai_api_key="sk-ZZT-slot-2222"),
            user_id=None,
        )
        body = service.to_response_dict(row)
        assert body["api_key_masked"] == "****1111"
        assert body["openai_api_key_masked"] == "****2222"


# ---- redaction ------------------------------------------------------------


def test_ac_r4_8_openai_key_is_redacted_like_the_gemini_one():
    # api_call_log_service redacts by KEY NAME (suffix `_api_key`), not by value,
    # so a PUT body carrying openai_api_key is hidden exactly like gemini_api_key.
    from app.services.api_call_log_service import REDACTED, redact_mapping

    out = redact_mapping({"gemini_api_key": "g", "openai_api_key": "sk-ZZT", "model": "m"})
    assert out["gemini_api_key"] == REDACTED
    assert out["openai_api_key"] == REDACTED
    assert out["model"] == "m"
