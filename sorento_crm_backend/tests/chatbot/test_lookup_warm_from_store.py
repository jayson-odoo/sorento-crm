"""LOOKUP-EMBED-CENTRAL slice 4: the lookup warm over the `lookup_word` store. Replaces the contract of the retired
per-container shared vector file (SPAN-PASS-PROD AC-1..AC-11): "one worker embeds, the rest load" now means a warm
loads the stored vectors with one SELECT (`load_lookup_vectors`), embeds only what is still missing, and writes it
back (`write_back`). A second process is simulated by clearing the module cache. Postgres only, no network."""
from __future__ import annotations

import hashlib
import logging
import uuid

import numpy as np
import pytest

import app.main  # noqa: F401  isort:skip
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import lookup_word_store
from tests._pg_fixture import blank_session

LOGGER = "app.services.chatbot.head.lookup_lists"


def vec(text):
    d = hashlib.sha256(text.encode()).digest()[:8]
    return [(b + 1) / 256.0 for b in d] + [0.0] * 1528


class Fake:
    """request(chunk): records every requested text, returns deterministic non-zero 1536-wide vectors."""

    def __init__(self, fail_on_call=None, forbid=False, error=None):
        self.texts: list[str] = []
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.forbid = forbid
        self.error = error

    def __call__(self, chunk):
        self.calls += 1
        self.texts.extend(chunk)
        assert not self.forbid, f"unexpected provider request for {chunk}"
        if self.fail_on_call == self.calls:
            raise self.error or RuntimeError("zz provider down")
        return [vec(t) for t in chunk]


class RateLimited(Exception):
    status_code = 429


def model(tag="m"):
    return "zzmodel" + tag + uuid.uuid4().hex[:8]


def texts(n, prefix="zz span"):
    return [f"{prefix} {i}" for i in range(n)]


class _Session:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


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
    monkeypatch.setattr(ll, "_sleep", lambda s: None, raising=False)
    monkeypatch.setattr(ll, "_jitter", lambda: 0.0, raising=False)
    monkeypatch.setattr(database, "SessionLocal", lambda: _Session(db))


def seed_documents(db, all_texts):
    """Two active lookup_word documents between them holding every text (the rows the warm's vectors land on)."""
    half = len(all_texts) // 2
    for n, part in enumerate((all_texts[: half or 1], all_texts[half or 1 :])):
        db.add(
            EmbeddingDocument(
                id=str(uuid.uuid4()), source_type="lookup_word", source_id=f"category:zzwarm-{uuid.uuid4().hex[:6]}-{n}",
                title="zz", body_text="\n".join(part), source_hash="h", is_active=True,
            )
        )
    db.flush()


def new_process():
    ll._cache.clear()
    ll._matrices.clear()
    ll._pieces.clear()


def stored(db, m):
    db.expire_all()
    return {c.chunk_text for c in db.query(EmbeddingChunk).filter_by(source_type="lookup_word", model_name=m, is_current=True)}


# ---- was AC-1 / AC-2: one worker embeds, the rest load
def test_second_process_loads_from_the_store_and_sends_nothing(db):
    m, ts = model(), texts(6)
    seed_documents(db, ts)
    first = Fake()
    ll._vector_embedder(m, first, 2).fill(ts)
    assert sorted(first.texts) == sorted(ts)
    assert stored(db, m) == set(ts)
    new_process()
    second = Fake(forbid=True)
    emb = ll._vector_embedder(m, second, 2)
    assert emb.fill(ts) == len(ts)  # how many vectors came from the store
    assert second.calls == 0 and emb.is_cached(ts)


def test_only_texts_the_store_lacks_are_sent(db):
    m = model()
    seed_documents(db, texts(5))
    ll._vector_embedder(m, Fake(), 2).fill(texts(3))
    new_process()
    second = Fake()
    ll._vector_embedder(m, second, 2).fill(texts(5))
    assert sorted(second.texts) == sorted(texts(5)[3:])


