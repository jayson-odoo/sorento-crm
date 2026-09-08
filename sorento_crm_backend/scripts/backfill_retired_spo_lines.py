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

WHY "CLOSED, NEVER RECEIVED" IS NOT EVIDENCE (round 2 security review, B1)
---------------------------------------------------------------------------
The first cut of this script read `line_status = 'closed'` with a zero receipt as retirement.
That is wrong: FOUR different writers close an `autocount` row, and only one of them is
retirement.

1. **A receipt.** The row is fully received - not retired, the record of what arrived.
2. **The SCM outstanding book's absence sweep** (`outstanding_import_service._spo_lines_to_close`).
   A file that no longer states a line means the goods ARRIVED and this channel does not carry
   a receipt figure to write - the row closes with `quantity_received` untouched, deliberately.
   Stamping `retired_at` here would hide a real arrival.
3. **A cancelled document** (`ShippingOrderIngestService._write_row`, `force_closed`). Every line
   of a cancelled shipping order closes at once, with `retired_at` explicitly cleared by the
   SAME write (D28d: the payload still names the row, so it is live). None of this is retirement.
4. **The deletion service, on a referenced row** (`DeletionService._delete_shipping_order`). A
   row a GRN pick or a claim still points at is closed rather than deleted, with no receipt and
   no later replacement anywhere - it is the document being removed, not one line being edited.

Only D28d's own two events - the leftover sweep (a re-push that stops naming a line) and a
DocKey change (the document was deleted and re-created) - are retirement, and both share ONE
observable fact none of the four closers above share: AutoCount wrote a REPLACEMENT for it.
The evidence this backfill looks for is therefore not the receipt, it is the replacement:

- `source_ref IS NOT NULL` - an ESB-pushed line (a `scm_upload`/xlsx-era row carries no DtlKey
  at all and is out of scope here regardless);
- an OPEN sibling exists in the row's OWN `(company_id, spo_number, product_id, location)`
  group (`procurement_service._spo_allocation_group_key`, the exact key the group receipt
  recompute shares over - reused here, not restated) with `created_at` strictly LATER than
  this row's own. That later, open, same-group row IS the line AutoCount replaced this one
  with.

A cancelled document has no open sibling anywhere in it, so every one of its lines drops out
under this test. An absence-closed row has no later sibling either - nothing replaced it, the
book just stopped stating it. A referenced row the deletion service closed has no later sibling
for the same reason: the document is gone, not edited. Anything this test cannot tell apart is
left alone - the ingest's own leftover sweep or DocKey-change path stamps it correctly the next
time AutoCount pushes that number, exactly as it does for every row retired after #740 shipped.

`retired_at IS NULL` narrows to rows this backfill (or a later ingest push) has not already
marked - the query naturally excludes its own prior writes, so a second run finds nothing
left to do (AC-H7, AC-H9). A row whose `receipt_status` is already `fully_received` is
excluded too (round 4, AC-H16): dropping the receipt predicate in round 2 let a LIVE line
AutoCount still names match this test, if a later open sibling happened to exist for the
same product and location - a received line is visible under R2 either way, so marking it
retired buys nothing and only costs it its share of its group's receipt.

THE ROUND-2/ROUND-4 INTERACTION (security review of the delta, 2026-09-08)
----------------------------------------------------------------------------
Round 2 dropped the receipt predicate above; round 2 also gave `PickingHeaderService
._sync_received_for_allocations` an unconditional write to a retired row (B2, so a receipt
approved after retirement still reaches `quantity_received`). Each is right alone. Together,
a row this script stamps that carries a real ESB-stated receipt but no `stated_received`
floor (every row written before migration 488 states nothing) could be zeroed by the VERY
NEXT recompute - `max(stated 0, own picking total 0) = 0` - and then hidden by
`visible_line_clauses()`, whose R2 arm is `quantity_received > 0`. This is the D28/MB1 defect
class landing on the one row shape that is invisible afterwards. Closed two ways, together
rather than either alone: `_sync_received_for_allocations`'s retired branch now skips a row
that is neither released nor picked against (the same ownership gate its non-AutoCount
sibling already has), and this script freezes `stated_received` BEFORE stamping `retired_at`
- see SAFETY below.

SAFETY / IDEMPOTENCY
---------------------
- `--dry-run` (the default) reports the plan and writes nothing; the session is rolled back
  at the end so no read state survives the run.
- One commit per document (`spo_number`), so an interrupted run leaves whole documents done
  and the rest untouched.
- Re-running is a no-op: `retired_at IS NULL` is part of the selection, so an already-marked
  row is not selected again, and stamping a row can only ever REMOVE it as a later sibling for
  some earlier row in its own group, never add one - a second pass finds strictly less to do.
- Per row, in this order (round 4): FIRST `stated_received = max(stated, quantity_received)`
  when positive - the same freeze the ingest's own leftover sweep
  (`shipping_order_ingest_service.py`) and `dedupe_spo_xlsx_superseded.py` apply before they
  retire a row - THEN `retired_at = coalesce(updated_at, now())`. `updated_at` is the row's
  own last-touched time (the closest surviving estimate of when it was retired), `now()`
  covers the rows that have never been touched since insert.

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.procurement import SPOAllocation
from app.services.company_scope import register_company_scope_listeners
from app.services.procurement_service import _spo_allocation_group_key
from app.services.rules import shipping_order_rules
from app.services.shipping_order_ingest_service import (
    LINE_CLOSED,
    LINE_OPEN,
    RECEIPT_FULLY_RECEIVED,
    RECEIPT_PENDING,
)

logger = logging.getLogger("scripts.backfill_retired_spo_lines")


