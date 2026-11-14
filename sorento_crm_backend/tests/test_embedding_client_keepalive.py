"""CHATBOT-SPEED: the embeddings transport keeps one open connection per process.

Since LOOKUP-EMBED-CENTRAL (#1967) every `embed_texts` call built a fresh `httpx.Client`, so every chatbot turn paid a
new DNS + TCP + TLS handshake on its lookup embedding round trip. The client is now shared (keep-alive) and re-made
only after a fork. No network: `httpx.Client.send` is stubbed (the seam the other embedding tests patch).
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.services import embedding_client, http_keepalive


def _vector() -> list[float]:
    return [1.0] + [0.0] * (embedding_client.EMBEDDING_DIMENSIONS - 1)


@pytest.fixture
def transport(monkeypatch):
    """Count client constructions and record every request; answer like either provider."""
    seen: dict[str, list] = {"clients": [], "requests": []}
    real_init = httpx.Client.__init__

    def init(self, *a, **k):
        seen["clients"].append(self)
        real_init(self, *a, **k)

    def send(self, request, **_kw):
        seen["requests"].append((self, request))
        body = json.loads(request.content)
        if "requests" in body:  # Gemini batchEmbedContents
            payload = {"embeddings": [{"values": _vector()} for _ in body["requests"]]}
        else:  # OpenAI embeddings
            payload = {"data": [{"index": i, "embedding": _vector()} for i, _ in enumerate(body["input"])]}
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    monkeypatch.setattr(httpx.Client, "send", send)
    http_keepalive.reset()
    yield seen
    http_keepalive.reset()


@pytest.mark.parametrize("provider,model", [("openai", "text-embedding-3-small"), ("gemini", "gemini-embedding-001")])
def test_two_calls_share_one_client(transport, provider, model):
    embedding_client.embed_texts(["a"], provider, model, api_key="test-key", timeout=3.0)
    embedding_client.embed_texts(["b"], provider, model, api_key="test-key", timeout=3.0)
    assert len(transport["requests"]) == 2
    assert len(transport["clients"]) == 1, "each embedding call opened a new connection (no keep-alive)"
    assert transport["requests"][0][0] is transport["requests"][1][0]


def test_both_providers_share_one_client(transport):
    embedding_client.embed_texts(["a"], "openai", "text-embedding-3-small", api_key="test-key", timeout=3.0)
    embedding_client.embed_texts(["b"], "gemini", "gemini-embedding-001", api_key="test-key", timeout=3.0)
    assert len(transport["clients"]) == 1


def test_each_call_keeps_its_own_timeout(transport):
    embedding_client.embed_texts(["a"], "openai", "text-embedding-3-small", api_key="test-key", timeout=3.0)
    embedding_client.embed_texts(["b"], "openai", "text-embedding-3-small", api_key="test-key", timeout=30.0)
    timeouts = [r.extensions["timeout"] for _, r in transport["requests"]]
    assert [t["read"] for t in timeouts] == [3.0, 30.0]
    assert [t["connect"] for t in timeouts] == [3.0, 30.0]
    assert [t["write"] for t in timeouts] == [3.0, 30.0]
    assert [t["pool"] for t in timeouts] == [3.0, 30.0]


def test_a_forked_process_builds_its_own_client(transport, monkeypatch):
    """A client made before a fork (gunicorn / RQ work-horse) is never used by the child: its sockets are shared."""
    embedding_client.embed_texts(["a"], "openai", "text-embedding-3-small", api_key="test-key", timeout=3.0)
    real_pid = http_keepalive.os.getpid()
    monkeypatch.setattr(http_keepalive.os, "getpid", lambda: real_pid + 1)
    embedding_client.embed_texts(["b"], "openai", "text-embedding-3-small", api_key="test-key", timeout=3.0)
    assert len(transport["clients"]) == 2
    assert transport["requests"][0][0] is not transport["requests"][1][0]


def test_an_idle_connection_outlives_the_gap_between_turns(transport):
    """httpx drops an idle connection after 5 s by default, so two turns more than 5 s apart paid the handshake again.
    The shared client keeps it for `KEEPALIVE_EXPIRY_SECONDS` (reviewer, 12 Nov)."""
    embedding_client.embed_texts(["a"], "openai", "text-embedding-3-small", api_key="test-key", timeout=3.0)
    client = transport["clients"][0]
    assert client._transport._pool._keepalive_expiry == embedding_client.KEEPALIVE_EXPIRY_SECONDS
    assert embedding_client.KEEPALIVE_EXPIRY_SECONDS >= 30
