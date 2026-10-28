"""ENTITY-EXTRACT-MATCH S3 round 2b (#1898): the background warm retries a rate limit (AC-S3-13) and logs its
completion (AC-S3-14). The turn path never retries or sleeps."""
from __future__ import annotations

import logging
import random
import threading
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.services.llm_provider import GeminiHTTPError
from app.services.chatbot.head import lookup_lists as ll
from tests.chatbot.test_semantic_bridge import R

LOGGER = "app.services.chatbot.head.lookup_lists"


class RateLimitError(Exception):
    """An OpenAI-style error: only the class name says rate limit."""


class Flaky:
    """request(chunk): raises `errors` in order (one per call) while any remain, then succeeds."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def __call__(self, chunk):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return [[1.0, 0.0, 0.0] for _ in chunk]


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})
    monkeypatch.setattr(ll, "_warm_lock", threading.Lock())
    sleeps: list[float] = []
    monkeypatch.setattr(ll, "_sleep", sleeps.append, raising=False)
    monkeypatch.setattr(ll, "_jitter", lambda: 0.0, raising=False)
    return sleeps


def _model():
    return "zz-model-" + uuid.uuid4().hex[:8]


def _texts(n):
    return [f"zz text {i}" for i in range(n)]


def test_ac_s3_13_one_429_is_waited_out_once_and_every_text_is_cached(env):
    flaky = Flaky([GeminiHTTPError("zz", 429)])
    emb = ll._vector_embedder(_model(), flaky, 2)
    texts = _texts(4)
    emb.fill(texts)
    assert env == [15], env
    assert emb.is_cached(texts)


def test_ac_s3_13_three_429s_back_off_15_30_60(env):
    flaky = Flaky([GeminiHTTPError("zz", 429)] * 3)
    emb = ll._vector_embedder(_model(), flaky, 2)
    texts = _texts(4)
    emb.fill(texts)
    assert env == [15, 30, 60], env
    assert emb.is_cached(texts)


def test_ac_s3_13_four_429s_give_up_and_earlier_chunks_stay_cached(env):
    # chunk 1 succeeds, chunk 2 hits four 429s in a row
    calls = {"n": 0}

    def request(chunk):
        calls["n"] += 1
        if calls["n"] == 1:
            return [[1.0, 0.0, 0.0] for _ in chunk]
        raise GeminiHTTPError("zz", 429)

    emb = ll._vector_embedder(_model(), request, 2)
    texts = _texts(4)
    with pytest.raises(GeminiHTTPError):
        emb.fill(texts)
    assert env == [15, 30, 60], env
    assert emb.is_cached(texts[:2]) and not emb.is_cached(texts[2:])


@pytest.mark.parametrize("error", [GeminiHTTPError("zz", 500), RuntimeError("zz")])
def test_ac_s3_13_other_errors_are_not_retried(env, error):
    flaky = Flaky([error])
    emb = ll._vector_embedder(_model(), flaky, 2)
    with pytest.raises(type(error)):
        emb.fill(_texts(2))
    assert env == [] and flaky.calls == 1, (env, flaky.calls)


def test_ac_s3_13_a_class_named_rate_limit_is_retried(env):
    flaky = Flaky([RateLimitError("zz")])
    emb = ll._vector_embedder(_model(), flaky, 2)
    texts = _texts(2)
    emb.fill(texts)
    assert env == [15], env
    assert emb.is_cached(texts)


def test_ac_s3_13_the_turn_path_raises_on_429_without_sleeping(env):
    emb = ll._vector_embedder(_model(), Flaky([GeminiHTTPError("zz", 429)]), 2)
    with pytest.raises(GeminiHTTPError):
        emb(_texts(2))
    assert env == []
    emb2 = ll._vector_embedder(_model(), Flaky([GeminiHTTPError("zz", 429)]), 2)
    with pytest.raises(GeminiHTTPError):
        emb2.pieces(["zz piece"])
    assert env == []


def test_ac_s3_14_a_finished_warm_logs_model_and_count(env, caplog):
    model = _model()
    emb = ll._vector_embedder(model, Flaky([]), 2)
    rows = [R("customer", f"c{i}", f"zz cust {i}") for i in range(5)]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        ll.warm(rows, emb)
        for t in threading.enumerate():
            if t.name == "lookup-lists-warm":
                t.join(10)
    lines = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]
    assert any(model in r.getMessage() and "5" in r.getMessage() and "warm" in r.getMessage() for r in lines), [
        r.getMessage() for r in caplog.records
    ]


def test_ac_s3_14_a_failed_warm_logs_a_warning(env, caplog):
    emb = ll._vector_embedder(_model(), Flaky([RuntimeError("zz")]), 2)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        ll.warm([R("customer", "c1", "zz cust")], emb)
        for t in threading.enumerate():
            if t.name == "lookup-lists-warm":
                t.join(10)
    assert any(r.name == LOGGER and r.levelno == logging.WARNING for r in caplog.records), caplog.records


# ---- round 2c
def test_ac_s3_13_full_jitter_stretches_each_wait_by_half(env, monkeypatch):
    monkeypatch.setattr(ll, "_jitter", lambda: 1.0, raising=False)
    emb = ll._vector_embedder(_model(), Flaky([GeminiHTTPError("zz", 429)] * 3), 2)
    emb.fill(_texts(2))
    assert env == [22.5, 45.0, 90.0], env


def test_ac_s3_13_default_jitter_keeps_every_wait_within_one_to_one_and_a_half(env, monkeypatch):
    monkeypatch.setattr(ll, "_jitter", random.random, raising=False)
    sleeps: list[float] = []
    monkeypatch.setattr(ll, "_sleep", sleeps.append, raising=False)
    monkeypatch.setattr(ll, "_cache", {})
    emb = ll._vector_embedder(_model(), Flaky([GeminiHTTPError("zz", 429)] * 3), 2)
    emb.fill(_texts(2))
    assert len(sleeps) == 3 and callable(getattr(ll, "_jitter", None)), sleeps
    for got, w in zip(sleeps, (15, 30, 60)):
        assert w <= got <= 1.5 * w, sleeps


class ResponseOnly(Exception):
    def __init__(self, status):
        super().__init__("zz")
        self.response = type("R", (), {"status_code": status})()


def test_ac_s3_13_a_429_on_the_response_object_is_retried(env):
    emb = ll._vector_embedder(_model(), Flaky([ResponseOnly(429)]), 2)
    texts = _texts(2)
    emb.fill(texts)
    assert env == [15], env
    assert emb.is_cached(texts)


def test_ac_s3_13_an_exhausted_quota_429_is_not_waited_out(env):
    flaky = Flaky([GeminiHTTPError("zz insufficient_quota", 429)])
    emb = ll._vector_embedder(_model(), flaky, 2)
    with pytest.raises(GeminiHTTPError):
        emb.fill(_texts(2))
    assert env == [] and flaky.calls == 1, (env, flaky.calls)


# AC-S3-15: a warm with nothing to fetch is a no-op
def test_ac_s3_15_a_fully_cached_warm_starts_nothing_and_logs_nothing(env, caplog, monkeypatch):
    emb = ll._vector_embedder(_model(), Flaky([]), 2)
    rows = [R("customer", f"c{i}", f"zz cust {i}") for i in range(3)]
    emb.fill(ll.row_texts(rows))
    started = []
    real = threading.Thread

    class Spy(real):
        def __init__(self, *a, **kw):
            started.append(kw.get("name"))
            super().__init__(*a, **kw)

    monkeypatch.setattr(ll.threading, "Thread", Spy)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        ll.warm(rows, emb)
    assert "lookup-lists-warm" not in started, started
    assert not [r for r in caplog.records if r.name == LOGGER], caplog.records
    assert ll._warm_lock.acquire(blocking=False), "the no-op warm took the lock"
    ll._warm_lock.release()


def test_ac_s3_15_a_partly_cached_warm_still_runs_and_logs_once(env, caplog):
    emb = ll._vector_embedder(_model(), Flaky([]), 2)
    rows = [R("customer", f"c{i}", f"zz cust {i}") for i in range(5)]
    emb.fill(ll.row_texts(rows)[:2])
    with caplog.at_level(logging.INFO, logger=LOGGER):
        ll.warm(rows, emb)
        for t in threading.enumerate():
            if t.name == "lookup-lists-warm":
                t.join(10)
    assert emb.is_cached(ll.row_texts(rows))
    assert len([r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]) == 1, caplog.records
