"""ENTITY-EXTRACT-MATCH S3 round 2b (#1898): the background warm retries a rate limit (AC-S3-13) and logs its
completion (AC-S3-14). The turn path never retries or sleeps."""
from __future__ import annotations

import logging
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
