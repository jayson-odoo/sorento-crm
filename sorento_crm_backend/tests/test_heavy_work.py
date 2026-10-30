"""BACKEND-MEM-2 S2: at most HEAVY_HANDLER_CONCURRENCY (default 1) heavy handlers run at once in a worker.

Since API-NONBLOCKING (#1951) a `def` handler runs in anyio's 40-thread pool, so a worker can build several exports
or reports at once, and it keeps the memory of the busiest moment until it exits (+160 MB kept one at a time, +528
MB eight at once, +900-1,170 MB 24 at once, with no speed gained: documentation/plans/deploy/PLAN-backend-mem-2-30oct.md).
No database, no network."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils import heavy_work


@pytest.fixture(autouse=True)
def one_at_a_time(monkeypatch):
    monkeypatch.setattr(heavy_work, "_semaphore", threading.BoundedSemaphore(1))


def _overlap(fn, n=4):
    """Run `fn` on n threads at once; return the most calls seen inside it at the same moment."""
    inside = [0]
    most = [0]
    lock = threading.Lock()

    def body():
        with lock:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with lock:
            inside[0] -= 1

    wrapped = fn(body)
    threads = [threading.Thread(target=wrapped) for _ in range(n)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    return most[0]


def test_heavy_handlers_run_one_at_a_time_by_default():
    assert _overlap(heavy_work.heavy) == 1


def test_the_knob_allows_more_at_once(monkeypatch):
    monkeypatch.setattr(heavy_work, "_semaphore", threading.BoundedSemaphore(2))
    assert _overlap(heavy_work.heavy) == 2


def test_zero_turns_the_limit_off(monkeypatch):
    monkeypatch.setattr(heavy_work, "_semaphore", None)
    assert _overlap(heavy_work.heavy) == 4


def test_the_knob_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "3")
    assert heavy_work._from_env()._value == 3  # noqa: SLF001 - BoundedSemaphore's own counter
    monkeypatch.setenv("HEAVY_HANDLER_CONCURRENCY", "0")
    assert heavy_work._from_env() is None
    monkeypatch.delenv("HEAVY_HANDLER_CONCURRENCY")
    assert heavy_work._from_env()._value == 1  # noqa: SLF001


def test_a_heavy_handler_calling_another_does_not_deadlock():
    @heavy_work.heavy
    def inner():
        return "inner"

    @heavy_work.heavy
    def outer():
        return inner()

    done: list[str] = []
    t = threading.Thread(target=lambda: done.append(outer()))
    t.start()
    t.join(5)
    assert done == ["inner"]


def test_the_slot_is_released_when_the_handler_raises():
    @heavy_work.heavy
    def boom():
        raise ValueError("zz")

    with pytest.raises(ValueError):
        boom()
    assert heavy_work._semaphore.acquire(blocking=False)  # noqa: SLF001
    heavy_work._semaphore.release()  # noqa: SLF001


def test_an_async_handler_is_refused():
    """An `async def` runs on the event loop: waiting on the semaphore there would stall every request."""
    with pytest.raises(TypeError):

        @heavy_work.heavy
        async def handler():
            return 1


def test_fastapi_still_sees_the_handler_signature():
    app = FastAPI()

    @app.get("/zz/{item}")
    @heavy_work.heavy
    def handler(item: str, limit: int = 5):
        return {"item": item, "limit": limit}

    assert TestClient(app).get("/zz/a?limit=7").json() == {"item": "a", "limit": 7}
