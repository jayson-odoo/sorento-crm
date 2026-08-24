"""SCM M2 golden-set derivation (INDEPENDENT reference).

Recomputes the blessed demand / ABC / XYZ numbers in tests/scm/fixtures/golden_m2.json
straight from the REAL historical DO ``order_lines`` in the local prod-copy DB, using
raw SQL + Python ``statistics`` - deliberately a DIFFERENT code path than
``app/services/scm/analytics_service.py`` so the golden test isn't circular. Run it
once to (re)bless the fixture; the engine is then written to reproduce these frozen
numbers.

    venv/bin/python scripts/scm_m2_golden_derive.py

Method (see golden_m2.json._derivation for the canonical prose):
  * as_of = 2026-06-01, window = 90 days = ~13 trailing 7-day (weekly) buckets.
  * bucket idx = floor((as_of - order_date - 1) / 7), newest-first (0 = last 7 days).
  * bucket demand = SUM(order_lines.quantity) over non-cancelled orders in the week.
  * avg_daily_demand = baseline_total / 90 ; demand_cv = pstdev/mean of the 13 weekly
    totals. Baseline = plain sum in the X (CV<=0.5) and Z (CV>1.0) bands; trimmed mean * n
    ONLY in the Y band (0.5<CV<=1.0, drop top+bottom 10% => floor(0.10*13)=1 period each
    tail). Z (lumpy) is kept whole so a single-spike SKU is not trimmed to a zero baseline.
  * method = 'trimmed_mean' only when 0.5<cv<=1.0, else 'mean'.
  * XYZ: X<=0.5, Y<=1.0, Z>1.0.  ABC: rank costed keys by trailing-365d qty*cost,
    cumulative-inclusive A<=80% / B<=95% / C=rest.
"""
from __future__ import annotations

import os
import re
import statistics as st
from datetime import date, timedelta

from sqlalchemy import create_engine, text

AS_OF = date(2026, 6, 1)
WINDOW_DAYS = 90
BUCKET_DAYS = 7
NUM_BUCKETS = (WINDOW_DAYS + BUCKET_DAYS - 1) // BUCKET_DAYS  # 13
ANNUAL_DAYS = 365
# Per-bucket day counts, newest-first: buckets 0..11 are full 7-day weeks, the
# oldest (index 12) is the short 6-day remainder clamped to the 90-day window
# start. CV is computed over per-bucket DAILY RATES using these lengths so the
# short oldest bucket does not structurally inflate variability (S3).
BUCKET_DAY_LENGTHS = [
    min(BUCKET_DAYS * (i + 1), WINDOW_DAYS) - BUCKET_DAYS * i for i in range(NUM_BUCKETS)
]  # == [7,7,7,7,7,7,7,7,7,7,7,7,6]


def _weekly_baseline(buckets: list[float]) -> dict:
    """Independent reimplementation of the engine's bucket_stats over weekly totals.

    CV is measured over per-bucket DAILY RATES (bucket_qty / bucket_days) so the
    short oldest bucket (6 days) does not structurally inflate variability (S3);
    the baseline maths stays on the raw weekly totals. Trim ONLY the moderate-
    variability Y band (0.5<CV<=1.0). X (CV<=0.5) and Z (CV>1.0) both use the plain
    mean (baseline == total): lumpy Z demand is the signal and must not be trimmed
    to a zero baseline.
    """
    n = len(buckets)
    total = sum(buckets)
    rates = [buckets[i] / BUCKET_DAY_LENGTHS[i] for i in range(n)] if n else []
    rate_mean = (sum(rates) / n) if n else 0.0
    cv = (st.pstdev(rates) / rate_mean) if rate_mean else 0.0
    if cv <= 0.5 or cv > 1.0:  # X band or Z band -> plain mean
        return {"total": total, "cv": cv, "method": "mean", "baseline_total": total}
    # Y band only -> trimmed mean
    trim = int(n * 0.10)
    kept = sorted(buckets)[trim: n - trim] if trim else list(buckets)
    kept_mean = (sum(kept) / len(kept)) if kept else (total / n if n else 0.0)
    return {"total": total, "cv": cv, "method": "trimmed_mean",
            "baseline_total": kept_mean * n}


