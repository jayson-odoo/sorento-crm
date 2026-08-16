"""The resolver half of the trajectory judgment: read the book, feed the maths.

Keyed ``"{product_id}:{segment}"`` because project and retail are never merged into one
figure (S13d): project demand is erratic and retail stable, and a number spanning both
describes neither. A row's side is its warehouse's segment - the same line the grid's Side
column draws.

What counts as an order here is what was ORDERED (`qty_ordered`) on a dated sales order,
whatever its status today. The trajectory question is about the flow of orders placed, not
about what is still open - a fulfilled order is exactly the evidence of demand the buyer is
asking about.

WHO SOLD IT: `sales_orders` carries no salesperson column, so agents are reported as
absent, never invented (AC-S13d.4: "named absent where the source carries none"). When a
feed lands that carries one, this is the seam it plugs into.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm.customer_label import (
    CUSTOMER_JOIN_ON,
    CUSTOMER_KEY_SQL,
    CUSTOMER_LABEL_SQL,
    customer_key_filter,
)
from app.services.scm.trajectory import (
    DEFAULT_PROJECT_MONTHS,
    DEFAULT_RETAIL_MONTHS,
    MOVEMENT_THRESHOLD_PCT,
    assess_trajectory,
    month_shift as _month_shift,
)

#: Months of series shipped to the popup's line graph: the current year and the one before,
#: so "vs last year" is visible on the chart rather than taken on faith.
SERIES_MONTHS = 24

#: Customers named per product+side. A few the reader can go and look at.
CUSTOMER_SAMPLE = 5


def _windows(db: Session) -> dict[str, int]:
    """The configured windows, from the global planning policy (S13d: config from day 1)."""
    row = db.execute(text(
        "SELECT trajectory_window_retail_months, trajectory_window_project_months "
        "FROM scm.reorder_policy WHERE scope_type = 'global' AND is_active = true "
        "ORDER BY priority DESC NULLS LAST LIMIT 1"
    )).first()
    return {
        "retail_months": int(row[0]) if row and row[0] else DEFAULT_RETAIL_MONTHS,
        "project_months": int(row[1]) if row and row[1] else DEFAULT_PROJECT_MONTHS,
    }


_SERIES_SQL = """
WITH pairs AS (
    SELECT DISTINCT r.product_id, COALESCE(w.segment, 'project') AS segment
    FROM scm.reorder_recommendation r
    LEFT JOIN warehouses w ON w.id = r.warehouse_id
    WHERE r.run_id = CAST(:run_id AS uuid)
)
SELECT sol.product_id::text AS product_id,
       COALESCE(w.segment, 'project') AS segment,
       to_char(date_trunc('month', so.order_date), 'YYYY-MM') AS month,
       SUM(sol.qty_ordered) AS qty
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
LEFT JOIN warehouses w ON w.id = sol.warehouse_id
JOIN pairs pr ON pr.product_id = sol.product_id
            AND pr.segment = COALESCE(w.segment, 'project')
WHERE so.order_date >= :since AND so.order_date < :until
  {co}
GROUP BY sol.product_id, COALESCE(w.segment, 'project'),
         date_trunc('month', so.order_date)
