"""CHATBOT-SPEED fix #3: the span call starts before the row loading, and AC-S2-2's session clause is restated
(crew ruling, 12 Nov): the span call never holds a DB session while it waits; the turn's session closes without
waiting on it. Three conditions, each tested here:

1. the span thread gets plain data only (config values and the message text), never the session or an ORM object,
   and opens or uses no session;
2. when the step before the parser fails, or the turn never reads the answer, the in-flight result is dropped
   cleanly: the thread ends, nothing is written late;
3. a slow span call (0.5 s) is still in flight when the turn's open-session count returns to 0.
"""
from __future__ import annotations

import dataclasses
import threading
import time
from unittest import mock

import sqlalchemy.orm

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import span_extract
from tests.chatbot.conftest import counting_session_factory, session_factory  # noqa: F401
from tests.chatbot.test_chatbot_speed_span_timing import _answer, _rows, _run_prep, prep_world
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401
from tests.chatbot.test_span_extract import BRAND, run, seed_world, spans_json

PLAIN = (str, int, float, bool, type(None))


def _span_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "span-call" and t.is_alive()]


# 1. plain data only, no session from the span thread ----------------------------------------------------------------

def test_the_span_thread_gets_plain_data_and_touches_no_session(
    counting_session_factory, session_factory, seeded, stub_access, monkeypatch  # noqa: F811
):
    seed_world(session_factory)
    used_in: list[str] = []
    real_execute, real_init = sqlalchemy.orm.Session.execute, sqlalchemy.orm.Session.__init__

    def execute(self, *a, **k):
        used_in.append(threading.current_thread().name)
        return real_execute(self, *a, **k)

    def init(self, *a, **k):
        used_in.append(threading.current_thread().name)
        real_init(self, *a, **k)

    monkeypatch.setattr(sqlalchemy.orm.Session, "execute", execute)
    monkeypatch.setattr(sqlalchemy.orm.Session, "__init__", init)
    seen: list[tuple] = []
    real_extract = span_extract.extract

    def spy(config, message):
        seen.append((threading.current_thread().name, config, message))
        return real_extract(config, message)

    monkeypatch.setattr(span_extract, "extract", spy)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} basin",
            span=spans_json((BRAND, "brand")), factory=counting_session_factory)
    assert r.events == ["span", "parser"], r.events
    assert len(seen) == 1
    thread_name, config, message = seen[0]
    assert thread_name == "span-call", "the span call did not run on its own thread"
    assert isinstance(message, str)
    assert all(isinstance(getattr(config, f.name), PLAIN) for f in dataclasses.fields(config)), config
    assert "span-call" not in used_in, "the span thread opened or used a DB session"


# 2. a failed step or an unread answer drops the result cleanly ------------------------------------------------------

def test_a_failed_prep_drops_the_in_flight_call_cleanly():
    def call(config, message):
        time.sleep(0.2)
        return _answer()

    def broken_rows(*a, **k):
        raise RuntimeError("zz loader down")

    with prep_world(load_rows=broken_rows), mock.patch.object(span_extract, "extract", side_effect=call), \
            mock.patch.object(engine_mod, "record_turn_llm_usage") as usage_log:
        assert _run_prep() is None
        time.sleep(0.4)
    assert _span_threads() == [], "the span thread outlived its call"
    usage_log.assert_not_called()


def test_an_answer_the_turn_never_reads_is_dropped_cleanly():
    def call(config, message):
        time.sleep(0.2)
        return _answer()

    with prep_world(), mock.patch.object(span_extract, "extract", side_effect=call), \
            mock.patch.object(engine_mod, "record_turn_llm_usage") as usage_log:
        prep = _run_prep()
        assert prep is not None and prep.span_answer is not None
        time.sleep(0.4)  # the turn ended before `_span_lookup`
    assert _span_threads() == [], "the span thread outlived its call"
    usage_log.assert_not_called()


# 3. a slow call is still in flight when the turn's sessions are all closed ------------------------------------------

def test_a_slow_span_call_holds_no_session_while_it_waits(
    counting_session_factory, session_factory, seeded, stub_access, monkeypatch  # noqa: F811
):
    seed_world(session_factory)
    samples: list[int] = []
    real_extract = span_extract.extract

    def slow(config, message):
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            samples.append(counting_session_factory.state["open"])
            time.sleep(0.01)
        return real_extract(config, message)

    monkeypatch.setattr(span_extract, "extract", slow)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} basin",
            span=spans_json((BRAND, "brand")), factory=counting_session_factory)
    assert r.events == ["span", "parser"], r.events
    assert samples and samples[-1] == 0, f"a session was still open at the end of the span call: {samples[-5:]}"
    assert samples.index(0) < len(samples) - 1, "the turn's session closed only when the call ended"
