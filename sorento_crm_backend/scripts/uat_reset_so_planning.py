"""Put one sales order back to "never planned" on a dev copy, so a UAT walk can be redone.

Dry run by default: prints what would go. ``--apply`` deletes inside one transaction.
``--rewind-book`` also restores the core and project lines a planning-change batch
moved, from that batch's own ``from_json`` (newest batch first, so the oldest FROM wins),
which puts the SO book back where it stood before the first re-upload.

Scope is ONE order, by its SO number. Removed, in dependency order:
order_inquiry_links -> order_inquiry_rows -> order_inquiries, the order-inquiry claims in
scm.order_link_claim, so_line_allocations, stock_transfers, so_supply_decisions,
planning_change_rows (and a batch left with no rows). Nothing else is touched: purchase
orders, SPO allocations, the products, the other orders in a shared batch.

    venv/bin/python -m scripts.uat_reset_so_planning --so SO381895
    venv/bin/python -m scripts.uat_reset_so_planning --so SO381895 --rewind-book --apply
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.database import engine


def _ids(conn, sql: str, **params) -> list[str]:
    return [str(r[0]) for r in conn.execute(text(sql), params).all()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", required=True, help="SO number, e.g. SO381895")
    ap.add_argument("--apply", action="store_true", help="really delete (default: dry run)")
    ap.add_argument("--rewind-book", action="store_true",
                    help="restore lines moved by planning-change batches from their from_json")
    args = ap.parse_args()

    with engine.begin() as conn:
        core = conn.execute(text("SELECT id FROM sales_orders WHERE so_number = :n"), {"n": args.so}).all()
        if len(core) != 1:
            print(f"{args.so}: expected one core sales order, found {len(core)}"); return 2
        core_id = str(core[0][0])
        pso = conn.execute(text(
            "SELECT id FROM projects.sales_orders WHERE so_id = :c OR autocount_doc_no = :n"
        ), {"c": core_id, "n": args.so}).all()
        if len(pso) != 1:
            print(f"{args.so}: expected one project sales order, found {len(pso)}"); return 2
        pid = str(pso[0][0])

        line_ids = _ids(conn, "SELECT id FROM projects.sales_order_lines WHERE project_sales_order_id = :p", p=pid)
        oi_ids = _ids(conn, "SELECT id FROM projects.order_inquiries WHERE project_sales_order_id = :p", p=pid)
        row_ids = _ids(conn, "SELECT id FROM projects.order_inquiry_rows WHERE order_inquiry_id = ANY(CAST(:o AS uuid[]))", o=oi_ids) if oi_ids else []
        link_ids = _ids(conn, "SELECT id FROM projects.order_inquiry_links WHERE row_id = ANY(CAST(:r AS uuid[]))", r=row_ids) if row_ids else []
        claim_ids = _ids(conn, "SELECT id FROM scm.order_link_claim WHERE so_number = :n AND source = 'order_inquiry'", n=args.so)
        alloc_ids = _ids(conn, "SELECT id FROM projects.so_line_allocations WHERE so_line_id = ANY(CAST(:l AS uuid[]))", l=line_ids) if line_ids else []
        transfer_ids = _ids(conn, "SELECT id FROM projects.stock_transfers WHERE project_sales_order_id = :p", p=pid)
        decision_ids = _ids(conn, "SELECT id FROM projects.so_supply_decisions WHERE project_sales_order_id = :p", p=pid)
        change_rows = conn.execute(text(
            "SELECT r.id, r.batch_id, r.core_line_id, r.project_line_id, r.line_no, r.from_json, b.upload_file_name "
            "FROM projects.planning_change_rows r JOIN projects.planning_change_batches b ON b.id = r.batch_id "
            "WHERE r.project_sales_order_id = :p ORDER BY b.created_at DESC, r.line_no"
        ), {"p": pid}).all()

        print(f"{args.so}: core {core_id}, project {pid}, {len(line_ids)} lines")
        print(f"  order inquiries {len(oi_ids)}, rows {len(row_ids)}, links {len(link_ids)}, claims {len(claim_ids)}")
        print(f"  allocations {len(alloc_ids)}, stock transfers {len(transfer_ids)}, supply decisions {len(decision_ids)}")
        print(f"  planning-change rows {len(change_rows)}")
        for r in change_rows:
            print(f"    line {r[4]} in '{r[6]}': back to {json.dumps(r[5])}" if args.rewind_book
                  else f"    line {r[4]} in '{r[6]}' (book NOT rewound; add --rewind-book)")

        if not args.apply:
            print("dry run: nothing changed. Add --apply.")
            conn.rollback()
            return 0

        if link_ids:
            conn.execute(text("DELETE FROM projects.order_inquiry_links WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": link_ids})
        if row_ids:
            conn.execute(text("DELETE FROM projects.order_inquiry_rows WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": row_ids})
        if oi_ids:
            conn.execute(text("DELETE FROM projects.order_inquiries WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": oi_ids})
        if claim_ids:
            conn.execute(text("DELETE FROM scm.order_link_claim WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": claim_ids})
        if alloc_ids:
            conn.execute(text("DELETE FROM projects.so_line_allocations WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": alloc_ids})
        if transfer_ids:
            conn.execute(text("DELETE FROM projects.stock_transfers WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": transfer_ids})
        if decision_ids:
            conn.execute(text("DELETE FROM projects.so_supply_decisions WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": decision_ids})

        if args.rewind_book:
            for r in change_rows:  # newest first, so the oldest FROM is the last write
                frm = r[5] or {}
                qty, status, date = frm.get("qty"), frm.get("status"), frm.get("required_date")
                if r[2]:
                    conn.execute(text(
                        "UPDATE sales_order_lines SET qty_ordered = COALESCE(:q, qty_ordered), "
                        "line_status = COALESCE(:s, line_status), required_date = :d WHERE id = :i"
                    ), {"q": qty, "s": status, "d": date, "i": str(r[2])})
                if r[3]:
                    conn.execute(text(
                        "UPDATE projects.sales_order_lines SET qty = COALESCE(:q, qty), delivery_date = :d WHERE id = :i"
                    ), {"q": qty, "d": date, "i": str(r[3])})
        batch_ids = sorted({str(r[1]) for r in change_rows})
        if change_rows:
            conn.execute(text("DELETE FROM projects.planning_change_rows WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": [str(r[0]) for r in change_rows]})
        for b in batch_ids:
            left = conn.execute(text("SELECT count(*) FROM projects.planning_change_rows WHERE batch_id = :b"), {"b": b}).scalar()
            if not left:
                conn.execute(text("DELETE FROM projects.planning_change_batches WHERE id = :b"), {"b": b})
                print(f"  batch {b} removed (no rows left)")
            else:
                print(f"  batch {b} kept ({left} rows of other orders)")
        print("applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
