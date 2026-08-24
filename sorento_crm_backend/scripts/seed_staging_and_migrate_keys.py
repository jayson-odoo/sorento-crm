#!/usr/bin/env python3
"""STAGING-ONLY: seed the staging bucket from prod objects + migrate keys to the uuid scheme.

Local rows point `file_path` at prod (`cdn-sorento.com/{flat_key}`); the objects live in the
PROD R2 bucket, which staging doesn't have. This helper, for each flat-keyed r2 row:
  1. READS the object from the prod bucket (`sorento-crm`) - read-only, no prod mutation.
  2. WRITES it to the staging bucket (whatever .env's R2_BUCKET_NAME is) at the NEW uuid key
     `{entity_type}/{attachment_id}/{filename}`.
  3. Repoints `file_path` to the staging CDN (`cdn_base_url`).

So staging ends up holding the migrated (uuid-keyed) objects and the local DB points at them.
PROD is only READ. Idempotent: a row already on the uuid scheme is skipped; a re-run whose
staging object already exists skips the upload and just repoints.

Run from sorento_crm_backend/ with .env pointing at the STAGING bucket:
    python scripts/seed_staging_and_migrate_keys.py [--dry-run] [--apply] [--limit N]
                                                    [--prod-bucket sorento-crm]

SAFETY: --dry-run (default) makes zero writes. --apply writes to STAGING + local DB only.
Refuses to run if R2_BUCKET_NAME is not a staging bucket (guard against pointing at prod).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.database import SessionLocal
from app.models.resources import Attachment
from app.services.r2_service import R2Service
from app.services.storage_router import cdn_base_url, extract_key

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("seed_staging_and_migrate_keys")


def _new_key_for(old_key: str, attachment_id: str):
    segs = [s for s in (old_key or "").split("/") if s]
    if len(segs) != 2:
        return None
    return f"{segs[0]}/{attachment_id}/{segs[1]}"


def _prod_client():
    acct = os.getenv("R2_ACCOUNT_ID")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}, signature_version="s3v4"),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--prod-bucket", default="sorento-crm")
    args = ap.parse_args()

    staging = R2Service()
    if "staging" not in (staging.bucket_name or "").lower():
        logger.error("REFUSING: R2_BUCKET_NAME=%r is not a staging bucket. Point .env at staging.", staging.bucket_name)
        return 2
    if args.prod_bucket == staging.bucket_name:
        logger.error("REFUSING: --prod-bucket equals the staging bucket.")
        return 2

    apply = bool(args.apply)
    prod = _prod_client()
    logger.info("%s: read prod=%s  write staging=%s", "APPLY" if apply else "dry-run",
                args.prod_bucket, staging.bucket_name)

    db: Session = SessionLocal()
    counts: dict[str, int] = defaultdict(int)
    try:
        q = (db.query(Attachment)
             .filter(Attachment.is_deleted == False,                # noqa: E712
                     Attachment.storage_provider == "r2",
                     Attachment.file_path.like("%cdn-sorento.com/%"))
             .order_by(Attachment.created_at.asc()))
        if args.limit:
            q = q.limit(args.limit)
        rows = q.all()
        logger.info("scanning %d r2 prod-pointed row(s)", len(rows))

        for a in rows:
            old_key = extract_key(a.file_path)
            new_key = _new_key_for(old_key, str(a.id)) if old_key else None
            if new_key is None:
                counts["SKIP_NOT_FLAT"] += 1
                continue

            if staging.file_exists(new_key):
                want = cdn_base_url("r2", new_key)
                if a.file_path != want:
                    if apply:
                        a.file_path = want
                        db.commit()
                    counts["REPOINTED"] += 1
                else:
                    counts["ALREADY"] += 1
                continue

            if not apply:
                counts["WOULD_SEED_MIGRATE"] += 1
                continue

            try:
                obj = prod.get_object(Bucket=args.prod_bucket, Key=old_key)
                body = obj["Body"].read()
                ctype = obj.get("ContentType") or a.mime_type or None
            except Exception as e:  # noqa: BLE001
                logger.warning("att=%s prod read failed %s: %s", a.id, old_key, e)
                counts["PROD_READ_FAILED"] += 1
                continue

            staging.upload_file(body, new_key, content_type=ctype)
            if not staging.file_exists(new_key):
                counts["VERIFY_FAILED"] += 1
                continue
            a.file_path = cdn_base_url("r2", new_key)
            db.commit()
            counts["SEEDED_MIGRATED"] += 1
            if counts["SEEDED_MIGRATED"] % 50 == 0:
                logger.info("... %d migrated", counts["SEEDED_MIGRATED"])
    finally:
        db.close()

    logger.info("summary: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
