"""Where a product is bought from (S3, `PLAN-local-supplier-oi-routing.md`).

`local` iff the product's supplier's country matches `HOME_COUNTRY_CODE` - a local Buy
raises no Order Inquiry on confirm (`project_order_inquiry_service.refresh_for_decision`).
The supplier is the primary `product_suppliers` link, else the newest-PO supplier
(same tiebreak `summary_order_service._last_po_supplier_map` (S15) uses:
`purchase_orders.issue_date DESC NULLS LAST, created_at DESC`) - the primary link wins
when both exist (decision 3 / AC-2.13), because it is what a buyer states on purpose and
a PO history entry can be a one-off. No supplier, or a supplier with no country, is
`overseas`.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.money import HOME_COUNTRY_CODE


def buy_origin_by_product(db: Session, product_ids: Iterable[str]) -> dict[str, str]:
    """``{product_id: "local" | "overseas"}`` for every id given, computed in TWO
    queries for the whole call regardless of how many products are asked about."""
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return {}

    co_ps, co_ps_params = company_sql_predicate(db, "ps.company_id", param_prefix="origps")
    primary_rows = db.execute(
        text(
            f"""
            SELECT ps.product_id::text AS pid, c.code AS country_code
            FROM product_suppliers ps
            JOIN suppliers s ON s.id = ps.supplier_id
            LEFT JOIN countries c ON c.id = s.country_id
            WHERE ps.product_id::text = ANY(:pids) AND ps.is_primary_supplier = true
              {("AND " + co_ps) if co_ps else ""}
            """
        ),
        {"pids": ids, **co_ps_params},
    ).fetchall()
    by_primary = {pid: code for pid, code in primary_rows}

    remaining = [pid for pid in ids if pid not in by_primary]
    by_po: dict[str, str | None] = {}
    if remaining:
        co_po, co_po_params = company_sql_predicate(db, "pol.company_id", param_prefix="originpo")
        po_rows = db.execute(
            text(
                f"""
                SELECT DISTINCT ON (pol.product_id) pol.product_id::text AS pid,
                       c.code AS country_code
                FROM purchase_order_lines pol
                JOIN purchase_orders po ON po.id = pol.purchase_order_id
                JOIN suppliers s ON s.id = po.supplier_id
                LEFT JOIN countries c ON c.id = s.country_id
                WHERE pol.product_id::text = ANY(:pids)
                  {("AND " + co_po) if co_po else ""}
                ORDER BY pol.product_id, po.issue_date DESC NULLS LAST, po.created_at DESC
                """
            ),
            {"pids": remaining, **co_po_params},
        ).fetchall()
        by_po = {pid: code for pid, code in po_rows}

    result: dict[str, str] = {}
    for pid in ids:
        code = by_primary.get(pid) or by_po.get(pid)
        result[pid] = "local" if code and code.upper() == HOME_COUNTRY_CODE else "overseas"
    return result
