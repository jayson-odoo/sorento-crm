"""WA-COMPLAINT-INTAKE live set: the REAL extractor model reads the submission type by meaning.

Opt-in, never in CI: `CHATBOT_LIVE_LLM=1` (the suite's `live_external` marker). Model
`WA_ISSUE_LIVE_MODEL`, default `gpt-5.4-mini` (the production parser model); key `OPENAI_API_KEY`,
or a placeholder where an egress proxy injects it. The prompt is the registry's own
`ideate_extractor` fallback and the schema is the production one, so this measures exactly
what `extract_ideate_turn` sends. Phrasings: an English bug report, a Malay one with a typo, a
greeting-prefixed one, a Chinese one, two feature requests and a product complaint (stays idea,
it is routed to the portal before this lane, UAC T-4). Each case is about one call (~2k tokens).
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.live_external

CASES = [
    ("The stock page shows a blank screen on my phone since this morning", "issue"),
    ("hi, the AI bot gave me the wrong stok number for my oder yesterday", "issue"),
    ("Salam, sistem CRM tak boleh buka page quotation, keluar eror", "issue"),
    ("AI 助手查库存的时候一直没有回复", "issue"),
    ("Can you add a button to export my orders to Excel?", "idea"),
    ("Boleh tak tambah fungsi untuk tengok sejarah harga produk", "idea"),
]


@pytest.fixture
def live_extractor(monkeypatch):
    from app.services import ai_prompt_registry, ideation_extractor

    model = os.environ.get("WA_ISSUE_LIVE_MODEL", "gpt-5.4-mini")
    key = os.environ.get("OPENAI_API_KEY") or "sk-proxy-injected"
    config = SimpleNamespace(provider="openai", model=model)
    monkeypatch.setattr(ideation_extractor.AIAssistantConfigService, "get", lambda self: config)
    monkeypatch.setattr(ideation_extractor, "resolve_api_key", lambda cfg, provider: key)
    fallback = ai_prompt_registry.PROMPT_KEYS["ideate_extractor"].fallback()
    monkeypatch.setattr(ideation_extractor.ai_prompt_registry, "render", lambda db, name: (fallback, 0))
    return ideation_extractor.extract_ideate_turn


@pytest.mark.parametrize("text,expected", CASES)
def test_live_the_model_reads_the_type_by_meaning(live_extractor, text, expected):
    out = live_extractor(None, message_text=text)
    assert not out.failed
    assert out.type == expected, (text, out.type)
    assert out.fields.get("problem"), out
    # Round 13: a title is always set once there is a problem statement, whatever the language (L3).
    assert (out.title or "").strip(), (text, out.title)
