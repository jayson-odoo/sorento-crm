"""Sub-plan A - generic per-IP fixed-window rate limiter.

Covers: disabled (limit<=0), fail-open when Redis is down, and allow-under /
block-over within a window with a Retry-After.
"""
import pytest

from app.services import rate_limit


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def incr(self, key):
        self.ops.append(("incr", key))
        return self

    def ttl(self, key):
        self.ops.append(("ttl", key))
        return self

    def execute(self):
        out = []
        for op, key in self.ops:
            if op == "incr":
                self.redis.store[key] = self.redis.store.get(key, 0) + 1
                out.append(self.redis.store[key])
            elif op == "ttl":
                out.append(self.redis.ttls.get(key, -1))
        self.ops = []
        return out


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def pipeline(self):
        return _FakePipeline(self)

    def expire(self, key, window):
        self.ttls[key] = window

    def delete(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis_conn", lambda: r)
    return r


def test_disabled_when_limit_zero(fake_redis):
    res = rate_limit.hit("x", "1.2.3.4", limit=0, window_seconds=60)
    assert res.allowed is True


def test_fail_open_without_redis(monkeypatch):
    monkeypatch.setattr(rate_limit, "_redis_conn", lambda: None)
    for _ in range(100):
        assert rate_limit.hit("x", "1.2.3.4", limit=3, window_seconds=60).allowed is True


def test_allows_under_then_blocks_over(fake_redis):
    ip = "9.9.9.9"
    assert rate_limit.hit("signup", ip, limit=3, window_seconds=3600).allowed is True
    assert rate_limit.hit("signup", ip, limit=3, window_seconds=3600).allowed is True
    assert rate_limit.hit("signup", ip, limit=3, window_seconds=3600).allowed is True
    blocked = rate_limit.hit("signup", ip, limit=3, window_seconds=3600)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 3600


def test_separate_ips_independent(fake_redis):
    assert rate_limit.hit("signup", "a", limit=1, window_seconds=60).allowed is True
    assert rate_limit.hit("signup", "a", limit=1, window_seconds=60).allowed is False
    # Different IP has its own bucket.
    assert rate_limit.hit("signup", "b", limit=1, window_seconds=60).allowed is True


def test_separate_buckets_independent(fake_redis):
    assert rate_limit.hit("signup", "a", limit=1, window_seconds=60).allowed is True
    # Same IP, different bucket - not shared.
    assert rate_limit.hit("reset", "a", limit=1, window_seconds=60).allowed is True