"""

_CUSTOMERS_SQL = f"""
WITH pairs AS (
    SELECT DISTINCT r.product_id, COALESCE(w.segment, 'project') AS segment
    FROM scm.reorder_recommendation r
    LEFT JOIN warehouses w ON w.id = r.warehouse_id
    WHERE r.run_id = CAST(:run_id AS uuid)
)
SELECT product_id, segment, customer_name, customer_key, qty, last_order_date FROM (
    SELECT sol.product_id::text AS product_id,
           COALESCE(w.segment, 'project') AS segment,
           {CUSTOMER_LABEL_SQL} AS customer_name,
           {CUSTOMER_KEY_SQL} AS customer_key,
           SUM(sol.qty_ordered) AS qty,
           MAX(so.order_date) AS last_order_date,
           ROW_NUMBER() OVER (
               PARTITION BY sol.product_id, COALESCE(w.segment, 'project')
               ORDER BY SUM(sol.qty_ordered) DESC
           ) AS rn
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    LEFT JOIN warehouses w ON w.id = sol.warehouse_id
    LEFT JOIN customers c ON {CUSTOMER_JOIN_ON}
    JOIN pairs pr ON pr.product_id = sol.product_id
                AND pr.segment = COALESCE(w.segment, 'project')
    WHERE so.order_date >= :since AND so.order_date < :until
      {{co}}
    -- Grouped on the KEY, not the printed name: two customers can share a name, and the
    -- drill below has to be able to open exactly the row that was clicked.
    GROUP BY sol.product_id, COALESCE(w.segment, 'project'),
             {CUSTOMER_LABEL_SQL}, {CUSTOMER_KEY_SQL}
) t WHERE rn <= :sample
"""

#: The orders behind ONE of those rows, newest first.
#:
#: Same window and the same joins as `_CUSTOMERS_SQL` on purpose: a drill that selected a
#: different set from the row it opened would be a second definition of the same fact, and
#: the quantities would stop adding up to the row above them.
_CUSTOMER_ORDERS_SQL = """
    SELECT so.so_number, so.order_date, sol.qty_ordered AS qty, sol.unit_price,
           w.warehouse_code
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    LEFT JOIN warehouses w ON w.id = sol.warehouse_id
    WHERE sol.product_id::text = :product_id
      AND COALESCE(w.segment, 'project') = :segment
      AND so.order_date >= :since AND so.order_date < :until
      AND {customer}
      {co}
"""


def trajectory_for_run(
    db: Session, run_id: str, *, as_of: Optional[date] = None
) -> dict[str, Any]:
    """Trajectory facts for every (product, side) pair the run touches."""
    as_of = as_of or date.today()
    windows = _windows(db)
    # The month the run sits in is excluded: a window ending mid-month compares a partial
    # month against whole ones and reads as demand falling every single time.
    until = _month_shift(as_of, 0)
    since = _month_shift(until, -SERIES_MONTHS)

    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="trj")
    co_clause = f"AND {co}" if co else ""
    params = {"run_id": run_id, "since": since, "until": until, **co_params}

    monthly: dict[str, dict[str, float]] = {}
    for r in db.execute(
        text(_SERIES_SQL.format(co=co_clause)), params
    ).mappings().all():
        key = f"{r['product_id']}:{r['segment']}"
        monthly.setdefault(key, {})[r["month"]] = float(r["qty"] or 0)

    customers: dict[str, list[dict[str, Any]]] = {}
    for r in db.execute(
        text(_CUSTOMERS_SQL.format(co=co_clause)),
        {**params, "sample": CUSTOMER_SAMPLE},
    ).mappings().all():
        key = f"{r['product_id']}:{r['segment']}"
        customers.setdefault(key, []).append(
            {
                "customer_name": r["customer_name"],
                # What the drill into this row's own orders is keyed by. On the row so the
                # FE never has to reconstruct an identity from a printed name.
                "customer_key": r["customer_key"],
                "qty": float(r["qty"] or 0),
                "last_order_date": (
                    r["last_order_date"].isoformat() if r["last_order_date"] else None
                ),
            }
        )

    def window_sum(series: dict[str, float], start: date, months: int) -> float:
        total = 0.0
        for i in range(months):
            m = _month_shift(start, i)
            total += series.get(f"{m.year:04d}-{m.month:02d}", 0.0)
        return total

    out: dict[str, Any] = {
        "windows": windows,
        # How far back the monthly series reaches. Stated rather than left for the screen to
        # know: the trend popover's empty state says "no orders dated in the last N months",
        # and a literal 24 there is a second copy of this constant that is free to disagree
        # with it the day the window changes.
        "series_months": SERIES_MONTHS,
        "movement_threshold_pct": MOVEMENT_THRESHOLD_PCT,
        "series": {},
    }
    for key, series in monthly.items():
        segment = key.rsplit(":", 1)[1]
        months = (
            windows["project_months"] if segment == "project"
            else windows["retail_months"]
        )
        recent_start = _month_shift(until, -months)
        prev_start = _month_shift(until, -2 * months)
        year_start = _month_shift(recent_start, -12)

        recent = window_sum(series, recent_start, months)
        previous = window_sum(series, prev_start, months)
        # Only claimed when the series actually reaches back that far; a book younger
        # than a year must say "no year-ago figure", not "zero last year".
        year_ago = (
            window_sum(series, year_start, months)
            if year_start >= since else None
        )

        t = assess_trajectory(recent=recent, previous=previous, year_ago=year_ago)
        out["series"][key] = {
            "verdict": t.verdict,
            "recent_qty": t.recent_qty,
            "previous_qty": t.previous_qty,
            "change_pct": t.change_pct,
            "year_ago_qty": t.year_ago_qty,
            "year_change_pct": t.year_change_pct,
            "window_months": months,
            "months": [
                {"month": m, "qty": q} for m, q in sorted(series.items())
            ],
            "customers": customers.get(key, []),
            # sales_orders carries no salesperson column. Absent, never invented.
            "agents": [],
            "agents_available": False,
        }
    return out


#: One screen's worth of orders behind a customer row. The total is reported beside it so
#: the cap is never silent.
DEFAULT_ORDER_LIMIT = 20

#: The (product, side) pairs THIS run planned - the same set `_CUSTOMERS_SQL` builds its
#: rows from, asked about one pair.
_RUN_PLANNED_PAIR_SQL = """
    SELECT 1
    FROM scm.reorder_recommendation r
    LEFT JOIN warehouses w ON w.id = r.warehouse_id
    WHERE r.run_id::text = :run_id
      AND r.product_id::text = :product_id
      AND COALESCE(w.segment, 'project') = :segment
    LIMIT 1
