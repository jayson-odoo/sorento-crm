"""N4 - two feeds write sales orders, and neither may clobber the other.

Joey's Order Inquiry sheet creates orders so he can plan without waiting for CS. CS's
outstanding extract is the statement of the whole open book. Both name the same `so_number`
sooner or later, and the question this suite settles is what happens when they meet.

The rule, and the reason it is a rule rather than "last writer wins":

* CS's extract ADOPTS an order the sheet created - one order, never two - and TAKES OWNERSHIP.
* After that the sheet annotates and never overwrites, so a quantity CS corrected on Monday
  is still there after Joey re-uploads on Tuesday.

Both orderings are run against the same data, because a precedence rule that only works when
the uploads happen in one order is not a precedence rule. That is the same test shape the
SO<->PO linkage uses, for the same reason.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import project_order_inquiry_import_service as inquiry
from tests._pg_fixture import pg_session

# This suite moved out of `tests/scm/` with the importer it covers (ADR 0010), so the SCM
# conftest is no longer auto-loaded for it. `scm_app` is imported by name rather than copied:
# the route half of the handover still goes through the SCM upload endpoints, and a second
# savepoint fixture would be the same thing maintained twice.
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401

pytestmark = requires_pg

MARKER = "ZZTHAND"
SORENTO = "00000000-0000-0000-0000-000000000001"

SO_NUMBER = "SO910001"
ITEM = "ZZTHAND-ITEM"
LOCATION = "ZZTHAND-WH"

#: What CS says, and what the sheet says. Different on purpose - the whole question is which
#: number survives which upload.
CS_QTY = 999.0
SHEET_QTY = 10.0


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} u",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=ITEM, product_name=f"{MARKER} item",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    wh = Warehouse(id=_u(), warehouse_code=LOCATION, warehouse_name=f"{MARKER} wh",
                   is_active=True, counts_as_available=True)
    db.add_all([product, wh])
    db.flush()
    return {"product": product, "warehouse": wh}


class _Row:
    def __init__(self, qty=SHEET_QTY):
        self.so_number = SO_NUMBER
        self.item_code = ITEM
        self.qty = qty
        self.so_date = date(2026, 7, 1)
        self.delivery_date = date(2026, 9, 1)
        self.project = ""
        self.location = LOCATION
        self.supplier = ""
        self.po_numbers = ()
        self.not_ordered = False
        self.sheet = "Sheet1"
        self.source_row = 2


class _Parsed:
    def __init__(self, rows):
        self.rows = rows
        self.ok = True
        self.problems = []
        self.sheets_read = ["Sheet1"]
        self.sheets_skipped = []
        self.with_location = len(rows)
        self.po_claims = 0


def _sheet_upload(db, qty=SHEET_QTY) -> dict:
    return inquiry._create_orders(db, _Parsed([_Row(qty)]), inquiry._now())


def _cs_upload(db, world) -> SalesOrder:
    """What CS's extract does to this document, at the point this suite cares about.

    The importer's own machinery (reader, alias resolution, diff) has its own suites; what is
    reproduced here is the ADOPTION step - find by number, take ownership, state the figures -
    because that is the behaviour under test and driving a whole workbook through would add a
    second thing that could fail.
    """
    header = (
        db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).one_or_none()
    )
    if header is None:
        header = SalesOrder(id=_u(), so_number=SO_NUMBER, status="open",
                            source_system="scm_upload", source_ref="sales-orders")
        db.add(header)
        db.flush()
    elif (header.source_system or "") not in ("", "scm_upload"):
        header.source_system = "scm_upload"
        header.source_ref = "sales-orders"

    line = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == str(header.id),
                SalesOrderLine.product_id == str(world["product"].id))
        .one_or_none()
    )
    if line is None:
        line = SalesOrderLine(id=_u(), sales_order_id=str(header.id),
                              product_id=str(world["product"].id), qty_ordered=CS_QTY,
                              qty_delivered=0, line_status="open",
                              required_date=date(2026, 12, 31))
        db.add(line)
    else:
        line.qty_ordered = CS_QTY
        line.required_date = date(2026, 12, 31)
    db.flush()
    return header


def _orders(db) -> list[SalesOrder]:
    return db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).all()


def _qty(db) -> float:
    order = _orders(db)[0]
    line = db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(order.id)
    ).one()
    return float(line.qty_ordered)


# --------------------------------------------------------------------------- #
# both orderings, same end state
# --------------------------------------------------------------------------- #

def test_the_sheet_first_then_cs(db, world):
    """Joey plans on Monday; CS exports on Friday. CS takes over and keeps their figure."""
    _sheet_upload(db)
    assert len(_orders(db)) == 1
    assert _orders(db)[0].source_system == inquiry.SOURCE_SYSTEM

    _cs_upload(db, world)

    assert len(_orders(db)) == 1, "CS duplicated an order the sheet had already created"
    assert _orders(db)[0].source_system == "scm_upload", "ownership did not transfer"
    assert _qty(db) == CS_QTY


def test_cs_first_then_the_sheet(db, world):
    """The mirror, and the one that matters more: the sheet must not undo CS."""
    _cs_upload(db, world)

    out = _sheet_upload(db)

    assert out["orders_created"] == 0
    assert out["orders_owned_elsewhere"] == 1
    assert len(_orders(db)) == 1
    assert _qty(db) == CS_QTY, "the sheet overwrote a quantity CS owns"


def test_a_later_sheet_upload_cannot_revert_what_cs_corrected(db, world):
    """The failure the ownership rule exists to prevent, stated as its own test.

    Without the handover the sheet keeps `source_system`, treats the order as its own, and
    Tuesday's upload silently puts Monday's spreadsheet number back over CS's correction.
    Nothing on any screen would show it.
    """
    _sheet_upload(db)
    _cs_upload(db, world)

    _sheet_upload(db, qty=SHEET_QTY)   # Joey re-uploads his working sheet

    assert _qty(db) == CS_QTY
    assert _orders(db)[0].source_system == "scm_upload"


def test_both_orderings_reach_the_same_state(db, world):
    """Stated on its own, because "it works" is not the requirement - "the order of the two
    uploads does not change the answer" is."""
    _sheet_upload(db)
    _cs_upload(db, world)
    first = (len(_orders(db)), _orders(db)[0].source_system, _qty(db))

    # Same pair, reversed, on a clean document.
    db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(_orders(db)[0].id)
    ).delete(synchronize_session=False)
    db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).delete(
        synchronize_session=False
    )
    db.flush()

    _cs_upload(db, world)
    _sheet_upload(db)
    second = (len(_orders(db)), _orders(db)[0].source_system, _qty(db))

    assert first == second == (1, "scm_upload", CS_QTY)


