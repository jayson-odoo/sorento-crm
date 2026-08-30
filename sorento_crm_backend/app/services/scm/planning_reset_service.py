"""Put one sales order back to never-planned, so a walk through planning can be redone.

The captain, 27 Aug 2026: a UAT walk has to be repeatable from the screen, not from a
script. Nothing in normal use needs this; it exists for the test box and the dev copy.

What goes, in dependency order, all scoped to ONE order: order_inquiry_links ->
order_inquiry_rows -> order_inquiries, that order's order-inquiry claims in
scm.order_link_claim, so_line_allocations, stock_transfers, so_supply_decisions,
planning_change_rows (and a batch left with no rows). ``rewind_book`` also restores the
core and project lines a planning-change batch moved, from the batch's own ``from_json``
(newest batch first, so the oldest FROM is the last write), which puts the SO book back
where it stood before the first re-upload.

Untouched: the order and its lines, purchase orders, SPO allocations, products, and every
other order (a shared batch keeps its other orders' rows).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.error_handler import AppException


def _ids(db: Session, sql: str, **params) -> list[str]:
    return [str(r[0]) for r in db.execute(text(sql), params).all()]


def _delete(db: Session, table: str, ids: list[str]) -> int:
    if not ids:
        return 0
    db.execute(text(f"DELETE FROM {table} WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
    return len(ids)


def reset_planning(db: Session, core_so_id: str, *, rewind_book: bool = False, apply: bool = True) -> dict:
    """Return what was (or, with ``apply=False``, would be) removed, by table."""
    core = db.execute(text("SELECT id, so_number FROM sales_orders WHERE id = :i"), {"i": core_so_id}).first()
    if core is None:
        raise AppException("Sales order not found", status_code=404)
    so_number = core[1]
    pso = db.execute(text(
        "SELECT id FROM projects.sales_orders WHERE so_id = :c OR autocount_doc_no = :n"
    ), {"c": core_so_id, "n": so_number}).all()
    removed = {
        "order_inquiries": 0, "order_inquiry_rows": 0, "order_inquiry_links": 0, "claims": 0,
        "allocations": 0, "stock_transfers": 0, "supply_decisions": 0,
        "planning_change_rows": 0, "planning_change_batches": 0, "lines_rewound": 0,
    }
    if not pso:
        return {"so_number": so_number, "planned": False, "removed": removed}
    pid = str(pso[0][0])

    line_ids = _ids(db, "SELECT id FROM projects.sales_order_lines WHERE project_sales_order_id = :p", p=pid)
    oi_ids = _ids(db, "SELECT id FROM projects.order_inquiries WHERE project_sales_order_id = :p", p=pid)
    row_ids = _ids(db, "SELECT id FROM projects.order_inquiry_rows WHERE order_inquiry_id = ANY(CAST(:o AS uuid[]))", o=oi_ids) if oi_ids else []
    link_ids = _ids(db, "SELECT id FROM projects.order_inquiry_links WHERE row_id = ANY(CAST(:r AS uuid[]))", r=row_ids) if row_ids else []
    claim_ids = _ids(db, "SELECT id FROM scm.order_link_claim WHERE so_number = :n AND source = 'order_inquiry'", n=so_number)
    alloc_ids = _ids(db, "SELECT id FROM projects.so_line_allocations WHERE so_line_id = ANY(CAST(:l AS uuid[]))", l=line_ids) if line_ids else []
    transfer_ids = _ids(db, "SELECT id FROM projects.stock_transfers WHERE project_sales_order_id = :p", p=pid)
    decision_ids = _ids(db, "SELECT id FROM projects.so_supply_decisions WHERE project_sales_order_id = :p", p=pid)
    change_rows = db.execute(text(
        "SELECT r.id, r.batch_id, r.core_line_id, r.project_line_id, r.from_json "
        "FROM projects.planning_change_rows r JOIN projects.planning_change_batches b ON b.id = r.batch_id "
        "WHERE r.project_sales_order_id = :p ORDER BY b.created_at DESC, r.line_no"
    ), {"p": pid}).all()

    removed.update({
        "order_inquiries": len(oi_ids), "order_inquiry_rows": len(row_ids),
        "order_inquiry_links": len(link_ids), "claims": len(claim_ids),
        "allocations": len(alloc_ids), "stock_transfers": len(transfer_ids),
        "supply_decisions": len(decision_ids), "planning_change_rows": len(change_rows),
    })
    if not apply:
        return {"so_number": so_number, "planned": True, "removed": removed}

    _delete(db, "projects.order_inquiry_links", link_ids)
    _delete(db, "projects.order_inquiry_rows", row_ids)
    _delete(db, "projects.order_inquiries", oi_ids)
    _delete(db, "scm.order_link_claim", claim_ids)
    _delete(db, "projects.so_line_allocations", alloc_ids)
    _delete(db, "projects.stock_transfers", transfer_ids)
    _delete(db, "projects.so_supply_decisions", decision_ids)

    if rewind_book:
        for r in change_rows:  # newest first, so the oldest FROM is the last write
            frm = r[4] or {}
            qty, status, date = frm.get("qty"), frm.get("status"), frm.get("required_date")
            if r[2]:
                db.execute(text(
                    "UPDATE sales_order_lines SET qty_ordered = COALESCE(:q, qty_ordered), "
                    "line_status = COALESCE(:s, line_status), required_date = :d WHERE id = :i"
                ), {"q": qty, "s": status, "d": date, "i": str(r[2])})
            if r[3]:
                db.execute(text(
                    "UPDATE projects.sales_order_lines SET qty = COALESCE(:q, qty), delivery_date = :d WHERE id = :i"
                ), {"q": qty, "d": date, "i": str(r[3])})
            removed["lines_rewound"] += 1
    _delete(db, "projects.planning_change_rows", [str(r[0]) for r in change_rows])
    for batch_id in sorted({str(r[1]) for r in change_rows}):
        left = db.execute(text("SELECT count(*) FROM projects.planning_change_rows WHERE batch_id = :b"), {"b": batch_id}).scalar()
        if not left:
            db.execute(text("DELETE FROM projects.planning_change_batches WHERE id = :b"), {"b": batch_id})
            removed["planning_change_batches"] += 1
    db.commit()
    return {"so_number": so_number, "planned": True, "removed": removed}
