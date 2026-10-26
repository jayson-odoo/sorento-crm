"""CHAT-SLIM-INDEX S1, red tests of the parser config + engine wiring over Postgres. AC-1, AC-2, AC-4, AC-13, AC-14.

Runs the REAL `parser.resolve_config` over a seeded prompt version and the real `run_turn`; only the
provider call (`parser.parse`) and the embedder are stubbed. The engine's embedder hook is not named
in the S1 contract, so these tests assume a module-level `lookup_lists.EMBED` (an `Embedder | None`
the engine hands to `shortlist`) and a module-level `lookup_lists.load_rows` the engine calls through
the module. Fake data only (ZZ prefix).
"""
from __future__ import annotations

import json
import types
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.marketing import PromotionType
from app.models.product import Brand, ProductCategory
from app.models.product_spec import ProductSpecRegistry
from app.services import ai_prompt_registry
from app.services import chatbot_prompt_vars as pv
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, _turn_row, seeded, stub_access  # noqa: F401

MARKER_LINE = "== LOOKUP LISTS =="
BASE = "Rules for {{current_date}}.\nThe Sales channels line lists the channels.\n"
WC_NAME = "ZZ Tandas Closet"
HIDDEN_NAME = "ZZ Hidden Thing"
HDR_CAT = "Category candidates (pick one only if the message means it):"
HDR_CHAN = "Sales channel candidates (pick one only if the message means it):"
PER_TURN = ("Product types:", "Product details:", "Known brands:", "Promotion kinds:", "Sales channels:")


@pytest.fixture(autouse=True)
def _fresh_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _seed_prompt(session_factory, monkeypatch, *, marker: bool) -> None:
    from app.services import ai_assistant_service, llm_provider

    template = BASE + (MARKER_LINE + "\n" if marker else "")
    db = session_factory()
    v = AIPromptVersion(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, version=1, type="text",
                        template=template, variables=["current_date"])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, label="production", version_id=v.id))
    db.commit()
    cfg = types.SimpleNamespace(provider="openai", model="gpt-test")
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: types.SimpleNamespace(get=lambda: cfg))
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")


def _seed_world(session_factory) -> None:
    db = session_factory()
    db.add_all([
        ProductCategory(id=str(uuid.uuid4()), category_code="ZZWC-" + uuid.uuid4().hex[:6], category_name=WC_NAME,
                        class_label=WC_NAME, search_synonyms=[], is_searchable=True, company_id=DEFAULT_COMPANY_ID),
        ProductCategory(id=str(uuid.uuid4()), category_code="ZZHID-" + uuid.uuid4().hex[:6], category_name=HIDDEN_NAME,
                        class_label=None, search_synonyms=[], is_searchable=False, company_id=DEFAULT_COMPANY_ID),
        Brand(id=str(uuid.uuid4()), brand_code="ZZBR", brand_name="ZZ Brand", company_id=DEFAULT_COMPANY_ID),
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="zz_tint", label="ZZ Tint", data_type="enum",
                            allowed_values=["zzruby"], synonyms={}),
        PromotionType(id=str(uuid.uuid4()), type_code="ZZPT", type_name="ZZ Promo Kind"),
    ])
    db.commit()


def _quiet() -> dict:
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[])


def _turn(session_factory, stub_access, monkeypatch, text: str, *, marker: bool, embed="none"):
    """(config, user_block, result) of one real turn. `embed`: 'none' = no embedder, or a callable."""
    _seed_prompt(session_factory, monkeypatch, marker=marker)
    _seed_world(session_factory)
    monkeypatch.setattr(ll, "EMBED", None if embed == "none" else embed, raising=False)
    seen: list = []

    def parse(config, user_block):
        seen.append((config, str(user_block)))
        return _quiet()

    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-lkp-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": text}}}
    result = engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    config, block = seen[-1]
    return config, block, result


def _trace(session_factory, result) -> list[dict]:
    row = _turn_row(session_factory, result.turn_id)
    return [r for r in row.trace if isinstance(r, dict) and r.get("kind") == "lookup_lists"]


# AC-1: no marker -> today's input
def test_version_without_the_marker_keeps_every_per_turn_line_and_has_no_lookup_block(session_factory, seeded, stub_access, monkeypatch):
    config, block, _r = _turn(session_factory, stub_access, monkeypatch, "dealer only", marker=False)
    assert config.lookup_lists is False
    assert "candidates (pick one only if the message means it)" not in block, block
    for prefix in PER_TURN:
        assert any(ln.startswith(prefix) for ln in block.splitlines()), (prefix, block)


# AC-2, AC-4
def test_version_with_the_marker_gets_blocks_and_loses_the_five_lines(session_factory, seeded, stub_access, monkeypatch):
    config, block, _r = _turn(session_factory, stub_access, monkeypatch, "dealer only", marker=True)
    assert config.lookup_lists is True
    lines = block.splitlines()
    assert HDR_CHAN in lines and "- dealer" in lines, block
    for prefix in PER_TURN:
        assert not any(ln.startswith(prefix) for ln in lines), (prefix, block)


def test_searchable_category_is_offered_and_a_non_searchable_one_never(session_factory, seeded, stub_access, monkeypatch):
    _c, block, _r = _turn(session_factory, stub_access, monkeypatch, f"{WC_NAME} and {HIDDEN_NAME}".lower(), marker=True)
    lines = block.splitlines()
    assert HDR_CAT in lines and f"- {WC_NAME}" in lines, block
    assert HIDDEN_NAME not in block, block


# AC-14
def test_turn_trace_carries_lookup_lists_pieces_and_hits(session_factory, seeded, stub_access, monkeypatch):
    _c, _b, result = _turn(session_factory, stub_access, monkeypatch, "dealer only", marker=True)
    events = _trace(session_factory, result)
    assert len(events) == 1, events
    ev = events[0]
    assert "dealer only" in ev["pieces"] and "dealer" in ev["pieces"], ev
    hit = next(h for h in ev["hits"] if h["label"] == "dealer")
    assert hit["piece"] == "dealer" and hit["spelling"] == 1.0 and "meaning" in hit, hit


def test_a_version_without_the_marker_writes_no_lookup_trace(session_factory, seeded, stub_access, monkeypatch):
    _c, _b, result = _turn(session_factory, stub_access, monkeypatch, "dealer only", marker=False)
    assert _trace(session_factory, result) == []


# AC-13
def test_loader_failure_means_no_block_and_the_turn_answers(session_factory, seeded, stub_access, monkeypatch):
    def boom(db):
        raise RuntimeError("zz loader down")

    monkeypatch.setattr(ll, "load_rows", boom, raising=False)
    _c, block, result = _turn(session_factory, stub_access, monkeypatch, "dealer only", marker=True)
    assert "candidates (pick one only if the message means it)" not in block, block
    assert (result.reply or {}).get("text"), result


def test_embedder_failure_falls_back_to_spelling_and_the_turn_answers(session_factory, seeded, stub_access, monkeypatch):
    def boom(texts):
        raise RuntimeError("zz embedding down")

    _c, block, result = _turn(session_factory, stub_access, monkeypatch, "dealer only", marker=True, embed=boom)
    assert "- dealer" in block.splitlines(), block
    assert (result.reply or {}).get("text"), result
