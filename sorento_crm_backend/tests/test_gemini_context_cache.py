"""Explicit Gemini context caching (GEMINI-EXPLICIT-CACHE, plan PLAN-gemini-explicit-cache-28oct.md).

A Gemini call that carries a `prompt_cache_key` and a system prompt puts the system prompt
in a `cachedContents` entry once and points every later call at it, so Google bills that
prefix at the cached rate. Any trouble with the cache answers the call uncached.

No network: the seam is `httpx.request`, the exact call `GeminiProvider._request` makes.
The shared name lives in Redis; these tests use a scratch Redis db when one answers and an
in-memory stand-in otherwise, so the cross-process case runs either way.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import gemini_context_cache
from app.services.llm_provider import GeminiProvider

SYSTEM = ("You are the parser. " * 50).strip()
MESSAGES = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": "stock for SRT123"},
]
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


class _FakeRedis:
    """The four calls the cache makes, in memory."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = value.encode() if isinstance(value, str) else value
        return True

    def delete(self, key):
        self.data.pop(key, None)


class _Resp:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _answer(cached: int = 0) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}, "finishReason": "STOP"}],
        "usageMetadata": {
            "promptTokenCount": 1200,
            "candidatesTokenCount": 5,
            "totalTokenCount": 1205,
            "cachedContentTokenCount": cached,
        },
        "modelVersion": "gemini-3.5-flash-lite",
    }


