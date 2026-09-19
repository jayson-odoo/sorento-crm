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

A header that SURVIVES because another upload's rows are still on it has its `state`
recomputed from what is left (`_refresh_inquiry_states`), which is the only header-level
field derived from the rows.

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)
from app.models.scm import OrderLinkClaim
from app.services.project_order_inquiry_import_service import (
    _LINE_OWN_ROW_VERBS,
    _MIGRATION_STAMP,
)
from app.services.scm import order_link_service
from scripts.delete_empty_order_inquiries import _no_rows_clause, _no_task_clause

#: The four counts every run answers with, in the order they are performed. `kept` /
#: `kept_rows` join them only when a planning trait actually kept a row (`_remove`) - never
#: unconditionally, or the exact `set(counts)` a pre-existing rollback caller may still
#: check would grow keys it never asked for.
COUNT_KEYS = ("rows", "links", "claims", "inquiries")


def _kept_trait(row: OrderInquiryRow) -> Optional[str]:
    """Which of the row's OWN three traits keeps it through a rollback, or `None` for the
    plain rows a rollback still deletes exactly as it always has."""
    if row.redirected_to_pool:
        return "redirected_to_pool"
    if row.changed_at is not None:
        return "changed_at"
    if row.supply_decision_id is not None:
        return "supply_decision_id"
    return None


def _siblings_by_line(
    db: Session, rows: Sequence[OrderInquiryRow]
) -> Dict[str, List[OrderInquiryRow]]:
    """Every LIVE row on the same line (`so_line_id`) as any of `rows` - one query for the
    whole file's candidate rows, never one per row (AC-RB-29)."""
    from app.models.project_so import INQUIRY_CANCELLED

    line_ids = sorted({str(row.so_line_id) for row in rows if row.so_line_id})
    if not line_ids:
        return {}
    siblings = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id.in_(line_ids),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    by_line: Dict[str, List[OrderInquiryRow]] = {}
    for sibling in siblings:
        by_line.setdefault(str(sibling.so_line_id), []).append(sibling)
    return by_line


def _has_planning_sibling(
    row: OrderInquiryRow, by_line: Dict[str, List[OrderInquiryRow]]
) -> bool:
    """AC-RB-29: this row's LINE carries some OTHER live row planning made - one with
    `supply_decision_id` set (a top-up or a restated row), a `Replaces N used` row (note
    starting `"Replaces "`, R6's own shape), or a notice row (a live row whose verb is
    outside `_LINE_OWN_ROW_VERBS` - R7/AC-RB-35's own split, ORDER, ORDER BACK and RESERVE
    AND ORDER, the SAME set `_settle_row_in_place` settles).
    """
    for sibling in by_line.get(str(row.so_line_id), []):
        if str(sibling.id) == str(row.id):
            continue
        if (
            sibling.supply_decision_id is not None
            or (sibling.note or "").startswith("Replaces ")
            or sibling.verb not in _LINE_OWN_ROW_VERBS
        ):
            return True
    return False


def _trait_of(row: OrderInquiryRow, by_line: Dict[str, List[OrderInquiryRow]]) -> Optional[str]:
    """Which trait keeps `row` through a rollback: its own three first (`_kept_trait`),
    then whether its LINE carries a planning sibling (AC-RB-29, checked AFTER the row's own
    traits, per the UAC's own ordering) - `"planning_row_on_line"`. `None` for a plain row
    on a plain line, which a rollback still deletes exactly as it always has.
    """
    own = _kept_trait(row)
    if own is not None:
        return own
    if _has_planning_sibling(row, by_line):
        return "planning_row_on_line"
    return None


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


def _stamped(db: Session, file_name: str) -> List[OrderInquiryRow]:
    """Every row this file raised, kept and removable both.

    `_note_for` writes the stamp alone, or the stamp then `"; <remark>"`, so those are the
    only two shapes this may match. A bare `startswith(stamp)` would additionally match every
    LONGER file name beginning with this one - `--file-name "JAN"` would take out
    `JAN - DEC 2026 ORDER.xlsx` - which is the wrong kind of surprise for a delete.

    `autoescape=True` because a file name is the operator's own text: `%` or `_` in it would
    otherwise be read as LIKE wildcards.
    """
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


def _partition_stamped(
    db: Session, file_name: str
) -> Tuple[List[OrderInquiryRow], List[Tuple[OrderInquiryRow, str]]]:
    """This file's stamped rows, split into `(removable, kept)` - ONE read of the rows
    (`_stamped`) and ONE read of their lines' siblings (`_siblings_by_line`), AC-RB-40:
    every caller derives both halves from that single pair of queries rather than reading
    the table twice for two answers that must agree."""
    stamped = _stamped(db, file_name)
    by_line = _siblings_by_line(db, stamped)
    removable: List[OrderInquiryRow] = []
    kept: List[Tuple[OrderInquiryRow, str]] = []
    for row in stamped:
        trait = _trait_of(row, by_line)
        if trait is None:
            removable.append(row)
        else:
            kept.append((row, trait))
    return removable, kept


