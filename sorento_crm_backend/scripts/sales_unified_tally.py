#!/usr/bin/env python3
"""The CRM side of the tally against the AutoCount reports (SALES-UNIFIED; owner, 27 Oct: "the
figures should tally between the provided report and our system, simple as that").

Read-only. Runs the SAME report definitions the screens and the chatbot run (no second
calculation) and prints, for one company and period:

1. Sales by sales type (the blocks), with ALL SALES and the AutoCount-report total (Dealer +
   Project team + Set apart), and, when given, the AutoCount figures beside them and the gap.
2. Sales by debtor type by sales agent: one line per block, agent and debtor type.
3. Top selling items (`--items N`).
4. `EXPLAIN ANALYZE` timing of the sales-type query for the period.

    python -m scripts.sales_unified_tally --company SRT --from 2026-01-01 --to 2026-01-31 \\
        --autocount dealer=6513047.67 project=6084471.57 set_apart=122232.99 all=14742279.29
"""
from __future__ import annotations

import argparse
import time
from decimal import Decimal


def _run(db, key, company_id, date_from, date_to, rows, cols, measures, **extra):
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine, registry as reg

    params = {
        "date_basis": "order_date",
        "period": {"kind": "custom", "from": date_from, "to": date_to},
        "company": [company_id],
        **extra,
    }
    view = ReportViewConfig.model_validate({
        "params": params, "detail": {"columns": [], "order": []},
        "pivot": {"rows": rows, "cols": cols, "measures": measures},
    })
    return engine.run(db, reg.get(key), params, view, company_grants=frozenset({company_id}))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", required=True, help="company code, e.g. SRT")
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--items", type=int, default=20)
    parser.add_argument("--autocount", nargs="*", default=[], help="key=value: dealer, project, set_apart, all")
    args = parser.parse_args(argv)

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models.base import company_scope
    from app.models.company import Company
    from app.services.sales import invoiced_sales as inv

    autocount = {k: Decimal(v) for k, v in (pair.split("=", 1) for pair in args.autocount)}
    db = SessionLocal()
    try:
        with company_scope(db, None):
            company_id = str(db.query(Company.id).filter(Company.code == args.company).scalar())
            result = _run(db, "sales_by_debtor_type", company_id, args.date_from, args.date_to,
                          "channel", "debtor_type", ["sales_value"])
            pivot = result.layouts.summary
            by_type = {v: Decimal(pivot.row_totals.get(v, {}).get("sales_value") or 0) for v in pivot.row_values}
            labels = dict((label, value) for value, label in inv.SALES_TYPES)
            print(f"== Sales by sales type, {args.company} {args.date_from} to {args.date_to} ==")
            print("sales type\tCRM\tAutoCount\tgap")
            for label, value in labels.items():
                crm = by_type.get(label, Decimal(0))
                ac = autocount.get(value)
                print(f"{label}\t{crm:,.2f}\t{'' if ac is None else f'{ac:,.2f}'}\t{'' if ac is None else f'{crm - ac:,.2f}'}")
            report_total = sum(by_type.get(dict(inv.SALES_TYPES)[k], Decimal(0)) for k in (inv.DEALER, inv.PROJECT, inv.SET_APART))
            all_sales = Decimal(pivot.grand_total.get("sales_value") or 0)
            for name, crm in (("AutoCount report total (Dealer + Project team + Set apart)", report_total), ("ALL SALES", all_sales)):
                ac = autocount.get("all") if name == "ALL SALES" else None
                print(f"{name}\t{crm:,.2f}\t{'' if ac is None else f'{ac:,.2f}'}\t{'' if ac is None else f'{crm - ac:,.2f}'}")

            print("\n== By sales type, sales agent and debtor type ==")
            by_agent = _run(db, "sales_by_debtor_type", company_id, args.date_from, args.date_to,
                            "sales_agent", "debtor_type", ["sales_value"])
            for block in by_agent.layouts.blocks or []:
                summary = block.summary
                labels_row = summary.row_value_labels or {}
                for agent in summary.row_values:
                    for dtype, cell in (summary.cells.get(agent) or {}).items():
                        print(f"{block.title}\t{labels_row.get(agent, agent)}\t{dtype}\t{cell.get('sales_value')}")
                    print(f"{block.title}\t{labels_row.get(agent, agent)}\tTOTAL\t{summary.row_totals.get(agent, {}).get('sales_value')}")

            top = _run(db, "top_selling_items", company_id, args.date_from, args.date_to,
                       "item_code", "year", ["quantity", "sales_value"])
            rows = sorted(
                ((v, top.layouts.summary.row_totals.get(v, {})) for v in top.layouts.summary.row_values),
                key=lambda r: -Decimal(r[1].get("sales_value") or 0),
            )[: args.items]
            print(f"\n== Top {args.items} selling items ==")
            for code, totals in rows:
                print(f"{code}\t{totals.get('quantity')}\t{totals.get('sales_value')}")

            started = time.monotonic()
            _run(db, "sales_by_debtor_type", company_id, args.date_from, args.date_to,
                 "channel", "debtor_type", ["sales_value"])
            print(f"\nsales type run: {time.monotonic() - started:.2f}s")
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
