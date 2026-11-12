"""CHATBOT-SPEED: the time before the parser is stored per piece on the `span_extract` trace event.

Crew's stage timings (12 Nov) put 2.11 s p50 before the parser on 11 Nov, of which the span call is 1.19 s; the rest
(row loading, span matching with its embedding round trip, the usage log write) was not stored anywhere. The event now
carries `prep_ms`, `resolve_ms` and `usage_log_ms`, so each speed fix gets a before/after from stored data.
Measurement only: no input to any model call changes. No network, no database.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from unittest import mock

import app.main  # noqa: F401  isort:skip
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import list_resolver, span_extract
from tests.chatbot.test_semantic_bridge import _rows  # noqa: F401


def _prep(prep_ms: int = 0):
    prep = engine_mod._SpanPrep(
        message="zz message", rows=_rows(), spec_key_rows=[], brand_words=frozenset(), numbers=[], held={}, embed=None,
        config=span_extract.SpanConfig("sys", 2, "openai", "gpt-zz", "ZZ-key", "label"),
    )
    prep.prep_ms = prep_ms
    return prep


def _answer():
    return span_extract.SpanAnswer([list_resolver.Span("zzkimlan", "customer")], {"prompt_tokens": 5}, 1)


def test_the_event_carries_the_prep_time_the_prep_measured():
    with mock.patch.object(span_extract, "extract", return_value=_answer()):
        _l, _e, event = engine_mod._span_lookup(_prep(prep_ms=321), session_factory=None, contact_respond_id="ZZ",
                                                dry_run=True, turn_id=None)
    assert event["prep_ms"] == 321


def test_the_event_times_the_span_matching():
    real = list_resolver.resolve

    def slow(*a, **k):
        time.sleep(0.06)
        return real(*a, **k)

    with mock.patch.object(span_extract, "extract", return_value=_answer()), \
            mock.patch.object(list_resolver, "resolve", side_effect=slow):
        _l, _e, event = engine_mod._span_lookup(_prep(), session_factory=None, contact_respond_id="ZZ",
                                                dry_run=True, turn_id=None)
    assert isinstance(event["resolve_ms"], int) and event["resolve_ms"] >= 60


def test_the_event_times_the_usage_log_write():
    @contextmanager
    def session(_factory):
        yield object()

    def slow_log(*a, **k):
        time.sleep(0.04)

    with mock.patch.object(span_extract, "extract", return_value=_answer()), \
            mock.patch.object(engine_mod, "_session", session), \
            mock.patch.object(engine_mod, "record_turn_llm_usage", side_effect=slow_log):
        _l, _e, event = engine_mod._span_lookup(_prep(), session_factory=object(), contact_respond_id="ZZ",
                                                dry_run=False, turn_id=None)
    assert isinstance(event["usage_log_ms"], int) and event["usage_log_ms"] >= 40


def test_a_dry_run_writes_no_usage_log_and_says_zero():
    with mock.patch.object(span_extract, "extract", return_value=_answer()):
        _l, _e, event = engine_mod._span_lookup(_prep(), session_factory=None, contact_respond_id="ZZ",
                                                dry_run=True, turn_id=None)
    assert event["usage_log_ms"] == 0


@contextmanager
def prep_world(load_rows=None):
    """`_span_prep` with every reader stubbed (no database): rows load through `load_rows`."""
    from app.services import product_spec_registry
    from app.services.chatbot.head import lookup_lists

    cfg = span_extract.SpanConfig("sys", 2, "openai", "gpt-zz", "ZZ-key", "label")
    with mock.patch.object(lookup_lists, "embedder", return_value=None), \
            mock.patch.object(engine_mod, "_lookup_visibility", return_value=(False, False, None, False)), \
            mock.patch.object(lookup_lists, "load_rows", side_effect=load_rows or (lambda *a, **k: _rows())), \
            mock.patch.object(product_spec_registry, "active_registry", return_value={}), \
            mock.patch.object(list_resolver, "spec_key_rows", return_value=[]), \
            mock.patch.object(lookup_lists, "brand_words", return_value=frozenset()), \
            mock.patch.object(lookup_lists, "number_hits", return_value=[]), \
            mock.patch.object(lookup_lists, "warm", return_value=None), \
            mock.patch.object(span_extract, "resolve_config", return_value=cfg):
        yield


def _run_prep():
    return engine_mod._span_prep(mock.MagicMock(), "zz message", frozenset(), "ZZ", None, None, {}, None)


def test_the_prep_measures_its_own_time():
    def slow_rows(*a, **k):
        time.sleep(0.05)
        return _rows()

    with prep_world(load_rows=slow_rows), mock.patch.object(span_extract, "extract", return_value=_answer()):
        prep = _run_prep()
    assert prep is not None and isinstance(prep.prep_ms, int) and prep.prep_ms >= 50
