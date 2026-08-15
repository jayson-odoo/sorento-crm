"""Find a SKU's purchase orders, and what we last paid for it.

> "in PO can I search this product also, like MWC7624-RL-S10 I want to see its PO and its
> last purchase price (unit cost), so at least I know if it doesn't appear in planning, I can
> check from here"

The purchase-order list searched the PO number and the supplier only, so the one question a
buyer asks of it - "have we ever bought this item, and for how much" - could not be asked. It
matters more now that the plan takes its cost from this book: when a line shows no cost, this
screen is where you find out whether that is because we have never bought it.

The search is on the LINES, so a PO is returned when any of its lines names the product. The
same filter also carries the last price, because "which orders" and "what did we pay" are one
question, not two.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTPOP"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    wanted = Product(id=_u(), product_code=f"{MARKER}-WANTED", product_name=f"{MARKER} wanted",
                     category_id=cat.id, base_uom_id=uom.id, list_price=0,
                     is_active=True, is_discontinued=False)
    other = Product(id=_u(), product_code=f"{MARKER}-OTHER", product_name=f"{MARKER} other",
                    category_id=cat.id, base_uom_id=uom.id, list_price=0,
                    is_active=True, is_discontinued=False)
    supplier = Supplier(id=_u(), supplier_code=unique_code("S"),
                        supplier_name=f"{MARKER} Supplier")
    db.add_all([wanted, other, supplier])
    db.flush()
    return {"wanted": wanted, "other": other, "supplier": supplier}


def _po(db, world, product, cost, when: date, *, qty=10) -> PurchaseOrder:
    po = PurchaseOrder(id=_u(), po_number=unique_code(MARKER),
                       supplier_id=world["supplier"].id, status="closed",
                       issue_date=when, currency="MYR")
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, qty_ordered=qty,
        qty_received=qty, unit_cost=cost, currency="MYR", line_status="closed",
    ))
    db.flush()
    return po


def _numbers(db, **kw) -> set[str]:
    out = PurchaseOrderService(db).list(
        page=1, limit=100, sort="po_number", direction="asc",
        query=MARKER, status=None, supplier=None, **kw,
    )
    return {row["po_number"] for row in out["data"]}


# --------------------------------------------------------------------------- #

def test_a_product_code_returns_the_orders_that_carry_it(db, world):
    mine = _po(db, world, world["wanted"], 8, date(2026, 6, 1))
    theirs = _po(db, world, world["other"], 8, date(2026, 6, 1))

    got = _numbers(db, product_code=world["wanted"].product_code)

    assert got == {mine.po_number}
    assert theirs.po_number not in got


def test_the_code_is_matched_whatever_its_casing_or_padding(db, world):
    mine = _po(db, world, world["wanted"], 8, date(2026, 6, 1))

    assert _numbers(db, product_code=f"  {world['wanted'].product_code.lower()} ") == {
        mine.po_number
    }


def test_a_code_nobody_holds_returns_nothing_rather_than_everything(db, world):
    """A filter that quietly ignores what it did not understand shows the whole book under a
    heading claiming it is narrowed."""
    _po(db, world, world["wanted"], 8, date(2026, 6, 1))

    assert _numbers(db, product_code=f"{MARKER}-NO-SUCH-CODE") == set()


def test_an_order_is_returned_once_even_when_it_carries_the_item_twice(db, world):
    """A split line must not double the order in the list."""
    po = _po(db, world, world["wanted"], 8, date(2026, 6, 1))
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=world["wanted"].id, qty_ordered=5,
        qty_received=5, unit_cost=9, currency="MYR", line_status="closed",
    ))
    db.flush()

    out = PurchaseOrderService(db).list(
        page=1, limit=100, sort="po_number", direction="asc", query=MARKER,
        status=None, supplier=None, product_code=world["wanted"].product_code,
    )

    assert [r["po_number"] for r in out["data"]].count(po.po_number) == 1
    assert out["pagination"]["total"] == 1


def test_it_reports_what_we_last_paid_and_on_which_order(db, world):
    """The answer to "does this SKU have a cost", in the place the buyer goes looking."""
    _po(db, world, world["wanted"], 9, date(2026, 1, 1))
    latest = _po(db, world, world["wanted"], 7, date(2026, 6, 1))

    out = PurchaseOrderService(db).list(
        page=1, limit=100, sort="po_number", direction="asc", query=MARKER,
        status=None, supplier=None, product_code=world["wanted"].product_code,
    )

    assert out["product_cost"]["unit_cost"] == 7.0
    assert out["product_cost"]["po_number"] == latest.po_number
    assert out["product_cost"]["issue_date"] == "2026-06-01"


def test_a_recorded_zero_is_reported_as_zero_not_as_unknown(db, world):
    """Free and never-bought are different answers, and this screen is where the buyer
    tells them apart."""
    _po(db, world, world["wanted"], 0, date(2026, 6, 1))

    out = PurchaseOrderService(db).list(
        page=1, limit=100, sort="po_number", direction="asc", query=MARKER,
        status=None, supplier=None, product_code=world["wanted"].product_code,
    )

    assert out["product_cost"]["unit_cost"] == 0.0


def test_no_cost_is_reported_when_the_item_was_never_bought(db, world):
    out = PurchaseOrderService(db).list(
        page=1, limit=100, sort="po_number", direction="asc", query=MARKER,
        status=None, supplier=None, product_code=f"{MARKER}-NO-SUCH-CODE",
    )

    assert out["product_cost"] is None


def test_no_cost_block_is_returned_when_no_product_was_asked_for(db, world):
    """The list is not about one product unless somebody said so."""
    _po(db, world, world["wanted"], 8, date(2026, 6, 1))

    out = PurchaseOrderService(db).list(
        page=1, limit=100, sort="po_number", direction="asc", query=MARKER,
        status=None, supplier=None,
    )

    assert out["product_cost"] is None


# --------------------------------------------------------------------------- #
# the wire, not just the service
# --------------------------------------------------------------------------- #

def test_the_response_model_actually_carries_the_cost_block():
    """The service built `product_cost` correctly and FastAPI dropped it on the way out,
    because the response model did not declare it. Nothing in the service tests could see
    that: the field only disappears at serialization.

    Asserted on the model rather than over HTTP, so it needs no principal and no seeded
    row, and it fails for the one reason that matters - the field is not on the contract.
    """
    from app.schemas.scm_orders import PurchaseOrderListResponse

    assert "product_cost" in PurchaseOrderListResponse.model_fields

    built = PurchaseOrderListResponse(
        data=[],
        empty=True,
        pagination={"total": 0, "page": 1},
        product_cost={
            "unit_cost": 0.0,
            "currency": "MYR",
            "po_number": "202606-S0024",
            "issue_date": "2026-06-01",
            "supplier_name": "Kaiping Kaixin",
        },
    )
    dumped = built.model_dump()
    assert dumped["product_cost"]["unit_cost"] == 0.0, "a free price survived as free"
    assert dumped["product_cost"]["po_number"] == "202606-S0024"


def test_the_cost_block_is_absent_rather_than_zeroed_when_unknown():
    from app.schemas.scm_orders import PurchaseOrderListResponse

    built = PurchaseOrderListResponse(data=[], empty=True, pagination={"total": 0, "page": 1})

    assert built.model_dump()["product_cost"] is None
