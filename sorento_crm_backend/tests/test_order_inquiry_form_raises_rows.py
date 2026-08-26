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
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

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

#: The hand-built sheet's own order. Marker-scoped so it cannot collide with the REAL
#: SO381895 the committed fixture forms name, which the tests at the foot seed.
SO_NUMBER = f"{MARKER}-SO381895"
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
        # Through the model, not raw SQL: `users` carries a dozen NOT NULL columns whose
        # defaults are declared on the mapper, and hand-listing them is a test that breaks
        # every time somebody adds one. Every apply below runs AS this person, because a
        # link records who made it and an upload with nobody to attribute one to is told to
        # leave the rows for Auto-link instead.
        from app.models.user import User

        uploader = User(
            id=_u(), email=f"{_u()}@example.com", name=f"{MARKER} uploader",
            password="x", status="active",
        )
        db.add(uploader)
        db.flush()
        self.actor = str(uploader.id)

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

    def row_qty(self, code: str, qty: float) -> OrderInquiryRow:
        """The instruction for this item at this quantity.

        By CONTENT, never by position: every row of one upload shares a `created_at` (one
        `now()` per transaction), so "the first one" is whatever order the ids happened to
        sort in - the tie this repo has been bitten by before.
        """
        found = [
            row for row in self.rows()
            if row.item_code == code and float(row.qty) == qty
        ]
        assert len(found) == 1, f"expected one {code} row of {qty}, got {len(found)}"
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


