"""Product economics behind the margin and discontinue advisories.

> "i want to look at the margin of the item also, by comparing the raw mat cost which is
>  the purchase cost and the selling price ... maybe it is a hot selling item, but the
>  margin is so little ... we need to suggest to discontinue or not, this is also looking
>  into multiple factors like the sales, the mobility of the stock, is it having good
>  margin, what's the cost, what's the turnover" (user markup, 2026-08-11)

This module supplies the FACTS, product by product, for the run's planned book:

- what the item actually SELLS for: quantity-weighted average over the last 12 months of
  real order lines (discounts included, cancelled orders excluded). `list_price` is only
  the fallback for an item with no sales, and the payload names which source it used -
  a margin against a price nobody paid must not look like one against real sales.
- how fast it MOVES: total on hand across every location vs the average monthly outflow,
  expressed as months of stock ("turnover_months"). No movement is reported as no
  movement, never as a number.

The VERDICTS (margin tone, "consider discontinuing") are drawn on the frontend from
these facts plus the line's own cost and trend, mirroring the priceAdvice/trajectory
split: the backend states what happened, the words live beside the screen that says them.
The thresholds the verdicts use are policy knobs carried in this payload so both sides
draw the same line.
"""
from __future__ import annotations

import logging
import uuid as uuid_mod
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.error_handler import AppException

log = logging.getLogger(__name__)

#: What a buyer can decide about a product's life. The advisory recomputes every run;
#: the decision is the human answer to it, recorded until they change their mind.
LIFECYCLE_DECISIONS = ("keep", "discontinue")

#: The line the business draws, when the policy has not drawn one.
DEFAULT_MARGIN_FLOOR_PCT = 15.0
DEFAULT_DEAD_TURNOVER_MONTHS = 6.0

#: Realized-price and movement window. Matches the project trajectory window so "what it
#: sells for" and "how the orders are trending" describe the same year of the book.
SELL_WINDOW_MONTHS = 12


def _thresholds(db: Session) -> dict[str, float]:
    row = db.execute(text(
        "SELECT margin_floor_pct, dead_turnover_months "
        "FROM scm.reorder_policy WHERE scope_type = 'global' AND is_active = true "
        "ORDER BY priority DESC NULLS LAST LIMIT 1"
    )).first()
    return {
        "margin_floor_pct": float(row[0]) if row and row[0] is not None
        else DEFAULT_MARGIN_FLOOR_PCT,
        "dead_turnover_months": float(row[1]) if row and row[1] is not None
        else DEFAULT_DEAD_TURNOVER_MONTHS,
    }


def _run_product_ids(db: Session, run_id: str) -> list[str]:
    return [r[0] for r in db.execute(text(
        "SELECT DISTINCT product_id::text FROM scm.reorder_recommendation "
        "WHERE run_id = :run_id"), {"run_id": run_id})]


