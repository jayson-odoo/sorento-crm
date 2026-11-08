"""Town tests share one real local Redis (queue_service.redis_conn). Every key the town feature
writes starts with `town:`, so the suite clears exactly that prefix before and after each test
and touches nothing else."""
from __future__ import annotations

import pytest


def _clear_town_keys() -> None:
    from app.services.queue_service import redis_conn

    for key in redis_conn.scan_iter(match="town:*", count=500):
        redis_conn.delete(key)


@pytest.fixture(autouse=True)
def _town_redis_clean(monkeypatch):
    monkeypatch.delenv("TOWN_REPLICA_DATABASE_URL", raising=False)
    _clear_town_keys()
    yield
    _clear_town_keys()
