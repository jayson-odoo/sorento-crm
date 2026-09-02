#!/usr/bin/env python3
"""Undo the automatic placements that took a project-bin line nobody attributed to them.

`PLAN-scm-reorder-oi-feedback-1sep.md` G12, captain 2 Sep 2026. G12 says a PO/SPO line
destined for a PROJECT BIN is auto-taken only by the sales order that CLAIMS it. Two
mechanisms broke that, and this repairs both:

  * `today` - the withdrawn BORN-CLAIMED pass (PR #490, live between 2 Sep 2026 02:00 and
    the fix). It let the cascade write an `order_inquiry` claim naming its OWN sales order
    for any project-bin line no external feed had claimed, and then take the line by
    reading the claim it had just made. Measured case: PO 202607-S0067's CB1178A-SS-NL at
    BRW-IB, 114 units bought for SO391853 per the AutoCount book, auto-linked to SO381895
    at 2026-09-02 02:47:41 with a self-written claim beside it. This scope undoes EXACTLY
    what that pass wrote: an `auto = true` link on a project-bin target whose only claims
    are `order_inquiry` rows written on or after the cut-off, plus those claims.

  * `legacy` - every OTHER automatic placement on a project-bin line that no EXTERNAL
    attribution names the row's own sales order for (captain's extension, 2 Sep 2026).
    These predate the born-claimed pass: G12's gate did not exist when they were written,
    so the cascade helped itself to bin lines as a matter of course.

**A human link is never touched, in either scope.** `auto = false` is somebody's deliberate
instruction and is evidence in its own right (G12: a manual link WRITES the claim).

**Rows that lose every link go back to uncovered ("Not found"). That is intended** - Joey
attributes them in AutoCount's `FromSODocList` and the next book upload seeds the claim, or
links them by hand.

ORDER MATTERS. `legacy` must run AFTER a fresh upload of the current PO & SPO outstanding
book, because that upload is what writes the `po_upload` claims the repair spares links
for. Run in the other order and it drops links the book would have justified. The `today`
scope has no such dependency: it undoes writes this codebase made itself, hours ago.

Run from sorento_crm_backend/:

    python scripts/repair_project_bin_self_claims.py --scope today            # dry run
    python scripts/repair_project_bin_self_claims.py --scope today --apply
    python scripts/repair_project_bin_self_claims.py --scope legacy           # dry run
    python scripts/repair_project_bin_self_claims.py --scope legacy --apply
    python scripts/repair_project_bin_self_claims.py --scope both

Deliberately NOT an Alembic migration. `alembic upgrade` runs unattended on every deploy and
this repair has a prerequisite a deploy cannot satisfy (the book re-upload above), so it is
a script somebody runs on purpose, in order, the same shape as
`scripts/migrate_attachments_to_r2.py` and `scripts/repair_20aug_placed_double_counts.py`.

Idempotent: a second run finds nothing left to match and reports zero.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

#: When the withdrawn born-claimed pass went live. A claim written before this is somebody
#: else's doing and is out of the `today` scope entirely.
CUT_OFF = "2026-09-02 00:00:00"

#: Sources that are a REAL attribution: the purchase book's own `FromSODocList`
#: (`po_history` / `po_upload`), a person in the Link dialog (`manual`), and the supply
#: writer that created the line for known demand (`crm_supply`). `so_upload` is reserved by
#: the constraint and unused, listed so the vocabulary stays in one place.
EXTERNAL_SOURCES = ("po_history", "po_upload", "manual", "crm_supply", "so_upload")

#: Every automatic link sitting on a PROJECT-BIN target, with the row's own sales-order
#: number beside it - the population both scopes narrow. One CTE, both targets, because a
#: link names a purchase-order line OR an SPO allocation and the rule is the same for both.
_POPULATION = """
WITH bin_link AS (
    SELECT l.id            AS link_id,
           l.claim_id      AS claim_id,
           l.document      AS document,
           l.qty           AS qty,
           l.linked_at     AS linked_at,
           r.id            AS row_id,
           r.item_code     AS item_code,
           r.company_id    AS company_id,
           COALESCE(pso.autocount_doc_no, pso.provisional_ref) AS so_number,
           COALESCE(l.po_line_id, l.spo_allocation_id)         AS target_id
      FROM projects.order_inquiry_links l
      JOIN projects.order_inquiry_rows r    ON r.id = l.row_id
      JOIN projects.order_inquiries oi      ON oi.id = r.order_inquiry_id
      JOIN projects.sales_orders pso        ON pso.id = oi.project_sales_order_id
      LEFT JOIN purchase_order_lines pol    ON pol.id = l.po_line_id
      LEFT JOIN spo_allocations sa          ON sa.id = l.spo_allocation_id
      JOIN warehouses w                     ON w.id = COALESCE(pol.warehouse_id,
                                                               sa.warehouse_id)
     WHERE l.auto IS TRUE
       AND COALESCE(w.segment, 'dealer') = 'project'
)
"""

#: `today`: the target carries NOTHING but self-written `order_inquiry` claims made on or
#: after the cut-off. Any other claim - an older one, or one from a real feed - means this
#: link is not the born-claimed pass's doing and is left for the `legacy` pass to judge.
_TODAY = _POPULATION + """
SELECT link_id, row_id, claim_id, document, item_code, so_number, qty, linked_at
  FROM bin_link b
 WHERE NOT EXISTS (
        SELECT 1
          FROM scm.order_link_claim c
         WHERE (c.po_line_id = b.target_id OR c.spo_allocation_id = b.target_id)
           AND (c.source <> 'order_inquiry' OR c.claimed_at < :cut_off)
       )
 ORDER BY linked_at