# ---- was AC-4: a failed warm keeps what it stored
def test_failed_warm_writes_back_the_chunks_it_finished_and_the_next_warm_sends_the_rest(db):
    m, ts = model(), texts(4)
    seed_documents(db, ts)
    with pytest.raises(RuntimeError):
        ll._vector_embedder(m, Fake(fail_on_call=2), 2).fill(ts)
    assert stored(db, m) == set(ts[:2])
    new_process()
    nxt = Fake()
    ll._vector_embedder(m, nxt, 2).fill(ts)
    assert sorted(nxt.texts) == sorted(ts[2:])


# ---- was AC-5: per model
def test_vectors_are_per_model(db):
    a, b, ts = model("a"), model("b"), texts(3)
    seed_documents(db, ts)
    ll._vector_embedder(a, Fake(), 2).fill(ts)
    new_process()
    fb = Fake()
    ll._vector_embedder(b, fb, 2).fill(ts)
    assert sorted(fb.texts) == sorted(ts), "model b read model a vectors"
    new_process()
    fa = Fake(forbid=True)
    ll._vector_embedder(a, fa, 2).fill(ts)
    assert fa.calls == 0


# ---- was AC-6: stored vectors come back as unit float32
def test_loaded_vectors_are_unit_float32(db):
    m, ts = model(), texts(4)
    seed_documents(db, ts)
    first = ll._vector_embedder(m, Fake(), 2)
    first.fill(ts)
    expected = {t: np.array(ll._cache[ll._key(t, m)]) for t in ts}
    new_process()
    second = ll._vector_embedder(m, Fake(forbid=True), 2)
    second.fill(ts)
    for t in ts:
        got = ll._cache[ll._key(t, m)]
        assert got.dtype == np.float32 and abs(float(np.linalg.norm(got)) - 1.0) < 1e-5
        assert np.allclose(got, expected[t], atol=1e-5)


# ---- was AC-7: an unusable store is advisory
def test_a_store_that_cannot_be_read_warns_and_the_warm_embeds_everything(db, monkeypatch, caplog):
    m, ts = model(), texts(3)

    def boom(*a, **k):
        raise RuntimeError("zz store down")

    monkeypatch.setattr(lookup_word_store, "load_lookup_vectors", boom)
    fake = Fake()
    emb = ll._vector_embedder(m, fake, 2)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        emb.fill(ts)
    assert sorted(fake.texts) == sorted(ts) and emb.is_cached(ts)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---- was AC-10: the turn path never touches the store
def test_embed_and_pieces_never_read_or_write_the_store(db, monkeypatch):
    import app.database as database

    m, ts = model(), texts(3)

    def forbidden():
        raise AssertionError("the turn path opened a session")

    monkeypatch.setattr(database, "SessionLocal", forbidden)
    fake = Fake()
    emb = ll._vector_embedder(m, fake, 2)
    emb(ts)
    emb.pieces(["zz piece"])
    assert sorted(fake.texts) == sorted([*ts, "zz piece"])


# ---- 429 retry waits and stop on persistent failure (the warm path that survives)
def test_a_rate_limited_chunk_is_waited_out_with_jitter_and_then_succeeds(db, monkeypatch):
    m, ts = model(), texts(2)
    seed_documents(db, ts)
    sleeps: list[float] = []
    monkeypatch.setattr(ll, "_sleep", sleeps.append)
    monkeypatch.setattr(ll, "_jitter", lambda: 1.0)
    fake = Fake(fail_on_call=1, error=RateLimited("zz rate limited"))
    ll._vector_embedder(m, fake, 2).fill(ts)
    assert sleeps == [ll.WARM_RETRY_WAITS[0] * 1.5]
    assert fake.calls == 2 and stored(db, m) == set(ts)


def test_a_persistently_rate_limited_chunk_stops_after_every_wait(db, monkeypatch):
    m, ts = model(), texts(2)
    seed_documents(db, ts)
    sleeps: list[float] = []
    monkeypatch.setattr(ll, "_sleep", sleeps.append)

    class Always(Fake):
        def __call__(self, chunk):
            self.calls += 1
            raise RateLimited("zz still rate limited")

    always = Always()
    with pytest.raises(RateLimited):
        ll._vector_embedder(m, always, 2).fill(ts)
    assert sleeps == list(ll.WARM_RETRY_WAITS)
    assert always.calls == len(ll.WARM_RETRY_WAITS) + 1
    assert stored(db, m) == set()
