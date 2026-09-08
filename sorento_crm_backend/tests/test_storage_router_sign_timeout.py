"""D9 (owner console pass, 8 Sep 2026): signing is best effort and bounded per file."""
from __future__ import annotations

import logging
import time

from app.services import storage_router


class _SlowBackend:
    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        time.sleep(storage_router.SIGN_TIMEOUT_SECONDS + 1.5)
        return f"https://late.invalid/{key}"


class _BrokenBackend:
    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        raise RuntimeError("the bucket is unreachable")


def test_a_signer_that_hangs_costs_one_link_not_the_call(monkeypatch, caplog):
    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _SlowBackend())
    monkeypatch.setattr(storage_router, "SIGN_TIMEOUT_SECONDS", 0.3)
    started = time.monotonic()
    with caplog.at_level(logging.WARNING):
        url = storage_router.resolve_signed_url(
            "https://cdn-sorento.com/product_photos/zzt-slow-%d.jpg" % int(started), provider="s3", strict=True
        )
    assert url is None
    assert time.monotonic() - started < 2.0, "the call must not wait for the hung signer"
    assert any("Signed URL generation failed" in r.getMessage() for r in caplog.records)


def test_a_signer_that_raises_still_returns_the_raw_path_when_not_strict(monkeypatch):
    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _BrokenBackend())
    raw = "https://cdn-sorento.com/product_photos/zzt-broken-%d.jpg" % int(time.time())
    assert storage_router.resolve_signed_url(raw, provider="s3", strict=False) == raw
    assert storage_router.resolve_signed_url(raw, provider="s3", strict=True) is None
