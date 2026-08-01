"""A URL that could not be signed is not a URL a catalogue may show.

`resolve_signed_url` fails OPEN: when signing raises, it logs and returns the
raw, unsigned path. For a download link that is a reasonable last resort - the
user gets something to try. For an IMAGE it is not, because nothing tries
anything: the browser requests it, CloudFront answers 403, and the reader sees a
broken image icon where the tile has a perfectly good no-image state waiting.

Found in a browser, not in review: 181 of 2,472 linked product images on the
local environment cannot be signed, so three tiles in one product's candidate
row rendered broken. The environment was the cause there, but the behaviour is
the product's - an unsignable image is offered as a choice, chosen by a human,
and then renders as a broken tile.

The default stays fail-open, because ten call sites depend on it and a download
link that might work beats no link at all. Callers that render an IMAGE opt in
to strict, where a signing failure is simply an absent image.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services import storage_router


class _ExplodingBackend:
    """A storage backend whose signer is down."""

    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        raise RuntimeError("signing key missing")


class TestDefaultStaysForgiving:
    def test_a_signing_failure_still_returns_something_to_try(self) -> None:
        # Ten callers rely on this, including downloads and the contact portal.
        # Changing the default under them is a bigger change than this fix.
        with patch.object(storage_router, "get_backend", return_value=_ExplodingBackend()):
            url = storage_router.resolve_signed_url("product/photo.jpg", provider="s3")

        assert url == "product/photo.jpg"


class TestStrictIsForImages:
    def test_a_signing_failure_becomes_no_image(self) -> None:
        with patch.object(storage_router, "get_backend", return_value=_ExplodingBackend()):
            url = storage_router.resolve_signed_url(
                "product/photo.jpg", provider="s3", strict=True
            )

        # None, not the raw path: the tile renders its no-image state instead of
        # a broken image, which is what that state exists for.
        assert url is None

    def test_a_successful_signature_is_unaffected(self) -> None:
        class _Working:
            def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
                return f"https://cdn.example/{key}?Signature=abc"

        with patch.object(storage_router, "get_backend", return_value=_Working()):
            url = storage_router.resolve_signed_url(
                "product/photo.jpg", provider="s3", strict=True
            )

        assert url == "https://cdn.example/product/photo.jpg?Signature=abc"

    def test_an_empty_path_is_no_image_rather_than_an_empty_string(self) -> None:
        # A soft-deleted attachment has an empty file_path in the live data, and
        # an empty string is a URL the browser will happily request.
        assert storage_router.resolve_signed_url("", provider="s3", strict=True) is None
        assert storage_router.resolve_signed_url(None, provider="s3", strict=True) is None

    def test_a_path_with_no_extractable_key_is_no_image(self) -> None:
        with patch.object(storage_router, "extract_key", return_value=""):
            url = storage_router.resolve_signed_url(
                "not-a-key", provider="s3", strict=True
            )

        assert url is None
