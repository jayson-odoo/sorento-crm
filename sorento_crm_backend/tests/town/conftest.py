"""Town tests share a real local Redis, but never the dev db 0: `queue_service.redis_conn` (and
the town route's by-name import of it) is pointed at db 15 for every test, and that db is flushed
before and after. Nothing else is touched."""
from __future__ import annotations

import pytest
import redis

TEST_REDIS_DB = 15


@pytest.fixture(autouse=True)
def _town_redis_clean(monkeypatch):
    from app.api.v1 import town as town_route
    from app.config import settings
    from app.services import queue_service

    client = redis.Redis.from_url(settings.redis_url, db=TEST_REDIS_DB, decode_responses=False)
    monkeypatch.setattr(queue_service, "redis_conn", client)
    monkeypatch.setattr(town_route, "redis_conn", client)
    monkeypatch.setattr(settings, "town_replica_database_url", None)
    client.flushdb()
    yield
    client.flushdb()
    client.close()
