#!/usr/bin/env python3
"""Dry run for lane BOARD-NO-HOLD: what Stock Debt says when board decisions stop holding stock.

Walks the Stock Debt VIEW (`StockDebtService._assignments(view=True)`, the page's own reading)
twice for every product a confirmed Fulfilment Planning decision holds today:

  A. as the code stands (decision holds bind first, at any date);
  B. with `ProjectSupplyService._hold_query` answering no rows, which is the one predicate every
     reader (Stock Debt, the board strip, location stock, the ladder) asks "is this holding stock".

Order inquiry placements, landed goods and the book's own S/O pins are untouched in both runs:
only the board-decision half (`so_line_allocations`) is switched off.

Prints, per product, every open sales-order line whose Assigned / Short / status changes, the
totals, and the named sales orders' lines in full. No customer names: SO numbers, product codes,
locations and quantities only. ONE transaction, READ ONLY, always rolled back.

    DATABASE_URL=postgresql://.../throwaway python -m scripts.board_no_hold_dry_run \\
        --product CB4702 --so SO400884 --so SO426986 [--csv out.csv]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Tuple


@contextmanager
def _decisions_hold_nothing() -> Iterator[None]:
    """Run B: the shared hold predicate matches no row. Restored on exit."""
    from sqlalchemy import false

    from app.services.project_supply_service import ProjectSupplyService

    original = ProjectSupplyService._hold_query

    def no_holds(self, product_ids, *, exclude_line_ids, entities=None):
        return original(
            self, product_ids, exclude_line_ids=exclude_line_ids, entities=entities
        ).filter(false())

    ProjectSupplyService._hold_query = no_holds
    try:
        yield
    finally:
        ProjectSupplyService._hold_query = original


def _held_products(db) -> List[Tuple[str, str, Optional[str]]]:
    """(id, code, name) of every product a confirmed decision holds stock of today."""
    from app.models.order import SalesOrderLine
    from app.models.product import Product
    from app.models.project_so import ProjectSalesOrderLine, SOLineAllocation
    from app.services.project_supply_service import ProjectSupplyService, _hold_product

    candidates = [
        str(pid)
        for (pid,) in db.query(_hold_product)
        .select_from(SOLineAllocation)
        .join(ProjectSalesOrderLine, ProjectSalesOrderLine.id == SOLineAllocation.so_line_id)
        .outerjoin(
            SalesOrderLine,
            SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id,
        )
        .filter(SOLineAllocation.confirmed_at.isnot(None))
        .distinct()
        if pid
    ]
    if not candidates:
        return []
    held = {
        str(pid)
        for (pid,) in ProjectSupplyService(db)
        ._hold_query(candidates, exclude_line_ids=None, entities=(_hold_product,))
        .distinct()
    }
    rows = db.query(Product.id, Product.product_code, Product.product_name).filter(
        Product.id.in_(sorted(held))
    )
    return sorted(((str(i), c or "", n) for i, c, n in rows), key=lambda r: r[1])


def _hold_totals(db, product_ids: List[str]) -> Dict[str, object]:
    """What run B releases: held qty per kind, and how many orders / lines hold it."""
    from app.models.project_so import (
        ALLOC_BORROW_SOURCES,
        ALLOC_RESERVE_SOURCES,
        ProjectSalesOrderLine,
        SOLineAllocation,
    )
    from app.models.order import SalesOrder
    from app.services.project_supply_service import ProjectSupplyService, held_qty_expr

    rows = (
        ProjectSupplyService(db)
        ._hold_query(
            product_ids,
            exclude_line_ids=None,
            entities=(
                SOLineAllocation.source_type,
                SalesOrder.so_number,
                ProjectSalesOrderLine.id,
                held_qty_expr(),
            ),
        )
        .all()
    )
    out: Dict[str, object] = {"rows": len(rows), "qty": 0.0}
    by_kind: Dict[str, float] = defaultdict(float)
    for source, _so, _line, qty in rows:
        kind = (
            "reserve" if source in ALLOC_RESERVE_SOURCES
            else "borrow" if source in ALLOC_BORROW_SOURCES
            else source
        )
        by_kind[kind] += float(qty or 0)
        out["qty"] = float(out["qty"]) + float(qty or 0)
    out["by_kind"] = dict(by_kind)
    out["orders"] = len({so for _s, so, _l, _q in rows if so})
    out["lines"] = len({line for _s, _so, line, _q in rows})
    return out


def _lines(assignments) -> Dict[str, dict]:
    out = {}
    for product_id, result in assignments.items():
        for row in result.lines:
            open_qty = float(row.line.open_qty)
            out[row.line.key] = {
                "product_id": product_id,
                "so": row.line.so_number,
                "line_no": row.line.core_line_no or row.line.line_no,
                "warehouse": row.line.warehouse or "",
                "required": row.line.required_date,
                "open": open_qty,
                "assigned": round(open_qty - float(row.uncovered), 4),
                "short": round(float(row.uncovered), 4),
                "short_at_date": round(float(row.short_at_date), 4),
                "status": row.status,
                "sources": "; ".join(
                    f"{item.event.ref or item.event.kind}"
                    f"{' ' + item.event.warehouse if item.event.warehouse else ''}"
                    f" {round(float(item.qty), 4)}{' (pinned)' if item.pinned else ''}"
                    for item in row.assigned
                ),
            }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", action="append", default=[],
                        help="product code to print in full (repeatable), default CB4702")
    parser.add_argument("--so", action="append", default=[],
                        help="SO number to print in full (repeatable)")
    parser.add_argument("--csv", help="write every changed line to this CSV")
    args = parser.parse_args()
    focus_products = set(args.product or ["CB4702"])
    focus_sos = set(args.so or ["SO400884", "SO426986"])

    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        report(db, focus_products=focus_products, focus_sos=focus_sos, csv_path=args.csv)
    finally:
        db.rollback()
        db.close()


def report(db, *, focus_products, focus_sos, csv_path=None) -> list:
    """The whole dry run on an open session; returns the changed lines. Writes nothing."""
    from app.services.scm.stock_debt_service import StockDebtService

    products = _held_products(db)
    codes = {pid: code for pid, code, _name in products}
    ids = [pid for pid, _c, _n in products]
    print(f"Products with a decision hold today: {len(products)}")
    totals = _hold_totals(db, ids) if ids else {}
    print(f"Decision holds released by the change: {totals}")
    if not ids:
        return []

    span = StockDebtService(db)._warehouses(None, "all")
    before = _lines(StockDebtService(db)._assignments(products, span, view=True))
    with _decisions_hold_nothing():
        after = _lines(StockDebtService(db)._assignments(products, span, view=True))

    changed = []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        if a is None or b is None:
            continue
        if (a["assigned"], a["short"], a["status"]) != (b["assigned"], b["short"], b["status"]):
            changed.append((key, a, b))

    per_product: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"lines": 0, "newly_short": 0, "short_before": 0.0, "short_after": 0.0}
    )
    for _key, a, b in changed:
        row = per_product[codes.get(a["product_id"], a["product_id"])]
        row["lines"] += 1
        row["short_before"] += a["short"]
        row["short_after"] += b["short"]
        if a["short"] <= 0 < b["short"]:
            row["newly_short"] += 1

    print(f"\nOpen SO lines whose Stock Debt reading changes: {len(changed)} "
          f"over {len(per_product)} products")
    gained = sum(1 for _k, a, b in changed if b["short"] < a["short"])
    lost = sum(1 for _k, a, b in changed if b["short"] > a["short"])
    print(f"  less short after: {gained} lines; more short after: {lost} lines")
    print(f"  short qty before {sum(a['short'] for _k, a, _b in changed):.2f}, "
          f"after {sum(b['short'] for _k, _a, b in changed):.2f}")

    stranded = sorted(
        code for code, row in per_product.items()
        if row["short_after"] - row["short_before"] > 0.0001
    )
    print(f"  products whose total short RISES (released stock no other line may draw today:"
          f" cross-group or site-pool plans): {len(stranded)} {stranded[:30]}")

    print("\nPer product (code | lines changed | newly short | short before -> after)")
    for code in sorted(per_product):
        row = per_product[code]
        print(f"  {code:<20} {row['lines']:>4} {row['newly_short']:>4} "
              f"{row['short_before']:>10.2f} -> {row['short_after']:.2f}")

    print("\nFocus: every open line of the named products / SOs, before | after")
    for key in sorted(before, key=lambda k: (codes.get(before[k]["product_id"], ""),
                                             str(before[k]["required"]))):
        a, b = before[key], after.get(key, {})
        if codes.get(a["product_id"]) not in focus_products and a["so"] not in focus_sos:
            continue
        print(f"  {codes.get(a['product_id'])} {a['so']} L{a['line_no']} {a['warehouse']} "
              f"due {a['required']} open {a['open']:g} | "
              f"{a['status']} assigned {a['assigned']:g} short {a['short']:g} [{a['sources']}] | "
              f"{b.get('status')} assigned {b.get('assigned')} short {b.get('short')} "
              f"[{b.get('sources')}]")

    if csv_path:
        with open(csv_path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "product", "so", "line", "location", "required", "open",
                "status_before", "assigned_before", "short_before",
                "status_after", "assigned_after", "short_after",
            ])
            for _key, a, b in changed:
                writer.writerow([
                    codes.get(a["product_id"]), a["so"], a["line_no"], a["warehouse"],
                    a["required"], a["open"], a["status"], a["assigned"], a["short"],
                    b["status"], b["assigned"], b["short"],
                ])
        print(f"\nWrote {len(changed)} rows to {csv_path}")
    return changed


if __name__ == "__main__":
    main()
