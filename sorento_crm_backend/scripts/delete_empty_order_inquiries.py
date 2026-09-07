#!/usr/bin/env python3
"""Delete order inquiry headers that were minted with nothing on them.

WHY THIS EXISTS
----------------
Before `fix/oi-empty-header`, `ProjectOrderInquiryService.refresh_for_decision` created an
`OrderInquiry` header on every confirmation, even one whose Buy residual and donor holes
were both empty - a plan covered entirely by Reserve, Borrow or timely SPO cover. The
header burned an OI number and left a dangling "Order inquiries" link on the sales order
list (`with_order_inquiries`), while the (rows-based) OI worklist showed nothing for it,
because it had nothing to show (prod OI-000020, local OI-000007). The fix stops new ones
being minted; this script clears out the ones already sitting in the database.

WHAT COUNTS AS EMPTY
---------------------
An `order_inquiries` header with:

* `amendment_id IS NULL` - the STANDARD-DEMAND header `refresh_for_decision` owns, which
  is where the defect this script cleans up after lives. An amendment's own header
  (`amendment_id` set) comes from a different writer (`_write`, called from
  `derive_for_amendment`) that can also net to zero rows when every changed row in the
  amendment was declined - but `project_so_delta_service.py`'s publish flow hands that
  header's id straight to its caller as `order_inquiry_id` the moment it is minted, so an
  amendment header is never something lying around unused the way a standard one can be.
  Out of scope for this script; a fix for it belongs to `derive_for_amendment`, not to a
  cleanup pass here.
* zero `order_inquiry_rows` against it, AND
* no `projects.tasks` row linking to it (`linked_entity_type = 'order_inquiry'`,
  `linked_entity_id = <header id>` - `TASK_LINK_ORDER_INQUIRY` in `app.models.projects`).

The task check matters even though a task is only ever created for a header that DID raise
rows (`_hand_to_purchasing`): a header a person has already looked at and started acting on
(e.g. manually attached a task) is not this script's business to remove.

SAFETY / IDEMPOTENCY
---------------------
`--dry-run` is the DEFAULT. Nothing is written without `--apply`. Query-based and
re-runnable: a header this script already deleted no longer matches, so a second run
reports zero. `--inquiry-no OI-000020` restricts a run to one header, for a targeted
cleanup or a manual double-check before the unrestricted run.

The DELETE re-checks the same "zero rows, no task" predicates the SELECT used, in the
SAME WHERE clause, rather than trusting the list the SELECT produced: between the report
and the delete, CS can press Confirm on the very order a listed header belongs to, and a
confirmation that finally has something to buy REUSES that header (`_existing` in
`ProjectOrderInquiryService`) rather than minting a new one. A DELETE keyed on id alone
would then take the header out from under its brand new row, and the row would go with
it (`order_inquiry_rows.order_inquiry_id` is `ON DELETE CASCADE`). Re-checking inside the
DELETE's own WHERE closes that window; anything the recheck disqualifies is reported as
skipped rather than deleted.

Run from sorento_crm_backend/:
    venv/bin/python scripts/delete_empty_order_inquiries.py
    venv/bin/python scripts/delete_empty_order_inquiries.py --apply
    venv/bin/python scripts/delete_empty_order_inquiries.py --inquiry-no OI-000020 --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.models.project_so import OrderInquiry, OrderInquiryRow, ProjectSalesOrder
from app.models.projects import TASK_LINK_ORDER_INQUIRY, ProjectTask


@dataclass
class EmptyInquiry:
    """One header with nothing raised on it and nobody working from it."""

    inquiry_id: str
    inquiry_no: str
    company_id: Optional[str]
    raised_at: Any
    so_ref: str

    def describe(self) -> str:
        return (
            f"{self.inquiry_no}  company={self.company_id}  "
            f"raised_at={self.raised_at}  SO={self.so_ref}"
        )


def _no_rows_clause():
    """`True` when no `order_inquiry_rows` row names this header.

    A correlated `NOT EXISTS` rather than the outer-join-plus-count a plain SELECT could
    use, so the SAME expression drops straight into the DELETE's own WHERE clause below -
    one predicate, checked twice, rather than two ways of asking the same question that
    could drift apart.
    """
    return ~exists().where(OrderInquiryRow.order_inquiry_id == OrderInquiry.id)


def _no_task_clause():
    """`True` when no purchasing task links to this header."""
    return (
        ~exists()
        .where(ProjectTask.linked_entity_type == TASK_LINK_ORDER_INQUIRY)
        .where(ProjectTask.linked_entity_id == OrderInquiry.id)
    )


def find_empty_inquiries(
    db: Session, *, inquiry_no: Optional[str] = None
) -> List[EmptyInquiry]:
    """Every STANDARD-DEMAND header (`amendment_id IS NULL`) with zero rows and no
    purchasing task attached. An amendment's own header is a different writer's problem
    (see the module docstring) and is deliberately excluded here.
    """
    query = (
        db.query(OrderInquiry, ProjectSalesOrder)
        .join(
            ProjectSalesOrder,
            ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
        )
        .filter(
            OrderInquiry.amendment_id.is_(None),
            _no_rows_clause(),
            _no_task_clause(),
        )
        .order_by(OrderInquiry.inquiry_no.asc())
    )
    if inquiry_no:
        query = query.filter(OrderInquiry.inquiry_no == inquiry_no)

    out: List[EmptyInquiry] = []
    for inquiry, order in query.all():
        so_ref = order.autocount_doc_no or order.provisional_ref or "(no ref)"
        out.append(
            EmptyInquiry(
                inquiry_id=str(inquiry.id),
                inquiry_no=inquiry.inquiry_no,
                company_id=inquiry.company_id,
                raised_at=inquiry.raised_at,
                so_ref=so_ref,
            )
        )
    return out


def apply_deletes(db: Session, empties: List[EmptyInquiry]) -> Dict[str, int]:
    """Delete every header found, in one transaction, RE-CHECKING the same predicates
    the SELECT used inside the DELETE's own WHERE clause.

    The list `empties` was read moments ago: between that SELECT and this DELETE, CS can
    confirm the very order one of these headers belongs to, and a confirmation that
    finally has something to buy REUSES the existing header rather than minting a new
    one (`ProjectOrderInquiryService._existing`). Deleting by id alone would then take
    that header down, cascading its brand new row with it. Anything the recheck
    disqualifies is left alone and counted as skipped rather than deleted.
    """
    ids = [row.inquiry_id for row in empties]
    if not ids:
        return {"deleted": 0, "skipped": 0}
    deleted = (
        db.query(OrderInquiry)
        .filter(
            OrderInquiry.id.in_(ids),
            OrderInquiry.amendment_id.is_(None),
            _no_rows_clause(),
            _no_task_clause(),
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return {"deleted": deleted, "skipped": len(ids) - deleted}


def run(db: Session, *, apply: bool, inquiry_no: Optional[str]) -> Dict[str, Any]:
    """Report (and optionally perform) every deletion. The caller commits."""
    empties = find_empty_inquiries(db, inquiry_no=inquiry_no)
    for row in empties:
        print(f"  {row.describe()}")
    result = apply_deletes(db, empties) if apply else {"deleted": 0, "skipped": 0}
    return {
        "found": len(empties),
        "deleted": result["deleted"],
        "skipped": result["skipped"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Delete the headers found. Without this the script only reports.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only (the default; accepted so a run can say so out loud).",
    )
    parser.add_argument(
        "--inquiry-no", type=str, default=None,
        help="Restrict to one inquiry number, e.g. OI-000020",
    )
    args = parser.parse_args()
    apply = args.apply and not args.dry_run

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    # A script has no request and no principal, so the session scope would be UNSET,
    # which is fail-closed and would return no rows at all. `None` is the sanctioned
    # system / all-companies scope - every header printed names its own company.
    set_company_scope(db, None)

    try:
        print(
            "Order inquiry headers with zero rows and no purchasing task "
            f"({'APPLYING' if apply else 'DRY-RUN, nothing is written'}):"
        )
        summary = run(db, apply=apply, inquiry_no=args.inquiry_no)
        if apply:
            db.commit()

        print("\n=== summary ===")
        print(f"mode:               {'APPLIED' if apply else 'DRY-RUN (no writes)'}")
        print(f"headers found:      {summary['found']}")
        print(f"headers deleted:    {summary['deleted']}")
        print(f"headers skipped:    {summary['skipped']} (no longer empty by the time of the delete)")
        if not apply and summary["found"]:
            print("\nRe-run with --apply to delete these headers.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
