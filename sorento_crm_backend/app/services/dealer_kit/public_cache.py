"""A short-lived cache for the public catalogue payload.

**Why this is a TTL and not a pin on the version id.** It is tempting to treat a
published page as immutable and cache it forever against its `page_version`,
because approval attests to exactly that id. It would be wrong. The live page is
that version PLUS two mutable joins: collections resolve their members at read
time, and the promotion that prices every tile lives on the page, not in the
document (ADR 0008). An offer that ends is supposed to stop reaching readers
without anybody republishing. A pin on the version id would keep quoting it.

So the staleness window is one number, `TTL_SECONDS`, and it bounds BOTH the
server-side entry and the `Cache-Control` we hand the browser. A price change is
visible to a new reader within that window, and a reader already on the page
sees it on their next load.

Process-local on purpose. Several workers each hold their own copy, which is
correct for a read-through cache with a short window and no invalidation
protocol: the worst case is one reader getting an entry up to `TTL_SECONDS` old,
which is exactly the guarantee a single shared cache would give.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Optional

from fastapi.encoders import jsonable_encoder

TTL_SECONDS = 60

# Bounded so a company publishing many pages cannot grow this without limit.
# Entries are large (the seeded A3 brochure serializes to roughly 400KB), so
# this is a memory ceiling of a few tens of megabytes, not an access-pattern
# optimisation.
MAX_ENTRIES = 32

_lock = threading.Lock()
_entries: dict[tuple[str, str], tuple[float, bytes, str]] = {}


def _now() -> float:
    return time.monotonic()


def get(company_id: str, slug: str) -> Optional[tuple[bytes, str]]:
    """The cached body and its ETag, or None when absent or expired."""
    key = (company_id, slug)
    with _lock:
        entry = _entries.get(key)
        if entry is None:
            return None
        expires_at, body, etag = entry
        if expires_at <= _now():
            _entries.pop(key, None)
            return None
        return body, etag


def put(company_id: str, slug: str, payload) -> tuple[bytes, str]:
    """Serialize, store and return the body and ETag for `payload`.

    The ETag is over the body, so two workers that computed the same page agree
    on it and a reader moving between them still gets a 304.
    """
    body = json.dumps(jsonable_encoder(payload), separators=(",", ":")).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    with _lock:
        if len(_entries) >= MAX_ENTRIES:
            # Oldest expiry first. Not an LRU: every entry has the same TTL, so
            # expiry order IS insertion order and the cheapest correct eviction.
            oldest = min(_entries, key=lambda item: _entries[item][0])
            _entries.pop(oldest, None)
        _entries[(company_id, slug)] = (_now() + TTL_SECONDS, body, etag)
    return body, etag


def clear() -> None:
    """Drop everything. For tests, and for a caller that has just changed what
    a published page says and does not want to wait out the window."""
    with _lock:
        _entries.clear()
