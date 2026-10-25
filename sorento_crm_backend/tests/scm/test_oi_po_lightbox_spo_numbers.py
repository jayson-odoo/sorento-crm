"""SUPPLY-SPO-LINK (owner, mock v2 approved 25 Oct 2026): the purchase order popup
(`GET /api/v1/project-sales/order-inquiries/po/{po_id}`) names, per line, the SPO(s) that
line was transferred onto.

The key is the order inquiry page's own OI-SPO-EXACT: an `spo_allocations` row belongs to a
PO line when `from_po_number = po_number AND trim(from_po_line_ref) = trim(line.source_ref)
AND product_id = line.product_id`. An allocation of the same PO and product that quotes
another line was bought for another line; one hidden by `visible_line_clauses()` (retired and
never received) is not shown; another company's row naming the same strings is never ours.

Same seeding as `test_book_linkage_oi_po_lightbox.py` (its helpers, its marker discipline,
the `scm_app` savepoint).
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.models.base import set_company_scope
from app.models.company import Company
from tests.scm._book_linkage_fixtures import response_lines as _lines
from tests.scm.conftest import SORENTO_COMPANY_ID, _REF_WAREHOUSE_CODE, requires_pg
from tests.scm.test_book_linkage_oi_po_lightbox import (  # noqa: F401 (helpers, not tests)
    BASE,
    _as,
    _seed_po_distinct_lines,
)

pytestmark = requires_pg

MARKER = "ZZTSPOLINK"

#: `uk_spo_allocations_company_spo_line`: one line number per SPO and company.
_LINE_NO = itertools.count(1)


def _codes(marker: str) -> list[str]:
    """Three products in ascending code order: `get_po_detail` sorts its lines by code."""
    return [f"{marker}-A", f"{marker}-B", f"{marker}-C"]


def _spo_line(db, *, spo_number: str, po_number: str, line_ref: str, product_id: str,
              retired: bool = False, received: int = 0, warehouse_id: str | None = None):
    """An SPO allocation quoting a PO line the way the AutoCount feed writes it (the ref
    padded, as the feed sometimes sends it: the match trims)."""
    from app.models.procurement import SPOAllocation

    row = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=spo_number,
        spo_line_number=next(_LINE_NO),
        product_id=product_id,
        warehouse_id=warehouse_id or _warehouse_id(db),
        allocated_quantity=10,
        quantity_received=received,
        receipt_status="pending",
        line_status="open",
        expected_date=date(2026, 9, 1),
        from_po_number=po_number,
        from_po_line_ref=f" {line_ref} ",
        retired_at=datetime(2026, 9, 2) if retired else None,
    )
    db.add(row)
    db.flush()
    return row


def _warehouse_id(db) -> str:
    """The reference bin. Read under the test's own company scope: under another company's
    scope it is invisible, so the foreign-company test reads it first and passes it in."""
    from app.models.inventory import Warehouse

    return str(
        db.query(Warehouse.id).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).scalar()
    )


def _po_lines(db, po_id: str):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
    lines = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id == po_id)
        .order_by(PurchaseOrderLine.source_ref)
        .all()
    )
    return po, lines


def test_each_po_line_names_the_spos_it_was_transferred_onto(scm_app):
    """Line A moved onto two shipping orders (one of them on two allocation lines, named
    once); line B never moved; line C's product only appears on an allocation that quotes
    LINE A's ref, which is another line's goods, so C names nothing and A does not borrow
    it either."""
    app, db = _as(scm_app)
    marker = f"{MARKER}{uuid.uuid4().hex[:6]}".upper()
    po_id, _ids = _seed_po_distinct_lines(db, marker, _codes(marker), [None, None, None])
    po, (line_a, _line_b, line_c) = _po_lines(db, po_id)

    first, second = f"{marker}-SPO-1", f"{marker}-SPO-2"
    _spo_line(db, spo_number=second, po_number=po.po_number, line_ref=line_a.source_ref,
              product_id=str(line_a.product_id))
    _spo_line(db, spo_number=first, po_number=po.po_number, line_ref=line_a.source_ref,
              product_id=str(line_a.product_id))
    _spo_line(db, spo_number=first, po_number=po.po_number, line_ref=line_a.source_ref,
              product_id=str(line_a.product_id))
    _spo_line(db, spo_number=f"{marker}-SPO-X", po_number=po.po_number,
              line_ref=line_a.source_ref, product_id=str(line_c.product_id))
    # Same line ref and product, another PO's number: not this document's goods.
    _spo_line(db, spo_number=f"{marker}-SPO-Y", po_number=f"{marker}-OTHER",
              line_ref=line_a.source_ref, product_id=str(line_a.product_id))

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    assert res.status_code == 200, res.text
    by_sku = {line["sku"]: line for line in _lines(res)}
    assert by_sku[f"{marker}-A"]["spo_numbers"] == [first, second]
    assert by_sku[f"{marker}-B"]["spo_numbers"] == []
    assert by_sku[f"{marker}-C"]["spo_numbers"] == []


def test_a_retired_spo_line_never_received_is_not_named_but_a_received_one_is(scm_app):
    """`visible_line_clauses()`: retired AND never received is hidden everywhere; a retired
    line that carries a receipt stays visible (stock really arrived on it)."""
    app, db = _as(scm_app)
    marker = f"{MARKER}{uuid.uuid4().hex[:6]}".upper()
    po_id, _ids = _seed_po_distinct_lines(db, marker, _codes(marker)[:1], [None])
    po, (line,) = _po_lines(db, po_id)
    _spo_line(db, spo_number=f"{marker}-SPO-GONE", po_number=po.po_number,
              line_ref=line.source_ref, product_id=str(line.product_id), retired=True)
    _spo_line(db, spo_number=f"{marker}-SPO-LANDED", po_number=po.po_number,
              line_ref=line.source_ref, product_id=str(line.product_id), retired=True,
              received=10)

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    [only] = _lines(res)
    assert only["spo_numbers"] == [f"{marker}-SPO-LANDED"]


def test_an_spo_line_in_another_company_is_never_named(scm_app):
    """The match is on plain text off the AutoCount feed, so another company's allocation
    naming the same PO number, ref and product must not read as ours."""
    app, db = _as(scm_app)
    marker = f"{MARKER}{uuid.uuid4().hex[:6]}".upper()
    po_id, _ids = _seed_po_distinct_lines(db, marker, _codes(marker)[:1], [None])
    po, (line,) = _po_lines(db, po_id)

    warehouse_id = _warehouse_id(db)
    other_company = str(uuid.uuid4())
    db.add(Company(
        id=other_company, name=f"{marker} other company",
        code=f"{marker}-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True,
    ))
    db.flush()
    set_company_scope(db, frozenset({other_company}))
    foreign = _spo_line(db, spo_number=f"{marker}-SPO-FOREIGN", po_number=po.po_number,
                        line_ref=line.source_ref, product_id=str(line.product_id),
                        warehouse_id=warehouse_id)
    foreign.company_id = other_company
    db.flush()
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    [only] = _lines(res)
    assert only["spo_numbers"] == []
    assert f"{marker}-SPO-FOREIGN" not in res.text
