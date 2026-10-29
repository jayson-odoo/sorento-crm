"""CHAT-V66-REGRESSIONS: the message-piece vector cache never drops a piece the current message still needs.

`provider_embedder().pieces` kept at most `_PIECES_CAP` vectors, evicting the oldest AFTER inserting the new ones
and then reading every piece of the message back from the cache: a message whose older pieces sat at the front
("stock", "check", cached on an early turn) lost them, raised KeyError, and `_meaning` quietly read that turn by
spelling only. Fake client only.
"""
from __future__ import annotations

import types

import numpy as np

from app.services.chatbot.head import lookup_lists as ll


def _embedder(monkeypatch, calls):
    from app.services import llm_provider

    class _Emb:
        def create(self, *, model, input):
            calls.append(list(input))
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[float(len(t))] + [1.0] * 1535) for t in input])

    for store in (ll._cache, ll._matrices, ll._pieces):
        store.clear()
    monkeypatch.setattr(llm_provider.OpenAIProvider, "_client", lambda self, **kw: types.SimpleNamespace(embeddings=_Emb()))
    return ll.provider_embedder("sk-zz-v66-pieces")


def test_a_full_cache_keeps_the_pieces_the_message_asks_for(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(ll, "_PIECES_CAP", 4)
    embed = _embedder(monkeypatch, calls)
    embed.pieces(["zz stock", "zz a", "zz b", "zz c"])  # the cache is full; "zz stock" is the oldest
    out = embed.pieces(["zz stock", "zz new"])
    assert out.shape == (2, 1536)
    assert np.allclose(out[0], ll._unit_rows([[8.0] + [1.0] * 1535])[0]), "the old piece's own vector"
    assert calls[-1] == ["zz new"], calls
    assert len(ll._pieces) <= 4


def test_a_message_with_more_pieces_than_the_cap_is_still_embedded_whole(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(ll, "_PIECES_CAP", 2)
    embed = _embedder(monkeypatch, calls)
    out = embed.pieces(["zz one", "zz two", "zz three"])
    assert out.shape == (3, 1536) and len(ll._pieces) <= 2
