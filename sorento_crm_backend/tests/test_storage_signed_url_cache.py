"""Signed URLs are memoised, and the memo must not outlive what it caches.

Signing is asked for in BULK. One published catalogue signs a photo for every
product on it - 439 on the seeded A3 brochure - and that was 3.0 of the 3.2
seconds the request took, more than all three of its database queries together.

The risk a cache like this carries is handing somebody a URL with seconds left
on it, so the TTL is a FRACTION of the URL's own lifetime and that is the part
worth pinning.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import storage_router


@pytest.fixture(autouse=True)
def _no_carry_over():
    storage_router.clear_signed_url_cache()
    yield
    storage_router.clear_signed_url_cache()


class _CountingBackend:
    def __init__(self, answer="https://cdn.example/signed?sig=1"):
        self.calls = 0
        self.answer = answer

    def get_signed_url(self, key, expires_in=3600):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return f"{self.answer}&key={key}"


def test_the_same_key_is_signed_once():
    backend = _CountingBackend()
    with patch.object(storage_router, "get_backend", return_value=backend):
        first = storage_router.resolve_signed_url("product_photos/a.jpg", provider="s3")
        second = storage_router.resolve_signed_url("product_photos/a.jpg", provider="s3")

    assert first == second
    assert backend.calls == 1


def test_different_keys_are_signed_separately():
    """The obvious way to get this wrong is a cache that answers everything."""
    backend = _CountingBackend()
    with patch.object(storage_router, "get_backend", return_value=backend):
        one = storage_router.resolve_signed_url("product_photos/a.jpg", provider="s3")
        two = storage_router.resolve_signed_url("product_photos/b.jpg", provider="s3")

    assert one != two
    assert backend.calls == 2


def test_a_key_asked_for_at_two_lifetimes_is_signed_at_each():
    """A ten-minute URL must never be served from an hour-long entry."""
    backend = _CountingBackend()
    with patch.object(storage_router, "get_backend", return_value=backend):
        storage_router.resolve_signed_url("a.jpg", provider="s3", expires_in=3600)
        storage_router.resolve_signed_url("a.jpg", provider="s3", expires_in=600)

    assert backend.calls == 2


def test_the_same_key_on_two_providers_does_not_collide():
    backend = _CountingBackend()
    with patch.object(storage_router, "get_backend", return_value=backend):
        storage_router.resolve_signed_url("a.jpg", provider="s3")
        storage_router.resolve_signed_url("a.jpg", provider="r2")

    assert backend.calls == 2


def test_a_cached_url_always_has_most_of_its_life_left():
    """The whole reason the TTL is a fraction and not the lifetime.

    Read at the last instant the entry is valid, the URL still has five sixths
    of its own hour ahead of it - so a reader cannot be handed one that expires
    while they scroll to the image.
    """
    lifetime = 3600
    ttl = max(1, lifetime // storage_router._SIGNED_TTL_DIVISOR)

    assert ttl < lifetime / 2, "a cached URL could be served older than half its life"
    assert lifetime - ttl >= 0.75 * lifetime


def test_a_key_that_cannot_be_signed_is_not_retried_per_call():
    """181 of 2,472 product images were unsignable on one environment, and the
    catalogue asks about every one of them on every read."""
    backend = _CountingBackend(answer=RuntimeError("no private key"))
    with patch.object(storage_router, "get_backend", return_value=backend):
        first = storage_router.resolve_signed_url("gone.jpg", provider="s3", strict=True)
        second = storage_router.resolve_signed_url("gone.jpg", provider="s3", strict=True)

    # Absent, not broken: the surfaces that render an image have a no-image
    # state and an unsigned URL would reach the browser and come back 403.
    assert first is None and second is None
    assert backend.calls == 1


def test_a_failure_still_fails_open_for_callers_that_asked_it_to():
    """`strict` decides what an unsignable file is worth, and caching the
    failure must not quietly change that answer for a download link."""
    backend = _CountingBackend(answer=RuntimeError("no private key"))
    with patch.object(storage_router, "get_backend", return_value=backend):
        storage_router.resolve_signed_url("gone.jpg", provider="s3", strict=True)
        lenient = storage_router.resolve_signed_url("gone.jpg", provider="s3", strict=False)

    assert lenient == "gone.jpg"
    assert backend.calls == 1


def test_clearing_the_cache_makes_the_next_read_sign_again():
    backend = _CountingBackend()
    with patch.object(storage_router, "get_backend", return_value=backend):
        storage_router.resolve_signed_url("a.jpg", provider="s3")
        storage_router.clear_signed_url_cache()
        storage_router.resolve_signed_url("a.jpg", provider="s3")

    assert backend.calls == 2
