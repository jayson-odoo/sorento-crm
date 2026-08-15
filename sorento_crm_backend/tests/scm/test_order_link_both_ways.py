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
from datetime import date, datetime, timedelta
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
#: Every item code the fixture workbook names. `test_every_resolvable_row_now_lands_...`
#: asserts every row resolves to a line, which is only true when the catalogue holds all
#: of them - on a from-zero database that means seeding them here, not borrowing whatever
#: a prod-copy restore happens to already have.
FIXTURE_ITEM_CODES = (
    "CWCX1009-RL", "CWCY1009", "CWC1009-SC", "CWB242", "CB65SS", "C-FHSS14",
)
#: The delivery date the fixture states for the first instalment of both items above.
#: An instalment is keyed by (SO number, item, date), so a seeded line dated anything else
#: is a different instalment and the sheet correctly declines to match it. Seeding it as
#: `today + 30` made the test pass on one day of the calendar and fail on the rest.
INSTALMENT_DATE = date(2026, 9, 14)


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
    for code in FIXTURE_ITEM_CODES:
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


def _clear_sales_orders(db, numbers) -> None:
    """Remove any sales order the FIXTURE names, so the test starts from the state it describes.

    These tests are about what happens when a sales order does NOT yet exist, or exists only as
    the SO book wrote it. The fixture uses real order numbers, so on a database restored from
    production every one of them is already there, imported by this very feed - "before the
    sales order" is then not true, nothing is created, and three tests fail for a reason that
    has nothing to do with the code. `so_number` is unique per company, so adopting the row is
    not enough either: the feed would own it and rewrite its lines.

    Everything here runs inside a transaction the fixture rolls back, so the real orders are
    untouched.
    """
    ids = [
        r[0]
        for r in db.query(SalesOrder.id).filter(SalesOrder.so_number.in_(list(numbers))).all()
    ]
    if not ids:
        return
    db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(SalesOrder).filter(SalesOrder.id.in_(ids)).delete(synchronize_session=False)
    db.flush()


def _fixture_so_numbers(db) -> set[str]:
    parsed = inquiry.read_order_inquiry(FIXTURE.read_bytes())
    instalments, _ = inquiry._instalments(parsed)
    return {r.so_number for r in instalments if r.so_number}


def _make_sales_order(db, world) -> SalesOrder:
    customer = Customer(
        id=_u(), customer_code=f"{MARKER}-{uuid.uuid4().hex[:8]}"[:30],
        customer_name=f"{MARKER} customer",
    )
    db.add(customer)
    db.flush()
    _clear_sales_orders(db, {SO_NUMBER})
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
            required_date=INSTALMENT_DATE,
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


def _order_level_claim(db, po_number: str) -> OrderLinkClaim:
    """A claim with no item: what the purchase-history notes produce."""
    return (
        db.query(OrderLinkClaim)
        .filter(
            OrderLinkClaim.so_number == SO_NUMBER,
            OrderLinkClaim.po_number == po_number,
            OrderLinkClaim.item_code.is_(None),
        )
        .one()
    )


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
    """The order the user called out: the SO does not exist when the claim is made.

    Carried by a PO-HISTORY claim rather than an inquiry one. The inquiry sheet now creates
    the sales order itself, so its own claims resolve in the same pass - which is the feature,
    and is pinned next door. The purchase-history notes cannot: they name a sales order and
    carry no item, quantity or date, so there is nothing to build an order out of. That is the
    case where a claim genuinely has to outlive a missing document, and it is the one worth
    proving here.
    """
    # The premise of the test, made true rather than assumed: on a database restored from
    # production this order already exists and the claim would resolve on the first pass.
    _clear_sales_orders(db, {SO_NUMBER})
    _make_purchase_order(db, world, LINKED[1])
    db.add(OrderLinkClaim(
        id=_u(), so_number=SO_NUMBER, po_number=LINKED[1], item_code=None,
        source="po_history", claimed_at=datetime(2026, 8, 5, 12, 0, 0),
    ))
    db.flush()

    # Nothing to link to yet - and the claim survives, which is the whole point.
    first = links.resolve(db)
    claim = _order_level_claim(db, LINKED[1])
    assert claim.po_line_id is not None, "the purchase side was there and should be pinned"
    assert claim.so_line_id is None
    assert claim.resolved_at is None
    assert first["resolved"] == 0

    _make_sales_order(db, world)
    second = links.resolve(db)

    claim = _order_level_claim(db, LINKED[1])
    assert claim.so_line_id is not None
    assert claim.resolved_at is not None
    assert second["resolved"] >= 1


def test_the_inquiry_sheet_resolves_its_own_sales_order_side_immediately(db, world):
    """Because it now CREATES the sales order, rather than waiting for CS to upload it.

    This is the whole point of promoting the sheet to a demand feed: the pairing is complete
    the moment the purchase order is there, with nobody else in the loop.
    """
    _make_purchase_order(db, world, LINKED[1])
    inquiry.apply(db, FIXTURE.read_bytes())
    links.resolve(db)

    claim = _claim(db, *LINKED)
    assert claim.so_line_id is not None, "the sheet created the order, so the side exists"
    assert claim.po_line_id is not None
    assert claim.resolved_at is not None


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


def test_every_resolvable_row_now_lands_because_the_sheet_creates_the_order(db, world):
    """The limit this test used to pin is gone, and that IS the feature.

    It read: "a location can only be written onto a line that exists", counted the rows whose
    sales order we did not hold, and named them so somebody could go and ask CS for the SO
    book. The sheet now creates those orders itself, so for every row whose item is in the
    catalogue there is a line by the time the counts are taken.

    What survives is the limit that cannot be removed: a row naming an item we do not hold
    still becomes nothing, because `product_id` is NOT NULL and the alternative is inventing
    a product. That half is pinned in `test_order_inquiry_creates_demand.py`.
    """
    _clear_sales_orders(db, _fixture_so_numbers(db))
    out = inquiry.apply(db, FIXTURE.read_bytes())

    assert out["orders_created"] >= 1, "the sheet is a demand feed now, not an annotation"
    assert out["lines_unmatched"] == 0, "every resolvable row has a line"
    assert out["sales_orders_not_found"] == []
    # And the counts agree with themselves: nothing is reported missing that was just created.
    assert out["lines_matched"] == out["rows"]


def test_open_claims_are_reportable(db, world):
    """"34 sales orders name a purchase order we have not seen" is how somebody finds out the
    PO book is a month behind. There is no other way to find it out."""
    inquiry.apply(db, FIXTURE.read_bytes())
    links.resolve(db)

    out = links.open_claims(db)
    assert out["open"] >= 1
    assert out["waiting_for_purchase_order"] >= 1
    assert any(po.startswith("2026") for po in out["purchase_orders"])
