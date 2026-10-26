#!/usr/bin/env python3
"""Release the links of PO / SO / SPO lines AutoCount removed BEFORE AC-REMOVED-LINES shipped
(PLAN-ac-removed-lines-26oct, owner ruling Q4 a, 26 Oct 2026).

WHAT IT DOES
------------
The ingest now releases a line's links on the push that removes it. Lines removed earlier
still hold them. This applies the SAME release, through the same functions the ingest calls:

- PO line, SPO line: `ProjectOrderInquiryService.release_removed_lines` (every link on the
  line deleted, no row note, no ack_state change, open claims resolved).
- SO line: `ProjectOrderInquiryService.retire_rows_for_removed_so_lines` (rows retired as
  Transfer to Cancel SO retires them; the core line gets no `cancelled_at`).

WHAT IT SELECTS (AC-RL-41)
--------------------------
- PO lines `cancelled`, AutoCount source with a DtlKey, header not cancelled, not
  `cancelled_by_cancel_doc`, with a live OI link or an open claim.
- SO lines the same, plus `cancelled_at IS NULL`, with an order inquiry row the retire
  would act on (raised / partly linked / placed, ORDER or ORDER BACK, not redirected: an
  actioned row is only ever flagged, so selecting on it would never run dry).
- SPO lines with `retired_at` set and a live OI link or an open claim.

A second run finds nothing: every selector needs a link, an open claim or a live row, and the
release removes exactly that.

SAFETY
------
`--apply` is required to write; the default prints the report and rolls back. The report
names document number, DtlKey, product code, quantities and a row count, never a customer.
One commit at the end of each kind. The SO retire runs with `notify=False` (AC-RL-44): these
removals are weeks old, so no purchasing handover email or other notification is sent.

USAGE
-----
    venv/bin/python -m scripts.release_removed_autocount_lines --company <company id>
    venv/bin/python -m scripts.release_removed_autocount_lines --company <company id> --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from decimal import Decimal
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, or_

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.models.product import Product
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)
from app.models.scm import OrderLinkClaim
from app.services.company_scope import register_company_scope_listeners
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

logger = logging.getLogger("scripts.release_removed_autocount_lines")

AUTOCOUNT = "autocount"
CANCELLED = "cancelled"


def _dtl_key(source_ref: str | None) -> str:
    """The DtlKey is the last segment of `<db>:<doc key>:<dtl key>`."""
    return (source_ref or "").rsplit(":", 1)[-1]


def _qty(value: Any) -> str:
    return format(Decimal(value or 0).normalize(), "f")


def _links_by(db, column) -> dict[str, tuple[Decimal, set[str]]]:
    """`{line id: (linked qty, row ids)}` over every OI link naming a line on `column`."""
    out: dict[str, tuple[Decimal, set[str]]] = {}
    for line_id, row_id, qty in db.query(column, OrderInquiryLink.row_id, OrderInquiryLink.qty).filter(
        column.isnot(None)
    ):
        total, rows = out.get(str(line_id), (Decimal(0), set()))
        out[str(line_id)] = (total + Decimal(qty or 0), rows | {str(row_id)})
    return out


def _open_claim_ids(db, column) -> set[str]:
    return {
        str(line_id)
        for (line_id,) in db.query(column).filter(
            column.isnot(None), OrderLinkClaim.resolved_at.is_(None)
        )
    }


def _po_candidates(db, company_id: str) -> list[dict[str, Any]]:
    links = _links_by(db, OrderInquiryLink.po_line_id)
    claims = _open_claim_ids(db, OrderLinkClaim.po_line_id)
    lines = (
        db.query(PurchaseOrderLine, PurchaseOrder.po_number, Product.product_code)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .outerjoin(Product, Product.id == PurchaseOrderLine.product_id)
        .filter(
            PurchaseOrderLine.company_id == company_id,
            PurchaseOrderLine.line_status == CANCELLED,
            PurchaseOrderLine.source_system == AUTOCOUNT,
            PurchaseOrderLine.source_ref.isnot(None),
            PurchaseOrderLine.cancelled_by_cancel_doc.is_(False),
            PurchaseOrder.status != CANCELLED,
        )
        .order_by(PurchaseOrder.po_number, PurchaseOrderLine.source_ref)
        .all()
    )
    found = []
    for line, number, code in lines:
        linked, rows = links.get(str(line.id), (Decimal(0), set()))
        if not rows and str(line.id) not in claims:
            continue
        found.append(
            {
                "kind": "po",
                "id": str(line.id),
                "document": number,
                "dtl_key": _dtl_key(line.source_ref),
                "product_code": code,
                "line_qty": _qty(line.qty_ordered),
                "linked_qty": _qty(linked),
                "rows_affected": len(rows),
            }
        )
    return found


def _spo_candidates(db, company_id: str) -> list[dict[str, Any]]:
    links = _links_by(db, OrderInquiryLink.spo_allocation_id)
    claims = _open_claim_ids(db, OrderLinkClaim.spo_allocation_id)
    lines = (
        db.query(SPOAllocation, Product.product_code)
        .outerjoin(Product, Product.id == SPOAllocation.product_id)
        .filter(
            SPOAllocation.company_id == company_id,
            SPOAllocation.retired_at.isnot(None),
        )
        .order_by(SPOAllocation.spo_number, SPOAllocation.source_ref)
        .all()
    )
    found = []
    for alloc, code in lines:
        linked, rows = links.get(str(alloc.id), (Decimal(0), set()))
        if not rows and str(alloc.id) not in claims:
            continue
        found.append(
            {
                "kind": "spo",
                "id": str(alloc.id),
                "document": alloc.spo_number,
                "dtl_key": _dtl_key(alloc.source_ref),
                "product_code": code,
                "line_qty": _qty(alloc.allocated_quantity),
                "linked_qty": _qty(linked),
                "rows_affected": len(rows),
            }
        )
    return found


def _so_candidates(db, company_id: str) -> list[dict[str, Any]]:
    live_rows = (
        db.query(
            ProjectSalesOrderLine.core_sales_order_line_id,
            func.count(OrderInquiryRow.id),
            func.coalesce(func.sum(OrderInquiryRow.qty), 0),
        )
        .join(OrderInquiryRow, OrderInquiryRow.so_line_id == ProjectSalesOrderLine.id)
        .filter(
            OrderInquiryRow.state.in_((INQUIRY_RAISED, INQUIRY_PARTLY_LINKED, INQUIRY_PLACED)),
            OrderInquiryRow.verb.in_((IV_ORDER, IV_ORDER_BACK)),
            OrderInquiryRow.redirected_to_pool.is_(False),
        )
        .group_by(ProjectSalesOrderLine.core_sales_order_line_id)
        .all()
    )
    live = {str(core_id): (count, qty) for core_id, count, qty in live_rows if core_id}
    links = {}
    if live:
        for core_id, qty in (
            db.query(ProjectSalesOrderLine.core_sales_order_line_id, func.sum(OrderInquiryLink.qty))
            .join(OrderInquiryRow, OrderInquiryRow.so_line_id == ProjectSalesOrderLine.id)
            .join(OrderInquiryLink, OrderInquiryLink.row_id == OrderInquiryRow.id)
            .group_by(ProjectSalesOrderLine.core_sales_order_line_id)
        ):
            if core_id:
                links[str(core_id)] = Decimal(qty or 0)
    lines = (
        db.query(SalesOrderLine, SalesOrder.so_number, Product.product_code)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .outerjoin(Product, Product.id == SalesOrderLine.product_id)
        .filter(
            SalesOrderLine.company_id == company_id,
            SalesOrderLine.line_status == CANCELLED,
            SalesOrderLine.source_system == AUTOCOUNT,
            SalesOrderLine.source_ref.isnot(None),
            SalesOrderLine.cancelled_by_cancel_doc.is_(False),
            SalesOrderLine.cancelled_at.is_(None),
            SalesOrder.status != CANCELLED,
        )
        .order_by(SalesOrder.so_number, SalesOrderLine.source_ref)
        .all()
    )
    found = []
    for line, number, code in lines:
        if str(line.id) not in live:
            continue
        found.append(
            {
                "kind": "so",
                "id": str(line.id),
                "document": number,
                "dtl_key": _dtl_key(line.source_ref),
                "product_code": code,
                "line_qty": _qty(line.qty_ordered),
                "linked_qty": _qty(links.get(str(line.id), Decimal(0))),
                "rows_affected": live[str(line.id)][0],
            }
        )
    return found


def run(db, company_id: str, dry_run: bool = True) -> dict[str, Any]:
    """The report for ONE company; with `dry_run=False` it also releases what it lists.

    `dry_run` defaults to `True` and a dry run ends with `db.rollback()`, so a caller that
    forgets the argument previews rather than writes.
    """
    register_company_scope_listeners()
    with company_scope(db, frozenset({company_id})):
        po = _po_candidates(db, company_id)
        spo = _spo_candidates(db, company_id)
        so = _so_candidates(db, company_id)
        if not dry_run:
            service = ProjectOrderInquiryService(db)
            if po:
                service.release_removed_lines(po_line_ids=[c["id"] for c in po])
                db.commit()
            if spo:
                service.release_removed_lines(spo_allocation_ids=[c["id"] for c in spo])
                db.commit()
            if so:
                cores = db.query(SalesOrderLine).filter(
                    SalesOrderLine.id.in_([c["id"] for c in so])
                ).all()
                service.retire_rows_for_removed_so_lines(cores, notify=False)
                db.commit()
        else:
            db.rollback()
    lines = [{k: v for k, v in c.items() if k != "id"} for c in (*po, *so, *spo)]
    return {
        "po_lines": len(po),
        "so_lines": len(so),
        "spo_lines": len(spo),
        "rows_affected": sum(c["rows_affected"] for c in (*po, *so, *spo)),
        "lines": lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", required=True, help="Company id")
    parser.add_argument("--apply", action="store_true", help="Write; the default is a dry run")
    args = parser.parse_args(argv)
    dry_run = not args.apply

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        print(f"=== {'DRY-RUN (no writes)' if dry_run else 'APPLYING'} ===")
        report = run(db, args.company, dry_run=dry_run)
        for line in report["lines"]:
            print(
                f"{line['kind'].upper()} {line['document']} dtl={line['dtl_key']} "
                f"product={line['product_code']} line_qty={line['line_qty']} "
                f"linked_qty={line['linked_qty']} rows={line['rows_affected']}"
            )
        print("\n=== summary ===")
        for key in ("po_lines", "so_lines", "spo_lines", "rows_affected"):
            print(f"{key}: {report[key]}")
        if dry_run and report["lines"]:
            print("\nRe-run with --apply to write these changes.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
