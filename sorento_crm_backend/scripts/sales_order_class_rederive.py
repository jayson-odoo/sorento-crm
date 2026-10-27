#!/usr/bin/env python3
"""Re-derive every sales order's class from the dated agent classes (SALES-UNIFIED round 3,
owner rulings Q8 and Q10 (a)): the stated order type, else the agent's class on the order's
date, else nothing.

Dry run by default: prints, per agent per month, how many orders and how much RM would move
from which class to which, and the totals. Writes nothing. `--apply` writes the same moves in
one transaction (run it only after the owner has read the dry run). Re-running is a no-op.

    python -m scripts.sales_order_class_rederive [--company SRT] [--from 2024-01] [--to 2026-10] [--apply]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from decimal import Decimal


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", help="company code (all companies when absent)")
    parser.add_argument("--from", dest="since", help="first month, YYYY-MM")
    parser.add_argument("--to", dest="until", help="last month, YYYY-MM")
    parser.add_argument("--apply", action="store_true", help="write the moves")
    args = parser.parse_args(argv)

    import app.main  # noqa: F401  (registers every model)
    from app.database import SessionLocal
    from app.models.base import company_scope
    from app.models.company import Company
    from app.services.sales import agent_class_service as svc
    from app.services.sales.set_apart_service import parse_month

    db = SessionLocal()
    try:
        with company_scope(db, None):
            company_id = None
            if args.company:
                company_id = db.query(Company.id).filter(Company.code == args.company).scalar()
                if company_id is None:
                    print(f"unknown company code {args.company}", file=sys.stderr)
                    return 2
            moves = svc.rederive(
                db,
                company_id=str(company_id) if company_id else None,
                from_month=parse_month(args.since, "from") if args.since else None,
                to_month=parse_month(args.until, "to") if args.until else None,
                apply=args.apply,
            )
            totals = defaultdict(lambda: [0, Decimal(0)])
            print("agent\tmonth\tfrom\tto\torders\tRM")
            for m in moves:
                print(f"{m.agent or '(no agent)'}\t{m.month}\t{m.before or '-'}\t{m.after or '-'}\t{m.orders}\t{m.amount:,.2f}")
                totals[(m.before, m.after)][0] += m.orders
                totals[(m.before, m.after)][1] += m.amount
            print()
            for (before, after), (n, amount) in sorted(totals.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
                print(f"TOTAL {before or '-'} -> {after or '-'}: {n} orders, RM {amount:,.2f}")
            if args.apply:
                db.commit()
                print("applied")
            else:
                db.rollback()
                print("dry run: nothing written")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
