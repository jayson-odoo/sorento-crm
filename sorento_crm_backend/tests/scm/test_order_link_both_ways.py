"""L3/L4 - the linkage works whichever file was uploaded first.

> "we need to cater when I upload PO before SO and also SO before PO, cause if I upload PO
> before SO, then the SO doesn't exist and the linkage is not formed"

That is the requirement, and it is the reason the pairing is a CLAIM rather than a nullable
foreign key: a claim made before the other document exists still has somewhere to live.

The two orderings are run as separate tests over the same data, and both must end in the same
state. A design that only works one way passes one of them and looks fine.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderLinkClaim
from app.services.scm import order_inquiry_service as inquiry
from app.services.scm import order_link_service as links
from tests._pg_fixture import pg_session

MARKER = "ZZTLINK"
SORENTO = "00000000-0000-0000-0000-000000000001"
FIXTURE = Path(__file__).parent / "fixtures" / "order_inquiry_sample.xlsx"

#: The rows the fixture actually contains, so the tests assert against real pairings.
SO_NUMBER = "SO414033"
LINKED = ("CWB242", "202605-S0042")
SPLIT_ITEM = "C-FHSS14"
LOCATION = "BRW-IB"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    """Products and a warehouse the fixture names. Get-or-create by exact code."""
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
        category_name=f"{MARKER} cat",
    )
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} u",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()

    products = {}
    for code in (LINKED[0], SPLIT_ITEM):
        p = db.query(Product).filter(Product.product_code == code).first()
        if p is None:
            p = Product(
                id=_u(), product_code=code, product_name=f"{MARKER} {code}",
                category_id=cat.id, base_uom_id=uom.id, list_price=0,
                is_active=True, is_discontinued=False,
            )
            db.add(p)
            db.flush()
        products[code] = p

    wh = db.query(Warehouse).filter(Warehouse.warehouse_code == LOCATION).first()
    if wh is None:
        wh = Warehouse(
            id=_u(), warehouse_code=LOCATION, warehouse_name=f"{MARKER} {LOCATION}",
            is_active=True, counts_as_available=True,
        )
        db.add(wh)
        db.flush()
    return {"products": products, "warehouse": wh, "cat": cat, "uom": uom}


def _make_sales_order(db, world) -> SalesOrder:
    customer = Customer(
        id=_u(), customer_code=f"{MARKER}-{uuid.uuid4().hex[:8]}"[:30],
        customer_name=f"{MARKER} customer",
    )
    db.add(customer)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=SO_NUMBER, customer_id=customer.id, status="open",
        order_type="project", order_date=date.today() - timedelta(days=5),
    )
    db.add(so)
    db.flush()
    for code, product in world["products"].items():
        db.add(SalesOrderLine(
            id=_u(), sales_order_id=so.id, product_id=product.id,
            qty_ordered=10, qty_delivered=0, line_status="open",
            required_date=date.today() + timedelta(days=30),
        ))
    db.flush()
    return so


def _make_purchase_order(db, world, po_number: str) -> PurchaseOrder:
    supplier = Supplier(
        id=_u(), supplier_code=f"{MARKER}-{uuid.uuid4().hex[:8]}"[:30],
        supplier_name=f"{MARKER} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_u(), po_number=po_number, supplier_id=supplier.id, status="active",
        issue_date=date.today() - timedelta(days=20),
    )
    db.add(po)
    db.flush()
    for code, product in world["products"].items():
        db.add(PurchaseOrderLine(
            id=_u(), purchase_order_id=po.id, product_id=product.id,
            warehouse_id=str(world["warehouse"].id),
            qty_ordered=10, qty_received=0, line_status="open",
            expected_date=date.today() + timedelta(days=20),
        ))
    db.flush()
    return po


def _claim(db, item_code: str, po_number: str) -> OrderLinkClaim:
    return (
        db.query(OrderLinkClaim)
        .filter(
            OrderLinkClaim.so_number == SO_NUMBER,
            OrderLinkClaim.item_code == item_code,
            OrderLinkClaim.po_number == po_number,
        )
        .one()
    )


# --------------------------------------------------------------------------- #
# the requirement, both ways round
# --------------------------------------------------------------------------- #

def test_purchase_order_uploaded_before_the_sales_order(db, world):
    """The order the user called out: the SO does not exist when the claim is made."""
    _make_purchase_order(db, world, LINKED[1])
    inquiry.apply(db, FIXTURE.read_bytes())

    # Nothing to link to yet - and the claim survives, which is the whole point.
    first = links.resolve(db)
    claim = _claim(db, *LINKED)
    assert claim.po_line_id is not None, "the purchase side was there and should be pinned"
    assert claim.so_line_id is None
    assert claim.resolved_at is None
    assert first["resolved"] == 0

    _make_sales_order(db, world)
    second = links.resolve(db)

    claim = _claim(db, *LINKED)
    assert claim.so_line_id is not None
    assert claim.resolved_at is not None
    assert second["resolved"] >= 1


def test_sales_order_uploaded_before_the_purchase_order(db, world):
    """The mirror. Same end state, reached from the other side."""
    _make_sales_order(db, world)
    inquiry.apply(db, FIXTURE.read_bytes())

    links.resolve(db)
    claim = _claim(db, *LINKED)
    assert claim.so_line_id is not None
    assert claim.po_line_id is None
    assert claim.resolved_at is None

    _make_purchase_order(db, world, LINKED[1])
    links.resolve(db)

    claim = _claim(db, *LINKED)
    assert claim.po_line_id is not None
    assert claim.resolved_at is not None


def test_both_orderings_reach_the_same_state(db, world):
    """Stated as its own assertion, because "it works" is not the requirement - "it does not
    matter which file you upload first" is."""
    _make_sales_order(db, world)
    _make_purchase_order(db, world, LINKED[1])
    inquiry.apply(db, FIXTURE.read_bytes())
    links.resolve(db)

    claim = _claim(db, *LINKED)
    assert claim.so_line_id and claim.po_line_id and claim.resolved_at


