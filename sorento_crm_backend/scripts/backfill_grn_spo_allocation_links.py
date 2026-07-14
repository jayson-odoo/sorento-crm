#!/usr/bin/env python3
"""Backfill picking_lines.spo_allocation_id for GRNs whose lines were left unlinked
by the weak import SPO matcher, then re-sync stored allocation quantity_received.

ROOT CAUSE
----------
GRN listing/lines import (`app/tasks/import_tasks.py`) matched a GRN line's SPO
number to `spo_allocations` with a separator-only normalizer (`/` -> `.`). But SPO
strings arrive in two shapes, e.g. header `SPO-2026/06-0095` vs allocation
`SPO-202606-0095`. Those are EQUAL under the system-wide `_spo_match_key`
(strip-all-non-alphanumeric, used by the linked-GRN display + service FIFO) but NOT
under the weak normalizer. So the import FIFO pool came back empty and every line
was written with `spo_allocation_id = NULL` — while the SPO detail page still showed
the GRN as "linked" (that view uses the strong key). Hence: GRN header shows an SPO
number, SPO detail lists the GRN, yet the GRN's per-line "SPO Allocation" column is
all "-". The import code has been fixed to use `_spo_match_key`; this script repairs
rows already written.

WHAT IT DOES
------------
For each affected GRN (picking_type='goods_received', header spo_number set), per
product: re-runs the SAME two-pass FIFO the import uses (same-warehouse first, then
cross-warehouse) over the allocation pool selected by `_spo_match_key`, but assigns
the FK to the currently-unlinked lines. Because import wrote one whole-quantity NULL
line per (product, warehouse), the repair deletes those NULL lines and recreates the
FIFO chunks (each chunk -> one PickingLine with its spo_allocation_id; any
un-coverable remainder -> one NULL line, exactly as a correct fresh import would).
Already-linked lines are never touched. Finally, `sync_received_for_spo_number`
refreshes each affected allocation's stored `quantity_received` / `receipt_status`
and the inbound-shipment line statuses (so the stored column the import availability
check reads agrees with the computed value the detail page shows).

Availability per allocation = allocated_quantity - compute_received_for_allocation()
(approved GRN lines only) — the SAME source of truth the service FIFO uses, so the
stored/computed divergence is closed rather than widened. NULL lines contribute 0 to
compute_received, so deleting/recreating them does not change the pool mid-run.

SAFETY / IDEMPOTENCY
--------------------
- Default scope: approved GRNs only (a GRN's lines count toward received only when
  approved; linking those is the safe, meaningful case). `--include-unapproved` to
  also process draft GRNs (logged separately).
- `--dry-run` writes nothing and prints the per-GRN plan (lines to relink, qty that
  stays unlinked because no allocation covers it).
- `--grn GR-2026/07-0037` limits to one GRN (repeatable) for a surgical fix.
- Re-running is safe: once linked, allocation availability drops to 0, so a leftover
  NULL line finds an empty pool and is left as-is. A second run reports zero changes.

Run from sorento_crm_backend/ AFTER deploying the import_tasks.py matcher fix:
    python scripts/backfill_grn_spo_allocation_links.py --dry-run
    python scripts/backfill_grn_spo_allocation_links.py            # apply all approved
    python scripts/backfill_grn_spo_allocation_links.py --grn GR-2026/07-0037
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.procurement import PickingHeader, PickingLine, SPOAllocation
from app.services.procurement_service import (
    PickingHeaderService,
    _spo_match_key,
)


def _fifo_chunks(
    null_lines: List[PickingLine],
    pool: List[List[Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Replicate the import two-pass FIFO over the product's unlinked lines.

    `pool` entries are mutable [alloc_id, alloc_warehouse_id, available] and are
    decremented in place. Returns (chunks, unlinked_qty) where each chunk carries the
    originating line's warehouses/condition so the recreated row matches the source.
    """
    chunks: List[Dict[str, Any]] = []
    unlinked_qty = 0

    # Deterministic, import-like order: oldest line first.
    ordered = sorted(
        null_lines,
        key=lambda l: (getattr(l, "created_at", None) or 0, str(l.id)),
    )

    for line in ordered:
        source_wh = str(line.source_warehouse_id) if line.source_warehouse_id else None
        dest_wh = line.destination_warehouse_id
        condition = getattr(line, "picked_condition", None) or "good"
        # Import consumed by picked qty (falls back to expected when picked is 0).
        remaining = int(line.quantity_picked or 0) or int(line.quantity_expected or 0)
        if remaining <= 0:
            continue

        def _take(same_wh: bool) -> None:
            nonlocal remaining
            for entry in pool:
                alloc_id, alloc_wh, avail = entry
                is_same = (alloc_wh == source_wh)
                if same_wh != is_same or avail <= 0 or remaining <= 0:
                    continue
                take = min(remaining, avail)
                chunks.append({
                    "product_id": str(line.product_id),
                    "source_warehouse_id": source_wh,
                    "destination_warehouse_id": dest_wh,
                    "picked_condition": condition,
                    "quantity": take,
                    "spo_allocation_id": alloc_id,
                })
                remaining -= take
                entry[2] = avail - take

        _take(same_wh=True)   # first pass: allocation warehouse == line warehouse
        _take(same_wh=False)  # second pass: any other warehouse

        if remaining > 0:
            # No allocation left to cover this — recreate as a NULL line (unchanged).
            chunks.append({
                "product_id": str(line.product_id),
                "source_warehouse_id": source_wh,
                "destination_warehouse_id": dest_wh,
                "picked_condition": condition,
                "quantity": remaining,
                "spo_allocation_id": None,
            })
            unlinked_qty += remaining

    return chunks, unlinked_qty


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")
    parser.add_argument("--grn", action="append", default=[],
                        help="Limit to this GRN picking_number (repeatable).")
    parser.add_argument("--include-unapproved", action="store_true",
                        help="Also process non-approved GRNs (default: approved only).")
    args = parser.parse_args()

    db = SessionLocal()
    proc = PickingHeaderService(db)

    headers_q = db.query(PickingHeader).filter(
        PickingHeader.picking_type == "goods_received",
        PickingHeader.spo_number.isnot(None),
    )
    if args.grn:
        headers_q = headers_q.filter(PickingHeader.picking_number.in_(args.grn))
    headers = headers_q.order_by(PickingHeader.created_at.asc()).all()

    total_relinked_lines = 0
    total_relinked_qty = 0
    total_still_unlinked_qty = 0
    affected_spo_numbers: set = set()
    skipped_unapproved = 0
    grns_touched = 0

    for header in headers:
        if header.picking_status != "approved" and not args.include_unapproved:
            # Count only GRNs that actually have unlinked lines, to keep the log honest.
            has_null = db.query(PickingLine.id).filter(
                PickingLine.picking_header_id == header.id,
                PickingLine.spo_allocation_id.is_(None),
            ).first()
            if has_null:
                skipped_unapproved += 1
            continue

        spo_key = _spo_match_key(header.spo_number)
        if not spo_key:
            continue

        # Unlinked lines for this GRN, grouped by product.
        null_lines = db.query(PickingLine).filter(
            PickingLine.picking_header_id == header.id,
            PickingLine.spo_allocation_id.is_(None),
        ).all()
        if not null_lines:
            continue

        by_product: Dict[str, List[PickingLine]] = defaultdict(list)
        for l in null_lines:
            if l.product_id:
                by_product[str(l.product_id)].append(l)

        header_plan: List[str] = []

        for product_id, lines in by_product.items():
            # Allocation pool for this product under the strong SPO key.
            allocs = db.query(SPOAllocation).filter(
                SPOAllocation.product_id == product_id,
                SPOAllocation.spo_number.isnot(None),
            ).order_by(SPOAllocation.created_at.asc()).all()
            matched = [a for a in allocs if _spo_match_key(a.spo_number) == spo_key]
            pool: List[List[Any]] = []
            for a in matched:
                received = proc.compute_received_for_allocation(str(a.id))
                available = int(a.allocated_quantity or 0) - int(received)
                if available > 0:
                    pool.append([str(a.id), str(a.warehouse_id) if a.warehouse_id else None, available])

            if not pool:
                # Genuinely nothing to link against (no allocation, or all consumed).
                continue

            chunks, unlinked = _fifo_chunks(lines, pool)
            linked_chunks = [c for c in chunks if c["spo_allocation_id"] is not None]
            if not linked_chunks:
                continue

            linked_qty = sum(c["quantity"] for c in linked_chunks)
            total_relinked_lines += len(linked_chunks)
            total_relinked_qty += linked_qty
            total_still_unlinked_qty += unlinked
            affected_spo_numbers.add(header.spo_number)
            header_plan.append(
                f"    product {product_id}: {len(lines)} null line(s) -> "
                f"{len(linked_chunks)} linked ({linked_qty} qty)"
                + (f", {unlinked} qty still unlinked" if unlinked else "")
            )

            if not args.dry_run:
                # Replace the unlinked lines with the FIFO chunks.
                for l in lines:
                    db.delete(l)
                db.flush()
                for c in chunks:
                    db.add(PickingLine(
                        picking_header_id=header.id,
                        product_id=c["product_id"],
                        source_warehouse_id=c["source_warehouse_id"],
                        destination_warehouse_id=c["destination_warehouse_id"],
                        quantity_expected=c["quantity"],
                        quantity_picked=c["quantity"],
                        spo_allocation_id=c["spo_allocation_id"],
                        picked_condition=c["picked_condition"],
                    ))
                db.flush()

        if header_plan:
            grns_touched += 1
            print(f"[{header.picking_number}] status={header.picking_status} spo={header.spo_number}")
            for line in header_plan:
                print(line)

    if not args.dry_run:
        # Refresh stored quantity_received / receipt_status + shipment line statuses.
        for spo_number in sorted(affected_spo_numbers):
            proc.sync_received_for_spo_number(spo_number)
        db.commit()

    print("\n=== summary ===")
    print(f"mode:                 {'DRY-RUN (no writes)' if args.dry_run else 'APPLIED'}")
    print(f"GRNs touched:         {grns_touched}")
    print(f"lines relinked:       {total_relinked_lines}")
    print(f"qty relinked:         {total_relinked_qty}")
    print(f"qty still unlinked:   {total_still_unlinked_qty}")
    print(f"SPO numbers resynced: {len(affected_spo_numbers)}")
    if skipped_unapproved:
        print(f"unapproved GRNs skipped (have null lines): {skipped_unapproved} "
              f"(use --include-unapproved to process)")

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