class _Google:
    """A scripted Gemini: records every request, answers by path."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.created = 0
        self.create_status = 200
        self.generate_failures: list[int] = []  # statuses to answer cached generates with, in order
        self.always_refuse_cached: int | None = None
        self.uncached_failures: list[int] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> _Resp:
        self.calls.append({"method": method, "url": url, **kwargs})
        body = kwargs.get("json") or {}
        if url.endswith("/cachedContents") and method == "POST":
            if self.create_status != 200:
                return _Resp({"error": {"message": "too few tokens"}}, self.create_status)
            self.created += 1
            return _Resp({"name": f"cachedContents/c{self.created}", "expireTime": "2026-10-28T10:00:00Z"})
        if method == "DELETE":
            return _Resp({})
        if ":generateContent" in url:
            if body.get("cachedContent") and (self.generate_failures or self.always_refuse_cached):
                status = self.generate_failures.pop(0) if self.generate_failures else self.always_refuse_cached
                return _Resp({"error": {"message": "CachedContent not found"}}, status)
            if not body.get("cachedContent") and self.uncached_failures:
                return _Resp({"error": {"message": "bad request"}}, self.uncached_failures.pop(0))
            return _Resp(_answer(cached=1100 if body.get("cachedContent") else 0))
        raise AssertionError(f"unexpected call {method} {url}")

    def creates(self) -> list[dict]:
        return [c for c in self.calls if c["url"].endswith("/cachedContents")]

    def generates(self) -> list[dict]:
        return [c for c in self.calls if ":generateContent" in c["url"]]


@pytest.fixture
def google(monkeypatch):
    fake = _Google()
    monkeypatch.setattr("httpx.request", fake)
    return fake


@pytest.fixture(autouse=True)
def shared_store(monkeypatch):
    store = _FakeRedis()
    gemini_context_cache.reset()
    monkeypatch.setattr(gemini_context_cache, "_redis", lambda: store)
    yield store
    gemini_context_cache.reset()


def _chat(provider: GeminiProvider | None = None, **kwargs: Any):
    provider = provider or GeminiProvider("key-1", default_model="gemini-3.5-flash-lite")
    return provider.chat(
        MESSAGES, json_schema=SCHEMA, prompt_cache_key="chatbot_parser:v7", **kwargs
    )


# AC-1
def test_first_call_creates_the_cache_and_points_the_request_at_it(google) -> None:
    result = _chat()

    assert len(google.creates()) == 1
    created = google.creates()[0]["json"]
    assert created["model"] == "models/gemini-3.5-flash-lite"
    assert created["systemInstruction"] == {"parts": [{"text": SYSTEM}]}
    assert created["ttl"].endswith("s")
    sent = google.generates()[0]["json"]
    assert sent["cachedContent"] == "cachedContents/c1"
    # The API refuses systemInstruction / tools beside cachedContent.
    assert "systemInstruction" not in sent
    assert "tools" not in sent
    # The schema is generation config, not cache content: it stays on the request.
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" in sent["generationConfig"]
    assert result.content == '{"ok": true}'


# AC-2 + AC-6
def test_second_call_reuses_the_cache_and_records_cached_tokens(google) -> None:
    _chat()
    second = _chat()

    assert len(google.creates()) == 1
    assert google.generates()[1]["json"]["cachedContent"] == "cachedContents/c1"
    assert second.cached_tokens == 1100
    assert second.prompt_tokens == 1200


# AC-3
def test_another_process_reuses_the_name_found_in_redis(google, shared_store) -> None:
    _chat()
    gemini_context_cache.reset_local()  # a second gunicorn worker: empty memory, same Redis

    _chat()

    assert len(google.creates()) == 1
    assert google.generates()[1]["json"]["cachedContent"] == "cachedContents/c1"


def test_a_new_day_in_the_system_prompt_is_a_new_cache(google) -> None:
    provider = GeminiProvider("key-1", default_model="gemini-3.5-flash-lite")
    provider.chat(MESSAGES, prompt_cache_key="k")
    tomorrow = [{"role": "system", "content": SYSTEM + "CURRENT DATE: tomorrow"}, MESSAGES[1]]
    provider.chat(tomorrow, prompt_cache_key="k")

    assert len(google.creates()) == 2


def test_another_model_or_key_is_another_cache(google) -> None:
    _chat()
    _chat(GeminiProvider("key-1", default_model="gemini-3.5-flash"))
    _chat(GeminiProvider("key-2", default_model="gemini-3.5-flash-lite"))

    assert len(google.creates()) == 3


# AC-4
@pytest.mark.parametrize("status", [400, 403, 404])
def test_an_expired_cache_answers_uncached_then_is_recreated(google, status) -> None:
    _chat()
    google.generate_failures = [status]

    retried = _chat()

    gens = google.generates()
    assert gens[1]["json"]["cachedContent"] == "cachedContents/c1"
    assert "cachedContent" not in gens[2]["json"]
    assert gens[2]["json"]["systemInstruction"] == {"parts": [{"text": SYSTEM}]}
    assert retried.content == '{"ok": true}'

    _chat()
    assert len(google.creates()) == 2
    assert google.generates()[3]["json"]["cachedContent"] == "cachedContents/c2"


def test_a_rate_limit_on_the_cached_call_is_not_swallowed(google) -> None:
    """429 / 5xx are the provider's, not the cache's: `llm_call` waits them out."""
    from app.services.llm_provider import GeminiHTTPError

    _chat()
    google.generate_failures = [429]

    with pytest.raises(GeminiHTTPError) as caught:
        _chat()
    assert caught.value.status_code == 429


# AC-5
def test_a_refused_create_answers_uncached_and_is_not_retried_every_turn(google) -> None:
    google.create_status = 400

    first = _chat()
    _chat()

    assert first.content == '{"ok": true}'
    assert len(google.creates()) == 1
    for sent in google.generates():
        assert "cachedContent" not in sent["json"]
        assert sent["json"]["systemInstruction"] == {"parts": [{"text": SYSTEM}]}


def test_a_redis_outage_still_caches_in_process(google, monkeypatch) -> None:
    class _Down:
        def __getattr__(self, name):
            def _boom(*a, **k):
                raise ConnectionError("redis down")

            return _boom

    monkeypatch.setattr(gemini_context_cache, "_redis", lambda: _Down())
    _chat()
    second = _chat()

    assert len(google.creates()) == 1
    assert second.cached_tokens == 1100


def test_a_create_that_lost_the_race_uses_the_winner_and_drops_its_own(
    google, shared_store, monkeypatch
) -> None:
    def _miss_while_another_worker_creates(key):
        # Our read misses; another worker stores its name before ours lands.
        shared_store.set(gemini_context_cache._redis_key(key), "cachedContents/winner")
        return None

    monkeypatch.setattr(gemini_context_cache, "lookup", _miss_while_another_worker_creates)
    _chat()

    assert google.generates()[0]["json"]["cachedContent"] == "cachedContents/winner"
    assert any(c["method"] == "DELETE" and c["url"].endswith("cachedContents/c1") for c in google.calls)


# AC-7
def test_no_cache_key_sends_the_request_unchanged(google) -> None:
    GeminiProvider("key-1").chat(MESSAGES, json_schema=SCHEMA)

    assert google.creates() == []
    assert google.generates()[0]["json"]["systemInstruction"] == {"parts": [{"text": SYSTEM}]}


def test_no_system_prompt_sends_the_request_unchanged(google) -> None:
    GeminiProvider("key-1").chat([MESSAGES[1]], prompt_cache_key="k")

    assert google.creates() == []
    assert "cachedContent" not in google.generates()[0]["json"]


def test_tools_ride_in_the_cache_not_beside_it(google) -> None:
    tools = [{"type": "function", "function": {"name": "find", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}}]
    GeminiProvider("key-1").chat(MESSAGES, tools=tools, prompt_cache_key="k")

    assert google.creates()[0]["json"]["tools"][0]["functionDeclarations"][0]["name"] == "find"
    sent = google.generates()[0]["json"]
    assert "tools" not in sent
    assert sent["cachedContent"] == "cachedContents/c1"


def test_the_clarifier_asks_for_a_cache_per_prompt_version(monkeypatch) -> None:
    from app.services.chatbot import llm_call
    from app.services.chatbot.lanes import casual

    seen: list[dict] = []

    class _Result:
        content = '{"response": "hi"}'

    def fake_chat(provider, key, model, messages, **kwargs):
        seen.append(kwargs)
        return _Result()

    monkeypatch.setattr(llm_call, "chat", fake_chat)
    for version in (12, None):
        config = casual.ClarifierConfig(
            system_prompt="s", prompt_version=version, provider="gemini", model="m", api_key="k"
        )
        casual.call_clarifier(config, "u")

    assert seen[0]["prompt_cache_key"] == "chatbot_clarifier:v12"
    assert seen[1]["prompt_cache_key"] == "chatbot_clarifier:vfallback"


def test_two_workers_share_one_entry_through_real_redis(google, monkeypatch) -> None:
    """The real client's `SET NX` / `GET` against a live Redis, when one answers."""
    redis = pytest.importorskip("redis")
    from app.config import settings

    client = redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
    try:
        client.ping()
    except Exception:
        pytest.skip("no Redis reachable")
    monkeypatch.setattr(gemini_context_cache, "_KEY_PREFIX", "gemini_cache_test")
    monkeypatch.setattr(gemini_context_cache, "_redis", lambda: client)
    key = gemini_context_cache.cache_key("key-1", "gemini-3.5-flash-lite", {"parts": [{"text": SYSTEM}]}, None)
    client.delete(gemini_context_cache._redis_key(key))
    try:
        _chat()
        gemini_context_cache.reset_local()
        second = _chat()

        assert len(google.creates()) == 1
        assert second.cached_tokens == 1100
        assert 0 < client.ttl(gemini_context_cache._redis_key(key)) <= gemini_context_cache.CACHE_TTL_SECONDS
    finally:
        client.delete(gemini_context_cache._redis_key(key))