#: The fixture sheet's form 1, rows 1 and 2, its second SRTWCX7405-RL-S-PJ row (12 at
#: BRW-BB, which form 2 later moves to BRW-IB), and one dated ORDER row - which must raise
#: nothing at all.
FORM = (
    (ITEM_X, 10, "ORDER BACK", "BRW-IB", "202604-S0083"),
    (ITEM_Y, 10, "ORDER BACK", "BRW-IB", "SPO-2026/08-0061 & 202606-S0082"),
    (ITEM_DATED, 20, date(2026, 8, 10), "BRW-IB", "ORDER"),
    (ITEM_X, 12, "ORDER BACK", "BRW-BB", "202604-S0083"),
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
    svc.apply(world.db, workbook(FORM), actor=world.actor)
    world.db.flush()
    return world


# ------------------------------------------------------------------ the rows are raised


def test_a_form_row_with_no_sales_order_line_raises_an_instruction(world, uploaded):
    """The fixture's `[NL]` rows. AutoCount closed the lines these quantities came from, so
    the board can decide nothing about them and the demand exists only on the form."""
    assert sorted(row.item_code for row in world.rows()) == [ITEM_X, ITEM_X, ITEM_Y]


def test_a_dated_order_row_raises_nothing(world, uploaded):
    """A date is ordinary demand and the sales-order book is its record. Raising an
    instruction beside a line the board already reads is how a quantity gets bought twice;
    a row the book has not got yet stays in `lines_unmatched`, exactly as it always has."""
    assert not [row for row in world.rows() if row.item_code == ITEM_DATED]


def test_two_order_backs_for_one_item_stay_two_instructions(world, uploaded):
    """Form 1 states SRTWCX7405-RL-S-PJ twice - 10 at BRW-IB and 12 at BRW-BB - and states
    C-FH14 30 at BRW-IB twice over, identically. An order back has no delivery date, so the
    `(SO, item, date)` instalment key cannot tell any of them apart, and collapsing them
    turns two things CS asked for into one quantity at one location."""
    rows = [row for row in world.rows() if row.item_code == ITEM_X]
    assert sorted((float(row.qty), row.stock_location) for row in rows) == [
        (10.0, "BRW-IB"),
        (12.0, "BRW-BB"),
    ]


def test_a_raised_row_carries_no_sales_order_line_and_says_so(world, uploaded):
    """`so_line_id` empty is the honest record: there IS no line in the book for it. A row
    pointed at the nearest line instead would attach somebody else's instalment."""
    assert all(row.so_line_id is None for row in world.rows())


def test_every_raised_row_is_an_order_back(world, uploaded):
    """`ORDER BACK` written where a date belongs is CS saying the quantity is owed against
    something already ordered (part 2 section 4b), and it is the ONLY thing this feed raises.

    Only an `ORDER_BACK` row may name an SPO, so reading that cell wrong is not a wording
    slip - it decides which documents the row is allowed to be linked to at all.
    """
    assert {row.verb for row in world.rows()} == {IV_ORDER_BACK}
    assert IV_ORDER not in {row.verb for row in world.rows()}


def test_an_order_back_row_carries_no_delivery_date_because_the_cell_stated_none(
    world, uploaded
):
    """"ORDER BACK" is not a date and must not become one. Inventing today, or the sales
    order's own date, would put the row on a planning horizon nobody asked for."""
    assert all(row.delivery_date is None for row in world.rows())


def test_the_row_takes_its_quantity_and_its_stock_location_from_the_form(world, uploaded):
    row = world.row_qty(ITEM_X, 10.0)
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
    row = world.row_qty(ITEM_X, 10.0)
    assert row.cited_document == "202604-S0083"
    assert row.note is None


def test_the_uploader_is_recorded_on_a_header_this_upload_created(world, uploaded):
    """Section 3.H: the order-inquiry page says WHO pushed it. For a header this feed
    created that is the person who uploaded the form."""
    inquiry = world.db.query(OrderInquiry).one()
    assert str(inquiry.raised_by) == world.actor
    assert inquiry.raised_at is not None


def test_an_inquiry_the_board_raised_is_not_restamped_by_an_upload(world, uploaded):
    """Raised by answers "who decided this order", and on a board-raised header that is the
    CS who confirmed it. Re-stamping it would make the page name whoever last sent a
    spreadsheet as the person who made the decision - the one question the column exists to
    answer."""
    inquiry = world.db.query(OrderInquiry).one()
    inquiry.raised_by = None
    inquiry.raised_at = datetime(2026, 8, 1, 9, 0, 0)
    world.db.flush()

    svc.apply(world.db, workbook(FORM), actor=world.actor)
    world.db.flush()

    world.db.refresh(inquiry)
    assert inquiry.raised_by is None
    assert inquiry.raised_at == datetime(2026, 8, 1, 9, 0, 0)


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
    summary = svc.apply(world.db, workbook(FORM), actor=world.actor)
    assert summary["rows_raised"] == 3
    assert summary["rows_restated"] == 0


# ------------------------------------------------------------------------- idempotency


def test_uploading_the_same_form_twice_leaves_the_same_rows(world, uploaded):
    """CS resends the same form; a second copy of every instruction would have purchasing
    buy twice."""
    before = {(row.id, row.item_code, float(row.qty)) for row in world.rows()}

    svc.apply(world.db, workbook(FORM), actor=world.actor)
    world.db.flush()

    assert {(row.id, row.item_code, float(row.qty)) for row in world.rows()} == before


def test_an_amended_form_restates_the_row_rather_than_adding_one(world, uploaded):
    """Form 2 of the fixture amends form 1's stock location. The instruction is the same
    instruction, so it is corrected in place.

    The 12 at BRW-BB moves to BRW-IB, which is exactly what form 2 does to four of the
    fourteen - and the 10 already at BRW-IB must not be the row it lands on."""
    amended = FORM[:3] + ((ITEM_X, 12, "ORDER BACK", "BRW-IB", "202604-S0083"),)
    svc.apply(world.db, workbook(amended), actor=world.actor)
    world.db.flush()

    moved = world.row_qty(ITEM_X, 12.0)
    assert moved.stock_location == "BRW-IB"
    assert world.row_qty(ITEM_X, 10.0).stock_location == "BRW-IB"
    assert len(world.rows()) == 3


def test_a_row_purchasing_has_already_linked_is_not_rewritten_by_a_re_upload(
    world, documents, uploaded
):
    """Once a row sits on a document, the form is no longer the only word about it: rewriting
    its quantity under a link would leave the link claiming more than the row asks for."""
    row = world.row_qty(ITEM_X, 10.0)
    assert row.state in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED)
    before = float(row.qty)

    amended = ((ITEM_X, 99, "ORDER BACK", "BRW-IB", "202604-S0083"),) + FORM[1:]
    svc.apply(world.db, workbook(amended), actor=world.actor)
    world.db.flush()

    assert float(world.row_qty(ITEM_X, 10.0).qty) == before


