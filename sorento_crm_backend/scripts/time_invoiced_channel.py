"""Time the Invoiced tab (Sales & outstanding > Invoiced), all columns, Channel only, or per column.

INVOICED-CHANNEL-PERF (`documentation/plans/sales/PLAN-invoiced-channel-perf-01nov.md`). Runs the
report engine in-process over the database `DATABASE_URL` names (read only: it only SELECTs), for
one day and one month.

Timing cases (`--cases`, comma separated; default ``all,channel,no_channel``):

- ``all``: every detail column, as the screen asks (`ReportPage.tsx` sends an empty column list);
- ``channel``: the Channel column alone;
- ``no_channel``: every detail column except Channel;
- ``each``: every per-row detail column alone, one case per column (finds the slow one);
- ``summary``: the summary (pivot) alone, as the screen opens it (month down, all across); ``rows``
  is its number of row values (a month is one row, so expect about zero seconds);
- ``summary_channel``: the summary alone, grouped by Channel;
- ``only:<column key>`` (e.g. ``only:sales_agent``): that column alone (``each`` prints these).

Each case runs ``--runs`` times (default 3); the seconds are printed with the 1-minute load average.
The FIRST case of a period pays the cold cache for every table the run reads (on a cold database
that was most of an all-columns run); ``--warmup`` runs one untimed all-columns pass first, so the
cases compare warm against warm. Run once without it to see the cold figure.

Tie-out mode (`--tieout`): no timing. For every per-row detail column, the whole period's lines
(uncapped) as (line id, value), printed as a count and an md5. Run it on main and on the lane head
against the same database: every line must match.

    cd sorento_crm_backend
    venv/bin/python -m scripts.time_invoiced_channel --day 2026-10-15 --month 2026-10
    venv/bin/python -m scripts.time_invoiced_channel --day 2026-10-15 --month 2026-10 \
        --skip-month --cases each --runs 1
    venv/bin/python -m scripts.time_invoiced_channel --day 2026-10-15 --month 2026-10 \
        --skip-month --tieout

`--company` defaults to the company with the most billing lines in the month.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
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


def _view(definition, period: Dict[str, str], columns: List[str], pivot: Optional[dict] = None):
    from app.schemas.report import ReportViewConfig

    return ReportViewConfig.model_validate(
        {
            "params": {"period": period, "date_basis": "order_date"},
            "detail": {"columns": columns, "order": columns, "sort": None},
            "pivot": pivot or dict(definition.default_view["pivot"]),
        }
    )


def _time_case(db, definition, company: str, period: Dict[str, str], case: str, columns, runs: int):
    from app.services.reports import engine

    pivot = None
    if case == "summary_channel":
        pivot = {"rows": "channel", "cols": "all", "measures": ["qty", "amount"]}
    view = _view(definition, period, columns or [], pivot)
    grants = frozenset({company})
    seconds = []
    rows = 0
    for _ in range(runs):
        started = time.perf_counter()
        if case in ("summary", "summary_channel"):
            # The summary (pivot) alone; `rows` is its number of row values.
            summary = engine.run_summary(db, definition, view.params, view, company_grants=grants)
            rows = len(summary.row_values)
        else:
            rows = engine.run(db, definition, view.params, view, company_grants=grants).row_count
        seconds.append(time.perf_counter() - started)
        db.rollback()
    return seconds, rows


def _row_columns(definition) -> List[str]:
    """The detail columns that have a value per line (a distinct count or a ratio is summary
    only, as `engine._select_columns` drops it)."""
    return [c.key for c in definition.dataset.columns if c.agg == "sum" and c.ratio_of is None]


def _tieout(db, definition, company: str, period_name: str, period: Dict[str, str]) -> None:
    from app.models.finance import BillingDocumentLine
    from app.services.reports import engine

    view = _view(definition, period, [])
    ctx = engine.resolve(db, definition, view.params, company_grants=frozenset({company}))
    for key in _row_columns(definition):
        column = ctx.dataset.column(key)
        started = time.perf_counter()
        with engine._unscoped(ctx):
            stmt = engine._detail_statement(ctx, [column], BillingDocumentLine.id.label("__line_id"))
            stmt = stmt.order_by(None).order_by(BillingDocumentLine.id)
            digest = hashlib.md5()
            count = 0
            for row in db.execute(stmt).mappings():
                digest.update(f"{row['__line_id']}:{row[key]!r}\n".encode())
                count += 1
        print(
            f"{period_name:<6} {key:<16} {count:>7}  {digest.hexdigest()}  "
            f"({time.perf_counter() - started:.1f} s)",
            flush=True,
        )
    db.rollback()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--company", default=None)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cases", default="all,channel,no_channel")
    parser.add_argument(
        "--warmup", action="store_true",
        help="one untimed all-columns run per period first, so the first case does not pay the cold cache",
    )
    parser.add_argument("--tieout", action="store_true", help="per-column count + md5, no timing")
    parser.add_argument("--skip-month", action="store_true", help="the day only")
    parser.add_argument("--skip-day", action="store_true", help="the month only")
    args = parser.parse_args(argv)

    from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
    import sqlalchemy as sa

    from app.database import SessionLocal
    from app.services.reports.datasets.billing_document_lines import ASK_DEFINITION

    day = date.fromisoformat(args.day)
    year, month = (int(x) for x in args.month.split("-"))
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    all_columns = [c.key for c in ASK_DEFINITION.dataset.columns]
    named = {
        "all": [],
        "channel": ["channel"],
        "no_channel": [k for k in all_columns if k != "channel"],
        "summary": None,
        "summary_channel": None,
    }
    cases: List[tuple] = []
    for case in (c.strip() for c in args.cases.split(",") if c.strip()):
        if case == "each":
            cases += [(f"only:{key}", [key]) for key in _row_columns(ASK_DEFINITION)]
        elif case in named and not case.startswith("only:"):
            cases.append((case, named[case]))
        elif case.removeprefix("only:") in all_columns:
            key = case.removeprefix("only:")
            cases.append((f"only:{key}", [key]))
        else:
            raise SystemExit(f"unknown case '{case}'")

    periods = [] if args.skip_day else [("day", _period(day, day))]
    if not args.skip_month:
        periods.append(("month", _period(month_start, month_end)))

    db = SessionLocal()
    try:
        company = args.company or _default_company(db, month_start, month_end)
        print("server jit:", db.execute(sa.text("SHOW jit")).scalar_one())
        db.rollback()
        if args.tieout:
            print(f"{'period':<6} {'column':<16} {'lines':>7}  md5")
            for period_name, period in periods:
                _tieout(db, ASK_DEFINITION, company, period_name, period)
            return
        print(f"{'period':<6} {'case':<20} {'rows':>6} {'load':>6}  seconds per run")
        for period_name, period in periods:
            if args.warmup:
                _time_case(db, ASK_DEFINITION, company, period, "all", [], 1)
            for case, columns in cases:
                load = os.getloadavg()[0]
                seconds, rows = _time_case(db, ASK_DEFINITION, company, period, case, columns, args.runs)
                runs = "  ".join(f"{s:7.2f}" for s in seconds)
                print(f"{period_name:<6} {case:<20} {rows:>6} {load:>6.1f}  {runs}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