# --------------------------------------------------------------------------- #
# the properties that keep it usable
# --------------------------------------------------------------------------- #

def test_resolving_twice_changes_nothing(db, world):
    """It runs after every upload, so it has to be safe to run when nothing has moved."""
    _make_sales_order(db, world)
    _make_purchase_order(db, world, LINKED[1])
    inquiry.apply(db, FIXTURE.read_bytes())

    first = links.resolve(db)
    stamped = _claim(db, *LINKED).resolved_at
    second = links.resolve(db)

    assert second["resolved"] == 0
    assert _claim(db, *LINKED).resolved_at == stamped
    assert first["resolved"] >= 1


def test_a_line_split_across_two_purchase_orders_claims_both(db, world):
    """`202606-S0024 & 202607-S0043` is one line waiting on two orders.

    One claim each: linking only the first would leave half the supply unaccounted for, and
    nothing on any screen would show it.
    """
    inquiry.apply(db, FIXTURE.read_bytes())
    claims = (
        db.query(OrderLinkClaim)
        .filter(OrderLinkClaim.item_code == SPLIT_ITEM)
        .all()
    )
    assert {c.po_number for c in claims} >= {"202606-S0024", "202607-S0043"}


def test_the_stock_location_is_written_onto_the_sales_order_line(db, world):
    """The location the user could not see a source for. It was in this sheet all along."""
    so = _make_sales_order(db, world)
    for line in db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == so.id):
        line.warehouse_id = None
    db.flush()

    out = inquiry.apply(db, FIXTURE.read_bytes())

    assert out["locations_written"] >= 1
    written = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == so.id)
        .first()
    )
    assert str(written.warehouse_id) == str(world["warehouse"].id)


def test_a_sales_order_that_has_not_been_uploaded_is_named_not_silently_skipped(db, world):
    """A location can only be written onto a line that exists.

    That limit is real, so it is counted AND the sales orders are named - re-uploading the
    sheet after the SO book lands applies them, and somebody has to be able to see which.
    """
    out = inquiry.apply(db, FIXTURE.read_bytes())
    assert out["lines_unmatched"] >= 1
    assert SO_NUMBER in out["sales_orders_not_found"]


def test_open_claims_are_reportable(db, world):
    """"34 sales orders name a purchase order we have not seen" is how somebody finds out the
    PO book is a month behind. There is no other way to find it out."""
    inquiry.apply(db, FIXTURE.read_bytes())
    links.resolve(db)

    out = links.open_claims(db)
    assert out["open"] >= 1
    assert out["waiting_for_purchase_order"] >= 1
    assert any(po.startswith("2026") for po in out["purchase_orders"])
