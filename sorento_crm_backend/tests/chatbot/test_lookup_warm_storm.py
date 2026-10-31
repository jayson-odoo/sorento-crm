"""LOOKUP-WARM-STORM (prod 30 Oct, documentation/plans/chatbot/PLAN-lookup-warm-storm-30oct.md): a fresh worker's
lookup warm must be cheap and must not call the provider for texts another process already embedded.

1. The spec-key texts (`list_resolver.spec_key_rows`, warmed at start-up with the lookup rows) are stored too, so a
   fresh process embeds none of them again.
2. The store load decodes each vector from pgvector's binary form, never as 1536 Python floats.
3. A warm that failed or left texts uncached is not retried by every turn: only after `WARM_RETRY_AFTER`, or for a
   text it did not already try.
Postgres only, no network."""
from __future__ import annotations

import threading
import types
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.services.chatbot.head import list_resolver
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import lookup_word_store
from tests.chatbot.test_lookup_warm_from_store import Fake, _Session, model, new_process, seed_documents, texts, vec
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture(autouse=True)
def env(monkeypatch, db):
    import app.database as database

    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})
    monkeypatch.setattr(ll, "_warm_lock", threading.Lock())
    monkeypatch.setattr(ll, "_gave_up", {}, raising=False)
    monkeypatch.setattr(ll, "_sleep", lambda s: None, raising=False)
    monkeypatch.setattr(ll, "_jitter", lambda: 0.0, raising=False)
    monkeypatch.setattr(database, "SessionLocal", lambda: _Session(db))
    monkeypatch.setattr(ll, "threading", _recording_threading())


# Warm threads as `ll.warm` starts them. A scan of `threading.enumerate()` after `warm()` returned missed a thread
# that had already finished (a provider failing on its first call), so the wait helper read "no warm started".
_started: list[threading.Thread] = []


def _recording_threading():
    class Thread(threading.Thread):
        def start(self):
            _started.append(self)
            super().start()

    proxy = types.SimpleNamespace(**{k: getattr(threading, k) for k in dir(threading) if not k.startswith("__")})
    proxy.Thread = Thread
    return proxy


# ---- 1. spec-key texts are stored
def test_sync_stores_the_spec_key_texts_so_a_fresh_process_embeds_none(db, monkeypatch):
    from app.services import embedding_settings

    m = model()
    tag = uuid.uuid4().hex[:6]
    row_texts = [f"zz storm cat {tag}", f"zz storm cat word {tag}"]
    key_texts = [f"zz storm key {tag}", f"zz storm key word {tag}"]
    monkeypatch.setattr(ll, "load_rows", lambda db, **kw: [ll.LookupRow("category", f"zzc{tag}", "zz", tuple(row_texts))])
    monkeypatch.setattr(
        list_resolver, "spec_key_rows", lambda registry: [ll.LookupRow("spec_key", f"zzk{tag}", "zz", tuple(key_texts))]
    )
    sent: list[str] = []
    monkeypatch.setattr(embedding_settings, "embed_for_model", lambda db, part, mdl: (sent.extend(part), [vec(t) for t in part])[1])

    lookup_word_store.sync_lookup_words(db, model=m)
    assert set(key_texts) <= set(sent)

    # The start-up warm's texts are the rows plus the spec keys (engine.start_lookup_warm): a fresh process loads all.
    new_process()
    fresh = Fake(forbid=True)
    assert ll._vector_embedder(m, fresh, 100).fill([*row_texts, *key_texts]) == 4
    assert fresh.calls == 0


# ---- 2. binary decode
def test_store_load_never_parses_vectors_as_python_floats(db, monkeypatch):
    """pgvector's text form parsed into 1536 Python floats per row was 1.66 s of a 2.4 s load of 6,788 rows
    (cProfile, plan "Measured"); the binary form decodes in numpy."""
    import numpy as np
    from pgvector import Vector

    m, ts = model(), texts(5)
    seed_documents(db, ts)
    ll._vector_embedder(m, Fake(), 5).fill(ts)
    expected = {t: ll._cache[ll._key(t, m)].copy() for t in ts}
    new_process()

    def no_text(*a, **kw):
        raise AssertionError("vector parsed from its text form")

    monkeypatch.setattr(Vector, "_from_text", classmethod(no_text))
    assert lookup_word_store.load_lookup_vectors(db, m) == 5
    for t in ts:
        got = ll._cache[ll._key(t, m)]
        assert got.dtype == np.float32 and got.shape == (1536,)
        assert np.allclose(got, expected[t], atol=1e-6)


# ---- 3. a failed warm is not retried every turn
def _rows(ts):
    return [ll.LookupRow("category", f"zz{i}", t, (t,)) for i, t in enumerate(ts)]


def _warm_and_wait(rows, emb):
    """True when `warm` started a warm thread (joined before returning), False when it started none."""
    before = len(_started)
    ll.warm(rows, emb)
    new = [t for t in _started[before:] if t.name == "lookup-lists-warm"]
    for t in new:
        t.join(10)
        assert not t.is_alive(), "warm thread still running after 10 s"
    return bool(new)


def test_a_failed_warm_is_not_retried_by_the_next_turn(db, monkeypatch):
    m, ts = model(), texts(3, "zz storm fail")
    seed_documents(db, ts)
    down = Fake(fail_on_call=1)
    emb = ll._vector_embedder(m, down, 100)
    clock = [1000.0]
    monkeypatch.setattr(ll, "_now", lambda: clock[0], raising=False)

    assert _warm_and_wait(_rows(ts), emb)
    assert down.calls == 1
    clock[0] += 60
    assert not _warm_and_wait(_rows(ts), emb), "a turn within the window started another warm"
    assert down.calls == 1

    clock[0] += ll.WARM_RETRY_AFTER
    assert _warm_and_wait(_rows(ts), emb)
    assert down.calls == 2
    assert m not in ll._gave_up, "a warm that succeeded left the window standing"


def test_a_new_text_is_warmed_inside_the_window(db, monkeypatch):
    m, ts = model(), texts(3, "zz storm new")
    seed_documents(db, ts)
    down = Fake(fail_on_call=1)
    emb = ll._vector_embedder(m, down, 100)
    monkeypatch.setattr(ll, "_now", lambda: 1000.0, raising=False)

    assert _warm_and_wait(_rows(ts[:2]), emb)
    assert _warm_and_wait(_rows(ts), emb), "a text the failed warm never tried waits for nothing"
    assert emb.is_cached(ts)


def test_a_warm_that_succeeds_clears_the_window(db, monkeypatch):
    m, ts = model(), texts(2, "zz storm ok")
    seed_documents(db, ts)
    emb = ll._vector_embedder(m, Fake(), 100)
    assert _warm_and_wait(_rows(ts), emb)
    assert ll._gave_up == {}
