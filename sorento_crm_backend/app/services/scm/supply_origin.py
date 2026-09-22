"""Where a product is bought from (S3, `PLAN-local-supplier-oi-routing.md`).

The rule is a switch, off by default (`PLAN-local-buy-routing-toggle.md`, owner ruling 18
Sep 2026): a local supplier does not mean CS buys it themselves, purchasing still raises the
Buy and buys overseas anyway, so hard-wiring the skip broke the handoff. While the switch is
off this resolver answers `None` for every id and runs no origin SQL at all; on, it answers
`local` iff the product's supplier's country matches `HOME_COUNTRY_CODE` - a local Buy raises
no Order Inquiry on confirm (`project_order_inquiry_service.refresh_for_decision`). The
supplier is the primary `product_suppliers` link, else the newest-PO supplier (same tiebreak
`summary_order_service._last_po_supplier_map` (S15) uses: `purchase_orders.issue_date DESC
NULLS LAST, created_at DESC`) - the primary link wins when both exist (decision 3 / AC-2.13),
because it is what a buyer states on purpose and a PO history entry can be a one-off. No
supplier, or a supplier with no country, is `overseas`.

`PLAN-brand-flows-to-purchasing.md` (owner ruling 22 Sep 2026, R4-R7): a brand can be marked
`flows_to_purchasing = false` (TP Enterprise is the named one - bought locally by CS, never
purchasing's job) independently of the switch above - R4, the two rules do not gate each
other. A product on a blocked brand answers `"local"` whatever the toggle state and whatever
its supplier's country: the brand read runs FIRST, in ONE statement for the whole call, and
its answer wins over the supplier-country chain when the toggle is on.

Company scope polarity on the brand read (review fix round, 23 Sep 2026): an UNSET scope
renders `company_sql_predicate` as `1=0` (fail-closed - see that helper's own docstring), so
`_blocked_brand_product_ids` returns nothing for a caller with no scope resolved, and a
blocked-brand Buy is answered as if unblocked and IS raised to Order Inquiries. That is the
unsafe direction for THIS rule (a blocked brand skipping is the safety property, not the
other way round), but the scope predicate is shared with the supplier-country statement
below, which has the same polarity for the same reason - a single helper, one behaviour, not
a special case for this one caller.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import SystemSetting
from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.money import HOME_COUNTRY_CODE

# Module-level so a test can EXPLAIN the exact statement this function runs without
# duplicating it (review fix round, 23 Sep 2026: the WHERE clause must cast :pids to
# uuid[] rather than casting the column, or `products_pkey` is unusable and every call
# falls back to a Seq Scan over the whole table).
BLOCKED_BRAND_PRODUCT_IDS_SQL = """
    SELECT p.id::text AS pid
    FROM products p
    JOIN brands b ON b.id = p.brand_id
    WHERE p.id = ANY(CAST(:pids AS uuid[])) AND b.flows_to_purchasing = false
      {company_predicate}
    """


def _blocked_brand_product_ids(db: Session, ids: list[str]) -> set[str]:
    """Product ids whose brand has `flows_to_purchasing = false`, in ONE statement for
    the whole call (never per line) - the board's own statement-count pin
    (`tests/test_ladder_v5_edges.py`) is why this is a single `p.id = ANY(:pids)` join
    rather than a per-product read. Company-scoped on `products`, the owned side of the
    join; `brands` needs no predicate of its own since a product's brand is always read
    through the product it is scoped by.

    `:pids` is cast to `uuid[]` rather than casting `p.id` to text: `p.id::text = ANY(...)`
    forces a per-row cast of the primary key, which makes `products_pkey` unusable and
    turns every call into a Seq Scan (measured: ~4.2ms/call over 15k rows vs ~0.8ms
    indexed). Casting the bind parameter instead lets Postgres use the index.
    """
    co_products, co_products_params = company_sql_predicate(
        db, "p.company_id", param_prefix="originbrand"
    )
    rows = db.execute(
        text(
            BLOCKED_BRAND_PRODUCT_IDS_SQL.format(
                company_predicate=("AND " + co_products) if co_products else ""
            )
        ),
        {"pids": ids, **co_products_params},
    ).fetchall()
    return {row[0] for row in rows}


def buy_origin_by_product(db: Session, product_ids: Iterable[str]) -> dict[str, Optional[str]]:
    """``{product_id: "local" | "overseas" | None}`` for every id given.

    Setting on: the supplier-country chain runs, in ONE statement for the whole call
    regardless of how many products are asked about, PLUS the brand read below. Setting
    off (the default): the supplier-country chain runs NOT AT ALL - only the settings
    read and the brand read (`PLAN-brand-flows-to-purchasing.md`) run, so a blocked-brand
    product still answers `"local"` while everything else answers `None`.

    One statement rather than two (CI fix round): the board runs this once per build, and
    `tests/test_ladder_v5_edges.py`'s statement-count pin counts every round trip a board
    makes, so the chain is resolved in SQL instead of by two reads merged in Python. The
    `NOT EXISTS` is the chain itself - a product whose primary link is stated answers off
    that link even when the linked supplier has no country (so it reads `overseas`, and a
    newer PO from a Chinese supplier does NOT override it, AC-2.13).

    Every caller already reads `origin_by_product.get(pid, "overseas")`, and `dict.get`
    returns the stored `None` when the key is present, so answering `None` here (setting
    off) is the whole gate: no caller change, no OI-service change, no FE board change.
    """
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return {}

    blocked = _blocked_brand_product_ids(db, ids)

    enabled = db.query(SystemSetting.local_buy_routing_enabled).first()
    if not (enabled and enabled[0]):
        return {pid: ("local" if pid in blocked else None) for pid in ids}

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
            if pid in blocked or (by_product.get(pid) or "").upper() == HOME_COUNTRY_CODE
            else "overseas"
        )
        for pid in ids
    }
