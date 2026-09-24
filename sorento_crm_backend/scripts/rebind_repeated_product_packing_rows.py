#!/usr/bin/env python3
"""Backfill: rebind a repeated product's packing rows away from the ONE line they all
collapsed onto (AC-C7, PLAN-pi-header-fields-convert-fixes-24sep.md, design C).

Before C1's fix, `replace_packing_rows`/`rebind_packing_rows` bound EVERY packing row of a
repeated product to ONE invoice line (`line_by_product = {product_id: line}`, last-writer-
wins over an unordered query) instead of the i-th row to the i-th line, in sheet order. A
PI already converted (or simply uploaded) under that bug still has its rows collapsed - a
NEW upload or a NEW rebind self-heals (C1), but nothing revisits an EXISTING one on its
own. This script finds every (invoice, product) whose packing rows are ALL bound to one
line while the invoice actually states MORE THAN ONE line for that product - the exact
shape the collapse bug leaves behind - and rebinds them by `row_no` -> `line_no` order,
the same rule C1's fixed binder uses.

Existing CONVERTED shipments/packing lists are not touched (AC-C7) - this only fixes which
INVOICE LINE a packing row is filed under (`proforma_invoice_packing_line.proforma_invoice_
line_id`), never an `inbound_shipment_line`.

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:
    python scripts/rebind_repeated_product_packing_rows.py --dry-run
    python scripts/rebind_repeated_product_packing_rows.py --apply

`--dry-run` prints (and this module's own `rebind_repeated_products` returns) the count of
affected (invoice, product) pairs and writes nothing; `--apply` rebinds and commits.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.scm import ProformaInvoiceLine, ProformaInvoicePackingLine


def _collapsed_groups(db) -> list[tuple[str, str, list, list]]:
    """Every (invoice_id, product_id) whose packing rows are ALL bound to ONE line while
    the invoice states more than one line for that product - the collapse bug's own
    signature. Returns `(invoice_id, product_id, rows_by_row_no, lines_by_line_no)`."""
    dup_products = (
        db.query(ProformaInvoiceLine.invoice_id, ProformaInvoiceLine.product_id)
        .filter(ProformaInvoiceLine.product_id.isnot(None))
        .group_by(ProformaInvoiceLine.invoice_id, ProformaInvoiceLine.product_id)
        .having(func.count(ProformaInvoiceLine.id) > 1)
        .all()
    )
    out: list[tuple[str, str, list, list]] = []
    for invoice_id, product_id in dup_products:
        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(
                ProformaInvoicePackingLine.proforma_invoice_id == invoice_id,
                ProformaInvoicePackingLine.product_id == product_id,
            )
            .order_by(ProformaInvoicePackingLine.row_no)
            .all()
        )
        if len(rows) < 2:
            continue
        distinct_lines = {
            str(r.proforma_invoice_line_id) for r in rows if r.proforma_invoice_line_id
        }
        if len(distinct_lines) != 1:
            # Already spread across several lines (a fresh upload/rebind healed it, or it
            # was never collapsed), or unbound - nothing this script needs to touch.
            continue
        lines = (
            db.query(ProformaInvoiceLine)
            .filter(
                ProformaInvoiceLine.invoice_id == invoice_id,
                ProformaInvoiceLine.product_id == product_id,
            )
            .order_by(ProformaInvoiceLine.line_no)
            .all()
        )
        out.append((str(invoice_id), str(product_id), rows, lines))
    return out


def rebind_repeated_products(db, dry_run: bool = True) -> dict:
    """Rebind every collapsed (invoice, product) group's packing rows by sheet order - the
    i-th row binds the i-th line, a surplus row binds the last one (C1's own rule).
    Returns `{"count": N}`, N = how many (invoice, product) pairs were (or, dry-run, would
    be) rebound. A dry run writes nothing."""
    groups = _collapsed_groups(db)
    if dry_run:
        return {"count": len(groups)}
    for _invoice_id, _product_id, rows, lines in groups:
        for i, row in enumerate(rows):
            row.proforma_invoice_line_id = lines[i].id if i < len(lines) else lines[-1].id
    db.flush()
    return {"count": len(groups)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="Count affected PIs; write nothing.",
    )
    mode.add_argument(
        "--apply", action="store_true", help="Rebind for real and commit.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = rebind_repeated_products(db, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
            print(
                f"[dry-run] {result['count']} proforma invoice/product pair(s) would be rebound."
            )
        else:
            db.commit()
            print(f"Rebound {result['count']} proforma invoice/product pair(s).")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
