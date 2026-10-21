"""CHAT-RELEASE-1021, crew review fix 2 of #1809: CHAT-LATENCY-SCOUT's budgets stay on the chatbot path.

- The spec reading's 3 s budget (`understand_phrase`) is the chatbot turn's: only the resolve
  endpoint the turn calls (`api/v1/system/references.py`) passes it. The CRM's Product
  Specifications preview (`api/v1/master_data/product_specifications.py`) asks as it did
  before #1801: no timeout, the SDK's own retries.
- The shared OpenAI client keeps one client per (key, timeout, retries): a call that passes no
  timeout (AI assistant, every other caller) is built with the SDK defaults, never with the
  0-retry client a timed call made. A caller timeout meaning max_retries=0 is main's own rule
  (`llm_provider.chat`), unchanged.
"""
from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.product import ProductCategory, UnitOfMeasure
from app.services import llm_provider
from app.services import product_spec_understanding as understanding
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session
from tests.test_chat_latency_llm_budget import _counting_openai

APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def db():
    with blank_session() as s:
        s.add_all(
            [
                ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS"),
                UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece"),
            ]
        )
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        yield s


def _spy(monkeypatch) -> list[dict]:
    seen: list[dict] = []
    result = SimpleNamespace(content=json.dumps({"specs": []}), prompt_tokens=1, completion_tokens=1, total_tokens=2)

    def chat(*_a, **kwargs):
        seen.append(kwargs)
        return result

    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (SimpleNamespace(chat=chat), "openai", "gpt-test")
    )
    return seen


def test_a_reading_with_no_budget_asks_with_no_timeout_as_before(db, monkeypatch):
    seen = _spy(monkeypatch)
    understanding.understand_phrase(db, "a stainless steel kitchen sink")
    assert len(seen) == 1 and seen[0].get("timeout") is None, seen


def test_derive_search_inputs_carries_the_callers_budget(db, monkeypatch):
    seen = _spy(monkeypatch)
    understanding.derive_search_inputs(
        db, "a stainless steel kitchen sink", model_timeout=understanding.CHAT_TURN_MODEL_TIMEOUT_SECONDS
    )
    understanding.derive_search_inputs(db, "a stainless steel kitchen sink")
    assert [k.get("timeout") for k in seen] == [pytest.approx(3.0), None], seen


def _calls(path: Path, name: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "attr", None) == name or getattr(node.func, "id", None) == name)
    ]


def test_every_chatbot_resolve_reading_passes_the_turn_budget():
    calls = _calls(APP / "api" / "v1" / "system" / "references.py", "derive_search_inputs")
    assert calls, "the resolve endpoint reads the sentence"
    for call in calls:
        assert any(kw.arg == "model_timeout" for kw in call.keywords), f"references.py:{call.lineno}"


def test_the_crm_specifications_preview_keeps_no_budget():
    calls = _calls(APP / "api" / "v1" / "master_data" / "product_specifications.py", "derive_search_inputs")
    assert calls, "the preview reads the sentence"
    for call in calls:
        assert not any(kw.arg == "model_timeout" for kw in call.keywords), f"product_specifications.py:{call.lineno}"


def test_an_untimed_call_never_gets_the_timed_calls_zero_retry_client(monkeypatch):
    built = _counting_openai(monkeypatch)
    provider = llm_provider.OpenAIProvider("sk-scope")

    provider.chat([{"role": "user", "content": "x"}], timeout=3.0)
    provider.chat([{"role": "user", "content": "y"}])
    provider.chat([{"role": "user", "content": "z"}])

    assert [(b.get("timeout"), b.get("max_retries")) for b in built] == [(3.0, 0), (None, None)]
