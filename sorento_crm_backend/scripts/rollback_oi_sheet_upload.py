#!/usr/bin/env python3
"""Take ONE order inquiry sheet upload back out: its rows, their links, their claims.

WHY THIS EXISTS
----------------
The order inquiry sheet is a migration tool (`PLAN-scm-oi-sheet-migration.md`): every row it
reads raises an order inquiry row against a real sales order line and pairs it to the
purchase or shipping order AutoCount states. When the pairing rule itself was wrong - as it
was for the 14 Sep 2026 upload, which paired through a poisoned August claim extract instead
of AutoCount's own line reference (`PLAN-scm-oi-sheet-pairing-repair.md`, section 2.4) - the
whole upload has to come back out before the file can be uploaded again. Re-uploading on top
raises nothing: D2 leaves a line that already carries a row exactly as it is.

WHAT IT REMOVES
----------------
Every `order_inquiry_rows` row whose `note` starts with the stamp the importer writes,
`"Migrated from order inquiry sheet <file name>"` (`_MIGRATION_STAMP`, imported rather than
retyped so the two cannot drift), and with them:

* their `order_inquiry_links`, and every `scm.order_link_claim` a deleted link's `claim_id`
  names - the audit claim `ProjectOrderInquiryService._write_link` wrote beside that link and
  nothing else. A claim another feed made is keyed on the same numbers but is not named by
  any of these links, so it stays;
* any `order_inquiries` header the deletion leaves with zero rows, under the SAME predicate
  `scripts/delete_empty_order_inquiries.py` already applies (imported from it) - a header
  with nothing on it burns an OI number and leaves a dangling "Order inquiries" link on the
  sales order list. A header still carrying another upload's rows stays.

Deliberately NOT removed: the sales order header stamps (`demand_origin`, the project label)
and the planning mirrors the adoption created. Both are harmless where they are, and the
re-upload rewrites them.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the DEFAULT: without `--apply` the deletions are performed inside a SAVEPOINT
and rolled straight back, so the counts printed are the counts the real run produces rather
than a second query that could disagree with the delete. Re-runnable: a row this script
already deleted no longer carries the stamp, so a second run reports zero.

`run()` does NOT commit and does NOT roll back the caller's transaction - the caller owns it,
exactly as `scripts/delete_empty_order_inquiries.py::run` does.

Run from sorento_crm_backend/:
    venv/bin/python scripts/rollback_oi_sheet_upload.py --file-name "JAN - DEC 2026 ORDERabc.xlsx"
    venv/bin/python scripts/rollback_oi_sheet_upload.py --file-name "JAN - DEC 2026 ORDERabc.xlsx" --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.models.project_so import OrderInquiry, OrderInquiryLink, OrderInquiryRow
from app.models.scm import OrderLinkClaim
from app.services.project_order_inquiry_import_service import _MIGRATION_STAMP
from scripts.delete_empty_order_inquiries import _no_rows_clause, _no_task_clause

#: The four counts every run answers with, in the order they are performed.
COUNT_KEYS = ("rows", "links", "claims", "inquiries")


def _stamp(file_name: str) -> str:
    """The exact prefix `_note_for` writes for this upload."""
    return f"{_MIGRATION_STAMP} {file_name}".strip()


def rows_of(db: Session, file_name: str) -> List[OrderInquiryRow]:
    """Every row this file raised.

    `startswith(..., autoescape=True)` because a file name is the operator's own text and
    `%` or `_` in it would otherwise be read as LIKE wildcards and match other uploads.
    """
    return (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.note.startswith(_stamp(file_name), autoescape=True))
        .all()
    )


def _remove(db: Session, file_name: str) -> Dict[str, int]:
    """Links, their claims, the rows, then the headers left empty. Counts as it goes."""
    rows = rows_of(db, file_name)
    counts = {key: 0 for key in COUNT_KEYS}
    if not rows:
        return counts

    row_ids = [str(row.id) for row in rows]
    inquiry_ids = sorted({str(row.order_inquiry_id) for row in rows if row.order_inquiry_id})

    links = (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id.in_(row_ids)).all()
    )
    claim_ids = sorted({str(link.claim_id) for link in links if link.claim_id})
    counts["links"] = (
        db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.row_id.in_(row_ids))
        .delete(synchronize_session=False)
    )
    if claim_ids:
        # After the links, so nothing still points at a claim as its evidence.
        counts["claims"] = (
            db.query(OrderLinkClaim)
            .filter(OrderLinkClaim.id.in_(claim_ids))
            .delete(synchronize_session=False)
        )
    counts["rows"] = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.id.in_(row_ids))
        .delete(synchronize_session=False)
    )
    db.flush()

    if inquiry_ids:
        # Only the headers THIS upload may have emptied, and only if the sibling script's
        # own predicates still hold: zero rows, no purchasing task, standard demand.
        counts["inquiries"] = (
            db.query(OrderInquiry)
            .filter(
                OrderInquiry.id.in_(inquiry_ids),
                OrderInquiry.amendment_id.is_(None),
                _no_rows_clause(),
                _no_task_clause(),
            )
            .delete(synchronize_session=False)
        )
    db.flush()
    return counts


def run(db: Session, file_name: str, apply: bool = False) -> Dict[str, int]:
    """Remove (or, without `apply`, merely count) one upload. The CALLER commits.

    A dry run performs the very same deletions inside a SAVEPOINT and rolls back to it, so
    the numbers it prints cannot differ from the numbers `--apply` produces. The caller's own
    transaction is untouched either way: `run` neither commits nor rolls back.
    """
    if apply:
        return _remove(db, file_name)
    nested = db.begin_nested()
    try:
        return _remove(db, file_name)
    finally:
        nested.rollback()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file-name", type=str, required=True,
        help='The upload\'s file name exactly as it was stamped, e.g. "JAN - DEC 2026 ORDERabc.xlsx"',
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Perform the deletions. Without this the script only reports.",
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
    # is fail-closed and would find no rows at all. `None` is the sanctioned system /
    # all-companies scope, and the stamp already names exactly one upload.
    set_company_scope(db, None)

    try:
        print(
            f"Order inquiry sheet upload {args.file_name!r} "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        counts = run(db, args.file_name, apply)
        if apply:
            db.commit()
        else:
            db.rollback()

        print("\n=== summary ===")
        print(f"mode:               {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"rows removed:       {counts['rows']}")
        print(f"links removed:      {counts['links']}")
        print(f"claims removed:     {counts['claims']}")
        print(f"empty headers:      {counts['inquiries']}")
        if not apply and counts["rows"]:
            print("\nRe-run with --apply to remove these rows.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
