"""Provider-aware storage dispatch for the S3 -> Cloudflare R2 transition.

During the dual-storage period each attachment row carries a ``storage_provider``
('s3' or 'r2') indicating where its bytes live. Read paths (preview, download,
external presigned URL, webhooks) call into this module instead of either
service directly so the right backend is hit per record. New uploads are
routed to ``STORAGE_DEFAULT_PROVIDER`` (defaults to 's3' until R2 is ready;
flip to 'r2' to migrate new traffic over).
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Protocol
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


PROVIDER_S3 = "s3"
PROVIDER_R2 = "r2"
_VALID_PROVIDERS = {PROVIDER_S3, PROVIDER_R2}


class StorageBackend(Protocol):
    """Common surface implemented by S3Service and R2Service."""

    def upload_file(
        self,
        file_content: bytes,
        file_path: str,
        content_type: Optional[str] = ...,
        signed_url_expires_in: int = ...,
    ) -> tuple[str, str]: ...

    def get_signed_url(self, key: str, expires_in: int = ...) -> str: ...

    def download_file(self, key: str) -> bytes: ...

    def delete_file(self, key: str) -> bool: ...

    def file_exists(self, key: str) -> bool: ...

    def copy_file(self, old_key: str, new_key: str) -> None: ...


def sanitize_storage_filename(name: Optional[str]) -> str:
    """Single source of truth for turning a display name into a storage-safe basename.

    Mirrors the upload path exactly so rename and upload can never drift. Keeps
    alphanumerics, space, dash, underscore, dot; collapses everything else away.
    """
    base = "".join(
        c for c in (name or "") if c.isalnum() or c in (" ", "-", "_", ".")
    ).strip()
    return base or "file"


def normalize_provider(value: Optional[str]) -> str:
    """Coerce stored provider values to one of the canonical names; default to S3."""
    if not value:
        return PROVIDER_S3
    v = str(value).strip().lower()
    return v if v in _VALID_PROVIDERS else PROVIDER_S3


def default_provider() -> str:
    """Provider used when a caller has no row context (only a raw file_path)."""
    return normalize_provider(os.getenv("STORAGE_DEFAULT_PROVIDER", PROVIDER_S3))


def get_backend(provider: Optional[str]) -> StorageBackend:
    """Return the storage service for the given provider."""
    p = normalize_provider(provider)
    if p == PROVIDER_R2:
        from app.services.r2_service import R2Service

        return R2Service()
    from app.services.s3_service import S3Service

    return S3Service()


def cdn_base_url(provider: str, key: str) -> str:
    """Return the stable, non-signed CDN URL stored on the DB row."""
    p = normalize_provider(provider)
    backend = get_backend(p)
    if p == PROVIDER_R2:
        return backend.get_cdn_base_url(key)  # type: ignore[attr-defined]
    return backend.get_cloudfront_base_url(key)  # type: ignore[attr-defined]


def detect_provider_from_url(file_path: Optional[str]) -> Optional[str]:
    """Return 's3' or 'r2' if the URL host matches a known CDN domain, else None.

    Used as a fallback when only a file_path string is available (e.g. the
    external /presigned_url endpoint or the avatar resolver, where the row
    isn't always loaded).
    """
    if not file_path:
        return None
    raw = str(file_path).strip()
    if not (raw.startswith("https://") or raw.startswith("http://")):
        return None
    host = (urlparse(raw).hostname or "").lower()
    if not host:
        return None

    cf_host = (os.getenv("CLOUDFRONT_DOMAIN") or "").strip().lower().rstrip("/")
    r2_host = (os.getenv("R2_CDN_DOMAIN") or "").strip().lower().rstrip("/")
    if r2_host and host == r2_host:
        return PROVIDER_R2
    if cf_host and host == cf_host:
        return PROVIDER_S3
    return None


def extract_key(file_path: Optional[str]) -> Optional[str]:
    """Strip scheme/host/query from a stored file_path to recover the storage key."""
    if not file_path:
        return None
    raw = str(file_path).strip()
    if not raw:
        return None
    if raw.startswith("https://") or raw.startswith("http://"):
        parsed = urlparse(raw)
        return unquote((parsed.path or "").lstrip("/")) or None
    return unquote(raw).lstrip("/") or None


def resolve_signed_url(
    file_path: Optional[str],
    *,
    provider: Optional[str] = None,
    expires_in: int = 3600,
    strict: bool = False,
) -> Optional[str]:
    """Return a fresh signed URL for the stored file_path.

    Dispatch order:
      1. If ``provider`` is given (caller has the row), use it directly.
      2. Otherwise, sniff provider from the URL hostname.
      3. Otherwise, fall back to ``STORAGE_DEFAULT_PROVIDER``.

    Already-signed URLs (CloudFront Policy/Key-Pair-Id query params or R2
    AWS4-HMAC-SHA256 signatures) are passed through unchanged when ``provider``
    cannot be determined and the URL clearly carries a live signature.

    ``strict`` decides what an UNSIGNABLE file is worth. By default this
    function fails open: signing raises, it logs, and it hands back the raw
    path. For a download link that is a fair last resort, because the user gets
    something to try and ten call sites depend on it.

    For an IMAGE it is the wrong answer. Nothing tries anything: the browser
    requests the unsigned URL, the CDN answers 403, and the reader gets a broken
    image where the surface already has a designed no-image state. So callers
    that render an image pass ``strict=True`` and treat a signing failure as an
    absent image. Not hypothetical: 181 of 2,472 linked product images could not
    be signed on one environment, and they rendered as broken tiles rather than
    as the empty state.
    """
    if not file_path:
        return None if strict else file_path

    raw = str(file_path).strip()
    if not raw:
        return None if strict else file_path

    chosen = (
        normalize_provider(provider)
        if provider is not None
        else (detect_provider_from_url(raw) or default_provider())
    )

    # If caller explicitly supplied a provider we always re-sign so expired
    # query strings don't leak through. Otherwise we treat an already-signed
    # URL as good enough to return as-is when provider is ambiguous.
    if provider is None and _looks_signed(raw) and detect_provider_from_url(raw) is None:
        return raw

    key = extract_key(raw)
    if not key:
        return None if strict else raw
    try:
        return get_backend(chosen).get_signed_url(key, expires_in=expires_in)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Signed URL generation failed for provider=%s key=%s: %s",
            chosen,
            (key or "")[:80],
            e,
        )
        return None if strict else raw


def copy_object_verified(provider: str, old_key: str, new_key: str) -> None:
    """Server-side copy old_key -> new_key, then verify new exists. No byte download.

    Raises AppException(409) if an object already lives at new_key (never clobber),
    AppException(500) if the copy can't be verified. Does NOT delete the old object —
    caller deletes after its DB commit so the DB never points at a missing object.
    """
    from app.services.error_handler import AppException

    old = (old_key or "").lstrip("/")
    new = (new_key or "").lstrip("/")
    if not old or not new:
        raise AppException(
            status_code=500,
            message="Storage rename requires both source and target keys.",
            code="STORAGE_RENAME_BAD_KEY",
        )
    if old == new:
        return
    backend = get_backend(provider)
    if backend.file_exists(new):
        raise AppException(
            status_code=409,
            message="A file already exists at the target name.",
            code="ATTACHMENT_FILENAME_COLLISION",
        )
    backend.copy_file(old, new)
    if not backend.file_exists(new):
        raise AppException(
            status_code=500,
            message="Storage copy could not be verified.",
            code="STORAGE_COPY_UNVERIFIED",
        )


def delete_object_best_effort(provider: str, key: str) -> None:
    """Delete an object, swallowing failure (leaves an orphan, never breaks the request)."""
    k = (key or "").lstrip("/")
    if not k:
        return
    try:
        get_backend(provider).delete_file(k)
    except Exception as e:  # noqa: BLE001
        logger.warning("delete_object_best_effort: delete of %s failed (orphan left): %s", k, e)


def _looks_signed(url: str) -> bool:
    """Heuristic: CloudFront uses Policy/Key-Pair-Id, R2/S3 v4 uses X-Amz-Signature."""
    return (
        ("Policy=" in url and "Key-Pair-Id=" in url)
        or "X-Amz-Signature=" in url
    )
