"""Town tests share a real local Redis, but never the dev db 0: `queue_service.redis_conn` (and
the town route's by-name import of it) is pointed at a private db for every test, and only
its `town:*` keys are deleted before and after. Nothing else is touched.

Under xdist each worker gets its own db (gw0 -> 15, gw1 -> 14, ... down to 8): the code's keys are
fixed (`town:lock`, `town:{company}:{day}:*`), so two workers sharing one db flushed each other's
keys mid-test (crew-tests.sh run, 8 Nov: 8 failures that passed serially)."""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import pytest
import redis


def _test_redis_db() -> int:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    index = int(worker[2:]) if worker[2:].isdigit() else 0
    return 15 - (index % 8)


def _url_with_db(url: str, db: int) -> str:
    # redis-py lets a db in the URL path win over a `db=` keyword, so the URL itself is rewritten
    # (`redis://host:6379/0` + db=15 kept serving db 0, the dev stack's db).
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db}", parts.query, parts.fragment))


def _clear(client) -> None:
    for key in client.scan_iter(match="town:*", count=500):
        client.delete(key)


@pytest.fixture(autouse=True)
def _town_redis_clean(monkeypatch):
    from app.api.v1 import town as town_route
    from app.config import settings
    from app.services import queue_service

    client = redis.Redis.from_url(_url_with_db(settings.redis_url, _test_redis_db()), decode_responses=False)
    monkeypatch.setattr(queue_service, "redis_conn", client)
    monkeypatch.setattr(town_route, "redis_conn", client)
    monkeypatch.setattr(settings, "town_replica_database_url", None)
    assert client.connection_pool.connection_kwargs["db"] >= 8, "town tests must never flush the dev db"
    _clear(client)
    yield
    _clear(client)
    client.close()
