#!/usr/bin/env python3
"""Backfill purchase_request_headers.approved_by: resolve raw UUIDs to names.

fix/pr-rejected-by-uuid: the `reject-submitted` path historically stored the
actor's raw user UUID into `approved_by` (e.g. PR26-0333 shows
"6d1a317c-8c96-4120-8116-d639b5b0a9e5" under "Rejected by"). Every other write
path stores a resolved display name, and the FE renders `approved_by` verbatim,
so those rejected rows leak a UUID. The service is now fixed forward; this
reconciles the rows already persisted.

Run from sorento_crm_backend/ AFTER deploying the fix:
    python scripts/backfill_pr_approved_by_names.py [--dry-run] [--batch 500]

For every header whose `approved_by` is UUID-shaped, it looks up the matching
User and rewrites `approved_by` to that user's name (or email). Rows whose UUID
matches no user are left untouched and reported. Idempotent: after a run the
values are names, so a second run finds nothing.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.procurement import PurchaseRequestHeader
from app.models.user import User
from app.services.procurement_service import PurchaseRequestService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report only; write nothing."
    )
    parser.add_argument(
        "--batch", type=int, default=500, help="Rows per commit batch (default 500)."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = PurchaseRequestService(db)
        uuid_re = svc._UUID_RE

        headers = (
            db.query(PurchaseRequestHeader)
            .filter(PurchaseRequestHeader.approved_by.isnot(None))
            .filter(PurchaseRequestHeader.approved_by != "")
            .all()
        )

        candidates = [
            h for h in headers if uuid_re.match((h.approved_by or "").strip())
        ]

        resolved = 0
        unresolved = 0
        pending = 0
        for h in candidates:
            uid = (h.approved_by or "").strip()
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                unresolved += 1
                print(
                    f"  UNRESOLVED  {h.request_number or h.id}: approved_by={uid} "
                    "matches no user - left as-is"
                )
                continue
            name = ((user.name or "").strip() or user.email or "").strip()
            if not name:
                unresolved += 1
                print(
                    f"  UNRESOLVED  {h.request_number or h.id}: user {uid} has no "
                    "name/email - left as-is"
                )
                continue
            print(f"  {h.request_number or h.id}: {uid} -> {name}")
            if not args.dry_run:
                h.approved_by = name
                pending += 1
                if pending >= args.batch:
                    db.commit()
                    pending = 0
            resolved += 1

        if not args.dry_run and pending:
            db.commit()

        verb = "would resolve" if args.dry_run else "resolved"
        print(
            f"\nScanned {len(headers)} headers, {len(candidates)} UUID-shaped; "
            f"{verb} {resolved}, unresolved {unresolved}."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
