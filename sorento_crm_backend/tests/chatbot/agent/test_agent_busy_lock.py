"""AGENT-PANEL-FIXES A: the one-turn-at-a-time lock cannot stick.

Owner, 11 Nov: a follow-up long after the first answer got "I am still working on your earlier message in
this chat". The lock was a Postgres session advisory lock; behind pgbouncer in transaction mode its unlock
could run on another server connection and fail silently. The lock is now a Redis key with a TTL.
"""
from __future__ import annotations

import logging
import time
import uuid

import pytest
import redis

from app.config import settings
from app.services.chatbot.agent import loop as agent_loop
from app.services.chatbot.agent.loop import AgentBusy, single_flight


def _client():
    return redis.from_url(settings.redis_url)


@pytest.fixture
def key():
    try:
        _client().ping()
    except Exception:  # noqa: BLE001
        pytest.skip("Redis is not reachable")
    k = f"zzt-{uuid.uuid4().hex}"
    yield k
    _client().delete(f"{agent_loop.BUSY_LOCK_PREFIX}{k}")


def test_a_held_lock_makes_the_next_turn_busy_and_its_release_frees_it(key):
    with single_flight(key):
        with pytest.raises(AgentBusy):
            with single_flight(key):
                pass
    with single_flight(key):  # the first turn finished: the next message is answered
        pass


def test_take_on_one_connection_and_release_on_another_still_frees_it(key, monkeypatch):
    """What pgbouncer transaction mode did to the advisory lock: every call on a fresh connection."""
    clients = []

    def fresh():
        clients.append(_client())
        return clients[-1]

    monkeypatch.setattr(agent_loop, "_busy_redis", fresh)
    with single_flight(key):
        pass
    with single_flight(key):  # NOT busy
        pass
    assert len(clients) == 4, "acquire and release each went through their own connection"
    ids = {id(c.connection_pool) for c in clients}
    assert len(ids) == 4


def test_a_lock_whose_release_never_ran_frees_itself_after_its_ttl(key):
    """A killed process never runs `finally`: the TTL frees the chat."""
    held = single_flight(key, ttl_seconds=0.3)
    held.__enter__()  # and never exits
    with pytest.raises(AgentBusy):
        with single_flight(key):
            pass
    time.sleep(0.5)
    with single_flight(key):
        pass


def test_the_default_ttl_covers_the_longest_turn_the_settings_allow(key):
    with single_flight(key):
        ttl_ms = _client().pttl(f"{agent_loop.BUSY_LOCK_PREFIX}{key}")
    assert 300_000 < ttl_ms <= agent_loop.BUSY_LOCK_TTL_SECONDS * 1000


def test_a_late_release_never_frees_a_later_turns_lock_and_logs_a_warning(key, caplog):
    first = single_flight(key, ttl_seconds=0.2)
    first.__enter__()
    time.sleep(0.4)  # the first turn outlived its TTL
    with single_flight(key):  # a second turn takes the chat
        with caplog.at_level(logging.WARNING, logger=agent_loop.logger.name):
            first.__exit__(None, None, None)
        assert any("already gone" in r.getMessage() for r in caplog.records), caplog.text
        with pytest.raises(AgentBusy):  # the second turn still holds it
            with single_flight(key):
                pass


def test_redis_down_runs_the_turn_unlocked(monkeypatch, caplog):
    class Down:
        def set(self, *a, **k):
            raise redis.ConnectionError("down")

    monkeypatch.setattr(agent_loop, "_busy_redis", lambda: Down())
    ran = []
    with caplog.at_level(logging.WARNING, logger=agent_loop.logger.name):
        with single_flight("zzt-any"):
            ran.append(1)
    assert ran == [1]
    assert any("unavailable" in r.getMessage() for r in caplog.records)

