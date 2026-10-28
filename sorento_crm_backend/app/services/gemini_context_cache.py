"""Which Gemini `cachedContents` entry holds a system prompt (GEMINI-EXPLICIT-CACHE).

Gemini reported 0 cached tokens on every parser call, so the ~28k-token static prompt was
billed in full each turn. An explicit cache entry (`POST cachedContents`) makes Google bill
that prefix at the cached rate; `GeminiProvider.chat` creates and uses it, this module only
remembers the entry's name.

The identity is a hash of the API key, model, system instruction and tools: everything the
entry holds plus the project it lives in. The parser's system prompt carries
`{{current_date}}`, so the identity rolls over at Malaysia midnight by itself.

The name is kept in this process AND in Redis, so every gunicorn worker shares one entry
instead of each paying to create and store its own. Redis is best-effort: unreachable, a
worker keeps its own name. A refused create is remembered for `FAILURE_BACKOFF_SECONDS` so
a prompt Google will not cache (too few tokens, a model without caching) costs one failed
POST per window, not one per turn.

Never raises: a cache that cannot be read is a cache miss.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# How long Google keeps an entry. Storage is billed per hour it lives, so an hour is enough
# for a prompt that serves several turns an hour and not much more than one quiet hour costs.
CACHE_TTL_SECONDS = 3600
# The name is forgotten this long before Google drops the entry, so a call never points at
# one that expires mid-flight. A call that does anyway is retried uncached by the provider.
EXPIRY_MARGIN_SECONDS = 120
FAILURE_BACKOFF_SECONDS = 900
_FAILED = "-"
_KEY_PREFIX = "gemini_cache"

_lock = threading.Lock()
_local: dict[str, tuple[str, float]] = {}
_client: list[Any] = []


def cache_key(api_key: str, model: str, system_instruction: Any, tools: Any) -> str:
    """What the entry holds, plus the project it lives in (an entry is per API key)."""
    payload = json.dumps(
        {
            "key": hashlib.sha256((api_key or "").encode()).hexdigest(),
            "model": model,
            "system": system_instruction,
            "tools": tools,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _redis_key(key: str) -> str:
    return f"{_KEY_PREFIX}:{key}"


def _redis() -> Any:
    """Its own client: this sits on every parser call, so a hung Redis costs a second."""
    if not _client:
        try:
            import redis

            from app.config import settings

            _client.append(
                redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
            )
        except Exception:  # noqa: BLE001 - best-effort
            _client.append(None)
    return _client[0]


def _local_get(key: str) -> Optional[str]:
    with _lock:
        held = _local.get(key)
        if held is None:
            return None
        if held[1] <= time.monotonic():
            _local.pop(key, None)
            return None
        return held[0]


def _local_set(key: str, value: str, seconds: float) -> None:
    with _lock:
        _local[key] = (value, time.monotonic() + seconds)


def _decode(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else str(raw)


def _lookup_raw(key: str) -> Optional[str]:
    held = _local_get(key)
    if held is not None:
        return held
    try:
        client = _redis()
        shared = _decode(client.get(_redis_key(key))) if client is not None else None
    except Exception:  # noqa: BLE001
        logger.warning("gemini cache: redis read failed", exc_info=True)
        return None
    if shared is not None:
        # The Redis TTL already counts down to the margin; a local copy for a short while
        # saves a round trip per turn without outliving it by much.
        _local_set(key, shared, 60)
    return shared


def lookup(key: str) -> Optional[str]:
    """The entry's name, or None when there is none to use (missing, or recently refused)."""
    held = _lookup_raw(key)
    return None if held in (None, _FAILED) else held


def recently_failed(key: str) -> bool:
    return _lookup_raw(key) == _FAILED


def claim(key: str, name: str) -> str:
    """Store `name` unless another worker stored one first; the name to use either way."""
    seconds = CACHE_TTL_SECONDS - EXPIRY_MARGIN_SECONDS
    winner = name
    try:
        client = _redis()
        if client is not None and not client.set(_redis_key(key), name, ex=seconds, nx=True):
            existing = _decode(client.get(_redis_key(key)))
            if existing and existing != _FAILED:
                winner = existing
            else:
                client.set(_redis_key(key), name, ex=seconds)
    except Exception:  # noqa: BLE001
        logger.warning("gemini cache: redis write failed", exc_info=True)
    _local_set(key, winner, seconds if winner == name else 60)
    return winner


def mark_failed(key: str) -> None:
    _store(key, _FAILED, FAILURE_BACKOFF_SECONDS)


def forget(key: str) -> None:
    """The entry is gone (expired or deleted at Google): the next call creates a new one."""
    with _lock:
        _local.pop(key, None)
    try:
        client = _redis()
        if client is not None:
            client.delete(_redis_key(key))
    except Exception:  # noqa: BLE001
        logger.warning("gemini cache: redis delete failed", exc_info=True)


def _store(key: str, value: str, seconds: int) -> None:
    _local_set(key, value, seconds)
    try:
        client = _redis()
        if client is not None:
            client.set(_redis_key(key), value, ex=seconds)
    except Exception:  # noqa: BLE001
        logger.warning("gemini cache: redis write failed", exc_info=True)


def reset_local() -> None:
    """Forget this process's names (test seam: a second worker)."""
    with _lock:
        _local.clear()


def reset() -> None:
    """Forget the names and the cached client. Test seam."""
    reset_local()
    _client.clear()