"""


def orders_for_customer(
    db: Session, *, run_id: str, product_id: str, segment: str, customer_key: str,
    limit: int = DEFAULT_ORDER_LIMIT, as_of: Optional[date] = None,
) -> dict[str, Any]:
    """The sales orders behind one Who-bought-it row, newest first.

    > "sells RM 0.94?"

    A name and a quantity say who buys the product; they do not say at what price, and
    that is the question the row is opened to answer. Same 24-month window and the same
    joins as the row itself, so the lines add up to the quantity above them.

    BOUNDED BY THE RUN, not merely reached through one. The row this drills from was built
    from the run's own (product, side) pairs, so the drill is refused for any other pair:
    checking only that the run may be seen turned a visible run into a way to read the
    order book for a product it never planned, by naming that product in the query string.
    """
    if db.execute(text(_RUN_PLANNED_PAIR_SQL), {
        "run_id": run_id, "product_id": product_id, "segment": segment,
    }).first() is None:
        raise AppException(
            status_code=404,
            message="This plan has no row for that product on that side.",
            code="NOT_FOUND",
        )

    as_of = as_of or date.today()
    until = _month_shift(as_of, 0)
    since = _month_shift(until, -SERIES_MONTHS)

    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="cus")
    customer_sql, customer_params = customer_key_filter(customer_key)
    sql = _CUSTOMER_ORDERS_SQL.format(
        customer=customer_sql, co=(f"AND {co}" if co else ""),
    )
    params: dict[str, Any] = {
        "product_id": product_id, "segment": segment,
        "since": since, "until": until, **customer_params, **co_params,
    }
    rows = db.execute(text(
        sql + " ORDER BY so.order_date DESC NULLS LAST, so.so_number DESC LIMIT :limit"
    ), {**params, "limit": max(1, int(limit or DEFAULT_ORDER_LIMIT))}).mappings().all()
    total = db.execute(
        text(f"SELECT count(*) FROM ({sql}) t"), params
    ).scalar() or 0

    lines = [
        {
            "so_number": r["so_number"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
            "qty": float(r["qty"] or 0),
            # Absent, never zero: an order line the extract carries no price for is a
            # price we do not know, and 0.00 is a price we would be claiming.
            "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else None,
            "warehouse_code": r["warehouse_code"],
        }
        for r in rows
    ]
    return {"lines": lines, "total": int(total), "shown": len(lines)}
