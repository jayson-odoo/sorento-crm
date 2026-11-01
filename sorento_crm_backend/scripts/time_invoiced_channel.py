"""Time the Invoiced tab (Sales & outstanding > Invoiced) with and without its Channel column.

INVOICED-CHANNEL-PERF (`documentation/plans/sales/PLAN-invoiced-channel-perf-01nov.md`). Runs the
report engine in-process over the database `DATABASE_URL` names (read only: it only SELECTs), for
one day and one month, three ways:

- ``all``: every detail column, as the screen asks (`ReportPage.tsx` sends an empty column list);
- ``channel``: the Channel column alone;
- ``no_channel``: every detail column except Channel.

Each is run ``--runs`` times (default 3) and the seconds are printed, with the 1-minute load average
before each case. Run it on main and on the lane head against the same database to compare.

    cd sorento_crm_backend
    venv/bin/python -m scripts.time_invoiced_channel --day 2026-10-15 --month 2026-10 \
        --company <company uuid>

`--company` defaults to the company with the most billing lines in the month.
"""
from __future__ import annotations

import argparse
import calendar
import os
import time
from datetime import date
from typing import Dict, List, Optional


def _period(start: date, end: date) -> Dict[str, str]:
    return {"kind": "custom", "from": start.isoformat(), "to": end.isoformat()}


def _default_company(db, start: date, end: date) -> str:
    import sqlalchemy as sa

    row = db.execute(
        sa.text(
            "SELECT d.company_id FROM finance.billing_documents d "
            "JOIN finance.billing_document_lines l ON l.document_id = d.id "
            "WHERE d.doc_date BETWEEN :a AND :b GROUP BY 1 ORDER BY count(*) DESC LIMIT 1"
        ),
        {"a": start, "b": end},
    ).first()
    if row is None:
        raise SystemExit("no billing lines in that month")
    return str(row[0])


def _time_case(db, definition, company: str, period: Dict[str, str], columns: List[str], runs: int):
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine

    params = {"period": period, "date_basis": "order_date"}
    view = ReportViewConfig.model_validate(
        {
            "params": params,
            "detail": {"columns": columns, "order": columns, "sort": None},
            "pivot": dict(definition.default_view["pivot"]),
        }
    )
    seconds = []
    rows = 0
    for _ in range(runs):
        started = time.perf_counter()
        result = engine.run(db, definition, view.params, view, company_grants=frozenset({company}))
        seconds.append(time.perf_counter() - started)
        rows = result.row_count
        db.rollback()
    return seconds, rows


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--company", default=None)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--skip-month", action="store_true", help="time the day only")
    args = parser.parse_args(argv)

    from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
    from app.database import SessionLocal
    from app.services.reports.datasets.billing_document_lines import ASK_DEFINITION

    day = date.fromisoformat(args.day)
    year, month = (int(x) for x in args.month.split("-"))
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    all_columns = [c.key for c in ASK_DEFINITION.dataset.columns]
    cases = {
        "all": [],
        "channel": ["channel"],
        "no_channel": [k for k in all_columns if k != "channel"],
    }
    periods = [("day", _period(day, day))]
    if not args.skip_month:
        periods.append(("month", _period(month_start, month_end)))

    db = SessionLocal()
    try:
        company = args.company or _default_company(db, month_start, month_end)
        import sqlalchemy as sa

        print("server jit:", db.execute(sa.text("SHOW jit")).scalar_one())
        db.rollback()
        print(f"{'period':<6} {'case':<10} {'rows':>6} {'load':>6}  seconds per run")
        for period_name, period in periods:
            for case, columns in cases.items():
                load = os.getloadavg()[0]
                seconds, rows = _time_case(db, ASK_DEFINITION, company, period, columns, args.runs)
                runs = "  ".join(f"{s:7.2f}" for s in seconds)
                print(f"{period_name:<6} {case:<10} {rows:>6} {load:>6.1f}  {runs}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