def _candidate_rows(db, company_id: str) -> list[tuple[SPOAllocation, SPOAllocation]]:
    """Every `(row, sibling)` pair this backfill has not already marked, oldest document
    first - `sibling` is the SPECIFIC later, open, same-group row that is the evidence
    (AC-H18: the dry-run report names it so the stamp is spot-checkable against AutoCount).

    `source_system = 'autocount'` AND `line_status = 'closed'` AND `source_ref IS NOT NULL`
    AND `coalesce(receipt_status, 'pending') != 'fully_received'` AND `retired_at IS NULL`,
    narrowed further in Python to only the rows whose own `(company, spo_number, product,
    location)` group (`_spo_allocation_group_key`, reused from `procurement_service` rather
    than restated) holds an OPEN row created strictly LATER than this one - see the module
    docstring for why that sibling, not the receipt, is the evidence of retirement.

    The `fully_received` exclusion (round 4, AC-H16) is NOT a return of round 1's receipt
    predicate - it does not require `quantity_received = 0`, only that the row is not
    ALREADY the record of a completed receipt. A row like that is a line AutoCount still
    names (a live sibling can only make a LIVE line match the sibling test - see the module
    docstring); marking it retired would buy nothing (R2 already keeps a received line
    visible) and would cost it its share of its group's receipt (it would stop being a
    live member of `_autocount_group_members`).
    """
    candidates = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.company_id == company_id,
            SPOAllocation.source_system == shipping_order_rules.AUTOCOUNT_SOURCE_SYSTEM,
            SPOAllocation.line_status == LINE_CLOSED,
            SPOAllocation.source_ref.isnot(None),
            func.coalesce(SPOAllocation.receipt_status, RECEIPT_PENDING) != RECEIPT_FULLY_RECEIVED,
            SPOAllocation.retired_at.is_(None),
        )
        .order_by(SPOAllocation.spo_number, SPOAllocation.spo_line_number, SPOAllocation.id)
        .all()
    )
    if not candidates:
        return []

    # The candidates' own OPEN siblings can only ever live among this company's OPEN
    # autocount rows - loaded once, indexed by the same group key, so N candidates cost
    # one query rather than N.
    open_rows = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.company_id == company_id,
            SPOAllocation.source_system == shipping_order_rules.AUTOCOUNT_SOURCE_SYSTEM,
            SPOAllocation.line_status == LINE_OPEN,
        )
        .all()
    )
    # The row itself, not just its `created_at` (AC-H18 needs its `source_ref` too) - the
    # LATEST-created open row per group, since that is the one that actually satisfies
    # "strictly later than this candidate" for the widest set of candidates.
    latest_open_by_group: dict[tuple, SPOAllocation] = {}
    for row in open_rows:
        key = _spo_allocation_group_key(row)
        current = latest_open_by_group.get(key)
        if current is None or row.created_at > current.created_at:
            latest_open_by_group[key] = row

    eligible: list[tuple[SPOAllocation, SPOAllocation]] = []
    for row in candidates:
        sibling = latest_open_by_group.get(_spo_allocation_group_key(row))
        if sibling is not None and sibling.created_at > row.created_at:
            eligible.append((row, sibling))
    return eligible


def run(db, company_id: str, dry_run: bool = True) -> dict[str, int]:
    """Every AutoCount document in ONE company holding a pre-#740 retired row.

    `dry_run` defaults to `True` so a caller that forgets the argument previews rather than
    writes, and a dry run ends with `db.rollback()` so no read state survives the sweep.
    """
    register_company_scope_listeners()

    summary = {"documents": 0, "rows_marked": 0}
    with company_scope(db, frozenset({company_id})):
        pairs = _candidate_rows(db, company_id)
        by_spo: dict[str, list[tuple[SPOAllocation, SPOAllocation]]] = {}
        for row, sibling in pairs:
            by_spo.setdefault(row.spo_number or "(no spo_number)", []).append((row, sibling))

        for spo_number, doc_pairs in by_spo.items():
            print(f"  {spo_number}: {len(doc_pairs)} row(s) to retire")
            # AC-H18: one line per ROW, not per document - nothing can pre-measure this
            # set (zero on the production copy, non-zero only on production), so the
            # dry run is the only artifact anyone reviews before an irreversible write,
            # and the sibling evidence has to be spot-checkable against AutoCount.
            for row, sibling in doc_pairs:
                print(
                    f"    id={row.id} source_ref={row.source_ref!r} "
                    f"source_doc_ref={row.source_doc_ref!r} created_at={row.created_at} "
                    f"quantity_received={row.quantity_received} "
                    f"receipt_status={row.receipt_status!r}"
                    f" -- replaced by sibling source_ref={sibling.source_ref!r} "
                    f"created_at={sibling.created_at}"
                )
            if not dry_run:
                now = datetime.now(timezone.utc)
                for row, _sibling in doc_pairs:
                    # Round 4 (AC-H15): freeze BEFORE stamping, the same order the
                    # ingest's own leftover sweep (shipping_order_ingest_service.py) and
                    # the dedupe script use - a row written before migration 488 states
                    # nothing (`stated_received IS NULL`), so without this floor the
                    # NEXT recompute's ownership-gated write (round 4 item 1) would see
                    # `stated_received 0` and could zero a real ESB-stated receipt the
                    # moment nothing picks against the row.
                    frozen = max(int(row.stated_received or 0), int(row.quantity_received or 0))
                    if frozen > 0:
                        row.stated_received = frozen
                    stamp = row.updated_at.replace(tzinfo=timezone.utc) if row.updated_at else now
                    row.retired_at = stamp
                db.commit()
            summary["documents"] += 1
            summary["rows_marked"] += len(doc_pairs)

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
