"""What we have actually paid for a product, and where that figure comes from.

The product page carried a Cost Price field that somebody typed, and nothing else. Asked
"what does this item cost", the honest answer is what the last purchase order paid for it,
and the only useful form of that answer names the order, the supplier and the date - a
number with no provenance cannot be checked, and a planner who cannot check it will not
trust the plan built on it.

Deliberately core, not SCM: the product page is master data and must not stop working when
the SCM module is not installed for a tenant. Everything here reads ``purchase_orders`` and
``purchase_order_lines``, which are core procurement tables.

No currency conversion. Each line is reported in the currency it was raised in, and the
summary names that currency, because restating a CNY order in ringgit needs a rate that may
not exist and a rate we do not have must never be silently assumed to be 1. Cross-currency
comparison is the planner's job and lives in the SCM cost model.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate

logger = logging.getLogger(__name__)

# The page shows a list, not an archive. A product with hundreds of orders is read for its
# recent prices; the count of everything is reported separately so the cap is never silent.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _iso(d) -> Optional[str]:
    return d.isoformat() if d is not None else None


def purchase_history(db: Session, product_id: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Every purchase-order line for this product, newest first, plus a cost summary.

    Ordered by issue date with the row's creation time as the tiebreak: a book imported in
    one go shares an issue date, and without the tiebreak the order among those lines would
    be whatever the database felt like.
    """
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    # Raw SQL, so the ORM company filter never sees it. A purchase order belongs to a
    # company; without the predicate the page would report another company's prices as
    # this company's cost.
    co, co_params = company_sql_predicate(db, "po.company_id", param_prefix="pph")
    co_clause = f"AND {co}" if co else ""
    params: dict[str, Any] = {"pid": str(product_id), **co_params}

    rows = db.execute(text(f"""
        SELECT po.id::text            AS purchase_order_id,
               po.po_number,
               po.issue_date,
               po.status,
               su.supplier_code,
               su.supplier_name,
               pol.qty_ordered,
               pol.qty_received,
               pol.unit_cost,
               COALESCE(pol.currency, po.currency) AS currency
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        LEFT JOIN suppliers su ON su.id = po.supplier_id
        WHERE pol.product_id = :pid
          {co_clause}
        ORDER BY po.issue_date DESC NULLS LAST, pol.created_at DESC
        LIMIT :limit
    """), {**params, "limit": limit}).mappings().all()

    total = db.execute(text(f"""
        SELECT count(*) FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        WHERE pol.product_id = :pid
          {co_clause}
    """), params).scalar() or 0

    lines = [
        {
            "purchase_order_id": r["purchase_order_id"],
            "po_number": r["po_number"],
            "issue_date": _iso(r["issue_date"]),
            "status": r["status"],
            "supplier_code": r["supplier_code"],
            "supplier_name": r["supplier_name"],
            "qty_ordered": _f(r["qty_ordered"]),
            "qty_received": _f(r["qty_received"]),
            "unit_cost": _f(r["unit_cost"]),
            "currency": r["currency"],
        }
        for r in rows
    ]
    return {
        "product_id": str(product_id),
        "lines": lines,
        "total": int(total),
        "shown": len(lines),
        "cost": _cost_summary(db, str(product_id), co_clause, params),
    }


def _cost_summary(db: Session, product_id: str, co_clause: str, params: dict) -> dict:
    """The one figure the page leads with: what we last paid, and on what evidence.

    ``cost_status`` separates two things a bare dash cannot: ``never_purchased`` (no order
    exists, so there is no cost from history) from ``no_price_recorded`` (orders exist but
    none carried a unit cost). A recorded 0 is a price OF zero and is kept - the customer's
    own book holds hundreds of those, and treating them as missing would hide real lines.
    """
    row = db.execute(text(f"""
        SELECT po.id::text AS purchase_order_id, po.po_number, po.issue_date,
               su.supplier_code, su.supplier_name,
               pol.unit_cost, COALESCE(pol.currency, po.currency) AS currency
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        LEFT JOIN suppliers su ON su.id = po.supplier_id
        WHERE pol.product_id = :pid AND pol.unit_cost IS NOT NULL
          {co_clause}
        ORDER BY po.issue_date DESC NULLS LAST, pol.created_at DESC
        LIMIT 1
    """), params).mappings().first()

    if row is not None:
        return {
            "status": "ok",
            "unit_cost": _f(row["unit_cost"]),
            "currency": row["currency"],
            "po_number": row["po_number"],
            "purchase_order_id": row["purchase_order_id"],
            "supplier_code": row["supplier_code"],
            "supplier_name": row["supplier_name"],
            "issue_date": _iso(row["issue_date"]),
        }

    any_line = db.execute(text(f"""
        SELECT 1 FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        WHERE pol.product_id = :pid
          {co_clause}
        LIMIT 1
    """), params).first()
    return {
        "status": "no_price_recorded" if any_line else "never_purchased",
        "unit_cost": None,
        "currency": None,
        "po_number": None,
        "purchase_order_id": None,
        "supplier_code": None,
        "supplier_name": None,
        "issue_date": None,
    }
