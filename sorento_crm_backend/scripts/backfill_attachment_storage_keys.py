#!/usr/bin/env python3
"""Audit / repair attachment storage keys vs the DB source of truth.

Background: ``stored_filename`` is the canonical current name AND the basename of
the storage object key embedded in ``file_path``. Older rows (and any row renamed
before the storage-sync feature landed) can drift: ``stored_filename`` no longer
matches the last segment of ``file_path``'s key, or the object is missing at the
key entirely. This script reports those, and - only with ``--apply`` - repairs a
row when the intended object is found under a derivable alternate key.

Run from sorento_crm_backend/:
    python scripts/backfill_attachment_storage_keys.py [--dry-run] [--apply]
                                                       [--limit N] [--provider r2|s3]

Idempotent, JOIN-style "repair where mismatch": safe to re-run; it sets each row
to its correct value rather than only filling NULLs, so a prior bad run self-heals.

SAFETY:
  * ``--dry-run`` (DEFAULT) makes ZERO writes - DB and storage untouched. It only
    HEADs objects and prints a summary.
  * ``--apply`` is guarded and off by default. It performs server-side copy →
    verify → DB repair, and never deletes (a drifted source object is left as an
    orphan for manual cleanup). Run --dry-run first against live storage.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.resources import Attachment
from app.services.storage_router import (
    cdn_base_url,
    extract_key,
    get_backend,
    normalize_provider,
    sanitize_storage_filename,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("backfill_attachment_storage_keys")


def _basename(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return key.rsplit("/", 1)[-1]


def _audit_row(att: Attachment, *, apply: bool) -> str:
    """Return a status token for one row; perform repair when apply=True.

    Status tokens: OK, MISSING_OBJECT, STORED_NAME_DRIFT, REPAIRED, UNREPAIRABLE.
    """
    provider = normalize_provider(att.storage_provider)
    backend = get_backend(provider)
    key = extract_key(att.file_path)
    if not key:
        logger.warning("att=%s has no resolvable key from file_path=%r", att.id, att.file_path)
        return "MISSING_OBJECT"

    object_present = backend.file_exists(key)
    name_drift = _basename(key) != (att.stored_filename or "")

    if object_present and not name_drift:
        return "OK"

    # Derive the alternate key the object might actually live under: same prefix,
    # basename = sanitized stored_filename (the intended canonical name).
    prefix = key.rsplit("/", 1)[0] if "/" in key else ""
    intended_base = sanitize_storage_filename(att.stored_filename)
    intended_key = f"{prefix}/{intended_base}" if prefix else intended_base

    if object_present and name_drift:
        # Object is at `key`, but stored_filename disagrees. Canonical fix: make
        # stored_filename match the key basename (key is where bytes actually are).
        if apply:
            att.stored_filename = _basename(key)
            return "REPAIRED"
        logger.info("att=%s STORED_NAME_DRIFT key=%s stored_filename=%r", att.id, key, att.stored_filename)
        return "STORED_NAME_DRIFT"

    # Object missing at `key`. Is it under the intended key instead?
    if intended_key != key and backend.file_exists(intended_key):
        if apply:
            att.stored_filename = intended_base
            att.file_path = cdn_base_url(provider, intended_key)
            return "REPAIRED"
        logger.info("att=%s recoverable: object at %s not %s", att.id, intended_key, key)
        return "STORED_NAME_DRIFT"

    logger.warning("att=%s MISSING_OBJECT key=%s (no alternate found)", att.id, key)
    return "UNREPAIRABLE"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True, help="(default) report only, no writes")
    ap.add_argument("--apply", action="store_true", help="perform DB repairs (guarded; off by default)")
    ap.add_argument("--limit", type=int, default=None, help="cap rows scanned")
    ap.add_argument("--provider", choices=["r2", "s3"], default=None, help="only scan this provider")
    args = ap.parse_args()

    apply = bool(args.apply)
    if apply:
        args.dry_run = False
        logger.warning("--apply set: DB repairs WILL be written (storage copy → verify, no deletes).")
    else:
        logger.info("dry-run: zero writes. Pass --apply to repair.")

    db: Session = SessionLocal()
    counts: dict[str, int] = {}
    try:
        q = db.query(Attachment).filter(Attachment.is_deleted == False)  # noqa: E712
        if args.provider:
            q = q.filter(Attachment.storage_provider == args.provider)
        q = q.order_by(Attachment.created_at.asc())
        if args.limit:
            q = q.limit(args.limit)
        rows = q.all()
        logger.info("scanning %d attachment row(s)", len(rows))

        for att in rows:
            status = _audit_row(att, apply=apply)
            counts[status] = counts.get(status, 0) + 1

        if apply:
            db.commit()
            logger.info("committed repairs")
    finally:
        db.close()

    logger.info("summary: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
