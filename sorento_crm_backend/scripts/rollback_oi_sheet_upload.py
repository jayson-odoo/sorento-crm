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

* their `order_inquiry_links`, and the `scm.order_link_claim` rows those links leaned on,
  through `order_link_service.free_claim_if_orphaned` - the SAME guard an Untag uses. A link
  does not necessarily own its claim: `claim_placed_on_po` returns whatever claim already sat
  at the identity `(company, so_number, po_number, item_code)`, which on the 14 Sep prod copy
  is often a pre-existing `autocount` or August `po_history` row, and one claim is shared by
  up to five links. So a claim goes only when its `source` is `order_inquiry` AND no
  surviving link still points at it; anything else stays, and the count reports what actually
  went rather than what was named;
* any `order_inquiries` header the deletion leaves with zero rows, under the SAME predicate
  `scripts/delete_empty_order_inquiries.py` already applies (imported from it) - a header
  with nothing on it burns an OI number and leaves a dangling "Order inquiries" link on the
  sales order list. A header still carrying another upload's rows stays.

Deliberately NOT restored: the sales order header stamps (`demand_origin`, the project
label) and the planning mirrors the adoption created - both harmless where they are, and the
re-upload rewrites them. Two consequences worth knowing before running it:

* `order_inquiry_rows.bundled_with_row_id` is `ON DELETE SET NULL`, so a SURVIVING row that
  was bundled with a removed one keeps its own quantity but loses the pointer saying which
  row it travelled with. Nothing re-derives that; the re-upload does not restore it.
* an emptied header is DELETED even when it pre-dated this upload (it is empty only because
  the upload's rows were all it held), so the re-upload mints a NEW OI number for that sales
  order. The old number is not reused.

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
from typing import Dict, List, Sequence

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.project_so import OrderInquiry, OrderInquiryLink, OrderInquiryRow
from app.models.scm import OrderLinkClaim
from app.services.project_order_inquiry_import_service import _MIGRATION_STAMP
from app.services.scm import order_link_service
from scripts.delete_empty_order_inquiries import _no_rows_clause, _no_task_clause

#: The four counts every run answers with, in the order they are performed.
COUNT_KEYS = ("rows", "links", "claims", "inquiries")


#: Refused rather than run. A blank name strips back to the bare stamp, which every migrated
#: row ever raised starts with - including the rows an older upload raised with no file name
#: at all - so the run would take out the whole migration instead of one file.
BLANK_NAME = (
    "a file name is required: an empty one names every migrated row ever raised, not one "
    "upload"
)


def _stamp(file_name: str) -> str:
    """The exact prefix `_note_for` writes for this upload."""
    return f"{_MIGRATION_STAMP} {file_name.strip()}"


def rows_of(db: Session, file_name: str) -> List[OrderInquiryRow]:
    """Every row this file raised, and no row of any other.

    `_note_for` writes the stamp alone, or the stamp then `"; <remark>"`, so those are the
    only two shapes this may match. A bare `startswith(stamp)` would additionally match every
    LONGER file name beginning with this one - `--file-name "JAN"` would take out
    `JAN - DEC 2026 ORDER.xlsx` - which is the wrong kind of surprise for a delete.

    `autoescape=True` because a file name is the operator's own text: `%` or `_` in it would
    otherwise be read as LIKE wildcards.
    """
    if not (file_name or "").strip():
        raise ValueError(BLANK_NAME)
    stamp = _stamp(file_name)
    return (
        db.query(OrderInquiryRow)
        .filter(
            or_(
                OrderInquiryRow.note == stamp,
                OrderInquiryRow.note.startswith(f"{stamp};", autoescape=True),
            )
        )
        .all()
    )


def _companies_of(db: Session, rows: Sequence[OrderInquiryRow]) -> List[tuple]:
    """`(company code, company id, row count)` per company, most rows first.

    Printed before anything is deleted, and the reason a cross-company run has to be asked
    for out loud: the scope this script runs under is the system scope (`None`, all
    companies), which is what lets one stamp be found at all, and it is also what would let
    one company's operator take another company's rows out without noticing.
    """
    counted: Dict[str, int] = {}
    for row in rows:
        counted[str(row.company_id)] = counted.get(str(row.company_id), 0) + 1
    names = {
        str(company_id): code
        for company_id, code in db.query(Company.id, Company.code).filter(
            Company.id.in_(sorted(counted))
        )
    }
    return sorted(
        ((names.get(company_id, "(unknown)"), company_id, count)
         for company_id, count in counted.items()),
        key=lambda entry: (-entry[2], entry[0]),
    )


def _remove(db: Session, file_name: str, all_companies: bool) -> Dict[str, int]:
    """Claims freed, then links, then the rows, then the headers left empty."""
    rows = rows_of(db, file_name)
    counts = {key: 0 for key in COUNT_KEYS}
    if not rows:
        print("  no rows carry that stamp")
        return counts

    companies = _companies_of(db, rows)
    for code, company_id, count in companies:
        print(f"  {code} ({company_id}): {count} rows")
    if len(companies) > 1 and not all_companies:
        raise ValueError(
            f"these rows span {len(companies)} companies "
            f"({', '.join(code for code, _id, _n in companies)}): re-run with "
            f"--all-companies if that is really what the upload was"
        )

    row_ids = [str(row.id) for row in rows]
    inquiry_ids = sorted({str(row.order_inquiry_id) for row in rows if row.order_inquiry_id})

    links = (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id.in_(row_ids)).all()
    )
    link_ids = [str(link.id) for link in links]
    claim_ids = sorted({str(link.claim_id) for link in links if link.claim_id})
    for claim_id in claim_ids:
        # The Untag guard, not a bulk delete: a link's `claim_id` is whatever claim already
        # sat at that identity, so it is often another feed's `autocount` / `po_history` row
        # - and the FK is ON DELETE SET NULL, which would have made taking one down silent.
        # This frees a claim only when it is ours (`source = 'order_inquiry'`) and no link
        # outside this pass still leans on it.
        order_link_service.free_claim_if_orphaned(db, claim_id, excluding=link_ids)
    db.flush()
    if claim_ids:
        # What actually went, not what was named.
        counts["claims"] = len(claim_ids) - (
            db.query(OrderLinkClaim).filter(OrderLinkClaim.id.in_(claim_ids)).count()
        )
    counts["links"] = (
        db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.row_id.in_(row_ids))
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


def run(
    db: Session, file_name: str, apply: bool = False, all_companies: bool = False
) -> Dict[str, int]:
    """Remove (or, without `apply`, merely count) one upload. The CALLER commits.

    A dry run performs the very same deletions inside a SAVEPOINT and rolls back to it, so
    the numbers it prints cannot differ from the numbers `--apply` produces. The caller's own
    transaction is untouched either way: `run` neither commits nor rolls back.

    Raises `ValueError` for a blank file name, and for rows spanning more than one company
    unless `all_companies` says that is deliberate.
    """
    if not (file_name or "").strip():
        raise ValueError(BLANK_NAME)
    if apply:
        return _remove(db, file_name, all_companies)
    nested = db.begin_nested()
    try:
        return _remove(db, file_name, all_companies)
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
    parser.add_argument(
        "--all-companies", action="store_true",
        help="Allow a run whose rows belong to more than one company. Refused otherwise.",
    )
    args = parser.parse_args()
    apply = args.apply and not args.dry_run
    if not (args.file_name or "").strip():
        # Before a session is opened, so a blank name cannot even reach a query.
        print(BLANK_NAME)
        return 2

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
        counts = run(db, args.file_name, apply, args.all_companies)
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
