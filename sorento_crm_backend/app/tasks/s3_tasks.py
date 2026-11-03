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


#: A delete that fails is tried this many times before it is logged as failed and left as an
#: orphan. A bucket's transient 5xx is the common case; the job never raises, so one stubborn key
#: never strands the rest of the batch.
_DELETE_ATTEMPTS = 3
_RETRY_SLEEP_SECONDS = 1.0
_RENDITION_SUFFIXES = (".thumb.jpg", ".medium.jpg")


def _with_renditions(key: str) -> list[str]:
    """An image original's key plus the renditions stored beside it (IMAGE-UNIFY). Deleting a
    rendition that never existed is a no-op, so every original gets the same treatment."""
    if key.endswith(_RENDITION_SUFFIXES):
        return [key]
    return [key] + [f"{key}{suffix}" for suffix in _RENDITION_SUFFIXES]


def delete_storage_files(items: list) -> dict:
    """Delete files from their respective providers, each original with its renditions.

    Args:
        items: list of (provider, key) tuples, where provider is 's3' or 'r2'.
    """
    import time

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
        for k in _with_renditions(key):
            for attempt in range(1, _DELETE_ATTEMPTS + 1):
                try:
                    backend.delete_file(k)
                    deleted += 1
                    break
                except Exception as e:  # noqa: BLE001 - retried, then logged; never raises
                    if attempt == _DELETE_ATTEMPTS:
                        failed += 1
                        logger.warning(
                            "Storage delete failed after %d attempts (provider=%s key=%s), orphan left: %s",
                            attempt, p, k, e,
                        )
                    else:
                        time.sleep(_RETRY_SLEEP_SECONDS * attempt)
    return {"deleted": deleted, "failed": failed}


def enqueue_replaced_original_cleanup(provider, old_file_path, new_key: str) -> None:
    """After a Replace commits: delete the OLD original and its renditions in the worker.

    Crew ruling (a) on #2133: a Replace writes new bytes under a new key, and the old objects would
    otherwise stay publicly reachable on R2. The delete runs on the existing
    ``delete_storage_files`` job, never in the request, and a failure to queue it is logged and
    never fails the Replace. Replacing with the same bytes lands on the same key: nothing to do.
    """
    old_key = _normalize_key(old_file_path or "")
    if not old_key or old_key == _normalize_key(new_key or ""):
        return
    try:
        from app.services.queue_service import enqueue_job

        enqueue_job(delete_storage_files, [(provider or "s3", old_key)], queue_name="imports", job_timeout=300)
    except Exception as e:  # noqa: BLE001 - the Replace already succeeded
        logger.warning("Replaced file left in storage, delete not queued (key=%s): %s", old_key, e)


def delete_s3_files(s3_keys: list[str]) -> dict:
    """Backwards-compatible entrypoint: assumes provider='s3' for each key."""
    if not s3_keys:
        return {"deleted": 0, "failed": 0}
    return delete_storage_files([("s3", k) for k in s3_keys])
