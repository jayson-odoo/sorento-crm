#!/usr/bin/env python3
"""Stamp `retired_at` on the SPO lines that were retired BEFORE PR #740 shipped
(PLAN-hide-retired-spo-lines, section 3).

WHAT IT DOES
------------
`spo_allocations.retired_at` (migration 488, D28d) is written going forward by the
shipping-order ingest's own leftover sweep and DocKey-change path (a re-push that stops
naming a line, or a document deleted and re-created under a fresh DocKey). Every row that
was retired by one of those two events BEFORE the column existed carries no marker, so
`spo_supply.visible_line_clauses()` cannot tell it from an ordinary open or closed line -
it still shows up in the SPO document lines tab, the allocations grid and the document
rollups, which is the defect PLAN-hide-retired-spo-lines exists to fix.

WHY THESE THREE CONDITIONS MEAN "RETIRED"
------------------------------------------
There is no audit trail for a pre-#740 retirement - `retired_at` itself did not exist yet,
and nothing else records WHY a row was closed. The receipt columns are the only surviving
evidence: an AutoCount row (`source_system = 'autocount'`) that is `line_status = 'closed'`
with `quantity_received = 0` AND a receipt status that never reached `fully_received` was
closed WITHOUT ever having been received. A line closes for exactly two reasons - a receipt
completed it, or the ingest retired it - and the receipt evidence rules out the first, which
leaves only the second. A row closed BY a receipt fails this test on `quantity_received = 0`
alone (R2's own reasoning, restated backwards): if goods arrived, the row is not retired, it
is the record of what came in.

`retired_at IS NULL` narrows to rows this backfill (or a later ingest push) has not already
marked - the query naturally excludes its own prior writes, so a second run finds nothing
left to do (AC-H7).

SAFETY / IDEMPOTENCY
---------------------
- `--dry-run` (the default) reports the plan and writes nothing; the session is rolled back
  at the end so no read state survives the run.
- One commit per document (`spo_number`), so an interrupted run leaves whole documents done
  and the rest untouched.
- Re-running is a no-op: `retired_at IS NULL` is part of the selection, so an already-marked
  row is not selected again.
- `retired_at = coalesce(updated_at, now())` - `updated_at` is the row's own last-touched
  time (the closest surviving estimate of when it was retired), `now()` covers the rows that
  have never been touched since insert.

USAGE
-----
    venv/bin/python scripts/backfill_retired_spo_lines.py --company SORENTO --dry-run
    venv/bin/python scripts/backfill_retired_spo_lines.py --company SORENTO --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.procurement import SPOAllocation
from app.services.company_scope import register_company_scope_listeners
from app.services.rules import shipping_order_rules
from app.services.shipping_order_ingest_service import (
    LINE_CLOSED,
    RECEIPT_FULLY_RECEIVED,
    RECEIPT_PENDING,
)

logger = logging.getLogger("scripts.backfill_retired_spo_lines")


def _candidate_rows(db, company_id: str) -> list[SPOAllocation]:
    """Every row this backfill has not already marked, oldest document first.

    `source_system = 'autocount'` AND `line_status = 'closed'` AND
    `coalesce(receipt_status, 'pending') != 'fully_received'` AND
    `coalesce(quantity_received, 0) = 0` AND `retired_at IS NULL` - see the module
    docstring for why those four conditions together mean "retired". Both COALESCEs are
    real, not defensive dressing: `receipt_status`/`quantity_received` are NOT NULL columns
    today, but a plain `!=` / `==` comparison reads a NULL as UNKNOWN and silently drops
    the row rather than including it, which is the opposite of what a nullable-in-spirit
    column (and any older row written before the NOT NULL constraint existed) needs here.
    """
    return (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.company_id == company_id,
            SPOAllocation.source_system == shipping_order_rules.AUTOCOUNT_SOURCE_SYSTEM,
            SPOAllocation.line_status == LINE_CLOSED,
            func.coalesce(SPOAllocation.receipt_status, RECEIPT_PENDING) != RECEIPT_FULLY_RECEIVED,
            func.coalesce(SPOAllocation.quantity_received, 0) == 0,
            SPOAllocation.retired_at.is_(None),
        )
        .order_by(SPOAllocation.spo_number, SPOAllocation.spo_line_number, SPOAllocation.id)
        .all()
    )


def run(db, company_id: str, dry_run: bool = True) -> dict[str, int]:
    """Every AutoCount document in ONE company holding a pre-#740 retired row.

    `dry_run` defaults to `True` so a caller that forgets the argument previews rather than
    writes, and a dry run ends with `db.rollback()` so no read state survives the sweep.
    """
    register_company_scope_listeners()

    summary = {"documents": 0, "rows_marked": 0}
    with company_scope(db, frozenset({company_id})):
        rows = _candidate_rows(db, company_id)
        by_spo: dict[str, list[SPOAllocation]] = {}
        for row in rows:
            by_spo.setdefault(row.spo_number or "(no spo_number)", []).append(row)

        for spo_number, doc_rows in by_spo.items():
            print(f"  {spo_number}: {len(doc_rows)} row(s) to retire")
            if not dry_run:
                now = datetime.now(timezone.utc)
                for row in doc_rows:
                    stamp = row.updated_at.replace(tzinfo=timezone.utc) if row.updated_at else now
                    row.retired_at = stamp
                db.commit()
            summary["documents"] += 1
            summary["rows_marked"] += len(doc_rows)

    if dry_run:
        db.rollback()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", required=True, help="Company CODE to backfill")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Print the plan, write nothing (the default)"
    )
    mode.add_argument("--apply", action="store_true", help="Write the plan")
    args = parser.parse_args()

    dry_run = not args.apply

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.code == args.company).first()
        if company is None:
            print(f"no company with code {args.company!r}")
            return 1
        print(f"=== {args.company} ({'DRY-RUN (no writes)' if dry_run else 'APPLYING'}) ===")
        summary = run(db, str(company.id), dry_run=dry_run)
        print("\n=== summary ===")
        print(f"mode:          {'DRY-RUN (no writes)' if dry_run else 'APPLIED'}")
        print(f"documents:     {summary['documents']}")
        print(f"rows retired:  {summary['rows_marked']}")
        if dry_run and summary["rows_marked"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
