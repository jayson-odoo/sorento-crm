"""What a product costs, and the evidence for it.

> "I want to see the cost of this product, and I want to know where it derives from, like
>  is it last purchase price, if yes, what's the PO and who is the supplier"

A number with no provenance cannot be checked. So the summary is never just a figure: it
names the order, the supplier and the date, or it says plainly that we have never bought
the item. The two ways of having no cost are distinct facts and are reported as such.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import product_purchase_history_service as svc
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _product(db, code: str) -> str:
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"CAT-{code}", category_name=f"Category {code}"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"UOM-{code}", uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    pid = str(uuid.uuid4())
    db.add(Product(
        id=pid, product_code=code, product_name=code,
        category_id=category.id, base_uom_id=uom.id, list_price=0, is_active=True,
    ))
    db.flush()
    return pid


def _supplier(db, name: str) -> str:
    sid = str(uuid.uuid4())
    db.add(Supplier(id=sid, supplier_code=unique_code("SUP"), supplier_name=name))
    db.flush()
    return sid


def _order(db, product_id: str, *, supplier_id, issued: date, cost, currency="MYR",
           qty=10) -> str:
    poid = str(uuid.uuid4())
    db.add(PurchaseOrder(
        id=poid, po_number=unique_code("PO"), supplier_id=supplier_id,
        issue_date=issued, status="active", currency=currency,
    ))
    db.flush()
    db.add(PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=poid, product_id=product_id,
        qty_ordered=qty, qty_received=0, unit_cost=cost, currency=currency,
    ))
    db.flush()
    return poid


def test_the_cost_names_the_order_the_supplier_and_the_date(db):
    pid = _product(db, unique_code("MWC"))
    weikaili = _supplier(db, "Weikaili")
    _order(db, pid, supplier_id=weikaili, issued=date(2025, 3, 1), cost=98.47)
    newest_supplier = _supplier(db, "Sanjiang")
    newest = _order(db, pid, supplier_id=newest_supplier, issued=date(2026, 1, 9), cost=88.00)

    result = svc.purchase_history(db, pid)
    cost = result["cost"]

    assert cost["status"] == "ok"
    assert cost["unit_cost"] == 88.00, "the LAST purchase, not the cheapest or the first"
    assert cost["currency"] == "MYR"
    assert cost["purchase_order_id"] == newest
    assert cost["supplier_name"] == "Sanjiang"
    assert cost["issue_date"] == "2026-01-09"


def test_never_purchased_is_said_plainly_rather_than_shown_as_a_dash(db):
    # The product the user asked about: real committed demand, no purchase order anywhere.
    # A bare dash reads as "we forgot to fill this in"; the truth is that nobody has bought it.
    pid = _product(db, unique_code("MWC"))

    result = svc.purchase_history(db, pid)

    assert result["lines"] == []
    assert result["total"] == 0
    assert result["cost"]["status"] == "never_purchased"
    assert result["cost"]["unit_cost"] is None


def test_bought_but_with_no_price_recorded_is_a_different_fact(db):
    pid = _product(db, unique_code("MWC"))
    sup = _supplier(db, "No Price Supplier")
    _order(db, pid, supplier_id=sup, issued=date(2025, 6, 1), cost=None)

    result = svc.purchase_history(db, pid)

    assert result["total"] == 1, "the order still shows in the history"
    assert result["cost"]["status"] == "no_price_recorded"


def test_a_recorded_zero_is_a_price_of_zero_not_a_missing_one(db):
    # > "if 0 unit cost right, it can mean we haven't purchased before, or it is genuinely
    # >  free" - the order line is the thing that tells those two apart.
    pid = _product(db, unique_code("MWC"))
    sup = _supplier(db, "Free Sample Supplier")
    _order(db, pid, supplier_id=sup, issued=date(2025, 8, 1), cost=0)

    cost = svc.purchase_history(db, pid)["cost"]

    assert cost["status"] == "ok"
    assert cost["unit_cost"] == 0.0


def test_history_is_newest_first_and_reports_what_it_did_not_show(db):
    pid = _product(db, unique_code("MWC"))
    sup = _supplier(db, "Repeat Supplier")
    for n, day in enumerate([date(2024, 1, 1), date(2025, 1, 1), date(2026, 1, 1)]):
        _order(db, pid, supplier_id=sup, issued=day, cost=10 + n)

    result = svc.purchase_history(db, pid, limit=2)

    assert [ln["issue_date"] for ln in result["lines"]] == ["2026-01-01", "2025-01-01"]
    assert result["shown"] == 2
    assert result["total"] == 3, "the cap must be visible, never silent"


def test_an_order_with_no_supplier_is_still_history(db):
    # 15 lines in the customer's own book sit on an order with no supplier. Dropping them
    # would understate how often the item was bought.
    pid = _product(db, unique_code("MWC"))
    _order(db, pid, supplier_id=None, issued=date(2025, 5, 5), cost=42.5)

    result = svc.purchase_history(db, pid)

    assert result["total"] == 1
    assert result["lines"][0]["supplier_name"] is None
    assert result["cost"]["unit_cost"] == 42.5


def test_another_products_orders_are_not_this_products_cost(db):
    mine = _product(db, unique_code("MWC"))
    theirs = _product(db, unique_code("OTHER"))
    sup = _supplier(db, "Shared Supplier")
    _order(db, theirs, supplier_id=sup, issued=date(2026, 2, 2), cost=999.0)

    result = svc.purchase_history(db, mine)

    assert result["total"] == 0
    assert result["cost"]["status"] == "never_purchased"
