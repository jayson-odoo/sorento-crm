"""AC-I3 - the Order Inquiry Form upload RAISES the rows the board cannot.

`PLAN-scm-cs-planning-uat.md` section 3.I (the BUILT block's last gap: "The Order Inquiry
Form upload does NOT raise rows"), `scm-cs-planning-uat-fixture.md` sections 2 and 3, and
part 2 section 4b for the `ORDER_BACK` verb.

Fourteen rows of SO381895's first two CS forms are marked `[NL]` on the fixture sheet: CS
writes `ORDER BACK` where a delivery DATE belongs and names the document the quantity is owed
against, and the sales-order lines those quantities came from were CLOSED in AutoCount. So
the fulfilment board has nothing to decide about them and can raise nothing - the demand
exists only on the form. Until now the upload wrote a stock location and a purchase-order
claim and nothing else, and those fourteen instructions reached purchasing on no screen at
all.

The two rows tested here are the fixture's own rows 1 and 2 of form 1:

    SRTWCX7405-RL-S-PJ  10  ORDER BACK  BRW-IB  202604-S0083
    SRTWCY7405-PJ       10  ORDER BACK  BRW-IB  SPO-2026/08-0061 & 202606-S0082

plus a dated ORDER row, because the verb comes off the delivery-date cell and a date means
something different from the words.

The workbook is GENERATED from the reader's own header spellings rather than committed:
`project_order_inquiry_reader` resolves its headers from a hard-coded table (no
`import_field_alias`, and therefore no migration seed to miss), so file and expectation are
built from one set of codes and cannot drift.

`blank_session`: the walk that picks a link target is ranked against the whole purchase book,
and the shared local database holds the captain's real one.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.services import project_order_inquiry_import_service as svc

from ._pg_fixture import blank_session

MARKER = "ZZT-FORM"

SO_NUMBER = "SO381895"
ITEM_X = f"{MARKER}-SRTWCX7405-RL-S-PJ"
ITEM_Y = f"{MARKER}-SRTWCY7405-PJ"
ITEM_DATED = f"{MARKER}-SRTWCX8605-S-RL-PJ"
PROJECT = "YOTU BUILDER / LOT 2752"

#: The forms' own headings, in the export's own order (`EXPORT_HEADINGS`).
HEADERS = (
    "SO DATE", "S/O NO", "ITEM CODE", "QTY", "DELIVERY DATE",
    "PROJECT/CUSTOMER", "STOCK LOCATION", "REMARK",
)
SO_DATE = date(2025, 12, 10)


def _u() -> str:
    return str(uuid.uuid4())


def workbook(rows) -> bytes:
    """One sheet, the forms' own headings, `rows` as `(item, qty, delivery, loc, remark)`."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SHEET"
    ws.append(("ORDER INQUIRY",))
    ws.append(HEADERS)
    for item, qty, delivery, location, remark in rows:
        ws.append((SO_DATE, SO_NUMBER, item, qty, delivery, PROJECT, location, remark))
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class _World:
    """The book as AutoCount holds it, plus the documents the form cites."""

    def __init__(self, db):
        self.db = db
        self.company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        self._build()

    def _build(self) -> None:
        db = self.db
        cat = ProductCategory(
            id=_u(), category_code=f"{MARKER}-CAT", category_name=f"{MARKER} cat"
        )
        uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U", uom_name=f"{MARKER} unit")
        db.add_all([cat, uom])
        db.flush()
        self.products = {}
        for code in (ITEM_X, ITEM_Y, ITEM_DATED):
            product = Product(
                id=_u(), product_code=code, product_name=code, category_id=cat.id,
                base_uom_id=uom.id, list_price=0, is_active=True, is_discontinued=False,
            )
            db.add(product)
            self.products[code] = product
        # BRW is a POOL because BRW-IB points at it, which is the only authority the link
        # tier rule reads.
        pool = Warehouse(
            id=_u(), warehouse_code="BRW", warehouse_name="BRW", is_active=True,
            counts_as_available=True,
        )
        db.add(pool)
        db.flush()
        self.warehouses = {"BRW": pool}
        for code in ("BRW-IB",):
            wh = Warehouse(
                id=_u(), warehouse_code=code, warehouse_name=code, is_active=True,
                counts_as_available=True, pool_warehouse_id=pool.id,
            )
            db.add(wh)
            self.warehouses[code] = wh
        self.supplier = Supplier(
            id=_u(), supplier_code=f"{MARKER}-SUP", supplier_name=f"{MARKER} supplier",
            is_active=True,
        )
        db.add(self.supplier)
        db.flush()

        # SO381895 as the book holds it: project class, open, and carrying only the
        # instalments AutoCount still states. The quantities CS marks ORDER BACK are NOT
        # here - that is what makes them `[NL]`.
        self.order = SalesOrder(
            id=_u(), so_number=SO_NUMBER, status="open", order_date=SO_DATE,
            order_type="project", demand_class="project", source_system="scm_upload",
        )
        db.add(self.order)
        db.flush()
        for code in (ITEM_X, ITEM_Y, ITEM_DATED):
            db.add(
                SalesOrderLine(
                    id=_u(), sales_order_id=str(self.order.id),
                    product_id=self.products[code].id,
                    warehouse_id=self.warehouses["BRW-IB"].id,
                    qty_ordered=25, qty_delivered=0, qty_required=25,
                    required_date=date(2026, 9, 5), line_status="open",
                    source_system="scm_upload",
                )
            )
        db.flush()

    # -- the documents the form cites ------------------------------------------

    def purchase_order(self, number: str, issue: date, lines) -> PurchaseOrder:
        """`lines` is (product code, location, qty, expected)."""
        po = PurchaseOrder(
            id=_u(), po_number=number, supplier_id=str(self.supplier.id),
            status="active", issue_date=issue, source_system="scm_upload",
        )
        self.db.add(po)
        self.db.flush()
        for code, location, qty, expected in lines:
            self.db.add(
                PurchaseOrderLine(
                    id=_u(), purchase_order_id=str(po.id),
                    product_id=self.products[code].id,
                    warehouse_id=self.warehouses[location].id,
                    qty_ordered=qty, qty_received=0, line_status="open",
                    expected_date=expected,
                )
            )
        self.db.flush()
        return po

    def spo_allocation(self, number: str, code: str, location: str, qty) -> SPOAllocation:
        allocation = SPOAllocation(
            id=_u(), spo_number=number, spo_line_number=1,
            product_id=self.products[code].id,
            warehouse_id=self.warehouses[location].id,
            allocated_quantity=qty, quantity_received=0, quantity_rejected=0,
            receipt_status="pending", line_status="open",
            issue_date=date(2026, 8, 12), expected_date=date(2026, 8, 1),
            supplier_id=str(self.supplier.id), synced_to_excel=False,
        )
        self.db.add(allocation)
        self.db.flush()
        return allocation

    # -- reads -----------------------------------------------------------------

    def rows(self) -> list[OrderInquiryRow]:
        return (
            self.db.query(OrderInquiryRow)
            .order_by(OrderInquiryRow.item_code, OrderInquiryRow.created_at)
            .all()
        )

    def row_for(self, code: str) -> OrderInquiryRow:
        found = [row for row in self.rows() if row.item_code == code]
        assert len(found) == 1, f"expected exactly one row for {code}, got {len(found)}"
        return found[0]

    def links_of(self, row_id: str) -> list[OrderInquiryLink]:
        return (
            self.db.query(OrderInquiryLink)
            .filter(OrderInquiryLink.row_id == row_id)
            .order_by(OrderInquiryLink.linked_at, OrderInquiryLink.id)
            .all()
        )


