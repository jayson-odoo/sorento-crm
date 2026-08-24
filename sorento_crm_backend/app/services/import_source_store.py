"""Retain the original uploaded file for an import job (tracing side-channel).

Business users upload Excel files to imports (delivery orders, GRN, SPO, order
tracking). Historically only the ``filename`` string survived; the bytes were parsed
and discarded. This helper streams the ORIGINAL uploaded bytes to the storage bucket
under a stable per-job key and records the reference on the ``import_jobs`` row, so the
exact file the business sent is retrievable from Import Job Details.

Best-effort by design: a storage failure must NEVER block a business import. On any
error the job simply keeps ``source_file_key`` NULL and the caller proceeds.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.job import ImportJob
from app.services.storage_router import (
    default_provider,
    get_backend,
    sanitize_storage_filename,
)

logger = logging.getLogger(__name__)

# Bucket prefix for retained import source files. Kept indefinitely; cleanup (if ever
# needed) is left to a bucket lifecycle rule on this prefix.
_SOURCE_PREFIX = "import-sources"


def store_import_source_file(
    job: ImportJob,
    file_bytes: Optional[bytes],
    filename: Optional[str],
    content_type: Optional[str] = None,
) -> bool:
    """Upload the original import bytes to the bucket and stamp the ``job`` row.

    Sets ``source_file_key`` / ``source_file_provider`` / ``source_file_size`` /
    ``source_filename`` on ``job`` (in memory - the caller's ``db.commit()`` persists
    them). Returns True on success, False if skipped/failed. Never raises.

    ``job`` must already be flushed so ``job.id`` is populated (JobService.create_job
    flushes). Pass the ORIGINAL uploaded bytes (before any macro-strip) so the retained
    file matches exactly what the business sent.
    """
    if not file_bytes:
        return False
    try:
        provider = default_provider()
        safe_name = sanitize_storage_filename(filename)
        key = f"{_SOURCE_PREFIX}/{job.id}/{safe_name}"
        get_backend(provider).upload_file(
            file_bytes,
            key,
            content_type or "application/octet-stream",
        )
        job.source_file_key = key
        job.source_file_provider = provider
        job.source_file_size = len(file_bytes)
        job.source_filename = filename or safe_name
        return True
    except Exception as exc:  # noqa: BLE001 - tracing must never break an import
        logger.warning(
            "store_import_source_file: failed to retain source file for job %s (%s); "
            "import continues without a stored file",
            getattr(job, "id", "?"),
            exc,
        )
        return False
