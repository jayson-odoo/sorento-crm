#!/usr/bin/env python3
"""Backfill chat_histories.respond_ts from the Respond message id.

Respond mints `messageId` as the message's epoch-MICROSECOND timestamp, so the
authoritative SLA clock was always present on the row — the ingest path just never
read it, and the resolver (the only writer of `respond_ts`) was failing every call.
Net effect on production: `turn_id` paired rows correctly, but every `respond_ts`
was NULL, so `chat_history_query` dropped every turn and the admin grid's Latency
and Delivery columns rendered "—" on every row.

This reconciles the history using the SAME parser the live ingest path now uses
(`chat_message_resolver.respond_ts_from_message_id`), so a backfilled row and a
freshly-ingested one are computed identically.

Run from sorento_crm_backend/ AFTER deploying the ingest fix:
    python scripts/backfill_chat_respond_ts.py [--dry-run] [--batch 1000] [--days N]

Two passes:

1. `respond_ts` — set wherever the id parses to a timestamp plausibly near `sent_at`.
   Ids that don't (sequence-style test rows, nulls) are left alone; a NULL respond_ts
   is honest and the row simply sits out of the SLA.

2. `delivery_status='not_sent'` — cleared ONLY on rows where pass 1 derived a
   timestamp. Respond minted an id for those, so "never sent" was a false verdict
   written by the resolver exhausting MAX_RESOLVE_ATTEMPTS against a failing call.
   `resolve_attempts` resets with it so the resolver retries and fills the real
   delivery status. Rows we cannot vouch for keep their verdict.

Idempotent: pass 1 is a "set where NULL and derivable" and pass 2 is scoped to rows
pass 1 can vouch for, so a second run reports zero changes.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.chat_history import ChatHistory
from app.services.chat_message_resolver import respond_ts_from_message_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report only; write nothing."
    )
    parser.add_argument(
        "--batch", type=int, default=1000, help="Rows committed per batch."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only rows sent within the last N days (default: all history).",
    )
    args = parser.parse_args()

    db = SessionLocal()
    scanned = derived = skipped = cleared = 0
    try:
        q = db.query(ChatHistory).filter(
            ChatHistory.message_id.isnot(None),
            ChatHistory.respond_ts.is_(None),
        )
        if args.days:
            q = q.filter(
                ChatHistory.sent_at >= datetime.utcnow() - timedelta(days=args.days)
            )

        # Keyset batches, NOT `yield_per`. `yield_per` opens a psycopg2 named
        # (server-side) cursor, and the mid-loop commit below closes the transaction
        # that cursor belongs to -- the next fetch then dies with "named cursor isn't
        # valid anymore". Streaming and committing are mutually exclusive here, so we
        # page explicitly instead.
        #
        # `id > last_id` (not OFFSET) because each commit removes rows from the
        # filter's own result set: an offset would skip forward over unprocessed rows
        # by exactly as many as it just fixed.
        last_id = 0
        while True:
            rows = (
                q.filter(ChatHistory.id > last_id)
                .order_by(ChatHistory.id.asc())
                .limit(args.batch)
                .all()
            )
            if not rows:
                break
            last_id = rows[-1].id

            for row in rows:
                scanned += 1
                ts = respond_ts_from_message_id(row.message_id, sent_at=row.sent_at)
                if ts is None:
                    skipped += 1
                    continue

                derived += 1
                # Respond issued an id for this message, so `not_sent` was the resolver
                # giving up, not evidence of a message that never existed.
                clears = row.delivery_status == "not_sent"
                if clears:
                    cleared += 1

                if args.dry_run:
                    # Assign nothing at all: a dirty row would be flushed to the
                    # transaction by autoflush before the next SELECT, making a
                    # "report only" run issue UPDATEs.
                    continue

                row.respond_ts = ts
                if clears:
                    row.delivery_status = None
                    row.resolve_attempts = 0

            if not args.dry_run:
                db.commit()

        if args.dry_run:
            db.rollback()
    finally:
        db.close()

    print(
        f"scanned={scanned} respond_ts_set={derived} "
        f"unparseable_id_skipped={skipped} not_sent_cleared={cleared}"
        + (" (dry run, nothing written)" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
