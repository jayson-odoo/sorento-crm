#!/usr/bin/env python3
"""Copy attachment + avatar bytes from AWS S3 to Cloudflare R2.

Run from sorento_crm_backend/:
    python scripts/migrate_attachments_to_r2.py [--dry-run] [--batch-size N] [--limit N]
                                                [--target attachments|avatars|both]
                                                [--entity-type promotion]

For each row whose ``storage_provider`` (or ``avatar_storage_provider``) is
``s3``, the script:
    1. downloads the bytes from S3 using the existing S3Service
    2. uploads the same key to R2 via R2Service
    3. verifies via HEAD on R2
    4. updates ``file_path`` to the R2 CDN base URL and flips
       ``storage_provider`` to ``r2`` in a single transaction

The script does NOT delete the original S3 objects; that is a separate
phase-out step the operator runs once R2 has been validated.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Iterable, Optional
from urllib.parse import urlparse

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.resources import Attachment
from app.models.user import User
from app.services.r2_service import R2Service
from app.services.s3_service import S3Service
from app.services.storage_router import PROVIDER_R2, PROVIDER_S3

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("migrate_attachments_to_r2")


def _extract_key(file_path: Optional[str]) -> Optional[str]:
    if not file_path:
        return None
    raw = str(file_path).strip()
    if not raw:
        return None
    if raw.startswith("https://") or raw.startswith("http://"):
        parsed = urlparse(raw)
        return (parsed.path or "").lstrip("/") or None
    return raw.lstrip("/") or None


def _migrate_one(
    *,
    s3: S3Service,
    r2: R2Service,
    file_path: str,
    content_type: Optional[str],
    dry_run: bool,
) -> tuple[bool, Optional[str]]:
    """Copy one object from S3 to R2. Returns (ok, new_file_path)."""
    key = _extract_key(file_path)
    if not key:
        return False, None

    # Skip if already on R2 (idempotency: the script may be re-run safely).
    if r2.file_exists(key):
        new_url = r2.get_cdn_base_url(key)
        logger.debug("Already present on R2, skipping copy: %s", key)
        return True, new_url

    if dry_run:
        logger.info("[dry-run] would copy %s", key)
        return True, r2.get_cdn_base_url(key)

    try:
        body = s3.download_file(key)
    except Exception as e:  # noqa: BLE001
        logger.error("S3 download failed for %s: %s", key, e)
        return False, None

    try:
        r2.upload_file(body, key, content_type=content_type or None)
    except Exception as e:  # noqa: BLE001
        logger.error("R2 upload failed for %s: %s", key, e)
        return False, None

    if not r2.file_exists(key):
        logger.error("R2 verify (HEAD) failed for %s", key)
        return False, None

    return True, r2.get_cdn_base_url(key)


def migrate_attachments(
    db: Session,
    s3: S3Service,
    r2: R2Service,
    *,
    dry_run: bool,
    batch_size: int,
    limit: Optional[int],
    entity_type: Optional[str],
) -> dict:
    moved = 0
    failed = 0
    seen = 0
    while True:
        q = (
            db.query(Attachment)
            .filter(Attachment.storage_provider == PROVIDER_S3)
            .filter(Attachment.file_path.isnot(None))
            .order_by(Attachment.uploaded_at.asc())
        )
        if entity_type:
            q = q.filter(Attachment.entity_type == entity_type)
        rows = q.limit(batch_size).all()
        if not rows:
            break
        for att in rows:
            seen += 1
            ok, new_path = _migrate_one(
                s3=s3,
                r2=r2,
                file_path=att.file_path,
                content_type=getattr(att, "mime_type", None),
                dry_run=dry_run,
            )
            if ok and new_path:
                if not dry_run:
                    att.file_path = new_path
                    att.storage_provider = PROVIDER_R2
                moved += 1
            else:
                failed += 1
            if limit is not None and seen >= limit:
                break
        if not dry_run:
            db.commit()
        logger.info("Attachments processed=%d moved=%d failed=%d", seen, moved, failed)
        if limit is not None and seen >= limit:
            break
    return {"target": "attachments", "seen": seen, "moved": moved, "failed": failed}


def migrate_avatars(
    db: Session,
    s3: S3Service,
    r2: R2Service,
    *,
    dry_run: bool,
    batch_size: int,
    limit: Optional[int],
) -> dict:
    moved = 0
    failed = 0
    seen = 0
    while True:
        rows = (
            db.query(User)
            .filter(User.avatar_storage_provider == PROVIDER_S3)
            .filter(User.avatar.isnot(None))
            .order_by(User.created_at.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        for user in rows:
            seen += 1
            avatar_url = (user.avatar or "").strip()
            # Only own-domain avatars are migrated; OAuth/external URLs stay put
            # but we still flip the provider so reads short-circuit cleanly.
            key = _extract_key(avatar_url)
            cf_domain = (os.getenv("CLOUDFRONT_DOMAIN") or "").strip().lower().rstrip("/")
            host = (urlparse(avatar_url).hostname or "").lower() if avatar_url.startswith("http") else ""
            if cf_domain and host and host != cf_domain:
                # External avatar (e.g. lh3.googleusercontent.com) — flip provider
                # so the avatar resolver passes it through without trying to sign.
                if not dry_run:
                    user.avatar_storage_provider = PROVIDER_R2
                continue
            if not key:
                continue
            ok, new_path = _migrate_one(
                s3=s3,
                r2=r2,
                file_path=avatar_url,
                content_type=None,
                dry_run=dry_run,
            )
            if ok and new_path:
                if not dry_run:
                    user.avatar = new_path
                    user.avatar_storage_provider = PROVIDER_R2
                moved += 1
            else:
                failed += 1
            if limit is not None and seen >= limit:
                break
        if not dry_run:
            db.commit()
        logger.info("Avatars processed=%d moved=%d failed=%d", seen, moved, failed)
        if limit is not None and seen >= limit:
            break
    return {"target": "avatars", "seen": seen, "moved": moved, "failed": failed}


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no S3 reads, no R2 writes, no DB updates")
    parser.add_argument("--batch-size", type=int, default=100, help="Rows per batch (default: 100)")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N rows total (per target)")
    parser.add_argument(
        "--target",
        choices=("attachments", "avatars", "both"),
        default="both",
        help="Which set to migrate (default: both)",
    )
    parser.add_argument(
        "--entity-type",
        type=str,
        default=None,
        help="Restrict attachments to this entity_type (e.g. 'promotion')",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    s3 = S3Service()
    r2 = R2Service()
    logger.info(
        "Source S3 bucket=%s region=%s -> Target R2 bucket=%s cdn=%s (dry_run=%s)",
        s3.bucket_name,
        s3.region,
        r2.bucket_name,
        r2.cdn_domain,
        args.dry_run,
    )

    db: Session = SessionLocal()
    try:
        results = []
        if args.target in ("attachments", "both"):
            results.append(
                migrate_attachments(
                    db,
                    s3,
                    r2,
                    dry_run=args.dry_run,
                    batch_size=args.batch_size,
                    limit=args.limit,
                    entity_type=args.entity_type,
                )
            )
        if args.target in ("avatars", "both"):
            results.append(
                migrate_avatars(
                    db,
                    s3,
                    r2,
                    dry_run=args.dry_run,
                    batch_size=args.batch_size,
                    limit=args.limit,
                )
            )
        for r in results:
            logger.info("Done: %s", r)
        any_failures = any(r["failed"] > 0 for r in results)
        return 1 if any_failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
