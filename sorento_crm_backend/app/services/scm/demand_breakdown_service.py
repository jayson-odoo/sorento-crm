"""Which orders a planned buy is actually for.

> "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh, i will
>  want to see in the reorder planning, what's the demand quantity, where it comes from, is
>  it project / retail"

A recommendation names a POOL, and pooled netting is the reason a shortage at BRW-IB is
bought into BRW. That is correct and completely opaque from the row alone: the planner sees
a location they did not order for, and a quantity larger than the order they remember.

This lists the open order lines the number was built from - order, location, class, quantity,
when it is needed, who ordered it and at what price - including the ones that named no
location and were attributed here. It explains, it never re-derives: the same filter
`scm.committed_v` applies, so the sum of these lines IS the committed figure the engine
netted.

SCOPE IS THE ROW'S, NOT THE POOL'S. A plan row is a product AT a location, and it was
netted per location unless the policy turned pooled netting on. Listing the whole pool
regardless answered a question nobody asked - the buyer looking at BRW-BB was shown
BRW-IB's orders and a total larger than the SO figure printed on their own row. So the
scope follows the same switch the engine planned under, and is stated in the header when
it is the pool.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm import reorder_engine as eng
from app.services.scm.customer_label import CUSTOMER_LABEL_SQL
from app.services.scm.demand import PLAN_DEMAND_ORDER_SQL

# One screen's worth. A pool with thousands of lines is a reading problem, not a listing
# problem, and the total is reported separately so the cap is never silent.
DEFAULT_LIMIT = 200

def _scope_for(db: Session, rec) -> tuple[list[str], str, Optional[str]]:
    """The locations this row's demand may be drawn from, and what to call that set.

    The engine nets per POOL only when the policy says siblings may cover for one another
    (`reorder_run_service._pool_netting_enabled`, resolved per product), and per LOCATION
    otherwise. This reads the same switch the same way, so the list under the row is the
    set the row was actually planned against.

    The policy is resolved as it stands NOW, not as it stood when the run was built - the
    run does not record it. A policy flipped between the run and the reading would describe
    the row by the new rule; that is a config change the buyer made, and the alternative
    (freezing a copy on every recommendation) is a second source of truth for a value one
    row already answers.
    """
    wid = rec["warehouse_id"]
    if not wid:
        # A network-scope row names no location, so there is nothing to narrow to.
        return [], "warehouse", None

    policy = eng.resolve_policy_for_sku(db, rec["product_id"], None) or {}
    if not policy.get("pool_netting"):
        return [wid], "warehouse", None

    # The row sits on the location that was short, NOT on the pool root, so the pool is
    # resolved FROM it: root first, then every member. Reading the row's own id as the pool
    # returned nothing for a bin, and the breakdown came back empty for exactly the rows
    # that most need explaining.
    rows = db.execute(text(
        "SELECT id::text AS id, warehouse_code, "
        "       COALESCE(pool_warehouse_id, id)::text AS pool_id "
        "FROM warehouses WHERE COALESCE(pool_warehouse_id, id) = ("
        "  SELECT COALESCE(pool_warehouse_id, id) FROM warehouses WHERE id::text = :wid"
        ")"
    ), {"wid": wid}).mappings().all()
    members = [r["id"] for r in rows]
    pool_id = next((r["pool_id"] for r in rows), None)
    pool_code = next((r["warehouse_code"] for r in rows if r["id"] == pool_id), None)
    # A pool of one is the row's own warehouse under another name, and calling that "pool"
    # in the header would invent a netting decision that never happened.
    if len(members) <= 1:
        return ([wid] if not members else members), "warehouse", None
    return members, "pool", pool_code


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
                "unlocated_total": 0.0, "locations": [], "scope": "warehouse",
                "pool_code": None}

    members, scope, pool_code = _scope_for(db, rec)

    # Unlocated demand was attributed to exactly one location per product, so it belongs to
    # this row only when THIS row is the one carrying it.
    include_unlocated = bool((rec["inputs"] or {}).get("unlocated_demand"))

    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="dbk")
    qty = ("GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
           "         - COALESCE(sol.qty_delivered, 0), 0)")
    where_loc = "sol.warehouse_id::text = ANY(:members)"
    plan_demand = PLAN_DEMAND_ORDER_SQL
    if include_unlocated:
        where_loc = f"({where_loc} OR sol.warehouse_id IS NULL)"

    params: dict[str, Any] = {"pid": rec["product_id"], "members": members, **co_params}
    sql = f"""
        SELECT so.so_number, so.order_type, so.demand_class, so.order_date,
               sol.required_date, w.warehouse_code, sol.unit_price,
               {CUSTOMER_LABEL_SQL} AS customer_label,
               {qty} AS qty
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        LEFT JOIN warehouses w ON w.id = sol.warehouse_id
        LEFT JOIN customers c ON c.id = so.customer_id
        WHERE sol.product_id::text = :pid
          AND so.status = 'open' AND sol.line_status = 'open'
          AND sol.purchasing_status <> 'covered'
          AND {qty} > 0
          AND {plan_demand}
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
            # Who ordered it, and what they pay. Both are read off the order rather than
            # looked up elsewhere: an unresolvable debtor code is still an attribution,
            # and a line the extract carries no price for says nothing rather than 0.
            "customer_label": r["customer_label"],
            "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else None,
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
        # Which set of locations the list was drawn from, and the pool's name when it is
        # the pool. Without it a pooled total reads as this bin's, which is the reading
        # the whole popover exists to correct.
        "scope": scope,
        "pool_code": pool_code,
    }
