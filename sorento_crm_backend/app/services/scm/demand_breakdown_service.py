"""Which orders a planned buy is actually for.

> "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh, i will
>  want to see in the reorder planning, what's the demand quantity, where it comes from, is
>  it project / retail"

A recommendation names a POOL, and pooled netting is the reason a shortage at BRW-IB is
bought into BRW. That is correct and completely opaque from the row alone: the planner sees
a location they did not order for, and a quantity larger than the order they remember.

This lists the open order lines the number was built from - order, location, class, quantity,
when it is needed - including the ones that named no location and were attributed here. It
explains, it never re-derives: the same filter `scm.committed_v` applies, so the sum of these
lines IS the committed figure the engine netted.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate

# One screen's worth. A pool with thousands of lines is a reading problem, not a listing
# problem, and the total is reported separately so the cap is never silent.
DEFAULT_LIMIT = 200


def demand_for_recommendation(db: Session, rec_id: str,
                              limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Open demand behind one recommendation, newest-needed first."""
    rec = db.execute(text(
        "SELECT product_id::text AS product_id, warehouse_id::text AS warehouse_id, "
        "       rec_type, inputs "
        "FROM scm.reorder_recommendation WHERE id = :id"
    ), {"id": rec_id}).mappings().first()
    if rec is None:
        return {"lines": [], "total": 0, "shown": 0, "committed_total": 0.0,
                "unlocated_total": 0.0, "locations": []}

    # The pool the row was planned against: a location with no pool pointer is its own pool,
    # which is what makes a single-location plan and a pooled one the same query.
    members = [r[0] for r in db.execute(text(
        "SELECT id::text FROM warehouses "
        "WHERE COALESCE(pool_warehouse_id, id)::text = :pool"
    ), {"pool": rec["warehouse_id"]}).fetchall()] if rec["warehouse_id"] else []

    # Unlocated demand was attributed to exactly one location per product, so it belongs to
    # this row only when THIS row is the one carrying it.
    include_unlocated = bool((rec["inputs"] or {}).get("unlocated_demand"))

    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="dbk")
    qty = ("GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
           "         - COALESCE(sol.qty_delivered, 0), 0)")
    where_loc = "sol.warehouse_id::text = ANY(:members)"
    if include_unlocated:
        where_loc = f"({where_loc} OR sol.warehouse_id IS NULL)"

    params: dict[str, Any] = {"pid": rec["product_id"], "members": members, **co_params}
    sql = f"""
        SELECT so.so_number, so.order_type, so.demand_class, so.order_date,
               sol.required_date, w.warehouse_code,
               {qty} AS qty
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        LEFT JOIN warehouses w ON w.id = sol.warehouse_id
        WHERE sol.product_id::text = :pid
          AND so.status = 'open' AND sol.line_status = 'open'
          AND sol.purchasing_status <> 'covered'
          AND {qty} > 0
          AND {where_loc}
          {("AND " + co) if co else ""}
    """
    rows = db.execute(text(
        sql + " ORDER BY sol.required_date NULLS LAST, so.so_number LIMIT :limit"
    ), {**params, "limit": max(1, int(limit or DEFAULT_LIMIT))}).mappings().all()
    totals = db.execute(text(
        f"SELECT count(*) AS n, COALESCE(sum(qty), 0) AS committed, "
        f"       COALESCE(sum(qty) FILTER (WHERE warehouse_code IS NULL), 0) AS unlocated "
        f"FROM ({sql}) t"
    ), params).mappings().first()

    lines = [
        {
            "so_number": r["so_number"],
            # The location the ORDER named, or the fact that it named none. "-" would read
            # as missing data; this is a fact about the order.
            "warehouse_code": r["warehouse_code"],
            "is_unlocated": r["warehouse_code"] is None,
            "order_type": r["order_type"],
            "demand_class": r["demand_class"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
            "required_date": r["required_date"].isoformat() if r["required_date"] else None,
            "qty": float(r["qty"] or 0),
        }
        for r in rows
    ]
    return {
        "lines": lines,
        "total": int(totals["n"] or 0),
        "shown": len(lines),
        "committed_total": float(totals["committed"] or 0),
        "unlocated_total": float(totals["unlocated"] or 0),
        # Where the demand actually sits, so "why BRW when I ordered for BRW-IB" is answered
        # by the row itself rather than by opening every order.
        "locations": sorted({(r["warehouse_code"] or "No location") for r in rows}),
    }
