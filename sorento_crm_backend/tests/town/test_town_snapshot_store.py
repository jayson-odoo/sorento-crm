"""SORENTO-TOWN Phase 0: `store()` / `load()` over a real Redis (AC-2 groundwork, AC-8 TTL).

Keys: `town:{company}:{day}:full|redacted|version`, gzip JSON, TTL 36 h, version = sha1 of the
full JSON with sorted keys. The suite's conftest clears `town:*` around every test.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import uuid
from datetime import date

import pytest

from tests.town._town_seed import DAY, deep, fake_full

TTL_MAX = 36 * 3600


@pytest.fixture
def redis():
    from app.services.queue_service import redis_conn

    return redis_conn


def _sha1_candidates(full: dict) -> set:
    """`sorted keys` pinned; the separators are the contract's silence, so both common forms pass."""
    return {
        hashlib.sha1(json.dumps(full, sort_keys=True).encode()).hexdigest(),
        hashlib.sha1(json.dumps(full, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def test_store_then_load_round_trips_gzip_json_for_both_variants(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    full = fake_full(DAY, company)
    version = town.store(redis, company, DAY, full)

    got_full = town.load(redis, company, DAY, "full")
    got_red = town.load(redis, company, DAY, "redacted")
    assert got_full is not None and got_red is not None
    full_bytes, full_version = got_full
    red_bytes, red_version = got_red
    assert isinstance(full_bytes, bytes) and full_bytes[:2] == b"\x1f\x8b"  # gzip magic
    assert json.loads(gzip.decompress(full_bytes)) == full
    assert json.loads(gzip.decompress(red_bytes)) == town.redact(full)
    assert full_version == red_version == version


def test_the_three_keys_exist_under_the_contract_names(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    version = town.store(redis, company, DAY, fake_full(DAY, company))
    base = f"town:{company}:{DAY.isoformat()}"
    assert redis.exists(f"{base}:full") and redis.exists(f"{base}:redacted")
    stored = redis.get(f"{base}:version")
    assert stored is not None and stored.decode() == version


def test_version_is_sha1_of_the_sorted_keys_full_json(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    full = fake_full(DAY, company)
    version = town.store(redis, company, DAY, full)
    assert len(version) == 40 and set(version) <= set("0123456789abcdef")
    assert version in _sha1_candidates(full)


def test_version_ignores_key_order_and_changes_with_content(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    full = fake_full(DAY, company)
    same = town.store(redis, company, DAY, full)
    reordered = {k: full[k] for k in reversed(list(full))}
    assert town.store(redis, company, DAY, reordered) == same
    changed = deep(full)
    changed["today"]["invoice_count"] += 1
    assert town.store(redis, company, DAY, changed) != same


def test_ttl_is_set_and_at_most_36_hours_on_every_key(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    town.store(redis, company, DAY, fake_full(DAY, company))
    for suffix in ("full", "redacted", "version"):
        ttl = redis.ttl(f"town:{company}:{DAY.isoformat()}:{suffix}")
        assert 0 < ttl <= TTL_MAX, (suffix, ttl)
        assert ttl > TTL_MAX - 600  # set fresh, not a stray short expiry


def test_load_returns_none_when_nothing_is_stored(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    assert town.load(redis, company, DAY, "full") is None
    assert town.load(redis, company, DAY, "redacted") is None
    town.store(redis, company, DAY, fake_full(DAY, company))
    assert town.load(redis, company, date(2026, 11, 4), "full") is None  # another day
    assert town.load(redis, str(uuid.uuid4()), DAY, "full") is None  # another company


def test_a_second_store_replaces_the_first(redis):
    from app.services.town import snapshot as town

    company = str(uuid.uuid4())
    first = fake_full(DAY, company)
    town.store(redis, company, DAY, first)
    second = deep(first)
    second["today"]["invoice_count"] = 999
    version = town.store(redis, company, DAY, second)
    data, loaded_version = town.load(redis, company, DAY, "full")
    assert json.loads(gzip.decompress(data))["today"]["invoice_count"] == 999
    assert loaded_version == version
