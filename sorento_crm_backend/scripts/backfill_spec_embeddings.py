#!/usr/bin/env python3
"""Backfill the `product_spec` embedding leg for spec rows that already exist.

The producer in `app/services/product_spec_change_listener.py` (issue #139) queues a
re-embed whenever a spec sentence changes from now on. It cannot cover the catalogue's
existing rows: those were written before the producer existed and nothing will rewrite
most of them, so without this run the semantic half of spec search stays blind to
almost everything in the catalogue.

One shot, and deliberately not a code path: WHEN it runs against production is an
operational decision, so it ships dry-run by default and a real run has to say `--apply`.

Idempotent by state rather than by a marker column, so a re-run is cheap and a killed
run needs no cleanup. A row is skipped when either

  * an unprocessed `embedding_queue` event for it is already waiting (a previous run,
    or the live producer, got there first), or
  * an active `embedding_documents` row for it is at least as new as the spec row
    (the worker has already embedded this sentence).

A row with no sentence is skipped outright: an empty embedding sits near everything and
would surface that product for every query.

Run from sorento_crm_backend/:
    python scripts/backfill_spec_embeddings.py                 # report only
    python scripts/backfill_spec_embeddings.py --apply
    python scripts/backfill_spec_embeddings.py --apply --limit 500
    python scripts/backfill_spec_embeddings.py --apply --start-after <spec_id>

Resumable: rows are paged by ascending `product_specifications.id` and the last id
reached is printed, so a run stopped by `--limit` or by a kill continues with
`--start-after <last_id>`. Needs the embedding worker running to have any effect: this
writes queue rows, the worker turns them into documents.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.embeddings import EmbeddingDocument, EmbeddingQueue
from app.models.product_spec import ProductSpecifications
from app.services.embedding_service import EmbeddingEventService

logger = logging.getLogger(__name__)

DEFAULT_TRIGGERED_BY = "cli-backfill-spec-embeddings"

# Statuses that mean "the worker has not dealt with this event yet". A completed or
# skipped row is history and must not stop a genuinely stale sentence being re-queued.
OPEN_QUEUE_STATUSES = ("pending", "processing")


def _already_queued(db: Session, product_id: str) -> bool:
    return (
        db.query(EmbeddingQueue.id)
        .filter(
            EmbeddingQueue.source_type == "product_spec",
            EmbeddingQueue.source_id == str(product_id),
            EmbeddingQueue.status.in_(OPEN_QUEUE_STATUSES),
        )
        .first()
        is not None
    )


def _already_current(db: Session, spec: ProductSpecifications) -> bool:
    """True when the live document already describes this row's sentence.

    Compared on `source_updated_at` because that is the spec row's own timestamp,
    copied onto the document by the worker: the alternative is re-rendering and
    re-hashing every sentence here, which duplicates the worker's job in a script
    whose whole point is to hand work TO the worker.
    """
    document = (
        db.query(EmbeddingDocument)
        .filter(
            EmbeddingDocument.source_type == "product_spec",
            EmbeddingDocument.source_id == str(spec.product_id),
            EmbeddingDocument.is_active.is_(True),
        )
        .order_by(EmbeddingDocument.created_at.desc())
        .first()
    )
    if document is None or document.source_updated_at is None:
        return False
    return document.source_updated_at >= (spec.updated_at or spec.created_at)


def run(
    db: Session,
    *,
    batch_size: int = 500,
    limit: int | None = None,
    dry_run: bool = True,
    start_after: str | None = None,
    triggered_by: str = DEFAULT_TRIGGERED_BY,
) -> dict:
    """Queue a `product_spec` re-embed for every spec row that needs one."""
    counts = {
        "dry_run": dry_run,
        "scanned": 0,
        "no_sentence": 0,
        "already_queued": 0,
        "already_current": 0,
        "queued": 0,
        "failed": 0,
        "last_id": start_after,
    }
    events = EmbeddingEventService(db)
    remaining = limit

    while True:
        page_size = batch_size if remaining is None else min(batch_size, remaining)
        if page_size <= 0:
            break

        # Keyset, NOT offset: `queue_event` commits, and a mid-run commit both invalidates
        # a server-side cursor and shifts what an offset points at. `id > last_id` is
        # stable under both, and is what makes `--start-after` a resume rather than a
        # guess.
        query = db.query(ProductSpecifications).order_by(ProductSpecifications.id.asc())
        if counts["last_id"] is not None:
            query = query.filter(ProductSpecifications.id > counts["last_id"])
        rows = query.limit(page_size).all()
        if not rows:
            break

        for spec in rows:
            counts["scanned"] += 1
            counts["last_id"] = spec.id
            if remaining is not None:
                remaining -= 1

            if not (spec.rendered_text or "").strip():
                counts["no_sentence"] += 1
                continue
            if _already_queued(db, spec.product_id):
                counts["already_queued"] += 1
                continue
            if _already_current(db, spec):
                counts["already_current"] += 1
                continue

            counts["queued"] += 1
            if dry_run:
                continue

            try:
                events.queue_event(
                    source_type="product_spec",
                    source_id=str(spec.product_id),
                    event_type="product_spec.updated",
                    source_updated_at=spec.updated_at or spec.created_at,
                    triggered_by=triggered_by,
                )
            except Exception:
                counts["queued"] -= 1
                counts["failed"] += 1
                logger.warning(
                    "spec embedding backfill failed for %s", spec.product_id, exc_info=True
                )
                # The failure may have left a half-written queue row behind, and the
                # next product's `queue_event` would commit it with no RQ job attached.
                db.rollback()

    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually queue the events. Without it the run reports and writes nothing.",
    )
    parser.add_argument("--batch", type=int, default=500, help="Rows read per page.")
    parser.add_argument("--limit", type=int, default=None, help="Stop after this many rows.")
    parser.add_argument(
        "--start-after",
        default=None,
        help="Resume after this product_specifications.id (printed by the previous run).",
    )
    parser.add_argument("--triggered-by", default=DEFAULT_TRIGGERED_BY)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    db = SessionLocal()
    try:
        # None = every company. A spec row exists per company copy and each one carries
        # its own document, exactly as the embedding worker runs.
        with company_scope(db, None):
            counts = run(
                db,
                batch_size=max(1, args.batch),
                limit=args.limit if args.limit and args.limit > 0 else None,
                dry_run=not args.apply,
                start_after=args.start_after,
                triggered_by=args.triggered_by,
            )
        if counts["dry_run"]:
            # `run` assigns nothing on a dry run, so this discards nothing. It is here
            # because "report only" has to be true of the session as well as of the
            # intent, and this is the only place that owns the session.
            db.rollback()
    finally:
        db.close()

    mode = "DRY-RUN (nothing written)" if counts["dry_run"] else "APPLIED"
    print(f"=== backfill_spec_embeddings [{mode}] ===")
    print(f"spec rows scanned : {counts['scanned']}")
    print(f"no sentence       : {counts['no_sentence']}")
    print(f"already queued    : {counts['already_queued']}")
    print(f"already current   : {counts['already_current']}")
    print(f"queued            : {counts['queued']}")
    print(f"failed            : {counts['failed']}")
    print(f"resume after id   : {counts['last_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
