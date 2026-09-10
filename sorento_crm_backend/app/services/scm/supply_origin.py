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
    """``{product_id: "local" | "overseas"}`` for every id given, in ONE statement for the
    whole call regardless of how many products are asked about.

    One statement rather than two (CI fix round): the board runs this once per build, and
    `tests/test_ladder_v5_edges.py`'s statement-count pin counts every round trip a board
    makes, so the chain is resolved in SQL instead of by two reads merged in Python. The
    `NOT EXISTS` is the chain itself - a product whose primary link is stated answers off
    that link even when the linked supplier has no country (so it reads `overseas`, and a
    newer PO from a Chinese supplier does NOT override it, AC-2.13).
    """
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return {}

    co_ps, co_ps_params = company_sql_predicate(db, "ps.company_id", param_prefix="origps")
    co_po, co_po_params = company_sql_predicate(db, "pol.company_id", param_prefix="originpo")
    rows = db.execute(
        text(
            f"""
            WITH primary_link AS (
                SELECT DISTINCT ON (ps.product_id)
                       ps.product_id::text AS pid, c.code AS country_code
                FROM product_suppliers ps
                JOIN suppliers s ON s.id = ps.supplier_id
                LEFT JOIN countries c ON c.id = s.country_id
                WHERE ps.product_id::text = ANY(:pids) AND ps.is_primary_supplier = true
                  {("AND " + co_ps) if co_ps else ""}
                ORDER BY ps.product_id
            ),
            newest_po AS (
                SELECT DISTINCT ON (pol.product_id) pol.product_id::text AS pid,
                       c.code AS country_code
                FROM purchase_order_lines pol
                JOIN purchase_orders po ON po.id = pol.purchase_order_id
                JOIN suppliers s ON s.id = po.supplier_id
                LEFT JOIN countries c ON c.id = s.country_id
                WHERE pol.product_id::text = ANY(:pids)
                  {("AND " + co_po) if co_po else ""}
                ORDER BY pol.product_id, po.issue_date DESC NULLS LAST, po.created_at DESC
            )
            SELECT pid, country_code FROM primary_link
            UNION ALL
            SELECT n.pid, n.country_code FROM newest_po n
            WHERE NOT EXISTS (SELECT 1 FROM primary_link p WHERE p.pid = n.pid)
            """
        ),
        {"pids": ids, **co_ps_params, **co_po_params},
    ).fetchall()
    by_product = {pid: code for pid, code in rows}

    return {
        pid: (
            "local"
            if (by_product.get(pid) or "").upper() == HOME_COUNTRY_CODE
            else "overseas"
        )
        for pid in ids
    }