@pytest.fixture()
def world():
    with blank_session() as db:
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


#: The fixture sheet's form 1, rows 1, 2 and one dated ORDER row.
FORM = (
    (ITEM_X, 10, "ORDER BACK", "BRW-IB", "202604-S0083"),
    (ITEM_Y, 10, "ORDER BACK", "BRW-IB", "SPO-2026/08-0061 & 202606-S0082"),
    (ITEM_DATED, 20, date(2026, 8, 10), "BRW-IB", "ORDER"),
)


@pytest.fixture()
def documents(world):
    """Everything the form's remarks name, plus a decoy that would win on date alone."""
    world.purchase_order(
        "202604-S0083", date(2026, 4, 28), [(ITEM_X, "BRW-IB", 25, date(2026, 8, 19))]
    )
    # Issued EARLIER and arriving EARLIER, so the cascade's own Q7 ordering (PO issue date
    # first) would take it - and must not, because CS named the other one.
    world.purchase_order(
        f"{MARKER}-DECOY", date(2026, 1, 5), [(ITEM_X, "BRW-IB", 500, date(2026, 5, 1))]
    )
    world.purchase_order(
        "202606-S0082", date(2026, 6, 22), [(ITEM_Y, "BRW-IB", 46, date(2026, 9, 4))]
    )
    world.spo_allocation("SPO-2026/08-0061", ITEM_Y, "BRW-IB", 2)
    world.purchase_order(
        f"{MARKER}-FRESH", date(2026, 7, 1), [(ITEM_DATED, "BRW-IB", 100, date(2026, 8, 5))]
    )
    return True


