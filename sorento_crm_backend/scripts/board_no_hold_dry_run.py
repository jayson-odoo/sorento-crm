#!/usr/bin/env python3
"""Dry run for lane BOARD-NO-HOLD: what Stock Debt says when board decisions stop holding stock.

Walks the Stock Debt VIEW (`StockDebtService._assignments(view=True)`, the page's own reading)
twice for every product a confirmed Fulfilment Planning decision holds today:

  A. as the code stands (decision holds bind first, at any date);
  B. the ruled rule (owner 27 Oct): `ProjectSupplyService._hold_query`, the one predicate every
     reader asks "is this holding stock", answers no RESERVE row (Borrow keeps holding, Q3), and
     Stock Debt hands each Reserve to the walk as a ROUTE (Q1 a): its line may draw the bin the
     plan names, at the line's own date, in date order (`supply_assignment.Hold.route`).

Order inquiry placements, landed goods, the book's own S/O pins and Borrow are untouched in both
runs. Read as company `--company` (default SRT), the scope an SRT user's page reads under.

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
    """Run B: the shared hold predicate matches no RESERVE row, and Stock Debt hands each
    Reserve to the walk as a route instead. Restored on exit."""
    from app.models.inventory import Warehouse
    from app.models.project_so import (
        ALLOC_RESERVE_SOURCES,
        ProjectSalesOrderLine,
        SOLineAllocation,
    )
    from app.services.project_supply_service import (
        ProjectSupplyService,
        _hold_product,
        held_qty_expr,
    )
    from app.services.scm.supply_assignment import KIND_ON_HAND, Hold

    original = ProjectSupplyService._hold_query

    def no_holds(self, product_ids, *, exclude_line_ids, entities=None):
        # Owner, 27 Oct ~18:15 (Q3): Borrow works like today and keeps holding; only a
        # Reserve stops.
        return original(
            self, product_ids, exclude_line_ids=exclude_line_ids, entities=entities
        ).filter(SOLineAllocation.source_type.notin_(ALLOC_RESERVE_SOURCES))

    from app.services.scm.stock_debt_service import StockDebtService

    original_holds = StockDebtService._holds

    def with_routes(self, product_ids, line_keys, **kwargs):
        # Owner Q1 (a): the Reserve still lets its line draw the bin it names, at the
        # line's own date, in date order - a ROUTE (`Hold.route`), not a hold.
        out = original_holds(self, product_ids, line_keys, **kwargs)
        if not line_keys:
            return out
        span = kwargs.get("span")
        supply_rows = kwargs.get("supply_rows") or {}
        rows = (
            original(
                self.supply,
                [str(pid) for pid in product_ids],
                exclude_line_ids=None,
                entities=(
                    ProjectSalesOrderLine.core_sales_order_line_id,
                    SOLineAllocation.warehouse_id,
                    held_qty_expr(),
                    Warehouse.warehouse_code,
                    _hold_product,
                ),
            )
            .join(Warehouse, Warehouse.id == SOLineAllocation.warehouse_id)
            .filter(
                ProjectSalesOrderLine.core_sales_order_line_id.in_(list(line_keys)),
                SOLineAllocation.source_type.in_(ALLOC_RESERVE_SOURCES),
            )
            .order_by(
                SOLineAllocation.confirmed_at,
                SOLineAllocation.created_at,
                SOLineAllocation.id,
            )
            .all()
        )
        for core_line_id, warehouse_id, qty, code, product_id in rows:
            key = f"on_hand:{warehouse_id}"
            # The same rule `_holds` applies to a pin: a bin in the span the read found
            # empty covers nobody (STOCK-DEBT-STALE-PIN).
            in_span_empty = span is not None and str(warehouse_id) in span and key not in {
                e.key for e in supply_rows.get(str(product_id), []) if e.kind == KIND_ON_HAND
            }
            if float(qty or 0) <= 0 or in_span_empty:
                continue
            out.append(
                Hold(
                    line_key=str(core_line_id), supply_key=key, qty=float(qty),
                    kind=KIND_ON_HAND, warehouse=code, route=True,
                )
            )
        return out

    ProjectSupplyService._hold_query = no_holds
    StockDebtService._holds = with_routes
    try:
        yield
    finally:
        ProjectSupplyService._hold_query = original
        StockDebtService._holds = original_holds


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
    parser.add_argument("--company", default="SRT", help="company code the page reads as")
    args = parser.parse_args()
    focus_products = set(args.product or ["CB4702"])
    focus_sos = set(args.so or ["SO400884", "SO426986"])

    from sqlalchemy import text

    # The scope filter is a session listener the API installs at startup; without it, and
    # without a scope on the session, `goods_chain`'s company predicate compiles to false
    # and every transferred-SPO / PO placement chain reads nothing (crew, 27 Oct). Same
    # pattern as `scripts/dealer_targets_dry_run.py`.
    from app.services import company_scope as scope_module

    scope_module.register_company_scope_listeners()
    from app.database import SessionLocal
    from app.models.base import company_scope

    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        company_id = db.execute(
            text("select id from companies where code = :c"), {"c": args.company}
        ).scalar()
        if not company_id:
            raise SystemExit(f"no company with code {args.company}")
        with company_scope(db, frozenset({str(company_id)})):
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
