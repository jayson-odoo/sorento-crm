#!/usr/bin/env python3
"""Backfill complaint <-> replacement Delivery Order links + fulfilment status.

PLAN-complaint-do-auto-fulfilment: replacement DOs created before this feature shipped
already name their complaint number(s) in Remarks CS, but no link rows / `fulfilled`
status exist yet. This script reconciles them into the correct, *already-notified* state
so only genuinely new deliveries notify going forward.

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:
    python scripts/backfill_complaint_fulfilment_orders.py [--dry-run] [--batch 500]

For every order with a non-empty Remarks CS it runs the same centralized helper the live
import/PUT use (`ComplaintFulfilmentService.reconcile_links_and_status`, dry_run=False):
creates the gated links (only `processed_by_cs`/`fulfilled` complaints link), sets
`fulfilled` where every non-cancelled linked DO is already delivered, and STAMPS
`delivery_notified_at = now()` on already-delivered links — but DISCARDS the returned
notify payloads, so NO historical delivery message is ever sent (stamp-without-send).

Idempotent: links carry a unique (complaint_id, order_id) constraint and the helper is
delta-aware (re-run adds no duplicate link, re-fulfils nothing, re-stamps nothing). A
second run reports zero new links / zero status flips.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.complaints import ComplaintFulfilmentOrder
from app.models.order import Order
from app.services.complaint_fulfilment_service import ComplaintFulfilmentService


def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report only; write nothing."
    )
    parser.add_argument(
        "--batch", type=int, default=500, help="Orders per reconcile batch (default 500)."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = ComplaintFulfilmentService(db)

        # Every order with a non-empty Remarks CS. old_remarks=None forces each into the
        # reconcile (the helper diffs desired-vs-existing links, so already-linked rows
        # are no-ops — the empty old_remarks does not re-create them).
        order_ids = [
            str(r[0])
            for r in db.query(Order.id)
            .filter(func.coalesce(func.trim(Order.remarks_cs), "") != "")
            .all()
        ]
        total_orders = len(order_ids)
        print(f"Scanning {total_orders} order(s) with a Remarks CS value...")

        links_before = db.query(func.count(ComplaintFulfilmentOrder.id)).scalar() or 0
        all_warnings: list[str] = []
        suppressed_notifies = 0

        for batch in _chunked(order_ids, max(1, args.batch)):
            orders = db.query(Order).filter(Order.id.in_(batch)).all()
            changes = [{"order": o, "old_remarks": None} for o in orders]
            warnings, notify_payloads = svc.reconcile_links_and_status(
                changes, dry_run=args.dry_run
            )
            all_warnings.extend(warnings)
            # STAMP-WITHOUT-SEND: the helper already set delivery_notified_at on the
            # links; we deliberately DROP the payloads so no historical message fires.
            suppressed_notifies += len(notify_payloads)
            if not args.dry_run:
                db.commit()

        links_after = (
            links_before
            if args.dry_run
            else (db.query(func.count(ComplaintFulfilmentOrder.id)).scalar() or 0)
        )

        print("")
        print("Backfill summary" + (" (DRY RUN — no writes)" if args.dry_run else ""))
        print(f"  orders scanned          : {total_orders}")
        print(f"  link rows before        : {links_before}")
        if not args.dry_run:
            print(f"  link rows after         : {links_after}  (+{links_after - links_before})")
        print(f"  deliveries stamped-no-send: {suppressed_notifies}")
        print(f"  warnings (not-linked etc): {len(all_warnings)}")
        for w in all_warnings[:20]:
            print(f"    - {w}")
        if len(all_warnings) > 20:
            print(f"    ... and {len(all_warnings) - 20} more")
        if args.dry_run:
            db.rollback()
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