@pytest.fixture()
def uploaded(world):
    svc.apply(world.db, workbook(FORM))
    world.db.flush()
    return world


# ------------------------------------------------------------------ the rows are raised


def test_a_form_row_with_no_sales_order_line_raises_an_instruction(world, uploaded):
    """The fixture's `[NL]` rows. AutoCount closed the lines these quantities came from, so
    the board can decide nothing about them and the demand exists only on the form."""
    codes = {row.item_code for row in world.rows()}
    assert codes == {ITEM_X, ITEM_Y, ITEM_DATED}


def test_a_raised_row_carries_no_sales_order_line_and_says_so(world, uploaded):
    """`so_line_id` empty is the honest record: there IS no line in the book for it. A row
    pointed at the nearest line instead would attach somebody else's instalment."""
    assert all(row.so_line_id is None for row in world.rows())


def test_the_verb_comes_off_the_delivery_date_cell(world, uploaded):
    """`ORDER BACK` written where a date belongs is CS saying the quantity is owed against
    something already ordered; a real date is a fresh purchase due then (part 2 section 4b).

    Only an `ORDER_BACK` row may name an SPO, so reading this cell wrong is not a wording
    slip - it decides which documents the row is allowed to be linked to at all.
    """
    assert world.row_for(ITEM_X).verb == IV_ORDER_BACK
    assert world.row_for(ITEM_Y).verb == IV_ORDER_BACK

    dated = world.row_for(ITEM_DATED)
    assert dated.verb == IV_ORDER
    assert dated.delivery_date == date(2026, 8, 10)


def test_an_order_back_row_carries_no_delivery_date_because_the_cell_stated_none(
    world, uploaded
):
    """"ORDER BACK" is not a date and must not become one. Inventing today, or the sales
    order's own date, would put the row on a planning horizon nobody asked for."""
    assert world.row_for(ITEM_X).delivery_date is None


def test_the_row_takes_its_quantity_and_its_stock_location_from_the_form(world, uploaded):
    row = world.row_for(ITEM_X)
    assert float(row.qty) == 10.0
    assert row.stock_location == "BRW-IB"


def test_the_first_document_in_the_remark_is_the_citation_and_the_rest_is_the_note(
    world, uploaded
):
    """`SPO-2026/08-0061 & 202606-S0082` names two documents. The FIRST is what the walk
    tries before any location tier or date; the others are kept as words rather than dropped,
    because CS wrote them and a second document is the answer when the first cannot cover it.
    """
    row = world.row_for(ITEM_Y)
    assert row.cited_document == "SPO-2026/08-0061"
    assert "202606-S0082" in (row.note or "")


def test_a_remark_naming_one_document_leaves_nothing_over(world, uploaded):
    row = world.row_for(ITEM_X)
    assert row.cited_document == "202604-S0083"


def test_the_uploader_is_recorded_as_who_raised_it(world):
    """Section 3.H: the order-inquiry page says WHO pushed it. For this feed that is the
    person who uploaded the form, not the CS who confirmed a board decision."""
    from app.models.user import User

    # Through the model, not raw SQL: `users` carries a dozen NOT NULL columns whose
    # defaults are declared on the mapper, and hand-listing them is a test that breaks
    # every time somebody adds one.
    uploader = User(
        id=_u(), email=f"{_u()}@example.com", name=f"{MARKER} uploader",
        password="x", status="active",
    )
    world.db.add(uploader)
    world.db.flush()
    actor = str(uploader.id)

    svc.apply(world.db, workbook(FORM), actor=actor)
    world.db.flush()

    inquiry = world.db.query(OrderInquiry).one()
    assert str(inquiry.raised_by) == actor
    assert inquiry.raised_at is not None


