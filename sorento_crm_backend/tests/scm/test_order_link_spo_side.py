"""The claim resolves an `SPO-` number against `spo_allocations`. Review blocker 1.

Since migration 420 a shipping order is a row in `spo_allocations`, not in
`purchase_order_lines`. A resolver that could only look in the second one left 12,393
claims, naming 2,989 sales orders, permanently unresolvable - and
`sales_order_service.with_links` reads `resolved_at`, so every one of those orders read
"awaiting purchase order" on the list with nothing that could ever clear it.

Both orderings are pinned, because both happen: the captain uploads the SPO book before the
sales order as often as after it, and the claim exists precisely so neither loses.

`blank_session`, so the counts are about this test's own rows.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderLinkClaim
from app.services.scm import order_link_service

from .._pg_fixture import blank_session

MARKER = "ZZTLINK"


def _uid() -> str:
    return str(uuid.uuid4())


def _company(db) -> str:
    from sqlalchemy import text

    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}{uuid.uuid4().hex[:6]}", uom_name="Set")
    category = ProductCategory(id=_uid(), category_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                               category_name=f"{MARKER} cat")
    db.add_all([uom, category])
    db.flush()
    row = Product(id=_uid(), product_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                  product_name=f"{MARKER} basin", category_id=category.id,
                  base_uom_id=uom.id, list_price=Decimal("10.00"))
    db.add(row)
    db.flush()
    return row


def _sales_order(db, company_id: str, product: Product) -> SalesOrder:
    so = SalesOrder(id=_uid(), company_id=company_id,
                    so_number=f"ZZT-SO-{uuid.uuid4().hex[:8]}", status="open")
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_uid(), company_id=company_id, sales_order_id=so.id, product_id=product.id,
        qty_ordered=Decimal("10"), qty_delivered=Decimal("0"), line_status="open",
    ))
    db.flush()
    return so


def _allocation(db, spo_number: str, product: Product, *, line_no: int) -> SPOAllocation:
    row = SPOAllocation(
        id=_uid(), spo_number=spo_number, spo_line_number=line_no, product_id=product.id,
        allocated_quantity=10, quantity_received=0, receipt_status="pending",
        line_status="open", source_system="scm_spo_history",
        expected_date=date.today(),
    )
    db.add(row)
    db.flush()
    return row


def _claim(db, so_number: str, doc: str, item_code, company_id) -> OrderLinkClaim:
    row = OrderLinkClaim(id=_uid(), so_number=so_number, po_number=doc, item_code=item_code,
                         source="po_history", company_id=company_id)
    db.add(row)
    db.flush()
    return row


def test_a_claim_naming_an_spo_resolves_against_the_allocation():
    with blank_session() as db:
        company_id = _company(db)
        product = _product(db)
        so = _sales_order(db, company_id, product)
        spo_number = f"SPO-2026/08-{uuid.uuid4().hex[:4]}"
        allocation = _allocation(db, spo_number, product, line_no=1)
        claim = _claim(db, so.so_number, spo_number, product.product_code, company_id)
        db.commit()

        out = order_link_service.resolve(db, so_numbers={so.so_number})
        db.expire_all()

        assert out["resolved"] == 1
        row = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim.id).one()
        assert row.spo_allocation_id == allocation.id
        assert row.po_line_id is None
        assert row.resolved_at is not None


def test_the_lowest_line_number_wins_where_a_document_states_the_item_twice():
    """Two containers of one product on one shipping order. The claim names the document and
    the item, not the container, so the pick has to be deterministic or a re-run moves it."""
    with blank_session() as db:
        company_id = _company(db)
        product = _product(db)
        so = _sales_order(db, company_id, product)
        spo_number = f"SPO-2026/08-{uuid.uuid4().hex[:4]}"
        second = _allocation(db, spo_number, product, line_no=2)
        first = _allocation(db, spo_number, product, line_no=1)
        claim = _claim(db, so.so_number, spo_number, product.product_code, company_id)
        db.commit()

        order_link_service.resolve(db, so_numbers={so.so_number})
        db.expire_all()

        row = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim.id).one()
        assert row.spo_allocation_id == first.id
        assert row.spo_allocation_id != second.id


def test_the_spo_side_can_arrive_after_the_claim():
    """The whole reason the pairing is a claim: whichever document is uploaded second
    completes it, and running the resolver before it exists loses nothing."""
    with blank_session() as db:
        company_id = _company(db)
        product = _product(db)
        so = _sales_order(db, company_id, product)
        spo_number = f"SPO-2026/08-{uuid.uuid4().hex[:4]}"
        claim = _claim(db, so.so_number, spo_number, product.product_code, company_id)
        db.commit()

        early = order_link_service.resolve(db, so_numbers={so.so_number})
        assert early["resolved"] == 0
        assert early["po_side"] == 0

        allocation = _allocation(db, spo_number, product, line_no=1)
        db.commit()

        late = order_link_service.resolve(db, so_numbers={so.so_number})
        db.expire_all()

        assert late["resolved"] == 1
        row = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim.id).one()
        assert row.spo_allocation_id == allocation.id


def test_a_purchase_order_still_resolves_to_its_line():
    """The other family, unchanged. Both live in the same loop, so the regression this
    guards against is a real one."""
    with blank_session() as db:
        company_id = _company(db)
        product = _product(db)
        so = _sales_order(db, company_id, product)
        supplier = Supplier(id=_uid(), supplier_code=f"{MARKER}{uuid.uuid4().hex[:6]}",
                            supplier_name=f"{MARKER} factory", is_active=True)
        db.add(supplier)
        db.flush()
        po_number = f"202608-S{uuid.uuid4().hex[:4]}"
        po = PurchaseOrder(id=_uid(), po_number=po_number, supplier_id=supplier.id,
                           status="active", company_id=company_id)
        db.add(po)
        db.flush()
        line = PurchaseOrderLine(
            id=_uid(), purchase_order_id=po.id, product_id=product.id,
            qty_ordered=Decimal("10"), qty_received=Decimal("0"), line_status="open",
            company_id=company_id,
        )
        db.add(line)
        claim = _claim(db, so.so_number, po_number, product.product_code, company_id)
        db.commit()

        order_link_service.resolve(db, so_numbers={so.so_number})
        db.expire_all()

        row = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim.id).one()
        assert row.po_line_id == line.id
        assert row.spo_allocation_id is None
        assert row.resolved_at is not None


def test_a_resolved_spo_claim_is_not_waiting_for_a_purchase_order():
    """`open_claims` feeds the upload result's "34 orders name a purchase order we have not
    seen". An SPO claim that HAS its allocation must not be counted there."""
    with blank_session() as db:
        company_id = _company(db)
        product = _product(db)
        # The order's only line is for a DIFFERENT item, so this claim never finds its
        # sales side and stays open - which is the case that proves the purchase side is
        # read from the right column rather than from `resolved_at`.
        other = _product(db)
        so = _sales_order(db, company_id, other)
        spo_number = f"SPO-2026/08-{uuid.uuid4().hex[:4]}"
        _allocation(db, spo_number, product, line_no=1)
        _claim(db, so.so_number, spo_number, product.product_code, company_id)
        db.commit()

        order_link_service.resolve(db, so_numbers={so.so_number})
        out = order_link_service.open_claims(db)

        waiting = [n for n in out["purchase_orders"] if n == spo_number]
        assert waiting == []
        assert out["waiting_for_sales_order"] >= 1
