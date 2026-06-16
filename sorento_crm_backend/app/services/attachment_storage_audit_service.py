"""Attachment storage accessibility audit.

Scheduled handler (`attachment_storage_audit`). For each storage provider that
backs at least one live attachment, list the bucket ONCE (cheap: a handful of
Class A list ops, zero egress), build the full key set, then flag every
non-deleted attachment as ``accessible`` / ``missing`` by exact key membership.

Bytes lost from the bucket (e.g. rows whose ``storage_provider`` was flipped to
r2 without the object ever being copied) surface as ``missing`` so the Files
page filter can list them for trashing. Deleted (``is_deleted``) rows are
skipped — no point auditing trash.
"""
import logging
from datetime import datetime
from typing import Dict, Set

from sqlalchemy.orm import Session

from app.models.resources import Attachment
from app.services.storage_router import (
    extract_key,
    normalize_provider,
    get_backend,
)

logger = logging.getLogger(__name__)

STATUS_ACCESSIBLE = "accessible"
STATUS_MISSING = "missing"

_UPDATE_BATCH = 500


def _list_bucket_keys(provider: str) -> Set[str]:
    """Return the full decoded key set for a provider's bucket via paginated list."""
    backend = get_backend(provider)
    # R2Service exposes `.client`, S3Service exposes `.s3_client`; both `.bucket_name`.
    client = getattr(backend, "client", None) or getattr(backend, "s3_client", None)
    bucket = getattr(backend, "bucket_name", None)
    if client is None or not bucket:
        raise RuntimeError(f"provider {provider!r} backend exposes no client/bucket")
    keys: Set[str] = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []) or []:
            keys.add(obj["Key"])
    logger.info("storage audit: provider=%s bucket=%s listed %d objects", provider, bucket, len(keys))
    return keys


def run_attachment_storage_audit(db: Session, task=None) -> Dict:
    """Scheduled-task handler. Flags live attachments accessible/missing per bucket.

    Returns a summary dict: {scanned, accessible, missing, by_provider, providers_failed}.
    """
    # Which providers actually back live rows? (avoid listing an unused bucket)
    providers = [
        normalize_provider(p)
        for (p,) in db.query(Attachment.storage_provider)
        .filter(Attachment.is_deleted.is_(False))
        .distinct()
        .all()
    ]
    providers = sorted(set(providers))

    key_sets: Dict[str, Set[str]] = {}
    providers_failed: Dict[str, str] = {}
    for provider in providers:
        try:
            key_sets[provider] = _list_bucket_keys(provider)
        except Exception as e:  # bucket unreachable -> leave its rows untouched this run
            providers_failed[provider] = str(e)
            logger.error("storage audit: failed to list provider %s: %s", provider, e)

    now = datetime.utcnow()
    scanned = accessible = missing = 0
    by_provider: Dict[str, Dict[str, int]] = {}

    # Fetch lightweight rows (no ORM identity map, no server-side cursor — a
    # mid-stream commit would invalidate a yield_per named cursor). Compute the
    # verdict in memory, then bulk-UPDATE in batches keyed by status.
    rows = (
        db.query(Attachment.id, Attachment.storage_provider, Attachment.file_path)
        .filter(Attachment.is_deleted.is_(False))
        .all()
    )
    # status -> list of attachment ids
    buckets: Dict[str, list] = {STATUS_ACCESSIBLE: [], STATUS_MISSING: []}
    for att_id, provider_raw, file_path in rows:
        provider = normalize_provider(provider_raw)
        keys = key_sets.get(provider)
        if keys is None:
            continue  # provider list failed this run; don't overwrite prior status
        key = extract_key(file_path)
        ok = bool(key) and key in keys
        status = STATUS_ACCESSIBLE if ok else STATUS_MISSING
        buckets[status].append(att_id)
        scanned += 1
        slot = by_provider.setdefault(provider, {"accessible": 0, "missing": 0})
        if ok:
            accessible += 1
            slot["accessible"] += 1
        else:
            missing += 1
            slot["missing"] += 1

    for status, ids in buckets.items():
        for i in range(0, len(ids), _UPDATE_BATCH):
            chunk = ids[i : i + _UPDATE_BATCH]
            db.query(Attachment).filter(Attachment.id.in_(chunk)).update(
                {Attachment.storage_status: status, Attachment.storage_checked_at: now},
                synchronize_session=False,
            )
            db.commit()

    summary = {
        "scanned": scanned,
        "accessible": accessible,
        "missing": missing,
        "by_provider": by_provider,
        "providers_failed": providers_failed,
    }
    logger.info("storage audit done: %s", summary)
    return summary
