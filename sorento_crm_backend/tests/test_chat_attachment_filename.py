"""AC-D5: a chat attachment reaches WhatsApp under its OWN filename.

WhatsApp names the delivered document from the LAST path segment of the URL
Respond.io fetches, so the uuid that segregates the storage key must be its own
path segment (``{table}/{id}/{uuid}/{filename}`` - the repo's existing attachment
key convention) instead of a ``{uuid}_{filename}`` basename prefix.

Storage is mocked (mirrors tests/test_attachment_keys.py); no DB, no network.
"""
from __future__ import annotations

import uuid as uuid_module
from urllib.parse import quote, urlparse

import pytest

from app.services import storage_router
from app.services.respond_chat_template_service import (
    respond_attachment_kind,
    upload_chat_attachment,
)

TABLE = "conversation_sla_tracking"
BIZ_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class FakeBackend:
    """Records the key it was asked to store, and mimics both URL branches."""

    def __init__(self):
        self.uploaded: list[tuple[str, str | None]] = []
        self.signed: list[tuple[str, int]] = []

    def upload_file(self, *, file_content, file_path, content_type=None):
        self.uploaded.append((file_path, content_type))
        return file_path

    def get_cdn_base_url(self, key):
        # r2_service.R2Service.get_cdn_base_url - raw concat, no encoding.
        return f"https://cdn.test/{key.lstrip('/')}"

    def get_signed_url(self, key, expires_in=3600):
        # cloudfront_signer.generate_url - percent-encodes the path, appends the policy.
        self.signed.append((key, expires_in))
        return f"https://cf.test/{quote(key.lstrip('/'), safe='/')}?Expires=1&Signature=x"


@pytest.fixture
def backend(monkeypatch):
    be = FakeBackend()
    monkeypatch.setattr(storage_router, "get_backend", lambda provider: be)
    return be


def _use_provider(monkeypatch, provider: str) -> None:
    monkeypatch.setattr(storage_router, "default_provider", lambda: provider)


def _uploaded_key(backend: FakeBackend) -> str:
    assert len(backend.uploaded) == 1
    return backend.uploaded[0][0]


# ------------------------------------------------------------------ key shape

def test_key_basename_is_the_clean_filename_with_a_uuid_segment(backend, monkeypatch):
    _use_provider(monkeypatch, storage_router.PROVIDER_R2)
    upload_chat_attachment(
        business_table=TABLE,
        business_id=BIZ_ID,
        content=b"xx",
        filename="Q3 stock.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    key = _uploaded_key(backend)
    table, biz, seg, basename = key.split("/")
    assert (table, biz) == (TABLE, BIZ_ID)
    # The uuid segregates the key but is NEVER part of the delivered name.
    uuid_module.UUID(seg)
    assert basename == "Q3_stock.xlsx"
    assert seg not in basename


def test_extension_and_stem_survive_sanitization(backend, monkeypatch):
    _use_provider(monkeypatch, storage_router.PROVIDER_R2)
    upload_chat_attachment(
        business_table=TABLE,
        business_id=BIZ_ID,
        content=b"xx",
        filename="Quotation (rev 2)+final.pdf",
        mime="application/pdf",
    )
    assert _uploaded_key(backend).rsplit("/", 1)[-1] == "Quotation_rev_2final.pdf"


def test_blank_filename_falls_back_without_losing_the_uuid_segment(backend, monkeypatch):
    _use_provider(monkeypatch, storage_router.PROVIDER_R2)
    upload_chat_attachment(
        business_table=TABLE,
        business_id=BIZ_ID,
        content=b"xx",
        filename="***",
        mime="application/octet-stream",
    )
    key = _uploaded_key(backend)
    assert len(key.split("/")) == 4
    assert key.rsplit("/", 1)[-1] == "file"


# ------------------------------------------------------------------ URL branches

def test_r2_cdn_url_path_ends_with_the_clean_encoded_filename(backend, monkeypatch):
    _use_provider(monkeypatch, storage_router.PROVIDER_R2)
    out = upload_chat_attachment(
        business_table=TABLE,
        business_id=BIZ_ID,
        content=b"xx",
        filename="Q3 stock.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert urlparse(out["url"]).path.rsplit("/", 1)[-1] == "Q3_stock.xlsx"
    assert out["kind"] == "file"


def test_s3_signed_url_path_ends_with_the_clean_filename_and_lives_7_days(
    backend, monkeypatch
):
    _use_provider(monkeypatch, storage_router.PROVIDER_S3)
    out = upload_chat_attachment(
        business_table=TABLE,
        business_id=BIZ_ID,
        content=b"xx",
        filename="Q3 stock.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    parsed = urlparse(out["url"])
    assert parsed.path.rsplit("/", 1)[-1] == "Q3_stock.xlsx"
    assert parsed.query  # still signed
    assert backend.signed == [(_uploaded_key(backend), 60 * 60 * 24 * 7)]


def test_non_ascii_filename_is_percent_encoded_in_the_url_but_raw_in_the_key(
    backend, monkeypatch
):
    _use_provider(monkeypatch, storage_router.PROVIDER_R2)
    out = upload_chat_attachment(
        business_table=TABLE,
        business_id=BIZ_ID,
        content=b"xx",
        filename="报价单.pdf",
        mime="application/pdf",
    )
    assert _uploaded_key(backend).rsplit("/", 1)[-1] == "报价单.pdf"
    assert out["url"].endswith(quote("报价单.pdf"))
    assert " " not in out["url"]


# ------------------------------------------------------------------ kind mapping (unchanged)

@pytest.mark.parametrize(
    "mime,expected",
    [
        ("image/jpeg", "image"),
        ("image/png", "image"),
        ("video/mp4", "video"),
        ("audio/ogg", "audio"),
        ("application/pdf", "file"),
        ("application/octet-stream", "file"),
        (None, "file"),
        ("", "file"),
    ],
)
def test_respond_attachment_kind_unchanged(mime, expected):
    assert respond_attachment_kind(mime) == expected