def _pg_url() -> str:
    for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
        if line.startswith("DATABASE_URL"):
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            return re.sub(r"^postgresql\+\w+", "postgresql", raw)
    raise SystemExit("no DATABASE_URL")


def main() -> None:
    eng = create_engine(_pg_url())
    lo = AS_OF - timedelta(days=WINDOW_DAYS)
    with eng.connect() as c:
        demand_skus = [
            ("WESERP10B", "BRW"), ("B2155-NL-BLUE", "BRW-IB"), ("ST-(L)-PCT", "BRW-IB"),
            ("FT-03", "BRW-IB"), ("SRTPTFE1207", "BRW"), ("C-FH24", "BRW-IR"),
        ]
        print(f"# demand (as_of={AS_OF}, {NUM_BUCKETS} weekly buckets)")
        for code, wh in demand_skus:
            # per-day outflow, bucketed into weeks in Python (independent of the engine SQL)
            rows = c.execute(text("""
                SELECT o.order_date::date AS d, SUM(ol.quantity) AS q
                FROM order_lines ol JOIN orders o ON o.id=ol.order_id
                JOIN products p ON p.id=ol.product_id JOIN warehouses w ON w.id=ol.warehouse_id
                WHERE o.is_cancelled=false AND p.product_code=:code AND w.warehouse_code=:wh
                  AND o.order_date>=:lo AND o.order_date<:as_of
                GROUP BY o.order_date::date
            """), {"lo": lo, "as_of": AS_OF, "code": code, "wh": wh}).fetchall()
            b = [0.0] * NUM_BUCKETS  # newest-first: index 0 = most recent 7 days
            for r in rows:
                diff = (AS_OF - r.d).days
                idx = (diff - 1) // BUCKET_DAYS
                idx = 0 if idx < 0 else (NUM_BUCKETS - 1 if idx >= NUM_BUCKETS else idx)
                b[idx] += float(r.q)
            s = _weekly_baseline(b)
            cv = s["cv"]
            avg_daily = s["baseline_total"] / WINDOW_DAYS
            xyz = "X" if cv <= 0.5 else ("Y" if cv <= 1.0 else "Z")
            print(f"  {code:16s}@{wh:8s} buckets={[int(x) for x in b]}")
            print(f"  {'':16s} {'':8s} total={int(s['total'])} baseline={s['baseline_total']:.2f} "
                  f"avg_daily={avg_daily:.4f} cv={cv:.4f} method={s['method']} xyz={xyz}")

        print("# abc (costed keys, trailing 365d)")
        rows = c.execute(text("""
            WITH val AS (
              SELECT p.product_code, w.warehouse_code,
                     SUM(ol.quantity*p.cost_price) av
              FROM order_lines ol JOIN orders o ON o.id=ol.order_id
              JOIN products p ON p.id=ol.product_id LEFT JOIN warehouses w ON w.id=ol.warehouse_id
              WHERE o.is_cancelled=false AND o.order_date>=:lo AND o.order_date<:as_of
                AND p.cost_price>0
              GROUP BY 1,2)
            SELECT product_code, warehouse_code, av,
              100.0*SUM(av) OVER (ORDER BY av DESC, product_code, warehouse_code
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)/SUM(av) OVER () cum,
              100.0*(SUM(av) OVER (ORDER BY av DESC, product_code, warehouse_code
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - av)/SUM(av) OVER () prev_cum
            FROM val ORDER BY av DESC
        """), {"lo": AS_OF - timedelta(days=ANNUAL_DAYS), "as_of": AS_OF}).fetchall()
        want = {(c1, w1) for c1, w1 in demand_skus}
        for r in rows:
            if (r.product_code, r.warehouse_code) in want:
                # ABC decided on the cumulative BEFORE this item is added (B1): the
                # boundary-crossing item belongs to the HIGHER class, and rank-1
                # (prev_cum=0) is ALWAYS A.
                abc = "A" if r.prev_cum <= 80 else ("B" if r.prev_cum <= 95 else "C")
                print(f"  {r.product_code:16s}@{r.warehouse_code:8s} "
                      f"cum={r.cum:.2f} prev_cum={r.prev_cum:.2f} abc={abc}")
    eng.dispose()


if __name__ == "__main__":
    main()
