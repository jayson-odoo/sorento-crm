"""Slice A of `PLAN-scm-book-linkage-on-document-lines.md` - the AutoCount book's SO
linkage, on the purchase order's own Lines tab.

Every AC in `scm-book-linkage-on-document-lines-acceptance-criteria.md`'s "Slice A"
section is named in the test that covers it. `scm_app` (savepoint-per-test, rolled
back) with every row behind the `ZZTBOOKPO` marker.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.scm import OrderLinkClaim
from app.services.scm import order_link_service
from tests.scm.conftest import (
    SORENTO_COMPANY_ID,
    _REF_PRODUCT_CODE,
    _REF_WAREHOUSE_CODE,
    as_user,
    requires_pg,
    seed_user,
)

pytestmark = requires_pg

MARKER = "ZZTBOOKPO"


def _as(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_po(db, *, n_lines: int = 1, marker: str | None = None) -> tuple[str, list[str]]:
    """A purchase order this test owns, with ``n_lines`` open lines.

    Returns ``(po_id, [line_ids])`` in line order.
    """
    from app.models.inventory import Warehouse
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product

    marker = marker or f"{MARKER}-{uuid.uuid4().hex[:8]}"
    product = db.query(Product).filter(Product.product_code == _REF_PRODUCT_CODE).one()
    warehouse = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).one()
    )
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
            id=str(uuid.uuid4()), purchase_order_id=str(po.id), product_id=str(product.id),
            warehouse_id=str(warehouse.id), qty_ordered=100, qty_received=0,
            line_status="open", expected_date=date(2026, 8, 4), source_ref=str(i + 1),
        )
        db.add(line)
        db.flush()
        line_ids.append(str(line.id))
    return str(po.id), line_ids


def _claim(db, *, po_line_id, so_number, so_line_id=None, source="po_history",
           po_number=f"{MARKER}-SRC", item_code=None) -> OrderLinkClaim:
    row = OrderLinkClaim(
        id=str(uuid.uuid4()), so_number=so_number, po_number=po_number, item_code=item_code,
        source=source, po_line_id=po_line_id, so_line_id=so_line_id,
    )
    db.add(row)
    db.flush()
    return row


def test_line_with_one_resolved_so_prints_its_number(scm_app):
    """AC-A1 - a line a claim resolves to a sales order prints that number."""
    app, db = _as(scm_app)
    po_id, (line_id,) = _seed_po(db)
    _claim(db, po_line_id=line_id, so_number="SO391853", source="order_inquiry")

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    line = res.json()["lines"][0]
    assert line["so_links"] == [
        {"so_number": "SO391853", "so_line_id": None, "source": "order_inquiry"}
    ]


def test_line_with_no_claim_prints_nothing_to_show(scm_app):
    """AC-A2 - a muted dash on the frontend, never a guess: an empty list, not a claim
    invented from the document number."""
    app, db = _as(scm_app)
    po_id, _lines = _seed_po(db)

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    assert res.json()["lines"][0]["so_links"] == []


def test_line_resolving_to_several_sales_orders_lists_every_one(scm_app):
    """AC-A3 - the backend hands over every distinct sales order; the frontend is the
    one that condenses to "first plus a count"."""
    app, db = _as(scm_app)
    po_id, (line_id,) = _seed_po(db)
    _claim(db, po_line_id=line_id, so_number="SO391853", source="order_inquiry")
    _claim(db, po_line_id=line_id, so_number="SO391900", source="po_history")

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    numbers = {x["so_number"] for x in res.json()["lines"][0]["so_links"]}
    assert numbers == {"SO391853", "SO391900"}


def test_document_level_claim_never_reaches_a_line(scm_app):
    """AC-A4 - a claim carrying no `po_line_id` (the PO-note case, order-level only) must
    never reach a line through a document-number fallback. That is how one customer's
    stock gets attributed to another customer's order."""
    app, db = _as(scm_app)
    marker = f"{MARKER}-A4-{uuid.uuid4().hex[:6]}"
    po_id, (line_id,) = _seed_po(db, marker=marker)
    _claim(db, po_line_id=None, so_number="SO999999", po_number=marker)

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.json()["lines"][0]["so_links"] == []

    # Direct on the reader too - no path exists that would surface it under any key.
    found = order_link_service.so_links_by_po_line(db, [line_id])
    assert found.get(line_id, []) == []


