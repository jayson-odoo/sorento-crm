"""ENTITY-EXTRACT-MATCH S3 round 2 (#1898): the startup warm of the lookup vectors (AC-S3-9..12).

Contract: `engine.start_lookup_warm(session_factory=None)` starts ONE daemon thread "lookup-lists-startup-warm" and
returns it at once (None when `CHATBOT_LOOKUP_WARM_ENABLED` is off). The thread opens a session, sets company scope
None, builds `lookup_lists.embedder(db)`, loads the widest rows plus the spec-name rows, closes the session, then
`lookup_lists.warm(rows, embed)`. Everything is advisory.
"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace
from unittest import mock

import pytest

import app.main  # noqa: F401  isort:skip
from fastapi.testclient import TestClient

from app.models.base import get_company_scope
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import list_resolver
from app.services.chatbot.head import lookup_lists as ll
from tests.chatbot.test_semantic_bridge import GEM_MODEL, R, fresh_cache  # noqa: F401

SWITCH = "CHATBOT_LOOKUP_WARM_ENABLED"
ROW_TEXT = "ZZ warm gold"
SPEC_TEXT = "ZZ warm finish"
SPAN = "zzmelo"


class FakeSession:
    """Stands in for a SQLAlchemy session: `.info` for the scope, an event log for rollback/close."""

    def __init__(self, log):
        self.info = {}
        self.log = log
        self.scope_at_load = "unset"

    def rollback(self):
        self.log.append("rollback")

    def close(self):
        self.log.append("close")


class World:
    def __init__(self):
        self.log: list[str] = []
        self.requested: list[str] = []
        self.sessions: list[FakeSession] = []
        self.load_kwargs: dict | None = None
        self.release = threading.Event()
        self.block = False
        self.rows = [R("customer", "c1", ROW_TEXT)]
        self.spec_rows = [R("spec_key", "k1", SPEC_TEXT)]

    def factory(self):
        s = FakeSession(self.log)
        self.sessions.append(s)
        return s

    def request(self, chunk):
        self.log.append("embed")
        if self.block:
            self.release.wait(30)
        self.requested.extend(chunk)
        # span -> (1,0,0); the row text -> cosine 0.9 against it; anything else orthogonal
        out = []
        for t in chunk:
            if t == SPAN:
                out.append([1.0, 0.0, 0.0])
            elif t == ROW_TEXT:
                out.append([0.9, (1 - 0.81) ** 0.5, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out


@pytest.fixture()
def world(monkeypatch, fresh_cache):  # noqa: F811
    w = World()
    monkeypatch.setenv(SWITCH, "1")
    emb = ll._vector_embedder(GEM_MODEL, w.request, 100)
    monkeypatch.setattr(ll, "EMBED", emb)
    monkeypatch.setattr(ll, "_warm_lock", threading.Lock())

    def load_rows(db, **kwargs):
        w.log.append("load")
        w.load_kwargs = kwargs
        w.scope_at_load = get_company_scope(db)
        return list(w.rows)

    monkeypatch.setattr(ll, "load_rows", load_rows)
    monkeypatch.setattr(list_resolver, "spec_key_rows", lambda registry: list(w.spec_rows))
    import app.services.product_spec_registry as reg

    monkeypatch.setattr(reg, "active_registry", lambda db: SimpleNamespace())
    w.embedder = emb
    yield w
    w.release.set()
    _join_all()


def _join_all(thread=None):
    if thread is not None:
        thread.join(10)
    for t in threading.enumerate():
        if t.name in ("lookup-lists-startup-warm", "lookup-lists-warm"):
            t.join(10)


def _start(w):
    t = engine_mod.start_lookup_warm(w.factory)
    assert t is not None
    return t


# 1. AC-S3-9: start-up does not wait for the provider
def test_ac_s3_9_start_returns_at_once_while_the_embedder_blocks(world):
    world.block = True
    t0 = time.monotonic()
    thread = engine_mod.start_lookup_warm(world.factory)
    took = time.monotonic() - t0
    assert thread is not None and took < 1.0, took
    assert thread.daemon and thread.name == "lookup-lists-startup-warm"
    world.release.set()
    _join_all(thread)
    assert not thread.is_alive()


# 2. AC-S3-10: the first turn after the warm has meaning
def test_ac_s3_10_a_fresh_turn_embedder_has_meaning_after_the_warm(world):
    _join_all(_start(world))
    fresh = ll._vector_embedder(GEM_MODEL, world.request, 100)
    rows = [*world.rows, *world.spec_rows]
    assert fresh is not world.embedder
    assert ll.usable_embedder(rows, fresh) is fresh
    res = list_resolver.resolve([list_resolver.Span(SPAN, None)], world.rows, embed=fresh)[0]
    assert res.status == "resolved" and res.candidates[0].signal == "meaning" and res.candidates[0].row.key == "c1", res


# 3. AC-S3-9 / AC-S3-12: widest visibility, spec-name rows, scope None
def test_ac_s3_9_loads_the_widest_rows_and_the_spec_names_under_scope_none(world):
    _join_all(_start(world))
    kw = world.load_kwargs
    assert kw is not None, "the loader was never called"
    assert kw.get("include_salespeople") is True and kw.get("include_customers") is True
    assert "customer_ids" in kw and kw["customer_ids"] is None
    assert world.scope_at_load is None
    assert ROW_TEXT in world.requested and SPEC_TEXT in world.requested


# 4. AC-S3-12: the read session is closed before any embedding request
def test_ac_s3_12_the_session_is_closed_before_the_first_embed_request(world):
    _join_all(_start(world))
    assert "embed" in world.log and "close" in world.log and "rollback" in world.log, world.log
    first_embed = world.log.index("embed")
    assert world.log.index("rollback") < first_embed and world.log.index("close") < first_embed, world.log


# 5. AC-S3-11: advisory
def test_ac_s3_11_no_embedder_means_no_request_and_no_error(world, monkeypatch):
    monkeypatch.setattr(ll, "EMBED", None)
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda a: errors.append(a))
    _join_all(_start(world))
    assert world.requested == [] and "embed" not in world.log and not errors, (world.log, errors)


def test_ac_s3_11_a_loader_failure_is_swallowed(world, monkeypatch):
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda a: errors.append(a))

    def boom(db, **kw):
        raise RuntimeError("zz database down")

    monkeypatch.setattr(ll, "load_rows", boom)
    _join_all(_start(world))
    assert world.requested == [] and not errors, errors


def test_ac_s3_11_a_provider_failure_is_swallowed(world, monkeypatch):
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda a: errors.append(a))

    def bad(chunk):
        raise RuntimeError("zz provider down")

    monkeypatch.setattr(ll, "EMBED", ll._vector_embedder(GEM_MODEL, bad, 100))
    _join_all(_start(world))
    assert not errors, errors


# 6. AC-S3-12: the switch
@pytest.mark.parametrize("value", ["0", "false", "off", "no"])
def test_ac_s3_12_switch_off_returns_none_and_builds_nothing(world, monkeypatch, value):
    monkeypatch.setenv(SWITCH, value)
    spy = mock.Mock(return_value=None)
    monkeypatch.setattr(ll, "embedder", spy)
    assert engine_mod.start_lookup_warm(world.factory) is None
    _join_all()
    assert not spy.called and world.sessions == []


# 7. AC-S3-12: the suite itself runs with the warm off
def test_ac_s3_12_conftest_turns_the_warm_off():
    assert os.environ.get(SWITCH) == "0"


# 8. AC-S3-9 / AC-S3-11: start-up wiring
def test_ac_s3_9_startup_calls_start_lookup_warm_once():
    with mock.patch.object(engine_mod, "start_lookup_warm", create=True) as start:
        with TestClient(app.main.app):
            pass
    assert start.call_count == 1, start.call_count


def test_ac_s3_11_startup_completes_when_start_lookup_warm_raises():
    with mock.patch.object(engine_mod, "start_lookup_warm", create=True, side_effect=RuntimeError("zz")) as start:
        with TestClient(app.main.app) as client:
            assert client is not None
    assert start.call_count == 1, start.call_count
