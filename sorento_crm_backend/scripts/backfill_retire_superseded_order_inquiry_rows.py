#!/usr/bin/env python3
"""Retire the provisional sales orders that were superseded before reconciliation shipped.

WHY THIS EXISTS
---------------
`project_so_ingest_service._reconcile_core_order` (ADR 0010, AC-F2/F3/F5) makes the Order
Inquiry sheet's provisional `sales_orders` row and AutoCount's real-numbered one name ONE
piece of demand. It runs at ingest time only. Every project whose AutoCount document was
ingested BEFORE that shipped therefore still has BOTH rows open, and `scm.committed_v`
counts the same demand twice, permanently: nothing re-runs the ingest for them.

WHAT IT DOES
------------
Finds the pairs the reconciliation would have merged, and merges them now:

* a `sales_orders` row the sheet created (`demand_origin = 'scm_order_inquiry'`), still
  `open`, whose number is some project sales order's `provisional_ref`,
* that project sales order has an `autocount_doc_no` (AutoCount named the document), and
* a DIFFERENT core row holds that `autocount_doc_no` - the outstanding book got there first.

For each pair it does exactly what the merge branch does, by CALLING it rather than
restating it: `ProjectSOIngestService._retire` closes the header and its lines and stamps
the "Retired: superseded by <doc no>" note, `_repoint_claims` moves the still-unresolved
SO<->PO claims onto the real number, and `so_id` is repointed under the service's own guard
(only when unset or still on the row being retired - a link a person made is left alone).

COMPANY ISOLATION
-----------------
The session runs all-companies so the real-numbered row is visible wherever it lives, and
each pair is then checked: a pair whose two rows sit in DIFFERENT companies is REPORTED and
SKIPPED, never merged. Same rule as the reconciliation itself - a double count is a
reporting error, a cross-company link is a breach.

SAFETY / IDEMPOTENCY
--------------------
JOIN-based and re-runnable per the repo's backfill doctrine: the match is "the provisional
row is still open while a real-numbered row exists", so a row this script already retired no
longer matches and a second run reports nothing. It corrects a prior partial run rather than
depending on one never having happened.

`--dry-run` is the DEFAULT. Nothing is written without `--apply`.

Run from sorento_crm_backend/:
    venv/bin/python scripts/backfill_retire_superseded_order_inquiry_rows.py
    venv/bin/python scripts/backfill_retire_superseded_order_inquiry_rows.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session, aliased

from app.models.order import SalesOrder
from app.models.project_so import ProjectSalesOrder
from app.models.projects import Project
from app.services.project_so_ingest_service import (
    DEMAND_ORIGIN_ORDER_INQUIRY,
    ProjectSOIngestService,
)

#: The state a provisional row must still be in to be worth retiring. Anything else was moved
#: on by somebody, and a backfill is not the place to overrule them.
LIVE_ORDER_STATUS = "open"


@dataclass
class SupersededPair:
    """One provisional row and the real-numbered row that superseded it."""

    project_sales_order_id: str
    project_label: str
    provisional_order_id: str
    provisional_number: str
    real_order_id: str
    real_number: str
    provisional_company_id: Optional[str]
    real_company_id: Optional[str]
    relinks_so_id: bool

    @property
    def cross_company(self) -> bool:
        if self.provisional_company_id is None or self.real_company_id is None:
            return False
        return str(self.provisional_company_id) != str(self.real_company_id)

    def describe(self) -> str:
        line = (
            f"{self.provisional_number} -> {self.real_number}  "
            f"[{self.project_label}]"
        )
        if self.cross_company:
            return (
                f"{line}  SKIPPED: provisional in company "
                f"{self.provisional_company_id}, real number in {self.real_company_id}"
            )
        return line + ("  (so_id repointed)" if self.relinks_so_id else "  (so_id left as is)")


def find_superseded_pairs(db: Session) -> List[SupersededPair]:
    """Every pair the reconciliation would have merged, had it existed at ingest time."""
    provisional = aliased(SalesOrder)
    real = aliased(SalesOrder)

    rows = (
        db.query(ProjectSalesOrder, provisional, real, Project)
        .join(provisional, provisional.so_number == ProjectSalesOrder.provisional_ref)
        .join(real, real.so_number == ProjectSalesOrder.autocount_doc_no)
        .outerjoin(Project, Project.id == ProjectSalesOrder.project_id)
        .filter(
            ProjectSalesOrder.autocount_doc_no.isnot(None),
            # Only rows the sheet created may be retired (AC-F5).
            provisional.demand_origin == DEMAND_ORIGIN_ORDER_INQUIRY,
            provisional.status == LIVE_ORDER_STATUS,
            provisional.id != real.id,
        )
        .order_by(ProjectSalesOrder.provisional_ref.asc())
        .all()
    )

    pairs: List[SupersededPair] = []
    for order, provisional_row, real_row, project in rows:
        pairs.append(
            SupersededPair(
                project_sales_order_id=str(order.id),
                project_label=(project.title if project is not None else None)
                or (project.project_code if project is not None else None)
                or "unnamed project",
                provisional_order_id=str(provisional_row.id),
                provisional_number=provisional_row.so_number,
                real_order_id=str(real_row.id),
                real_number=real_row.so_number,
                provisional_company_id=provisional_row.company_id,
                real_company_id=real_row.company_id,
                # The service's own guard: a link somebody put on a third row stays there.
                relinks_so_id=order.so_id is None or str(order.so_id) == str(provisional_row.id),
            )
        )
    return pairs


def apply_pair(db: Session, pair: SupersededPair) -> int:
    """Merge one pair, through the service rather than beside it. Returns claims moved."""
    order = (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == pair.project_sales_order_id)
        .one()
    )
    provisional = (
        db.query(SalesOrder).filter(SalesOrder.id == pair.provisional_order_id).one()
    )

    service = ProjectSOIngestService(db)
    service._retire(provisional, pair.real_number)
    # The retired row keeps its number, so a claim still waiting would resolve onto a line
    # that has just been closed. Resolved claims stay where somebody put them.
    claims_moved = service._repoint_claims(order, pair.real_number, unresolved_only=True)

    if pair.relinks_so_id:
        order.so_id = pair.real_order_id
    db.flush()
    return claims_moved


def run(db: Session, *, apply: bool) -> Dict[str, Any]:
    """Report (and optionally perform) every merge. The caller commits."""
    pairs = find_superseded_pairs(db)
    merged: List[SupersededPair] = []
    skipped: List[SupersededPair] = []
    claims_moved = 0

    for pair in pairs:
        print(f"  {pair.describe()}")
        if pair.cross_company:
            skipped.append(pair)
            continue
        merged.append(pair)
        if apply:
            claims_moved += apply_pair(db, pair) or 0

    return {
        "examined": len(pairs),
        "merged": len(merged),
        "skipped_cross_company": len(skipped),
        "so_id_repointed": sum(1 for p in merged if p.relinks_so_id),
        "claims_moved": claims_moved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the changes. Without this the script only reports.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only (the default; accepted so a run can say so out loud).",
    )
    args = parser.parse_args()
    apply = args.apply and not args.dry_run

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    # A script has no request and no principal, so the session scope would be UNSET, which
    # is fail-closed and would return no rows at all. `None` is the sanctioned system /
    # all-companies scope; every pair is company-checked individually below.
    set_company_scope(db, None)

    try:
        print(
            "Provisional rows superseded by an AutoCount number "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        summary = run(db, apply=apply)
        if apply:
            db.commit()

        print("\n=== summary ===")
        print(f"mode:                  {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"pairs examined:        {summary['examined']}")
        print(f"pairs merged:          {summary['merged']}")
        print(f"so_id repointed:       {summary['so_id_repointed']}")
        print(f"link claims moved:     {summary['claims_moved']}")
        print(f"skipped, cross-company:{summary['skipped_cross_company']}")
        if not apply and summary["merged"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
