"""ONE read of "what is on its way to the site pool", for every screen that has to foot.

PLAN-po-spo-site-pool-and-order-sheet-downloads.md, "Design - simplest thing that works":
`open_spo_by_product` / `open_po_by_product` are `summary_order_service`'s own
`_incoming_spo_qty_map` / `_po_open_qty_map` (+ `_grouped_supply_map`), moved here VERBATIM
(AC-14: `summary_order_service` imports them back, no behaviour change there) so the sheet's
own rule has one home a modal or the engine can read from too, instead of staying private to
the sheet and getting re-derived by hand wherever else the same number is needed.

Both apply `pool_predicate.active_site_pool_sql` - active, not `segment='project'` - and are
PRODUCT-WIDE: every site-pool warehouse the product has supply at, not narrowed to one run's
plan basis. A document naming no warehouse, or naming a project bin, is not counted either
way: not known to be site-pool supply, or known not to be.
"""
from __future__ import annotations

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment, SPOAllocation
from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.pool_predicate import ACTIVE_SITE_POOL_SQL, active_site_pool_sql
from app.services.scm.spo_supply import open_incoming_clauses


def _grouped_supply_map(rows) -> dict[str, dict]:
    """Common shape for `open_po_by_product` / `open_spo_by_product` (issue #796, AC-13):
    rows of ``(product_id, document_number, qty)`` collapse to ``{pid: {"qty": total,
    "docs": [{"number", "qty"}, ...]}}``.

    `docs` is sorted by number, a NULL number groups under "(no number)". Each document's
    remainder is CLAMPED to 0 before it is added to `qty` or considered for the list
    (review fix round, AC-15): an over-received still-open line (a line the book marks
    open despite `qty_received > qty_ordered`, or an SPO allocation over-received the
    same way) would otherwise SUBTRACT from the total while contributing nothing to the
    list, so the listed lines no longer summed to the figure printed above them. An
    over-received line is not incoming supply either way, so 0 is the right reading of
    it, not a negative one. This makes `qty` NO LONGER byte-identical to the old
    ungrouped SUM on an over-received line - deliberately: the old SUM let a negative
    remainder net other documents down, which is the same bug restated as an arithmetic
    "feature" rather than fixed.
    """
    out: dict[str, dict] = {}
    for pid, number, qty in rows:
        key = str(pid)
        q = max(float(qty or 0.0), 0.0)
        bucket = out.setdefault(key, {"qty": 0.0, "docs": []})
        bucket["qty"] += q
        if q > 0:
            bucket["docs"].append({"number": number or "(no number)", "qty": q})
    for bucket in out.values():
        bucket["docs"].sort(key=lambda d: d["number"])
    return out


def open_po_by_product(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """``{product_id: {"qty": total, "docs": [...]}}`` of open PO lines still owed at a
    SITE POOL location - the sheet's own "BRW PO Qty" (Phase 3 nit), the same
    `pool_predicate` module `po_book_service`/`reorder_run_service` already read, rather
    than a second, wider reading that also counted project-bin PO lines a buyer would
    never call "BRW PO Qty". A PO line naming no warehouse is not known to be pool supply
    and is not counted either.

    Grouped by `purchase_orders.po_number` too (issue #796, AC-13/AC-15): the buyer wants
    to see WHICH document the total is owed on, for traceability.
    """
    if not product_ids:
        return {}
    co, co_params = company_sql_predicate(db, "pol.company_id", param_prefix="poo")
    rows = db.execute(text(f"""
        SELECT pol.product_id::text AS pid,
               po.po_number AS po_number,
               SUM(pol.qty_ordered - COALESCE(pol.qty_received, 0)) AS qty
        FROM purchase_order_lines pol
        JOIN warehouses w ON w.id = pol.warehouse_id
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        WHERE pol.product_id::text = ANY(:pids)
          AND pol.line_status = 'open'
          AND {ACTIVE_SITE_POOL_SQL}
          {("AND " + co) if co else ""}
        GROUP BY pol.product_id, po.po_number
    """), {"pids": [str(p) for p in product_ids], **co_params}).fetchall()
    return _grouped_supply_map(rows)


def open_spo_by_product(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """``{product_id: {"qty": total, "docs": [...]}}`` still to come on an open SPO at a
    SITE POOL warehouse only - `spo_supply`'s own "trust the book" rule (open, not yet
    received, not landed), re-scoped (S14, AC-S14.2) to the same `pool_predicate` rule the
    PO column's "BRW PO Qty" already applies - the sheet's own "BRW incoming Qty". An
    allocation naming no warehouse, or naming a project bin, is not counted: not known to
    be pool supply, or known not to be, either way it is not a site-pool figure.

    Grouped by `spo_allocations.spo_number` too (issue #796, AC-13/AC-15) - the document
    IS the line (D3, no header table), so the number is the row's own identity, one group
    per allocation number.
    """
    if not product_ids:
        return {}
    rows = (
        db.query(
            SPOAllocation.product_id,
            SPOAllocation.spo_number,
            func.sum(
                SPOAllocation.allocated_quantity
                - func.coalesce(SPOAllocation.quantity_received, 0)
            ),
        )
        .join(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
        .outerjoin(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
        .filter(
            SPOAllocation.product_id.in_(product_ids),
            *open_incoming_clauses(),
            text(active_site_pool_sql("warehouses")),
        )
        .group_by(SPOAllocation.product_id, SPOAllocation.spo_number)
        .all()
    )
    return _grouped_supply_map(rows)
