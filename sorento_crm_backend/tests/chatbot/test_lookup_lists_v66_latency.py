"""CHAT-V66-REGRESSIONS case 7: the lookup's per-turn embedding round trip no longer waits for the rows to load.

Prod 26 Oct: turn medians rose about 2 s when the lookup went live while the parser call stayed flat. The one
network call the lookup makes per turn (the message pieces' vectors) ran after the contact checks and `load_rows`;
it now starts first and overlaps them, and one HTTP client per key is kept for the process instead of one per call.
Same hits either way. Fake data only (ZZ prefix).
"""
from __future__ import annotations

import threading
import types

import numpy as np

import app.main  # noqa: F401  isort:skip
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _seed_world  # noqa: F401

ROWS = [ll.LookupRow("category", "c1", "ZZ Water Closet", ("zz water closet", "zz toilet bowl"))]


def _fake_openai(calls: list[list[str]], made: list[int], gate: threading.Event | None = None):
    class _Emb:
        def create(self, *, model, input):
            if gate is not None:
                gate.wait(5)
            calls.append(list(input))
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[1.0] + [0.0] * 1535) for _ in input])

    def client(self, **kw):
        made.append(1)
        return types.SimpleNamespace(embeddings=_Emb())

    return client


def _fresh_embedder(monkeypatch, calls, made, gate=None):
    from app.services import llm_provider

    for store in (ll._cache, ll._matrices, ll._pieces):
        store.clear()
    monkeypatch.setattr(llm_provider.OpenAIProvider, "_client", _fake_openai(calls, made, gate))
    return ll.provider_embedder("sk-zz-v66")


def test_prefetched_pieces_are_not_embedded_again_by_the_shortlist(monkeypatch):
    calls: list[list[str]] = []
    made: list[int] = []
    embed = _fresh_embedder(monkeypatch, calls, made)
    embed(ll.row_texts(ROWS))
    before = len(calls)
    join = ll.prefetch("zz toilet bowl please", embed)
    join()
    after_prefetch = len(calls)
    assert after_prefetch == before + 1, calls
    hits = ll.shortlist("zz toilet bowl please", ROWS, embed)
    assert len(calls) == after_prefetch, f"the shortlist embedded the pieces again: {calls[after_prefetch:]}"
    assert [h.row.key for h in hits["category"]] == ["c1"], hits


def test_prefetch_runs_off_the_calling_thread_and_join_waits_for_it(monkeypatch):
    calls: list[list[str]] = []
    made: list[int] = []
    gate = threading.Event()
    embed = _fresh_embedder(monkeypatch, calls, made, gate)
    join = ll.prefetch("zz toilet bowl", embed)  # returns while the request is still in flight
    assert calls == []
    gate.set()
    join()
    assert len(calls) == 1 and "zz toilet bowl" in calls[0], calls


def test_prefetch_without_an_embedder_or_pieces_is_a_no_op():
    ll.prefetch("zz toilet bowl", None)()
    ll.prefetch("SRTZZ1234", lambda texts: (_ for _ in ()).throw(AssertionError("called")))()


def test_one_http_client_serves_every_call_of_an_embedder(monkeypatch):
    calls: list[list[str]] = []
    made: list[int] = []
    embed = _fresh_embedder(monkeypatch, calls, made)
    embed(["zz one"])
    embed(["zz two"])
    embed.pieces(["zz three"])
    embed.fill(["zz four"])
    assert len(calls) == 4 and len(made) == 1, (calls, made)


def test_the_engine_embedder_is_built_once_per_key(monkeypatch):
    from app.services import ai_assistant_service, llm_provider

    monkeypatch.setattr(ll, "EMBED", ll.USE_PROVIDER)
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: types.SimpleNamespace(get=lambda: None))
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-zz-v66-a")
    first = ll.embedder(None)
    assert first is not None and ll.embedder(None) is first
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-zz-v66-b")
    assert ll.embedder(None) is not first


def test_lookup_lines_starts_the_piece_embedding_before_the_rows_load(session_factory, monkeypatch):  # noqa: F811
    order: list[str] = []
    real_prefetch, real_load = ll.prefetch, ll.load_rows

    def prefetch(message, embed):
        order.append("prefetch")
        return real_prefetch(message, embed)

    def load_rows(*a, **k):
        order.append("load_rows")
        return real_load(*a, **k)

    _seed_world(session_factory)
    monkeypatch.setattr(ll, "EMBED", lambda texts: np.ones((len(texts), 4), dtype=np.float32))
    monkeypatch.setattr(ll, "prefetch", prefetch)
    monkeypatch.setattr(ll, "load_rows", load_rows)
    db = session_factory()
    lines, event = engine_mod._lookup_lines(db, "zz tandas closet", None, frozenset(), "ZZ-no-contact", None)
    assert not event.get("failed"), event
    assert order[:2] == ["prefetch", "load_rows"], order