def test_a_restatement_never_blanks_the_note_a_relocation_wrote(world, uploaded):
    """The note carries the cascade's own stamp and the relocation a book re-upload wrote.
    An amended form correcting a quantity must not throw away the only record of why the row
    sits where it does."""
    row = world.row_qty(ITEM_X, 10.0)
    row.note = "Moved to the BRW-IB line of 202604-S0083 after the book was re-uploaded"
    world.db.flush()

    svc.apply(world.db, workbook(FORM), actor=world.actor)
    world.db.flush()

    assert "Moved to the BRW-IB line" in (world.row_qty(ITEM_X, 10.0).note or "")


# -------------------------------------------------------------------------- the auto-link


def test_the_cited_document_is_linked_before_any_other(world, documents, uploaded):
    """AC-I3. The form is the oracle: CS named `202604-S0083`, and the decoy purchase order
    would win on the cascade's own date ordering (issued January, arriving May) if the
    citation did not come first."""
    row = world.row_qty(ITEM_X, 10.0)
    (link,) = world.links_of(row.id)
    assert link.document == "202604-S0083"
    assert float(link.qty) == 10.0
    assert link.auto is True


def test_every_citation_is_tried_before_the_generic_walk_in_the_order_written(
    world, documents, uploaded
):
    """Item 12. `SPO-2026/08-0061 & 202606-S0082` names two documents and the row has ONE
    `cited_document` column, so the second is written onto the note and read back by the
    walk. Both must outrank the generic candidate the tiers and dates would otherwise pick.

    The decoy here is a BRW-IB line of the same product on a purchase order issued earlier
    and arriving earlier than either cited document - so under the cascade's own Q7 ordering
    it wins outright, and under a citation that is a FLAG rather than a RANK the two cited
    documents fall into one bucket and the dates pick between them.
    """
    world.purchase_order(
        f"{MARKER}-Y-DECOY", date(2026, 1, 3),
        [(ITEM_Y, "BRW-IB", 500, date(2026, 5, 1))],
    )
    world.db.flush()
    svc.apply(world.db, workbook(FORM), actor=world.actor)
    world.db.flush()

    row = world.row_for(ITEM_Y)
    documents_linked = [link.document for link in world.links_of(row.id)]
    assert documents_linked[:2] == ["SPO-2026/08-0061", "202606-S0082"]
    assert f"{MARKER}-Y-DECOY" not in documents_linked[:2]


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


def test_a_row_with_nothing_to_link_to_stays_raised(world, uploaded):
    """No purchase book at all, so nothing is linked and every row is still purchasing's to
    act on - never silently marked done."""
    assert {row.state for row in world.rows()} == {INQUIRY_RAISED}


# ----------------------------------------------------------- the real forms (AC-J1/AC-I3)


FIXTURES = Path(__file__).resolve().parents[2] / "documentation" / "plans" / "scm" / "fixtures"
FORM_1 = FIXTURES / "SO381895-form-1-2026-08-12-1610.xlsx"
FORM_2 = FIXTURES / "SO381895-form-2-2026-08-19-1025.xlsx"


