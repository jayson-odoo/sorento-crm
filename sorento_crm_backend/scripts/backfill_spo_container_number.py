#!/usr/bin/env python3
"""Backfill `spo_allocations.container_number` (migration 477, D6) from the
inbound shipment each allocation already links to.

WHAT IT DOES
------------
`container_number` is a NEW column (S3, ingest-parity-standardisation): every
allocation written from now on stores it, but the rows this database already
holds were written before the column existed. Where an allocation already
carries `inbound_shipment_id`, the shipment's own `shipping_container_number`
is the fact this column exists to record - so this script fills it from
there, one UPDATE per distinct (shipment, cleaned container) pair.

Every value is passed through the SAME `shipping_order_rules
.extract_container_number` the two live writers use, so a shipment's raw
`shipping_container_number` (which may itself carry the "F-... (MOCHA)"
noise a Loading Date cell does) lands cleaned, not as a second, differently-
formatted copy of the same fact.

PAGING (nit, review re-check 2026-09-06)
-----------------------------------------
A single `.all()` loaded every eligible row across every company into memory
at once - fine on a lane DB, not something to run unmodified against
production without knowing the row count first. Paged per company (each
company's rows fetched inside `company_scope`, so the company-scope filter
narrows the query the same way it does for every other caller rather than
scanning cross-company) and, within a company, by KEYSET on `SPOAllocation.id`
rather than `Session.query(...).yield_per(...)` - `yield_per` holds a
server-side named cursor open across the whole loop, and this script commits
per page to bound memory, which is exactly the "yield_per + commit = dead
named cursor" trap (LESSONS-LEARNT): the cursor does not survive the first
commit, so every page after it raises or silently returns nothing.

SAFETY / IDEMPOTENCY
---------------------
- Only touches rows with `container_number IS NULL AND inbound_shipment_id
  IS NOT NULL` - an allocation with no shipment has nothing to backfill
  from, and a row already carrying a value (a fresh write) is never
  overwritten.
- `--dry-run` prints the count and a sample without writing.
- Re-running is a no-op once every eligible row is filled.

USAGE
-----
    python scripts/backfill_spo_container_number.py --dry-run
    python scripts/backfill_spo_container_number.py
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.procurement import InboundShipment, SPOAllocation
from app.services.rules.shipping_order_rules import extract_container_number

BATCH_SIZE = 500


def _company_ids(db) -> list[str]:
    return [str(row[0]) for row in db.query(Company.id).order_by(Company.id).all()]


def _backfill_company(db, company_id: str, dry_run: bool) -> tuple[int, int, int, list[str]]:
    """One company, one page at a time (keyset on `SPOAllocation.id`, never
    `yield_per` - see the module docstring). Returns
    (eligible, updated, skipped_blank, sample)."""
    eligible = updated = skipped_blank = 0
    sample: list[str] = []
    last_id: str | None = None
    with company_scope(db, frozenset({company_id})):
        while True:
            query = (
                db.query(SPOAllocation, InboundShipment.shipping_container_number)
                .join(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
                .filter(
                    SPOAllocation.container_number.is_(None),
                    SPOAllocation.inbound_shipment_id.isnot(None),
                )
            )
            if last_id is not None:
                query = query.filter(SPOAllocation.id > last_id)
            page = query.order_by(SPOAllocation.id).limit(BATCH_SIZE).all()
            if not page:
                break
            for allocation, raw_container in page:
                eligible += 1
                cleaned = extract_container_number(raw_container)
                if not cleaned:
                    skipped_blank += 1
                    continue
                if len(sample) < 10:
                    sample.append(f"  {allocation.id}: {raw_container!r} -> {cleaned!r}")
                if not dry_run:
                    allocation.container_number = cleaned
                updated += 1
            last_id = page[-1][0].id
            if not dry_run:
                db.commit()
            if len(page) < BATCH_SIZE:
                break
    return eligible, updated, skipped_blank, sample


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, write nothing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        total_eligible = total_updated = total_skipped = 0
        sample: list[str] = []
        for company_id in _company_ids(db):
            eligible, updated, skipped_blank, company_sample = _backfill_company(
                db, company_id, args.dry_run
            )
            total_eligible += eligible
            total_updated += updated
            total_skipped += skipped_blank
            if len(sample) < 10:
                sample.extend(company_sample[: 10 - len(sample)])

        print("\n=== summary ===")
        print(f"mode:                {'DRY-RUN (no writes)' if args.dry_run else 'APPLIED'}")
        print(f"eligible rows:       {total_eligible}")
        print(f"filled:              {total_updated}")
        print(f"skipped (no cleanable container on the shipment): {total_skipped}")
        if sample:
            print("sample:")
            for line in sample:
                print(line)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