"""

#: `legacy`: no EXTERNAL claim names THIS ROW'S OWN sales order for this target. A link the
#: book (or a person, or the buy that created the line) justifies survives; everything else
#: was the cascade helping itself.
_LEGACY = _POPULATION + """
SELECT link_id, row_id, claim_id, document, item_code, so_number, qty, linked_at
  FROM bin_link b
 WHERE NOT EXISTS (
        SELECT 1
          FROM scm.order_link_claim c
         WHERE (c.po_line_id = b.target_id OR c.spo_allocation_id = b.target_id)
           AND c.so_number = b.so_number
           AND c.source = ANY(:external)
       )
 ORDER BY linked_at
"""


def _find(db, scope: str) -> list[dict]:
    sql = _TODAY if scope == "today" else _LEGACY
    params = {"cut_off": CUT_OFF} if scope == "today" else {
        "external": list(EXTERNAL_SOURCES)
    }
    return [dict(row._mapping) for row in db.execute(text(sql), params)]


def _repair(db, scope: str, *, apply: bool) -> dict:
    """Delete the links this scope names, and the self-written claim behind each.

    The CLAIM goes only when it is the `order_inquiry` audit row this very placement wrote
    (`OrderInquiryLink.claim_id`, and the source test) - the same rule
    `order_link_service.delete_own_claim` applies on an ordinary untag. A claim another feed
    made at the same identity is somebody else's evidence and stays, whether or not this
    link survives.
    """
    found = _find(db, scope)
    if not found:
        print(f"[{scope}] nothing to repair")
        return {"links": 0, "claims": 0, "rows": 0}

    link_ids = [f["link_id"] for f in found]
    claim_ids = sorted({f["claim_id"] for f in found if f["claim_id"]})
    row_ids = sorted({f["row_id"] for f in found})

    print(f"[{scope}] {len(found)} automatic placements on project-bin lines, "
          f"{len(row_ids)} rows, {len(claim_ids)} self-written claims")
    for f in found[:20]:
        print(f"    {f['so_number']} {f['item_code']} qty {f['qty']} on "
              f"{f['document']} linked {f['linked_at']}")
    if len(found) > 20:
        print(f"    ... and {len(found) - 20} more")

    if not apply:
        return {"links": len(found), "claims": len(claim_ids), "rows": len(row_ids)}

    deleted_links = db.execute(
        text("DELETE FROM projects.order_inquiry_links WHERE id = ANY(:ids)"),
        {"ids": link_ids},
    ).rowcount
    deleted_claims = 0
    if claim_ids:
        deleted_claims = db.execute(
            text(
                "DELETE FROM scm.order_link_claim "
                " WHERE id = ANY(:ids) AND source = 'order_inquiry'"
            ),
            {"ids": claim_ids},
        ).rowcount
    print(f"[{scope}] deleted {deleted_links} links and {deleted_claims} claims")
    return {"links": deleted_links, "claims": deleted_claims, "rows": len(row_ids)}


def _refresh_rows(db, row_ids: list[str]) -> None:
    """Put each touched row back into the state its remaining links describe.

    A row that has lost every link is uncovered again and reads "Not found" on the
    worklist, which is the intended outcome: nothing attributed its supply, so nothing
    should claim it is covered.
    """
    if not row_ids:
        return
    from app.models.project_so import OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    rows = (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.id.in_(row_ids)).all()
    )
    ProjectOrderInquiryService(db)._refresh_link_state(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--scope", choices=("today", "legacy", "both"), default="today",
        help="`today` undoes the born-claimed pass's own writes; `legacy` needs a fresh "
             "PO/SPO book upload first (see the module docstring).",
    )
    parser.add_argument("--apply", action="store_true",
                        help="Write the repair. Default is dry-run.")
    args = parser.parse_args()

    scopes = ("today", "legacy") if args.scope == "both" else (args.scope,)
    db = SessionLocal()
    try:
        touched: list[str] = []
        for scope in scopes:
            found = _find(db, scope)
            result = _repair(db, scope, apply=args.apply)
            if args.apply and result["links"]:
                touched.extend(sorted({f["row_id"] for f in found}))
        if args.apply:
            _refresh_rows(db, sorted(set(touched)))
            db.commit()
            print("\nCommitted.")
        else:
            db.rollback()
            print("\nDry run only - nothing written. Re-run with --apply to write.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
