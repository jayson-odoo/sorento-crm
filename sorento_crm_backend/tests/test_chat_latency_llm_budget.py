"""CHAT-LATENCY-SCOUT (documentation/plans/chatbot/CARD-chat-latency-scout-20oct.md).

B: the spec reading (`product_spec_understanding.understand_phrase`) sits on the chatbot
reply path, after the resolver code reader, and asked the provider with NO timeout - the SDK
default of 600 s with two silent retries. It now gets the code reader's own 3 s budget, which
also turns the SDK retries off (`llm_provider.chat`: a caller timeout means max_retries=0). A
timeout ends in the deterministic reading, the same arm any provider failure already takes,
so the turn answers from the literal words instead of waiting.

C: `OpenAIProvider._client` built a new `OpenAI` (and so a new TCP + TLS connection) on every
call. One client is now kept per (key, timeout, retries, base_url), shared across threads.
"""
from __future__ import annotations

import json
import threading
import uuid
from types import SimpleNamespace

import pytest

from app.models.product import ProductCategory, UnitOfMeasure
from app.services import llm_provider
from app.services import product_spec_understanding as understanding
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session


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


# --------------------------------------------------------------------------- #
# B: the spec reading's budget
# --------------------------------------------------------------------------- #
def test_the_spec_reading_asks_the_provider_with_the_code_readers_budget(db, monkeypatch):
    seen: list[dict] = []
    result = SimpleNamespace(content=json.dumps({"specs": []}), prompt_tokens=1, completion_tokens=1, total_tokens=2)

    def chat(*_a, **kwargs):
        seen.append(kwargs)
        return result

    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (SimpleNamespace(chat=chat), "openai", "gpt-test")
    )

    understanding.understand_phrase(db, "a stainless steel kitchen sink")

    assert len(seen) == 1
    assert seen[0].get("timeout") == pytest.approx(3.0), "no timeout means the SDK's 600 s and 2 retries"


def test_a_spec_reading_timeout_ends_in_the_deterministic_reading(db, monkeypatch):
    """Never stuck: the turn gets the literal reading and goes on to the ranker."""
    from openai import APITimeoutError

    def chat(*_a, **_k):
        raise APITimeoutError("Request timed out.")

    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (SimpleNamespace(chat=chat), "openai", "gpt-test")
    )

    reading = understanding.understand_phrase(db, "a stainless steel kitchen sink")

    assert reading.source == "deterministic"
    assert reading.free_terms[0] == "a stainless steel kitchen sink"


# --------------------------------------------------------------------------- #
# C: one OpenAI client per (key, timeout, retries, base_url)
# --------------------------------------------------------------------------- #
class _Completions:
    def create(self, **_kwargs):
        message = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2, prompt_tokens_details=None),
            model="gpt-test",
        )


def _counting_openai(monkeypatch) -> list[dict]:
    built: list[dict] = []

    def factory(**kwargs):
        built.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    monkeypatch.setattr("openai.OpenAI", factory)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    return built


def test_two_calls_with_the_same_key_and_timeout_share_one_client(monkeypatch):
    built = _counting_openai(monkeypatch)
    provider = llm_provider.OpenAIProvider("sk-a")

    provider.chat([{"role": "user", "content": "x"}], timeout=3.0)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "y"}], timeout=3.0)

    assert len(built) == 1, "a new client per call is a new TCP + TLS handshake per call"


def test_a_different_key_or_timeout_gets_its_own_client(monkeypatch):
    built = _counting_openai(monkeypatch)

    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
    llm_provider.OpenAIProvider("sk-b").chat([{"role": "user", "content": "x"}], timeout=3.0)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=9.0)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}])

    assert [(b["api_key"], b.get("timeout"), b.get("max_retries")) for b in built] == [
        ("sk-a", 3.0, 0),
        ("sk-b", 3.0, 0),
        ("sk-a", 9.0, 0),
        ("sk-a", None, None),
    ]


def test_a_different_base_url_gets_its_own_client(monkeypatch):
    built = _counting_openai(monkeypatch)

    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)

    assert [b.get("base_url") for b in built] == [None, "https://llm.example.com/v1"]


def test_concurrent_first_calls_build_one_client(monkeypatch):
    built = _counting_openai(monkeypatch)
    start = threading.Barrier(8)
    errors: list[BaseException] = []

    def worker():
        try:
            start.wait()
            llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(built) == 1