def test_the_inquiry_hangs_off_the_sales_orders_own_planning_record(world, uploaded):
    """One inquiry per sales order, on the record every other reader already addresses -
    adopting the core order is what creates it, and adoption is idempotent."""
    inquiry = world.db.query(OrderInquiry).one()
    record = (
        world.db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == inquiry.project_sales_order_id)
        .one()
    )
    assert str(record.so_id) == str(world.order.id)
    assert record.autocount_doc_no == SO_NUMBER


def test_the_raised_row_is_reported_on_the_upload_result(world):
    """A write nobody is told about is a write nobody checks."""
    summary = svc.apply(world.db, workbook(FORM))
    assert summary["rows_raised"] == 3


# ------------------------------------------------------------------------- idempotency


def test_uploading_the_same_form_twice_leaves_the_same_rows(world, uploaded):
    """CS resends the same form; a second copy of every instruction would have purchasing
    buy twice."""
    before = {(row.id, row.item_code, float(row.qty)) for row in world.rows()}

    svc.apply(world.db, workbook(FORM))
    world.db.flush()

    assert {(row.id, row.item_code, float(row.qty)) for row in world.rows()} == before


def test_an_amended_form_restates_the_row_rather_than_adding_one(world, uploaded):
    """Form 2 of the fixture amends form 1's stock location. The instruction is the same
    instruction, so it is corrected in place."""
    amended = (
        (ITEM_X, 12, "ORDER BACK", "BRW", "202604-S0083"),
    ) + FORM[1:]
    svc.apply(world.db, workbook(amended))
    world.db.flush()

    row = world.row_for(ITEM_X)
    assert float(row.qty) == 12.0
    assert row.stock_location == "BRW"
    assert len(world.rows()) == 3


def test_a_row_purchasing_has_already_linked_is_not_rewritten_by_a_re_upload(
    world, documents, uploaded
):
    """Once a row sits on a document, the form is no longer the only word about it: rewriting
    its quantity under a link would leave the link claiming more than the row asks for."""
    row = world.row_for(ITEM_X)
    assert row.state in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED)
    before = float(row.qty)

    amended = ((ITEM_X, 99, "ORDER BACK", "BRW-IB", "202604-S0083"),) + FORM[1:]
    svc.apply(world.db, workbook(amended))
    world.db.flush()

    assert float(world.row_for(ITEM_X).qty) == before


# -------------------------------------------------------------------------- the auto-link


def test_the_cited_document_is_linked_before_any_other(world, documents, uploaded):
    """AC-I3. The form is the oracle: CS named `202604-S0083`, and the decoy purchase order
    would win on the cascade's own date ordering (issued January, arriving May) if the
    citation did not come first."""
    row = world.row_for(ITEM_X)
    (link,) = world.links_of(row.id)
    assert link.document == "202604-S0083"
    assert float(link.qty) == 10.0
    assert link.auto is True


def test_an_order_back_row_reaches_its_cited_spo_allocation(world, documents, uploaded):
    """AC-I3 and part 2 section 4b: an order back is owed against what is already shipped
    before it is owed against a new purchase, and the SPO is the only kind of document this
    verb may name."""
    row = world.row_for(ITEM_Y)
    links = world.links_of(row.id)
    assert links[0].document == "SPO-2026/08-0061"
    assert links[0].spo_allocation_id is not None
    # The allocation only holds 2, so the walk carries on to the other document CS named
    # rather than leaving 8 unanswered.
    assert [float(link.qty) for link in links] == [2.0, 8.0]
    assert links[1].document == "202606-S0082"


def test_a_dated_order_row_links_to_a_purchase_order_line(world, documents, uploaded):
    """A fresh ORDER is a new purchase, so it may name a purchase order and nothing else."""
    row = world.row_for(ITEM_DATED)
    (link,) = world.links_of(row.id)
    assert link.po_line_id is not None
    assert link.spo_allocation_id is None
    assert row.state == INQUIRY_PLACED


def test_a_row_with_nothing_to_link_to_stays_raised(world, uploaded):
    """No purchase book at all, so nothing is linked and every row is still purchasing's to
    act on - never silently marked done."""
    assert {row.state for row in world.rows()} == {INQUIRY_RAISED}