def test_demand_origin_survives_both_orderings(db, world):
    """S13b (AC-S13b.5). Project demand is keyed on `demand_origin`, so whichever feed lands
    first, an order the inquiry names must end up stamped - CS adopting it must not erase
    the stamp (sheet first), and the sheet annotating a CS-owned order must still write it
    (CS first). Demand identical in both orderings follows from this, because
    `scm.committed_v` reads exactly this column."""
    _sheet_upload(db)
    _cs_upload(db, world)
    first = _orders(db)[0].demand_origin

    db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(_orders(db)[0].id)
    ).delete(synchronize_session=False)
    db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).delete(
        synchronize_session=False
    )
    db.flush()

    _cs_upload(db, world)
    _sheet_upload(db)
    second = _orders(db)[0].demand_origin

    assert first == second == inquiry.SOURCE_SYSTEM


# --------------------------------------------------------------------------- #
# the same claim, against the REAL importer
# --------------------------------------------------------------------------- #

def test_the_real_outstanding_importer_adopts_an_inquiry_created_order(scm_app):
    """The tests above reproduce the adoption step; this one runs it.

    A reproduction can agree with itself while the real path does something else, and the
    thing being protected here - one order, ownership transferred - is only true if the
    SHIPPED importer does it. Driven through `svc.apply` with a real workbook.
    """
    from tests.scm._outstanding_workbooks import make_codes, seed_catalogue, week1
    from app.services.scm import outstanding_import_service as svc
    from app.services.scm.outstanding_reader import SO

    _app, db, _gcu, _gcuk = scm_app
    codes = make_codes()
    seed_catalogue(db, codes)

    # The sheet gets there first: an order carrying the number CS's extract will also name.
    sheet_order = SalesOrder(
        id=_u(), so_number=codes.project_so, status="open",
        source_system=inquiry.SOURCE_SYSTEM, source_ref=inquiry.SOURCE,
    )
    db.add(sheet_order)
    db.flush()

    out = svc.apply(db, week1(codes), SO)

    assert out["ok"] is True, out
    orders = db.query(SalesOrder).filter(SalesOrder.so_number == codes.project_so).all()
    assert len(orders) == 1, "the extract duplicated an order the sheet had created"
    assert str(orders[0].id) == str(sheet_order.id), "it created a new row beside it"
    assert orders[0].source_system == "scm_upload", "ownership did not transfer to CS"
    # Reported, not silent: a change of who may edit a document is worth saying out loud.
    assert codes.project_so in out["adopted_documents"]


def test_the_extract_does_not_churn_the_orders_it_already_owns(scm_app):
    """Adoption claims a FOREIGN source only. Re-uploading the same extract every week must
    not rewrite `source_ref` on every document it already owns."""
    from tests.scm._outstanding_workbooks import make_codes, seed_catalogue, week1
    from app.services.scm import outstanding_import_service as svc
    from app.services.scm.outstanding_reader import SO

    _app, db, _gcu, _gcuk = scm_app
    codes = make_codes()
    seed_catalogue(db, codes)

    svc.apply(db, week1(codes), SO)
    second = svc.apply(db, week1(codes), SO)

    assert second["adopted_documents"] == []
