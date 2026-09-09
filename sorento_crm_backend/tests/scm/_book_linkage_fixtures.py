"""Shared seeding for the book-linkage test pair (review of PR #764, F8).

`tests/scm/test_book_linkage_po_lines.py` and `tests/scm/test_book_linkage_oi_po_lightbox.py`
ask the SAME question of two different routes - does a purchase-order line's own
`from_so_line_ref` resolve to a sales order number - and had each grown a near line-for-line
copy of the seeding to ask it: a purchase order with N lines, an optional per-line ref, and a
sales-order HEADER with deliberately NO lines under the book's own `{database}:{DocKey}`
document key. Moved here so the two files cannot drift on what "the same shape of document"
means - the same reason `tests/scm/_revamp_fixtures.py` and `tests/scm/_queued_import.py`
exist. The test BODIES stay where they are; only this seeding moved.

Each caller keeps its own `MARKER` / `BOOK` (`f"AED_{MARKER}"`): the two suites' rows must
never collide with each other or with the real book's `AED_SORENTO` rows on the shared
prod-copy database, so the book-key builders take `book` explicitly rather than closing
over a module constant.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from tests.scm.conftest import _REF_PRODUCT_CODE, _REF_WAREHOUSE_CODE


def book_ref(book: str, doc_key: str, dtl_key: str) -> str:
    """AutoCount's own `"{database}:{DocKey}:{DtlKey}"` - a machine key, and the thing
    that must NEVER reach the wire on either surface."""
    return f"{book}:{doc_key}:{dtl_key}"


def doc_key_ref(book: str, doc_key: str) -> str:
    """The `"{database}:{DocKey}"` half a `sales_orders.source_ref` carries."""
    return f"{book}:{doc_key}"


def ref_fks(db) -> tuple[str, str]:
    """`(product_id, warehouse_id)` of the suite's own reference rows, under the CURRENT
    company scope, for the PURCHASE lines. The sales-order side needs neither."""
    from app.models.inventory import Warehouse
    from app.models.product import Product

    product = db.query(Product).filter(Product.product_code == _REF_PRODUCT_CODE).one()
    warehouse = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).one()
    )
    return str(product.id), str(warehouse.id)


def seed_po(db, *, marker: str, n_lines: int = 1,
            refs: Optional[list[Optional[str]]] = None) -> tuple[str, list[str]]:
    """A purchase order this test owns, with ``n_lines`` open lines.

    ``refs`` sets each line's ``from_so_line_ref`` positionally (``None`` leaves the line
    with no book linkage at all). Returns ``(po_id, [line_ids])`` in line order. ``marker``
    is REQUIRED rather than defaulted here - the two callers prefix it with their own
    `MARKER`, so a stray row is always recognisable as belonging to one suite or the other.
    """
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier

    product_id, warehouse_id = ref_fks(db)
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=marker[:30], supplier_name=f"{marker} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=marker, supplier_id=str(supplier.id),
        status="active", issue_date=date(2026, 7, 16), expected_date=date(2026, 8, 4),
    )
    db.add(po)
    db.flush()
    line_ids = []
    for i in range(n_lines):
        line = PurchaseOrderLine(
            id=str(uuid.uuid4()), purchase_order_id=str(po.id), product_id=product_id,
            warehouse_id=warehouse_id, qty_ordered=100, qty_received=0,
            line_status="open", expected_date=date(2026, 8, 4), source_ref=str(i + 1),
            from_so_line_ref=(refs[i] if refs else None),
        )
        db.add(line)
        db.flush()
        line_ids.append(str(line.id))
    return str(po.id), line_ids


def seed_sales_order(db, *, book: str, doc_key: str, so_number: str) -> str:
    """A sales order HEADER whose ``source_ref`` is the book's ``{database}:{DocKey}``, and
    deliberately NO lines.

    That is the whole contract of the document-level join: the number on screen belongs to
    the ORDER, so a held header is sufficient to name it and a missing line cannot suppress
    it. Seeded in full rather than borrowed off an existing row - CI's database has no
    data, and a `LIMIT 1` off `sales_orders` would pick up whatever the last suite left.
    """
    from app.models.order import SalesOrder

    so = SalesOrder(
        id=str(uuid.uuid4()), so_number=so_number, order_date=date(2026, 7, 1),
        demand_class="project", source_ref=doc_key_ref(book, doc_key),
    )
    db.add(so)
    db.flush()
    return str(so.id)


def response_lines(res) -> list[dict]:
    assert res.status_code == 200, res.text
    return res.json()["lines"]
