#!/usr/bin/env python3
"""Relocate flat-scheme attachment objects to uuid-segregated keys (COPY-ONLY, no delete).

Flat keys `{entity_type}/{filename}` collide across folders (two live rows, same type + name,
different folders → one object → silent clobber). This migration moves each flat object to
`{entity_type}/{attachment_id}/{filename}` - the uuid dir makes every key unique - and repoints
`file_path` at the new key.

**The old object is KEPT, never deleted.** Old public/CDN links still resolve. A later cleanup
phase (after those links are retired) can delete the stale flat objects. This script never
deletes anything.

Run from sorento_crm_backend/:
    python scripts/migrate_attachment_keys_to_uuid.py [--dry-run] [--apply]
                                                      [--limit N] [--provider r2|s3]

Idempotent: a row already on the uuid scheme is a no-op; a re-run whose new object already
exists skips the copy and just ensures file_path is correct.

SAFETY:
  * --dry-run (DEFAULT): zero writes. Reports what WOULD move, plus rows whose SOURCE object is
    missing in the bucket (can't copy) and rows already migrated.
  * --apply (guarded): server-side copy → verify → update file_path (single tx per row). No deletes.

NOTE on bucket: the backend talks to whatever R2/S3 bucket the current .env points at. The
source objects must live there. Local rows whose bytes are only in the prod bucket will report
SOURCE_MISSING when run against a staging bucket - that's expected; run against the bucket that
actually holds the objects.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict

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
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("migrate_attachment_keys_to_uuid")


def _new_key_for(old_key: str, attachment_id: str) -> str | None:
    """Inject the attachment uuid between the prefix and the filename of a FLAT key.

    Returns None for keys that are NOT flat `{prefix}/{filename}` - i.e. already uuid-scoped,
    promotion `{p}/{entity_id}/{name}`, portal `{portal}/{contact}/{uuid}{ext}`. Those are
    skipped (already collision-safe / already migrated).
    """
    segs = [s for s in (old_key or "").split("/") if s]
    if len(segs) != 2:
        return None  # not flat → skip
    prefix, filename = segs
    return f"{prefix}/{attachment_id}/{filename}"


def _migrate_one(att: Attachment, *, apply: bool, counts: dict) -> str:
    provider = normalize_provider(att.storage_provider)
    backend = get_backend(provider)
    old_key = extract_key(att.file_path)
    if not old_key:
        return "NO_KEY"

    new_key = _new_key_for(old_key, str(att.id))
    if new_key is None:
        return "SKIP_NOT_FLAT"          # already scoped/uuid/portal/promotion

    # Idempotency: new object already there (prior run) → just ensure file_path is right.
    if backend.file_exists(new_key):
        want = cdn_base_url(provider, new_key)
        if att.file_path != want:
            if apply:
                att.file_path = want
            return "REPOINTED"
        return "ALREADY_MIGRATED"

    # New object absent → need to copy from old. Source must exist.
    if not backend.file_exists(old_key):
        logger.warning("att=%s SOURCE_MISSING old_key=%s (bucket=%s)", att.id, old_key, getattr(backend, "bucket_name", "?"))
        return "SOURCE_MISSING"

    if not apply:
        return "WOULD_MIGRATE"

    backend.copy_file(old_key, new_key)
    if not backend.file_exists(new_key):
        logger.error("att=%s copy unverified old=%s new=%s", att.id, old_key, new_key)
        return "COPY_UNVERIFIED"
    att.file_path = cdn_base_url(provider, new_key)   # OLD object kept on purpose
    return "MIGRATED"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True, help="(default) report only, no writes")
    ap.add_argument("--apply", action="store_true", help="perform copy + file_path update (guarded; no deletes)")
    ap.add_argument("--limit", type=int, default=None, help="cap rows scanned")
    ap.add_argument("--provider", choices=["r2", "s3"], default=None, help="only this provider")
    args = ap.parse_args()

    apply = bool(args.apply)
    if apply:
        args.dry_run = False
        logger.warning("--apply: copies + file_path updates WILL be written. Old objects are KEPT (never deleted).")
    else:
        logger.info("dry-run: zero writes. Pass --apply to migrate.")

    db: Session = SessionLocal()
    counts: dict[str, int] = defaultdict(int)
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
            # Per-row isolation: one bad row (copy error, commit blip) must not
            # abort the whole run. Roll back its partial state and carry on - the
            # copy-before-flip + idempotent re-run make this safe (a re-run REPOINTs
            # any row whose object copied but whose file_path never committed).
            try:
                status = _migrate_one(att, apply=apply, counts=counts)
                # Commit per row so a mid-run failure leaves a consistent prefix migrated.
                if apply and status in ("MIGRATED", "REPOINTED"):
                    db.commit()
            except Exception as e:
                db.rollback()
                status = "ERROR"
                logger.error("att=%s migration error: %s", att.id, e, exc_info=True)
            counts[status] += 1
    finally:
        db.close()

    logger.info("summary: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
