#!/usr/bin/env python3
"""Convert existing CMYK/YCCK image attachments to RGB JPEG in place.

WhatsApp Cloud API (and Meta's media validator behind Respond.io) reject CMYK
JPEGs with a generic "Media upload error" — print-pipeline tech-spec drawings
hit this constantly. New uploads are normalized at the upload boundary
(`app.services.image_normalizer`); this script fixes rows already in storage.

Run from sorento_crm_backend/:
    python scripts/backfill_cmyk_attachments_to_rgb.py [--dry-run] [--limit N]
                                                       [--batch-size N] [--id UUID]

For each image attachment whose stored bytes decode to a CMYK/YCCK color space,
the script:
    1. downloads the bytes from the row's storage provider (s3 or r2)
    2. transcodes CMYK/YCCK -> RGB JPEG (via image_normalizer.ensure_rgb_image)
    3. re-uploads to the SAME key on the SAME provider (overwrite in place)
    4. updates file_size_bytes + mime_type in the DB

Idempotent: a row already in an accepted color space is skipped, so re-runs are
safe and only touch rows that still need fixing. The storage key and filenames
are left unchanged (CMYK source is always JPEG, so the extension already fits),
so n8n linkages, signed URLs, and display names stay stable. No n8n webhook is
re-triggered — this is a byte-level fix, not a content change.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.resources import Attachment
from app.services.image_normalizer import ensure_rgb_image, needs_rgb_conversion
from app.services.storage_router import extract_key, get_backend, normalize_provider

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("backfill_cmyk_attachments")

# Candidate rows: JPEG mime or .jpg/.jpeg/.jfif name. (PNG can't be CMYK, so the
# byte-level check below is what actually decides — this just narrows the scan.)
_IMAGE_MIMES = ("image/jpeg", "image/jpg", "image/pjpeg")
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".jfif")


def _candidate_query(db: Session, only_id: Optional[str]):
    q = db.query(Attachment)
    if only_id:
        return q.filter(Attachment.id == only_id)
    name_filters = [Attachment.original_filename.ilike(f"%{s}") for s in _IMAGE_SUFFIXES]
    name_filters += [Attachment.stored_filename.ilike(f"%{s}") for s in _IMAGE_SUFFIXES]
    return (
        q.filter(
            or_(
                Attachment.mime_type.in_(_IMAGE_MIMES),
                *name_filters,
            )
        )
        # Skip linkage/template rows that never got a stored object.
        .filter(Attachment.file_path.isnot(None))
        .filter(func.trim(Attachment.file_path) != "")
        .order_by(Attachment.uploaded_at.asc())
    )


def _process_one(db: Session, row: Attachment, dry_run: bool) -> str:
    """Return one of: 'converted', 'skipped', 'error'."""
    provider = normalize_provider(row.storage_provider)
    key = extract_key(row.file_path)
    if not key:
        logger.warning("attachment %s has no resolvable key (%s)", row.id, row.file_path)
        return "skipped"

    try:
        backend = get_backend(provider)
        content = backend.download_file(key)
    except Exception as exc:  # noqa: BLE001
        # get_backend('s3') needs the CloudFront key (absent locally); a single
        # bad provider init or download must not abort the whole batch.
        logger.warning("attachment %s download failed (%s/%s): %s", row.id, provider, key, exc)
        return "error"

    if not needs_rgb_conversion(content, row.mime_type or "image/jpeg"):
        return "skipped"

    new_content, _name, new_mime = ensure_rgb_image(content, row.original_filename, row.mime_type)
    if new_content is content or len(new_content) == 0:
        # ensure_rgb_image bailed (decode/convert failure) — leave row untouched.
        logger.warning("attachment %s flagged CMYK but conversion no-op'd", row.id)
        return "error"

    logger.info(
        "attachment %s (%s) CMYK -> RGB: %d -> %d bytes [%s/%s]",
        row.id, row.original_filename, len(content), len(new_content), provider, key,
    )
    if dry_run:
        return "converted"

    try:
        backend.upload_file(file_content=new_content, file_path=key, content_type="image/jpeg")
    except Exception as exc:  # noqa: BLE001
        logger.error("attachment %s re-upload failed (%s/%s): %s", row.id, provider, key, exc)
        return "error"

    row.file_size_bytes = len(new_content)
    row.mime_type = new_mime or "image/jpeg"
    db.add(row)
    db.commit()
    return "converted"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report without writing/uploading.")
    parser.add_argument("--limit", type=int, default=None, help="Max candidate rows to scan.")
    parser.add_argument("--batch-size", type=int, default=200, help="Rows per fetch.")
    parser.add_argument("--id", dest="only_id", default=None, help="Process a single attachment id.")
    args = parser.parse_args()

    db: Session = SessionLocal()
    counts = {"converted": 0, "skipped": 0, "error": 0}
    scanned = 0
    try:
        base_query = _candidate_query(db, args.only_id)
        if args.only_id:
            rows = base_query.all()
            for row in rows:
                scanned += 1
                counts[_process_one(db, row, args.dry_run)] += 1
        else:
            offset = 0
            while True:
                fetch = args.batch_size
                if args.limit:
                    remaining = args.limit - scanned
                    if remaining <= 0:
                        break
                    fetch = min(fetch, remaining)
                rows = base_query.offset(offset).limit(fetch).all()
                if not rows:
                    break
                for row in rows:
                    scanned += 1
                    counts[_process_one(db, row, args.dry_run)] += 1
                offset += len(rows)
                if len(rows) < fetch:
                    break
    finally:
        db.close()

    logger.info(
        "Done. scanned=%d converted=%d skipped=%d error=%d%s",
        scanned, counts["converted"], counts["skipped"], counts["error"],
        " (dry-run, nothing written)" if args.dry_run else "",
    )
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