def test_whole_document_costs_one_claim_query_whatever_its_line_count(scm_app):
    """AC-A5 - the QUERY COUNT, not the wall time. A per-line query would be 89 round
    trips on a real document; asserted here on the SHAPE (constant regardless of how
    many lines are asked about), not a specific line count."""
    app, db = _as(scm_app)
    _, small_lines = _seed_po(db, n_lines=2, marker=f"{MARKER}-A5S-{uuid.uuid4().hex[:6]}")
    _, large_lines = _seed_po(db, n_lines=8, marker=f"{MARKER}-A5L-{uuid.uuid4().hex[:6]}")
    for line_id in small_lines + large_lines:
        _claim(db, po_line_id=line_id, so_number=f"SO-{line_id[:8]}")
    db.flush()

    def _count_queries(fn):
        calls = {"n": 0}

        def _count(conn, cursor, statement, parameters, context, executemany):
            calls["n"] += 1

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", _count)
        try:
            fn()
        finally:
            event.remove(connection, "before_cursor_execute", _count)
        return calls["n"]

    small_n = _count_queries(lambda: order_link_service.so_links_by_po_line(db, small_lines))
    large_n = _count_queries(lambda: order_link_service.so_links_by_po_line(db, large_lines))
    assert small_n == 1, "one document's worth of lines must cost exactly one query"
    assert large_n == 1, "a bigger document must not cost more queries than a small one"


def test_claim_from_another_company_is_invisible(scm_app):
    """AC-A6 - the claim read is company-scoped, through `order_link_service` and the
    ORM's `do_orm_execute` filter, never raw SQL."""
    app, db = _as(scm_app)
    po_id, (line_id,) = _seed_po(db)

    other_company = str(uuid.uuid4())
    db.add(Company(
        id=other_company, name=f"{MARKER} other company",
        code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True,
    ))
    db.flush()
    set_company_scope(db, frozenset({other_company}))
    _claim(db, po_line_id=line_id, so_number="SO000000", source="po_history")
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))

    found = order_link_service.so_links_by_po_line(db, [line_id])
    assert found.get(line_id, []) == [], "a claim stamped to another company is invisible"

    # And over the route, scoped as the Sorento user the rest of the suite runs as.
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.json()["lines"][0]["so_links"] == []


def test_allocations_panel_is_unchanged_alongside_the_new_column(scm_app):
    """AC-A7 - the allocations panel below still answers "who reserved this line through
    our own order-inquiry flow", independently of the book's own linkage. A line can
    carry one fact, the other, both or neither; this seeds a claim that feeds BOTH so the
    two co-exist rather than one crowding out the other."""
    app, db = _as(scm_app, "purchasing")
    from tests.scm.test_channel_read_model import _core_so_line
    from tests.scm.test_m3_run import _mk_product
    from tests.scm.test_po_detail_dedication_route import _active_po, _project_bin

    bin_id = _project_bin(db)
    pid = _mk_product(db, f"{MARKER}-A7-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id, number = _active_po(db, product_id=pid, warehouse_id=bin_id, qty=114)

    claiming, claiming_line = _core_so_line(
        db, product_id=pid, warehouse_id=bin_id, qty=114, demand_class="project",
    )
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=claiming.so_number, po_number=number,
        item_code=None, so_line_id=str(claiming_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    body = res.json()

    # The OLD fact, at its old address, unchanged.
    blocks = body.get("allocations") or []
    block = next(b for b in blocks if b["line_id"] == line_id)
    assert [d["so_number"] for d in block["dedicated_to"]] == [claiming.so_number]

    # The NEW fact, on the line itself, naming the SAME sales order independently.
    line = next(ln for ln in body["lines"] if ln["id"] == line_id)
    assert [x["so_number"] for x in line["so_links"]] == [claiming.so_number]


def test_column_shape_carries_size_and_the_full_list_is_on_the_row(scm_app):
    """AC-A8 - checked at the data contract's own boundary: every entry the frontend
    needs to build "first plus a count, full list on the title" is present per row."""
    app, db = _as(scm_app)
    po_id, (line_id,) = _seed_po(db)
    _claim(db, po_line_id=line_id, so_number="SO1", source="order_inquiry")
    _claim(db, po_line_id=line_id, so_number="SO2", source="po_history")

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    links = res.json()["lines"][0]["so_links"]
    assert len(links) == 2
    for entry in links:
        assert {"so_number", "so_line_id", "source"} <= set(entry)
