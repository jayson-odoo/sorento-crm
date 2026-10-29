"""CHAT-V66-REGRESSIONS case 7: the lookup's per-turn embedding round trip no longer waits for the rows to load.

Prod 26 Oct: turn medians rose about 2 s when the lookup went live while the parser call stayed flat. The one
network call the lookup makes per turn (the message pieces' vectors) ran after the contact checks and `load_rows`;
it now starts first and overlaps them (the provider already keeps one client per key, `OpenAIProvider._client`).
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


from tests.chatbot._embed_http import patch_openai_embeddings


def _fake_openai(calls: list[list[str]], made: list[int], gate: threading.Event | None = None):
    class _Emb:
        def create(self, *, model, input):
            if gate is not None:
                gate.wait(5)
            calls.append(list(input))
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[1.0] + [0.0] * 1535) for _ in input])

    emb = _Emb()

    def create(*, model, input):
        made.append(1)
        return emb.create(model=model, input=input)

    return create


def _fresh_embedder(monkeypatch, calls, made, gate=None):
    from app.services import llm_provider

    for store in (ll._cache, ll._matrices, ll._pieces):
        store.clear()
    patch_openai_embeddings(monkeypatch, _fake_openai(calls, made, gate))
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


def test_prefetch_join_says_whether_the_pieces_arrived(monkeypatch):
    calls: list[list[str]] = []
    made: list[int] = []
    embed = _fresh_embedder(monkeypatch, calls, made)
    assert ll.prefetch("zz toilet bowl", embed)() is True
    gate = threading.Event()
    slow = _fresh_embedder(monkeypatch, [], [], gate)
    monkeypatch.setattr(ll, "EMBED_TIMEOUT", 0.2)
    assert ll.prefetch("zz slow piece", slow)() is False  # still in flight at the deadline
    gate.set()

    def broken(*a, **k):
        raise RuntimeError("provider down")

    failing = _fresh_embedder(monkeypatch, [], [])
    monkeypatch.setattr(failing, "pieces", broken)
    assert ll.prefetch("zz failing piece", failing)() is False


def test_a_prefetch_that_did_not_arrive_means_spelling_only_and_no_second_request(session_factory, monkeypatch):  # noqa: F811
    _seed_world(session_factory)
    seen: dict = {}
    provider_like = types.SimpleNamespace(pieces=lambda texts: None, needs_warm=False)
    monkeypatch.setattr(ll, "embedder", lambda db: provider_like)
    monkeypatch.setattr(ll, "prefetch", lambda message, embed: (lambda: False))
    real = ll.shortlist

    def shortlist(message, rows, embed, **kw):
        seen["embed"] = embed
        return real(message, rows, None, **kw)

    monkeypatch.setattr(ll, "shortlist", shortlist)
    lines, event = engine_mod._lookup_lines(session_factory(), "zz tandas closet", None, frozenset(), "ZZ-no-contact", None)
    assert not event.get("failed"), event
    assert seen["embed"] is None


def test_a_failing_key_read_leaves_the_blocks_and_the_session_usable(session_factory, monkeypatch):  # noqa: F811
    from sqlalchemy import text

    _seed_world(session_factory)
    db = session_factory()

    def broken(d):
        d.execute(text("SELECT * FROM zz_no_such_table_v66"))

    monkeypatch.setattr(ll, "embedder", broken)
    lines, event = engine_mod._lookup_lines(db, "zz tandas closet", None, frozenset(), "ZZ-no-contact", None)
    assert not event.get("failed"), event
    assert db.execute(text("SELECT 1")).scalar() == 1
