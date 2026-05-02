"""Background tasks for storage operations (delete files after hard delete).

Supports both S3 and Cloudflare R2 during the dual-storage transition. The
RQ task accepts ``(provider, key)`` tuples so each row's provider is honored.
The legacy ``delete_s3_files`` entrypoint is preserved so already-queued jobs
keep draining after deploy.
"""
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _normalize_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if key.startswith("https://") or key.startswith("http://"):
        parsed = urlparse(key)
        key = (parsed.path or "").lstrip("/")
    return key


def delete_storage_files(items: list) -> dict:
    """Delete files from their respective providers.

    Args:
        items: list of (provider, key) tuples, where provider is 's3' or 'r2'.
    """
    if not items:
        return {"deleted": 0, "failed": 0}

    from app.services.storage_router import get_backend, normalize_provider

    backends: dict = {}
    deleted = 0
    failed = 0
    for entry in items:
        try:
            provider, raw_key = entry
        except (TypeError, ValueError):
            failed += 1
            logger.warning("Malformed delete entry skipped: %r", entry)
            continue
        key = _normalize_key(raw_key)
        if not key:
            continue
        p = normalize_provider(provider)
        backend = backends.setdefault(p, get_backend(p))
        try:
            backend.delete_file(key)
            deleted += 1
        except Exception as e:
            failed += 1
            logger.warning("Storage delete failed (provider=%s key=%s): %s", p, raw_key, e)
    return {"deleted": deleted, "failed": failed}


def delete_s3_files(s3_keys: list[str]) -> dict:
    """Backwards-compatible entrypoint: assumes provider='s3' for each key."""
    if not s3_keys:
        return {"deleted": 0, "failed": 0}
    return delete_storage_files([("s3", k) for k in s3_keys])