@pytest.fixture()
def book(world):
    """SO381895 as AutoCount holds it, plus every master the two real forms name.

    The real files, not a hand-built sheet: `scm-cs-planning-uat-fixture.md` counts fourteen
    `[NL]` rows off THESE workbooks, and a test that generated its own would be counting its
    own assumptions. Only the masters are seeded - the sales order carries one dated
    instalment and none of the fourteen closed quantities, which is what makes them `[NL]`.
    """
    from app.services.project_order_inquiry_reader import read_order_inquiry

    codes, locations = set(), set()
    for path in (FORM_1, FORM_2):
        for row in read_order_inquiry(path.read_bytes()).rows:
            codes.add(row.item_code)
            if row.location:
                locations.add(row.location)

    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-BOOK-CAT", category_name=f"{MARKER} book"
    )
    uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-BOOK-U", uom_name=f"{MARKER} book")
    world.db.add_all([cat, uom])
    world.db.flush()
    for code in codes:
        world.db.add(
            Product(
                id=_u(), product_code=code, product_name=code, category_id=cat.id,
                base_uom_id=uom.id, list_price=0, is_active=True, is_discontinued=False,
            )
        )
    for code in locations:
        if code in world.warehouses:
            continue
        world.db.add(
            Warehouse(
                id=_u(), warehouse_code=code, warehouse_name=code, is_active=True,
                counts_as_available=True,
                pool_warehouse_id=world.warehouses["BRW"].id if code != "BRW" else None,
            )
        )
    world.db.flush()

    order = SalesOrder(
        id=_u(), so_number="SO381895", status="open", order_date=date(2025, 12, 10),
        order_type="project", demand_class="project", source_system="scm_upload",
    )
    world.db.add(order)
    world.db.flush()
    world.db.add(
        SalesOrderLine(
            id=_u(), sales_order_id=str(order.id),
            product_id=world.db.query(Product)
            .filter(Product.product_code == "C-FH14").one().id,
            warehouse_id=world.db.query(Warehouse)
            .filter(Warehouse.warehouse_code == "BRW-IB").one().id,
            qty_ordered=25, qty_delivered=0, qty_required=25,
            required_date=date(2026, 9, 5), line_status="open",
            source_system="scm_upload",
        )
    )
    world.db.flush()
    return order


def test_the_real_form_1_raises_the_fixture_sheets_fourteen_rows(world, book):
    """`scm-cs-planning-uat-fixture.md` section 2 marks exactly fourteen rows `[NL]`.

    Every one is an ORDER BACK, and the sixty-nine dated rows beside them raise nothing.
    """
    out = svc.apply(world.db, FORM_1.read_bytes(), actor=world.actor)
    world.db.flush()

    assert out["rows_raised"] == 14
    assert out["rows_restated"] == 0
    rows = world.db.query(OrderInquiryRow).all()
    assert len(rows) == 14
    assert {row.verb for row in rows} == {IV_ORDER_BACK}


def test_form_2_restates_form_1_rather_than_raising_fourteen_more(world, book):
    """Form 2 is the same instructions with the stock location amended to BRW-IB. Fourteen
    rows exist after it, not twenty-eight, and the four that said BRW-BB now say BRW-IB."""
    svc.apply(world.db, FORM_1.read_bytes(), actor=world.actor)
    world.db.flush()
    out = svc.apply(world.db, FORM_2.read_bytes(), actor=world.actor)
    world.db.flush()

    assert (out["rows_raised"], out["rows_restated"]) == (0, 14)
    rows = world.db.query(OrderInquiryRow).all()
    assert len(rows) == 14
    assert {row.stock_location for row in rows} == {"BRW-IB"}


def test_the_fourteen_carry_the_documents_the_forms_cite(world, book):
    """The form is the oracle (fixture section 1.2), so every document CS named is on a row -
    including SPO-2026/08-0046, which this system does not hold and which AC-J2 says is
    RECORDED rather than silently skipped."""
    svc.apply(world.db, FORM_1.read_bytes(), actor=world.actor)
    world.db.flush()

    rows = world.db.query(OrderInquiryRow).all()
    cited = {row.cited_document for row in rows if row.cited_document}
    assert "SPO-2026/08-0061" in cited
    assert "SPO-2026/08-0046" in cited
    assert "202604-S0083" in cited
    # The second document of `SPO-2026/08-0061 & 202606-S0082` is not lost, it is on the
    # note where the walk reads it back.
    assert any("202606-S0082" in (row.note or "") for row in rows)