def economics_for_run(db: Session, run_id: str,
                      *, as_of: Optional[date] = None) -> dict[str, Any]:
    """Sell price, movement and stock facts, keyed by product id."""
    pids = _run_product_ids(db, run_id)
    if not pids:
        return {"products": {}, "count": 0, "thresholds": _thresholds(db),
                "sell_window_months": SELL_WINDOW_MONTHS}

    today = as_of or date.today()
    # Whole calendar months: 12 back from the start of the current one.
    total = (today.year * 12 + (today.month - 1)) - SELL_WINDOW_MONTHS
    start = date(total // 12, total % 12 + 1, 1)
    end = date(today.year, today.month, 1)

    # Realized selling: quantity-weighted, discounts included via the line total. A line
    # with no total falls back to qty x unit_price; a zero-priced line still counts its
    # quantity (free units drag the realized price down, which is the truth of it).
    sold = {r["product_id"]: r for r in db.execute(text("""
        SELECT ol.product_id::text AS product_id,
               SUM(COALESCE(ol.total_excluding_tax, ol.quantity * ol.unit_price, 0)) AS revenue,
               SUM(ol.quantity) AS qty
          FROM order_lines ol
          JOIN orders o ON o.id = ol.order_id
         WHERE ol.product_id = ANY(CAST(:pids AS uuid[]))
           AND o.is_cancelled = false
           AND o.order_date >= :start AND o.order_date < :end
         GROUP BY ol.product_id
    """), {"pids": pids, "start": start, "end": end}).mappings().all()}

    list_prices = {r["product_id"]: r["list_price"] for r in db.execute(text(
        "SELECT id::text AS product_id, list_price FROM products "
        "WHERE id = ANY(CAST(:pids AS uuid[]))"
    ), {"pids": pids}).mappings().all()}

    on_hand = {r["product_id"]: float(r["qty"] or 0) for r in db.execute(text(
        "SELECT product_id::text AS product_id, SUM(quantity_on_hand) AS qty "
        "FROM stock WHERE product_id = ANY(CAST(:pids AS uuid[])) GROUP BY product_id"
    ), {"pids": pids}).mappings().all()}

    moved = {r["product_id"]: float(r["qty"] or 0) for r in db.execute(text(
        "SELECT product_id::text AS product_id, SUM(qty_out) AS qty "
        "FROM scm.consumption_v WHERE product_id = ANY(CAST(:pids AS uuid[])) "
        "AND day >= :start AND day < :end GROUP BY product_id"
    ), {"pids": pids, "start": start, "end": end}).mappings().all()}

    decisions = {r["product_id"]: dict(r) for r in db.execute(text(
        "SELECT product_id::text AS product_id, decision, decided_at "
        "FROM scm.product_lifecycle_decision "
        "WHERE product_id = ANY(CAST(:pids AS uuid[]))"
    ), {"pids": pids}).mappings().all()}

    out: dict[str, Any] = {}
    for pid in pids:
        s = sold.get(pid)
        qty = float(s["qty"]) if s and s["qty"] else 0.0
        revenue = float(s["revenue"]) if s and s["revenue"] else 0.0
        if qty > 0 and revenue > 0:
            sell_price, sell_source = revenue / qty, "orders"
        else:
            lp = list_prices.get(pid)
            # A zero list price is "not priced", not a price of zero: report NO selling
            # price so the margin reads unknown instead of -100%.
            sell_price = float(lp) if lp is not None and float(lp) > 0 else None
            sell_source = "list_price" if sell_price is not None else None

        monthly = moved.get(pid, 0.0) / SELL_WINDOW_MONTHS
        held = on_hand.get(pid, 0.0)
        out[pid] = {
            "product_id": pid,
            "avg_sell_price": round(sell_price, 4) if sell_price is not None else None,
            "sell_source": sell_source,
            "sold_qty": round(qty, 4),
            "on_hand": round(held, 4),
            "avg_monthly_out": round(monthly, 4),
            # Months of stock at the current pace. None when nothing moves - a division
            # by zero is not "infinite months", it is "the pace is zero", said as such.
            "turnover_months": round(held / monthly, 2) if monthly > 0 else None,
            "no_movement": monthly <= 0,
            # The buyer's standing answer to the advisory, or None while undecided.
            "lifecycle_decision": decisions.get(pid, {}).get("decision"),
            "lifecycle_decided_at": (decisions[pid]["decided_at"].isoformat()
                                     if pid in decisions and decisions[pid]["decided_at"]
                                     else None),
        }

    return {
        "products": out,
        "count": len(out),
        "thresholds": _thresholds(db),
        "sell_window_months": SELL_WINDOW_MONTHS,
    }


def record_lifecycle_decision(db: Session, *, product_id: str, decision: Optional[str],
                              decided_by: Optional[str]) -> dict[str, Any]:
    """Record (or withdraw, with None) the buyer's keep-or-discontinue call.

    Overwrite-in-place: the decision is the CURRENT answer, not a history - the advisory
    itself recomputes every run and asks again when the facts change. Never touches
    `products.is_discontinued`, which AutoCount's description derives on every sync;
    marking it there is the buyer's job, and this row is the reminder of what they chose.
    """
    if decision is not None and decision not in LIFECYCLE_DECISIONS:
        raise AppException(status_code=422,
                           message=f"decision must be one of {', '.join(LIFECYCLE_DECISIONS)}.")
    exists = db.execute(text("SELECT 1 FROM products WHERE id = CAST(:p AS uuid)"),
                        {"p": product_id}).first()
    if exists is None:
        raise AppException(status_code=404, message="Product not found.")

    now = datetime.utcnow()
    if decision is None:
        db.execute(text(
            "DELETE FROM scm.product_lifecycle_decision "
            "WHERE product_id = CAST(:p AS uuid)"),
            {"p": product_id})
    else:
        db.execute(text("""
            INSERT INTO scm.product_lifecycle_decision
                (id, product_id, decision, decided_by, decided_at)
            VALUES (:id, :p, :d, :by, :now)
            ON CONFLICT (product_id)
            DO UPDATE SET decision = :d, decided_by = :by, decided_at = :now
        """), {"id": str(uuid_mod.uuid4()), "p": product_id, "d": decision,
               "by": decided_by, "now": now})
    db.commit()
    return {"product_id": product_id, "decision": decision,
            "decided_at": now.isoformat() if decision else None}
