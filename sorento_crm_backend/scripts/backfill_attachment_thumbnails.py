"""Backfill grid thumbnails for existing image attachments.

For every non-deleted image row without a thumbnail_path, download the original,
generate a ~320px JPEG thumbnail, upload it to "{key}.thumb.jpg" in the same
provider bucket, and set attachments.thumbnail_path to its CDN base URL.

Idempotent + re-runnable: skips rows that already carry a thumbnail_path whose
object exists. Per-row try/except so one bad image never aborts the batch; a
dropped/skipped summary is logged (no silent truncation).

Usage:
    venv/bin/python scripts/backfill_attachment_thumbnails.py [--limit N] [--dry-run]

See docs/plans/PLAN-attachment-grid-thumbnails.md.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_thumbnails")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all).")
    parser.add_argument("--dry-run", action="store_true", help="Report counts, write nothing.")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    from app.database import SessionLocal
    from app.models.resources import Attachment
    from app.services.image_thumbnailer import generate_thumbnail, thumbnail_key_for
    from app.services.storage_router import cdn_base_url, extract_key, get_backend

    db = SessionLocal()
    processed = made = skipped = failed = 0
    try:
        q = (
            db.query(Attachment)
            .filter(
                Attachment.is_deleted.is_(False),
                Attachment.mime_type.ilike("image/%"),
                Attachment.thumbnail_path.is_(None),
            )
            .order_by(Attachment.uploaded_at.desc())
        )
        if args.limit:
            q = q.limit(args.limit)
        rows = q.all()
        logger.info("Found %d image rows without a thumbnail.", len(rows))

        for att in rows:
            processed += 1
            key = extract_key(att.file_path)
            if not key:
                skipped += 1
                logger.warning("Skip %s: no extractable key from file_path.", att.id)
                continue
            provider = getattr(att, "storage_provider", None)
            try:
                backend = get_backend(provider)
                original = backend.download_file(key)
                thumb = generate_thumbnail(original, att.mime_type)
                if not thumb:
                    skipped += 1
                    logger.warning("Skip %s: not a decodable image (%s).", att.id, att.mime_type)
                    continue
                thumb_key = thumbnail_key_for(key)
                if args.dry_run:
                    made += 1
                    logger.info("[dry-run] would write %s (%d bytes).", thumb_key, len(thumb))
                    continue
                backend.upload_file(
                    file_content=thumb, file_path=thumb_key, content_type="image/jpeg"
                )
                att.thumbnail_path = cdn_base_url(provider, thumb_key)
                db.commit()
                made += 1
                logger.info("Thumb %s -> %s (%d bytes).", att.id, thumb_key, len(thumb))
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
                db.rollback()
                failed += 1
                logger.error("Failed %s: %s", att.id, exc)

        logger.info(
            "Done. processed=%d made=%d skipped=%d failed=%d%s",
            processed, made, skipped, failed, " (dry-run)" if args.dry_run else "",
        )
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