def rows_of(db: Session, file_name: str) -> List[OrderInquiryRow]:
    """This file's rows the rollback actually REMOVES - the sheet's own, never a row
    planning has since worked on, on the row itself (section 2.3, ruling R3:
    `redirected_to_pool`, `changed_at`, `supply_decision_id`) or on its LINE (AC-RB-29):
    `_trait_of` excludes both, which `_kept_rows_of` reads back separately so a caller
    cannot delete what this leaves out by accident.
    """
    if not (file_name or "").strip():
        raise ValueError(BLANK_NAME)
    removable, _kept = _partition_stamped(db, file_name)
    return removable


def _kept_rows_of(db: Session, file_name: str) -> List[Tuple[OrderInquiryRow, str]]:
    """`rows_of`'s complement: the stamped rows a trait keeps, paired with which one."""
    _removable, kept = _partition_stamped(db, file_name)
    return kept


def _kept_row_info(db: Session, row: OrderInquiryRow, trait: str) -> Dict[str, Any]:
    """What the dry run and `--apply` both name a kept row by (AC-RB-19): its sales order,
    item, quantity, date and which trait kept it - the same read
    `project_order_inquiry_service.py::_row_core_so_number` uses for a row's own current
    order.
    """
    so_number = None
    if row.so_line_id:
        found = (
            db.query(SalesOrder.so_number)
            .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
            )
            .filter(ProjectSalesOrderLine.id == row.so_line_id)
            .first()
        )
        so_number = found[0] if found else None
    return {
        "so_number": so_number,
        "item_code": row.item_code,
        "qty": row.qty,
        "delivery_date": row.delivery_date,
        "trait": trait,
    }


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


def _remove(db: Session, file_name: str, all_companies: bool) -> Dict[str, Any]:
    """Claims freed, then links, then the rows, then the headers left empty - a row
    planning has worked on since it was raised is never touched (section 2.3): `rows_of`
    already excludes it, and `kept` / `kept_rows` here are its own separate count and
    listing (AC-RB-19), added to the result only when there is something to say.

    AC-RB-39: the more-than-one-company refusal is evaluated over EVERY stamped row, kept
    ones included, and BEFORE anything about a kept row is printed, counted or returned -
    a second company whose only stamped row happens to be a kept one must still trip it.
    """
    removable, kept = _partition_stamped(db, file_name)
    stamped = removable + [row for row, _trait in kept]

    companies = _companies_of(db, stamped)
    for code, company_id, count in companies:
        print(f"  {code} ({company_id}): {count} rows")
    if len(companies) > 1 and not all_companies:
        raise ValueError(
            f"these rows span {len(companies)} companies "
            f"({', '.join(code for code, _id, _n in companies)}): re-run with "
            f"--all-companies if that is really what the upload was"
        )

    counts = {key: 0 for key in COUNT_KEYS}
    if kept:
        counts["kept"] = len(kept)
        counts["kept_rows"] = [_kept_row_info(db, row, trait) for row, trait in kept]
    if not removable:
        print("  no rows carry that stamp" if not kept else "  every stamped row is kept")
        return counts

    rows = removable
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
    # AC-RB-40: self-guarding - the DELETE repeats the row's own three kept traits as
    # predicates beside `id IN (...)`, so a row planning touched AFTER the read above
    # (which is what decided it belonged in `removable`) is not deleted anyway. `counts
    # ["rows"]` is the DELETE's own row count, so it always reflects what actually went,
    # never what `removable` merely named a moment earlier.
    counts["rows"] = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.id.in_(row_ids),
            OrderInquiryRow.redirected_to_pool.is_(False),
            OrderInquiryRow.changed_at.is_(None),
            OrderInquiryRow.supply_decision_id.is_(None),
        )
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

    # A header carries ONE derived field, `state`, and `_refresh_inquiry_states` computes it
    # from the states of its rows: raised while anything on it still waits, actioned when
    # nothing does. Pulling rows out in bulk changes that set without going through the
    # writer, so a header that keeps ANOTHER file's rows would sit on a state its own rows no
    # longer support (an upload's rows are born raised or actioned by `_close_history`, so
    # the two mix on one header routinely). Recomputed for every header this pass touched;
    # the ones it deleted are skipped by that reader's own missing-header check.
    if inquiry_ids:
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        ProjectOrderInquiryService(db)._refresh_inquiry_states(set(inquiry_ids))
    return counts


def run(
    db: Session, file_name: str, apply: bool = False, all_companies: bool = False
) -> Dict[str, Any]:
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
        if counts.get("kept"):
            # AC-RB-19: named, not only counted - purchasing and CS need to know WHICH row a
            # planning trait kept, not merely how many.
            print(f"rows kept:          {counts['kept']}")
            for named in counts.get("kept_rows") or []:
                print(
                    f"  - {named.get('so_number') or '(no SO)'} / "
                    f"{named.get('item_code') or '(no item)'}: {named.get('qty')} @ "
                    f"{named.get('delivery_date')} ({named.get('trait')})"
                )
        if not apply and counts["rows"]:
            print("\nRe-run with --apply to remove these rows.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
