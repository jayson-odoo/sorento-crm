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

from sqlalchemy import func, or_

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.models.scm import ProformaInvoiceLine, ProformaInvoicePackingLine


def _collapsed_groups(db) -> list[tuple[str, str, list, list]]:
    """Every (invoice_id, product_key) whose packing rows are ALL bound to ONE line while
    the invoice states more than one line for that product/set - the collapse bug's own
    signature. `product_key` is a `product_id` OR a `product_set_id` (R5, review round 1
    - the original cut only ever looked at `product_id`, so a repeated SET line was never
    found). Returns `(invoice_id, product_key, rows_by_row_no, lines_by_line_no)`."""
    dup_products = (
        db.query(
            ProformaInvoiceLine.invoice_id,
            ProformaInvoiceLine.product_id,
            ProformaInvoiceLine.product_set_id,
        )
        .filter(
            or_(
                ProformaInvoiceLine.product_id.isnot(None),
                ProformaInvoiceLine.product_set_id.isnot(None),
            )
        )
        .group_by(
            ProformaInvoiceLine.invoice_id,
            ProformaInvoiceLine.product_id,
            ProformaInvoiceLine.product_set_id,
        )
        .having(func.count(ProformaInvoiceLine.id) > 1)
        .all()
    )
    out: list[tuple[str, str, list, list]] = []
    for invoice_id, product_id, product_set_id in dup_products:
        row_filter = (
            ProformaInvoicePackingLine.product_id == product_id
            if product_id
            else ProformaInvoicePackingLine.product_set_id == product_set_id
        )
        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice_id, row_filter)
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
        line_filter = (
            ProformaInvoiceLine.product_id == product_id
            if product_id
            else ProformaInvoiceLine.product_set_id == product_set_id
        )
        lines = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == invoice_id, line_filter)
            .order_by(ProformaInvoiceLine.line_no)
            .all()
        )
        out.append((str(invoice_id), str(product_id or product_set_id), rows, lines))
    return out


def rebind_repeated_products(db, dry_run: bool = True) -> dict:
    """Rebind every collapsed (invoice, product) group's packing rows by sheet order - the
    i-th row binds the i-th line, a surplus row binds the last one (C1's own rule).
    Returns `{"count": N}`, N = how many (invoice, product) pairs were (or, dry-run, would
    be) rebound. A dry run writes nothing.

    R5 (review round 1): sets the session's OWN company scope to `None` ("all companies",
    `app.models.base`'s own four-state table) before querying - every model this touches
    is `CompanyScopedMixin`, so a fresh `SessionLocal()` nobody has scoped yet (exactly
    what `main()` hands this, and what a test calling this directly with no prior
    `set_company_scope` also looks like) reads 0 rows under the fail-closed `UNSET`
    default and silently reports nothing to rebind. This is a cross-tenant maintenance
    script, not a request handler, so "every company" is the correct scope for it - the
    caller never gets to choose one company over another.
    """
    set_company_scope(db, None)
    groups = _collapsed_groups(db)
    if dry_run:
        return {"count": len(groups)}
    affected_invoice_ids: set[str] = set()
    for invoice_id, _product_key, rows, lines in groups:
        for i, row in enumerate(rows):
            row.proforma_invoice_line_id = lines[i].id if i < len(lines) else lines[-1].id
        affected_invoice_ids.add(invoice_id)
    db.flush()
    # Each rebound line's own carton/weight/volume figures (AC-B8) - the pre-rebind
    # collapse last wrote them from whichever ONE line held every row; nothing revisits
    # them just because the rows moved unless this runs the same rollup every other
    # packing write does.
    from app.services.scm.proforma_invoice_packing_service import rollup_invoice

    for invoice_id in affected_invoice_ids:
        rollup_invoice(db, invoice_id)
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
    # R5: a fresh `SessionLocal()` carries no company scope at all (`UNSET`, fail-closed) -
    # set explicitly here too, not only inside `rebind_repeated_products` (belt and
    # braces: this IS the entry point that hands a scopeless session to everything else
    # `main()` might do around it).
    set_company_scope(db, None)
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
