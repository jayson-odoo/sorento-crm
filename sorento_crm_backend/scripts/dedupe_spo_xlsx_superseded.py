#!/usr/bin/env python3
"""Dedupe the shipping orders the first ESB push DUPLICATED (D29,
spo-xlsx-supersede).

WHAT IT DOES
------------
Between the ESB's Shipping order task going live and D25 shipping, every
xlsx-loaded shipping order was APPENDED to rather than replaced on its first
push: the xlsx-era rows (`source_ref IS NULL`, closed by a Sorento GRN)
stayed, and AutoCount's own line-set landed beside them as fresh open rows.
Reorder planning then counted those open rows as incoming supply for goods
already in the warehouse (3,294 documents on production).

This script applies the rule the ingest now applies at push time, once, to
the rows already in the database: for every `spo_number` in the company that
holds BOTH ref-less rows AND ref rows, the existing ref rows (in
`spo_line_number` order) ARE the incoming line-set, so

- the xlsx-era receipt is carried onto them per `(product_id,
  upper(location_code))` group, in line order, each line up to its own
  allocated quantity and any remainder onto the last (D26);
- whatever pointed at a superseded xlsx-era row - a GRN pick, an order-link
  claim, an order-inquiry placement - is repointed onto the group's FIRST
  line, and the xlsx-era row is then deleted (D27);
- a ref-less group AutoCount named no line for is left exactly as it is: the
  push already closed it, and there is nothing to supersede it with.

ONE ALGORITHM, NOT A SECOND COPY
--------------------------------
The plan comes from `shipping_order_rules.plan_xlsx_supersede`, the same pure
function `ShippingOrderIngestService._supersede_xlsx_rows` runs at push time,
and the link move from the same `repoint_allocation_dependants`. Only the
writing differs: the push CREATES the incoming lines, this script UPDATES the
ref rows a push already appended.

SAFETY / IDEMPOTENCY
--------------------
- `--dry-run` (the default) computes and prints the whole plan, writes
  nothing, and never leaves the session dirty.
- One commit per document, so an interrupted run leaves whole documents done
  and the rest untouched.
- Re-running is a no-op: a document with no ref-less row left is not selected
  at all, and a ref-less group with no counterpart yields no group to apply.
- `--since` narrows to the documents an ESB push actually touched in the
  incident window (a document qualifies when ANY of its ref rows was created
  at or after the timestamp; its whole ref line-set is then the incoming
  side, since a document's lines arrive together).

USAGE
-----
    python scripts/dedupe_spo_xlsx_superseded.py --company SORENTO --dry-run
    python scripts/dedupe_spo_xlsx_superseded.py --company SORENTO \
        --since 2026-09-06T05:15:00 --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.procurement import SPOAllocation
from app.services.rules.shipping_order_rules import (
    carried_received,
    plan_xlsx_supersede,
    repoint_allocation_dependants,
)
from app.services.shipping_order_ingest_service import (
    LINE_CLOSED,
    LINE_OPEN,
    RECEIPT_FULLY_RECEIVED,
    RECEIPT_PENDING,
)

BATCH_SIZE = 200


def _document_numbers(db, company_id: str, after: Optional[str]) -> list[str]:
    """One keyset page of `spo_number`s holding at least one ref-less row.

    Keyset on `spo_number` rather than `Session.query(...).yield_per(...)`:
    this loop commits per document, and a `yield_per` server-side cursor does
    not survive the first commit (LESSONS-LEARNT).
    """
    query = (
        db.query(SPOAllocation.spo_number)
        .filter(
            SPOAllocation.company_id == company_id,
            SPOAllocation.spo_number.isnot(None),
            SPOAllocation.source_ref.is_(None),
        )
        .distinct()
    )
    if after is not None:
        query = query.filter(SPOAllocation.spo_number > after)
    return [row[0] for row in query.order_by(SPOAllocation.spo_number).limit(BATCH_SIZE).all()]


def _incoming_values(row: SPOAllocation) -> dict[str, Any]:
    """One already-appended ref row expressed as the "incoming" line it was.

    The same keys `ShippingOrderIngestService._line_values` produces for the
    planner to read, with `line_number` standing in for AutoCount's Seq - the
    order the push itself wrote them in.
    """
    return {
        "product_id": row.product_id,
        "location_code": row.location_code,
        "warehouse_id": row.warehouse_id,
        "allocated_quantity": int(row.allocated_quantity or 0),
        "quantity_received": int(row.quantity_received or 0),
        "inbound_shipment_id": row.inbound_shipment_id,
        "line_number": row.spo_line_number,
    }


def _apply_document(
    db, company_id: str, spo_number: str, since: Optional[datetime], dry_run: bool
) -> Optional[dict[str, int]]:
    """One document, or `None` when there is nothing to do for it.

    Returns `{rows_removed, lines_touched, links_moved, groups_kept}`.
    """
    rows = (
        db.query(SPOAllocation)
        .filter(
            SPOAllocation.company_id == company_id,
            SPOAllocation.spo_number == spo_number,
        )
        .order_by(SPOAllocation.spo_line_number, SPOAllocation.id)
        .all()
    )
    refless = [row for row in rows if not row.source_ref]
    refs = [row for row in rows if row.source_ref]
    if not refless or not refs:
        return None
    if since is not None and not any(
        row.created_at is not None and row.created_at >= since for row in refs
    ):
        return None

    plan = plan_xlsx_supersede([_incoming_values(row) for row in refs], refless)
    if not plan.groups:
        # Every ref-less row of this document is a group AutoCount names no
        # line for - kept by D27, so this document is already settled.
        return None

    by_id = {str(row.id): row for row in refless}
    counts = {
        "rows_removed": 0,
        "lines_touched": 0,
        "links_moved": 0,
        "groups_kept": len(plan.kept_row_ids),
    }

    for group in plan.groups:
        target: Optional[SPOAllocation] = None
        for line_plan in group.lines:
            row = refs[line_plan.index]
            allocated = int(row.allocated_quantity or 0)
            received, closed = carried_received(
                allocated, row.quantity_received, line_plan.carried_received
            )
            if not dry_run:
                row.quantity_received = received
                row.line_status = LINE_CLOSED if closed else LINE_OPEN
                row.receipt_status = RECEIPT_FULLY_RECEIVED if closed else RECEIPT_PENDING
                if not row.inbound_shipment_id and line_plan.inbound_shipment_id:
                    row.inbound_shipment_id = line_plan.inbound_shipment_id
            counts["lines_touched"] += 1
            if target is None:
                target = row
        removing = [by_id[row_id] for row_id in group.superseded_row_ids if row_id in by_id]
        if target is not None:
            counts["links_moved"] += repoint_allocation_dependants(
                db,
                [str(row.id) for row in removing],
                str(target.id),
                company_id=company_id,
                dry_run=dry_run,
            )
        if not dry_run:
            for row in removing:
                db.delete(row)
        counts["rows_removed"] += len(removing)

    if not dry_run:
        db.commit()
    return counts


def run(
    db, company_id: str, since: Optional[datetime] = None, dry_run: bool = True
) -> dict[str, int]:
    """Every affected document of ONE company. Prints one line per document.

    `dry_run` defaults to `True` so a caller that forgets the argument
    previews rather than writes.
    """
    summary = {
        "documents": 0,
        "rows_removed": 0,
        "lines_touched": 0,
        "links_moved": 0,
        "groups_kept": 0,
    }
    with company_scope(db, frozenset({company_id})):
        after: Optional[str] = None
        while True:
            numbers = _document_numbers(db, company_id, after)
            if not numbers:
                break
            for spo_number in numbers:
                counts = _apply_document(db, company_id, spo_number, since, dry_run)
                if counts is None:
                    continue
                summary["documents"] += 1
                for key, value in counts.items():
                    summary[key] += value
                print(
                    f"  {spo_number}: xlsx rows removed {counts['rows_removed']}, "
                    f"lines touched {counts['lines_touched']}, "
                    f"links moved {counts['links_moved']}, "
                    f"groups kept {counts['groups_kept']}"
                )
            after = numbers[-1]
            if len(numbers) < BATCH_SIZE:
                break
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", required=True, help="Company CODE to dedupe")
    parser.add_argument(
        "--since",
        default=None,
        help="Only documents whose ESB rows were created at or after this ISO timestamp",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Print the plan, write nothing (the default)"
    )
    mode.add_argument("--apply", action="store_true", help="Write the plan")
    args = parser.parse_args()

    dry_run = not args.apply
    since = datetime.fromisoformat(args.since) if args.since else None

    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.code == args.company).first()
        if company is None:
            print(f"no company with code {args.company!r}")
            return 1
        print(f"=== {args.company} ({'DRY-RUN (no writes)' if dry_run else 'APPLYING'}) ===")
        summary = run(db, str(company.id), since=since, dry_run=dry_run)
        print("\n=== summary ===")
        print(f"mode:                {'DRY-RUN (no writes)' if dry_run else 'APPLIED'}")
        print(f"documents:           {summary['documents']}")
        print(f"xlsx rows removed:   {summary['rows_removed']}")
        print(f"lines touched:       {summary['lines_touched']}")
        print(f"links moved:         {summary['links_moved']}")
        print(f"ref-less groups kept: {summary['groups_kept']}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
