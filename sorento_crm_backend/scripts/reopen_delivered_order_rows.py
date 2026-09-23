#!/usr/bin/env python3
"""One-off: reopen an importer-closed ORDER / ORDER_BACK row the pre-R1 history-close
rule wrongly stamped `actioned` because its core line read delivered or closed.

`PLAN-oi-order-rows-uncapped.md` S4 (owner ruling R1, 23 Sep 2026, SO421985). Before this
lane, `_close_history` (`project_order_inquiry_import_service.py`) closed ANY raised row
whose core line was no longer "open demand" - delivered in full, closed, or covered. R1
retired that: a raised row is owed until it is LINKED, whatever the line's own delivered
column says, so only a row against a CANCELLED line is history the moment it is uploaded
(R2). S1/S3 of this lane stop it happening on a NEW upload; this script repairs what
already shipped that way - SO421985's own shape, and everything like it.

WHAT IT DOES
------------
Scans `projects.order_inquiry_rows` directly (no sheet to re-read - unlike its sibling
`backfill_order_back_rows.py`, which repairs a DIFFERENT bug off a re-read book) for a
row that is:

* `verb IN ('ORDER', 'ORDER_BACK')`, `state = 'actioned'`;
* still owed - its own quantity less every `order_inquiry_links` quantity against it is
  greater than zero (a fully linked row is genuinely settled, reopening it would be
  wrong regardless of why it closed);
* IMPORTER-closed, not a person's own later action - the SAME two-signal test
  `backfill_order_back_rows.py::_is_importer_closed` uses (R3/R4 precedent, reused here
  rather than restated): the CLOCK (`actioned_at` within 60 seconds of the header's own
  `raised_at`, or of `raised_at + 8h` for the S5a timezone-bug window) together with the
  PRINCIPAL (`actioned_by == order_inquiries.raised_by`);
* against a core line that is NOT cancelled (R2's own boundary: a cancelled line is
  correctly history, a delivered or closed one no longer is);
* delivered at or after `--delivery-from` - the ruling this script's own argument
  answers is R3 (open, 23 Sep 2026): how far back to reopen. Owner options were A (none
  automatic), B (1 Sep 2026 onward, 168 rows / 9,221 units on the 23 Sep prod copy) or C
  (another date); this script takes the argument rather than baking in a choice, so the
  ruling only sets `--delivery-from`, it never runs without one. A row with no delivery
  date at all always counts (unscheduled demand is still demand, the same reading
  `horizon_committed_select_sql` gives it, G2).

A flip sets: `state = 'raised'`, `actioned_by = NULL`, `actioned_at = NULL`, and the
row's own inquiry header `state = 'raised'`.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the DEFAULT and writes nothing: every candidate is read and classified,
and a row is only mutated `if apply`. `--apply` commits once at the end. A second run
over rows this script already flipped reads `state = 'raised'` rather than `'actioned'`,
so they are simply no longer candidates - never a double-flip.

`--delivery-from` is MANDATORY (never a silent full-history run): omitting it exits 2
before touching the database.

Run from sorento_crm_backend/:
    venv/bin/python scripts/reopen_delivered_order_rows.py --delivery-from 2026-09-01
    venv/bin/python scripts/reopen_delivered_order_rows.py --delivery-from 2026-09-01 \\
        --apply --company SRT
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)

# Reused verbatim rather than restated - the two-signal "did the IMPORTER close this, not
# a person" test is subtle enough (the S5a timezone-skew window) that a second copy would
# be one more place to drift from the first (R3/R4 precedent).
from scripts.backfill_order_back_rows import _is_importer_closed


def _company_code(db, company_id: str) -> Optional[str]:
    return db.query(Company.code).filter(Company.id == company_id).scalar()


def run(
    db, *, delivery_from: date, company_code: Optional[str] = None, apply: bool,
) -> List[Dict[str, Any]]:
    """One dict per candidate row: `{so_number, item_code, qty, delivery_date,
    company_code, action}`, `action` one of `reopened` / `skipped_person_actioned` /
    `skipped_cancelled_line` / `skipped_before_from`. A row with nothing left unlinked is
    not a candidate at all and is simply absent - reopening a fully settled row would be
    wrong whatever closed it. `apply` commits once at the end; a dry run writes nothing.
    """
    company_id: Optional[str] = None
    if company_code is not None:
        company_id = db.query(Company.id).filter(Company.code == company_code).scalar()
        if company_id is None:
            raise ValueError(f"no company with code {company_code}")
        company_id = str(company_id)

    query = (
        db.query(OrderInquiryRow, OrderInquiry, SalesOrder, SalesOrderLine)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .join(ProjectSalesOrder, ProjectSalesOrder.id == OrderInquiry.project_sales_order_id)
        .join(SalesOrder, SalesOrder.id == ProjectSalesOrder.so_id)
        # OUTER on the core line: a form-leg row may name no core line at all (or one its
        # own mirror does not carry), and such a row is treated as never cancelled below -
        # there is nothing to say it is.
        .outerjoin(
            ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id
        )
        .outerjoin(
            SalesOrderLine, SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id
        )
        .filter(OrderInquiryRow.verb.in_((IV_ORDER, IV_ORDER_BACK)))
        .filter(OrderInquiryRow.state == INQUIRY_ACTIONED)
    )
    if company_id is not None:
        query = query.filter(SalesOrder.company_id == company_id)

    results: List[Dict[str, Any]] = []
    for row, inquiry, so, core_line in query.order_by(OrderInquiryRow.id.asc()).all():
        linked = (
            db.query(func.coalesce(func.sum(OrderInquiryLink.qty), 0))
            .filter(OrderInquiryLink.row_id == row.id)
            .scalar()
        )
        unlinked = Decimal(str(row.qty or 0)) - Decimal(str(linked or 0))
        if unlinked <= 0:
            # Fully linked already - genuinely settled, not a row this bug touched.
            continue

        common = {
            "so_number": so.so_number,
            "item_code": row.item_code,
            "qty": row.qty,
            "delivery_date": row.delivery_date,
            "company_code": _company_code(db, so.company_id),
        }

        if row.delivery_date is not None and row.delivery_date < delivery_from:
            results.append({**common, "action": "skipped_before_from"})
            continue

        if core_line is not None and core_line.line_status == "cancelled":
            results.append({**common, "action": "skipped_cancelled_line"})
            continue

        if not (
            _is_importer_closed(row.actioned_at, inquiry.raised_at)
            and row.actioned_by == inquiry.raised_by
        ):
            results.append({**common, "action": "skipped_person_actioned"})
            continue

        if apply:
            row.state = INQUIRY_RAISED
            row.actioned_by = None
            row.actioned_at = None
            inquiry.state = INQUIRY_RAISED
            # Flushed so a LATER row in this same run (another sheet, another company)
            # reads this write rather than a stale one - the same reason
            # `backfill_order_back_rows.py` flushes per row.
            db.flush()
        results.append({**common, "action": "reopened"})

    # A dry run mutates nothing above (`if apply:` gates every write), so there is
    # nothing to roll back.
    if apply:
        db.commit()
    return results


def main(argv: Optional[Sequence[str]] = None, db=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--delivery-from", dest="delivery_from", required=True, type=date.fromisoformat,
        help="reopen a candidate delivered on or after this date (YYYY-MM-DD); mandatory "
             "- this script never runs a full-history reopen (AC-OU-10)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the changes; the default is a dry run",
    )
    parser.add_argument(
        "--company", dest="company_code", default=None,
        help="narrow the match to one company code (e.g. SRT); default is every company",
    )
    args = parser.parse_args(argv)
    apply = bool(args.apply)

    owns_db = db is None
    if db is None:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        # A script has no request and no principal, so the session scope would be UNSET
        # (fail-closed, 0 rows) - the same reason `backfill_order_back_rows.py` sets it.
        set_company_scope(db, None)

        print(
            f"Importer-closed ORDER / ORDER_BACK rows delivered on or after "
            f"{args.delivery_from.isoformat()} "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'})"
            f"{f' in company {args.company_code}' if args.company_code else ''}:"
        )
        try:
            results = run(
                db, delivery_from=args.delivery_from, company_code=args.company_code,
                apply=apply,
            )
        except ValueError as exc:
            print(f"\nREFUSING: {exc}")
            db.rollback()
            return 2

        counts: Dict[str, int] = {}
        for entry in results:
            counts[entry["action"]] = counts.get(entry["action"], 0) + 1
            print(
                f"  [{entry['action']}] {entry['company_code'] or '?'} "
                f"SO {entry['so_number']} / {entry['item_code']} "
                f"qty {entry['qty']} @ {entry['delivery_date'] or '(no date)'}"
            )

        print("\n=== summary ===")
        print(f"mode:                      {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"candidates read:           {len(results)}")
        print(f"reopened:                  {counts.get('reopened', 0)}")
        print(f"skipped (before cutoff):   {counts.get('skipped_before_from', 0)}")
        print(f"skipped (cancelled line):  {counts.get('skipped_cancelled_line', 0)}")
        print(f"skipped (person actioned): {counts.get('skipped_person_actioned', 0)}")
        if not apply and counts.get("reopened"):
            print("\nRe-run with --apply to write these changes.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
