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
from app.models.procurement import InboundShipment, SPOAllocation
from app.services.rules.shipping_order_rules import extract_container_number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, write nothing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(SPOAllocation, InboundShipment.shipping_container_number)
            .join(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
            .filter(
                SPOAllocation.container_number.is_(None),
                SPOAllocation.inbound_shipment_id.isnot(None),
            )
            .all()
        )

        updated = 0
        skipped_blank = 0
        sample: list[str] = []
        for allocation, raw_container in rows:
            cleaned = extract_container_number(raw_container)
            if not cleaned:
                skipped_blank += 1
                continue
            if len(sample) < 10:
                sample.append(f"  {allocation.id}: {raw_container!r} -> {cleaned!r}")
            if not args.dry_run:
                allocation.container_number = cleaned
            updated += 1

        if not args.dry_run and updated:
            db.commit()

        print("\n=== summary ===")
        print(f"mode:                {'DRY-RUN (no writes)' if args.dry_run else 'APPLIED'}")
        print(f"eligible rows:       {len(rows)}")
        print(f"filled:              {updated}")
        print(f"skipped (no cleanable container on the shipment): {skipped_blank}")
        if sample:
            print("sample:")
            for line in sample:
                print(line)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
