"""The storage backend is built once per process, not once per call.

``get_backend`` used to construct a brand-new service on every call, and every
read path (presign, preview, download) calls it per request. Construction is
pure setup, none of it per-request:

  * ``boto3.client(...)`` — ~350ms on the first build in a process, ~3ms after.
  * ``S3Service`` also builds a ``CloudFrontSigner``, which reads and parses the
    RSA private key — ~225ms EVERY build.

So a presign was ~99% setup and an n8n loop over N attachments paid it N times.
Measured on the real endpoint: first request 2.39s -> 0.068s, steady-state
~44ms -> ~10ms.
"""
from __future__ import annotations

import app.services.storage_router as sr


def _reset_cache():
    sr._backends.clear()


def test_the_same_provider_returns_one_shared_instance(monkeypatch):
    _reset_cache()
    builds = []

    class FakeBackend:
        def __init__(self, tag):
            self.tag = tag

    monkeypatch.setattr(
        sr, "_build_backend", lambda p: builds.append(p) or FakeBackend(p)
    )

    first = sr.get_backend("r2")
    for _ in range(25):
        assert sr.get_backend("r2") is first, "a rebuilt backend re-pays full setup"
    assert builds == ["r2"], f"expected exactly one build, got {builds}"
    _reset_cache()


def test_each_provider_is_cached_separately(monkeypatch):
    """Dual-storage: an S3-era row and an R2 row must not share a client."""
    _reset_cache()

    class FakeBackend:
        def __init__(self, tag):
            self.tag = tag

    monkeypatch.setattr(sr, "_build_backend", lambda p: FakeBackend(p))

    s3, r2 = sr.get_backend("s3"), sr.get_backend("r2")
    assert s3 is not r2
    assert s3.tag == "s3" and r2.tag == "r2"
    assert sr.get_backend("s3") is s3 and sr.get_backend("r2") is r2
    _reset_cache()


def test_an_unknown_provider_normalizes_rather_than_building_a_new_entry(monkeypatch):
    """Junk provider values fall back to S3 (normalize_provider) and must reuse
    that one instance instead of caching a bogus key per bad value."""
    _reset_cache()

    class FakeBackend:
        def __init__(self, tag):
            self.tag = tag

    monkeypatch.setattr(sr, "_build_backend", lambda p: FakeBackend(p))

    a = sr.get_backend("s3")
    assert sr.get_backend("nonsense") is a
    assert sr.get_backend(None) is a
    assert set(sr._backends) == {"s3"}
    _reset_cache()


def test_warm_backends_never_raises(monkeypatch):
    """A misconfigured provider must not stop the app booting - it surfaces on the
    first real call exactly as it did before."""
    _reset_cache()

    def boom(_p):
        raise ValueError("storage configuration incomplete")

    monkeypatch.setattr(sr, "_build_backend", boom)
    sr.warm_backends()  # must not raise
    _reset_cache()