# Review round 1 (B1): the cache steps spend from the caller's budget, never add to it.
def test_the_create_is_bounded_and_the_call_keeps_inside_the_callers_timeout(google) -> None:
    _chat(timeout=20.0)

    create = google.creates()[0]
    assert create["timeout"] <= gemini_context_cache.CREATE_TIMEOUT_SECONDS
    assert google.generates()[0]["timeout"] <= 20.0

    _chat(GeminiProvider("key-1", default_model="gemini-3.5-flash"), timeout=2.0)
    assert google.creates()[1]["timeout"] <= 2.0


def test_a_slow_create_is_abandoned_and_the_call_answers_uncached(google, monkeypatch) -> None:
    import httpx

    real = google.__call__

    def _slow_create(method, url, **kwargs):
        if url.endswith("/cachedContents"):
            raise httpx.ReadTimeout("slow")
        return real(method, url, **kwargs)

    monkeypatch.setattr("httpx.request", _slow_create)
    result = _chat(timeout=20.0)

    assert result.content == '{"ok": true}'
    assert "cachedContent" not in google.generates()[0]["json"]


# Review round 1 (S1): an entry Google refuses as soon as it is made is not remade every turn.
def test_an_entry_refused_right_after_create_is_backed_off(google) -> None:
    google.always_refuse_cached = 400

    for _ in range(3):
        assert _chat().content == '{"ok": true}'

    assert len(google.creates()) == 1
    cached_calls = [g for g in google.generates() if g["json"].get("cachedContent")]
    assert len(cached_calls) == 1
    assert any(c["method"] == "DELETE" and c["url"].endswith("cachedContents/c1") for c in google.calls)


# Review round 1 (S2): a 400 the request itself earns does not throw the cache away.
def test_a_400_the_uncached_call_also_gets_is_raised_and_the_cache_kept(google) -> None:
    from app.services.llm_provider import GeminiHTTPError

    _chat()
    google.generate_failures = [400]
    google.uncached_failures = [400]

    with pytest.raises(GeminiHTTPError):
        _chat()

    _chat()
    assert len(google.creates()) == 1
    assert google.generates()[-1]["json"]["cachedContent"] == "cachedContents/c1"


# Review round 1 (S3): a stale name failing does not delete the fresh one another worker stored.
def test_forget_leaves_a_newer_name_from_another_worker(shared_store) -> None:
    key = "k"
    shared_store.set(gemini_context_cache._redis_key(key), "cachedContents/fresh")

    gemini_context_cache.forget(key, "cachedContents/stale")

    assert shared_store.get(gemini_context_cache._redis_key(key)) == b"cachedContents/fresh"

    gemini_context_cache.forget(key, "cachedContents/fresh")
    assert shared_store.get(gemini_context_cache._redis_key(key)) is None


def test_a_create_that_lands_after_another_workers_failure_marker_is_used(shared_store) -> None:
    key = "k"
    shared_store.set(gemini_context_cache._redis_key(key), gemini_context_cache.FAILED)

    assert gemini_context_cache.claim(key, "cachedContents/ours") == "cachedContents/ours"
    assert shared_store.get(gemini_context_cache._redis_key(key)) == b"cachedContents/ours"


def test_the_generate_gets_only_the_time_the_create_left(google, monkeypatch) -> None:
    import app.services.llm_provider as llm_provider

    clock = {"now": 1000.0}
    monkeypatch.setattr(llm_provider.time, "monotonic", lambda: clock["now"])
    real = google.__call__

    def _create_takes_four_seconds(method, url, **kwargs):
        if url.endswith("/cachedContents"):
            clock["now"] += 4.0
        return real(method, url, **kwargs)

    monkeypatch.setattr("httpx.request", _create_takes_four_seconds)
    _chat(timeout=20.0)

    assert google.generates()[0]["timeout"] == pytest.approx(16.0)
