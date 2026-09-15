"""The order inquiry sheet as a MIGRATION tool (`PLAN-scm-oi-sheet-migration.md`, S1).

Contract: `documentation/plans/scm/scm-oi-sheet-migration-acceptance-criteria.md`,
AC-S1-1 to AC-S1-36. One test per criterion, named as the plan's section 4 names it.

TEST-FIRST. Written before the importer was rewritten, so the red state is a missing
result key, a missing method (`ProjectSOAdoptionService.adopt_for_migration`) or the OLD
behaviour (a sales order created, a dated row not raised) - never an import error.

What the sheet is now. AutoCount already holds the sales orders, the purchase orders and
the shipping orders, in real time. What it does NOT hold is the operator's own Excel: which
SO line is owed where, and which PO or SPO it waits on. So the importer creates NO sales
order and writes NO warehouse; it raises one order inquiry row against the sales order line
the sheet names, and pairs that row to the document AutoCount's own linkage states, falling
back to the sheet's remark only for the need AutoCount leaves (D9).

Postgres, never sqlite (`tests/_pg_fixture.py`): `blank_session` for the behaviour, and
`pg_session` for AC-S1-29 alone, which reads `scm.committed_v` - a VIEW, so it exists only
in a migrated (or bootstrapped) database and not in a `create_all` scratch schema.

Every foreign key target is seeded here behind the `ZZT-OISM` marker, and every document
number is minted per test. Nothing is read off an existing row: CI's database is empty.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from itertools import count

import pytest
import sqlalchemy as sa

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
    ACK_ACKNOWLEDGED,
    INQUIRY_ACTIONED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.scm import OrderLinkClaim
from app.models.user import User
from app.services import project_order_inquiry_import_service as importer
from app.services.import_outcome import ImportOutcome
from app.services.project_so_adoption_service import ProjectSOAdoptionService

from ._pg_fixture import blank_session, pg_session

MARKER = "ZZT-OISM"

#: The customer's own header row, exactly as the reader spells it. Unchanged by this slice.
HEADERS = ("SO NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION", "REMARK")

D_OCT = date(2026, 10, 15)
D_NOV = date(2026, 11, 1)

#: Exactly what `apply` and `preview` answer with (AC-S1-22). `ok` and `problems` sit
#: beside the criterion's own list because the reader's verdict travels on the same dict
#: (AC-S1-25) and the frontend type carries both (AC-S2-5). `orders_adopted` and
#: `orders_stamped` joined them on 14 Sep (security review SF2): what the upload does to
#: the book's neighbours is said before Confirm, not discovered afterwards.
RESULT_KEYS = {
    "ok",
    "problems",
    "orders_adopted",
    "orders_stamped",
    "rows",
    "rows_raised",
    "rows_already_raised",
    "rows_line_not_found",
    "line_not_found",
    "sales_orders_not_found",
    "orders_not_plannable",
    "links_written",
    "links_partial",
    "links_from_autocount",
    "documents_not_linkable",
    "sheets_read",
    "sheets_skipped",
}

#: Every key the migration retires (AC-S1-22). Named rather than implied by the set above,
#: so a failure says WHICH leftover is still on the result.
RETIRED_KEYS = {
    "orders_created",
    "lines_created",
    "lines_refreshed",
    "lines_withdrawn",
    "orders_owned_elsewhere",
    "locations_written",
    "claims_written",
    "lines_matched",
    "lines_unmatched",
    "instalments",
    "po_claims",
    "rows_linked",
    "link_error",
}

_SEQ = count(1)


def _uid() -> str:
    return str(uuid.uuid4())


def _n() -> int:
    return next(_SEQ)


def _po_number() -> str:
    """A purchase order number in the family the sheet's remark parser recognises.

    The reader finds documents with `_PO_NUMBER`, so a made-up `ZZT-PO-9` would simply not
    be read out of the remark and the citation half of these tests would assert nothing.
    """
    return f"2026{_n() % 12 + 1:02d}-S{_n():04d}"


def _spo_number() -> str:
    return f"SPO-2026/08-{_n():04d}"


# --------------------------------------------------------------------------- #
# the workbook                                                                 #
# --------------------------------------------------------------------------- #


def sheet(rows, *, name: str = "Sheet1", headers=HEADERS) -> bytes:
    """One tab, the customer's header row, and the rows as written.

    A row is `(SO NO, ITEM CODE, QTY, DELIVERY DATE, STOCK LOCATION, REMARK)`; the delivery
    cell takes a `date`, `None`, or the words `ORDER BACK`, which is what CS writes where a
    date belongs when the quantity is owed against something already ordered.
    """
    import openpyxl

    workbook = openpyxl.Workbook()
    tab = workbook.active
    tab.title = name
    tab.append(list(headers))
    for row in rows:
        tab.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def book(**tabs) -> bytes:
    """Several tabs of one workbook: `book(JAN_26=[row], ROLLUP=[row])`.

    The customer's own shape - a month tab, a roll-up tab covering that month and a dated
    snapshot - which is the only way to state the same delivery twice (AC-S1-38).
    """
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in tabs.items():
        tab = workbook.create_sheet(title=name)
        tab.append(list(HEADERS))
        for row in rows:
            tab.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# the world                                                                    #
# --------------------------------------------------------------------------- #


class World:
    """One company's worth of seeded chain, with the writers each test needs."""

    def __init__(self, db, company_id: str):
        self.db = db
        self.company_id = company_id
        self.actor = self.user()
        self.warehouse = self.warehouse_row()
        self.product = self.product_row()

    # -- catalogue

    def user(self) -> str:
        row = User(
            id=_uid(),
            email=f"{MARKER}-{_uid()[:8]}@example.test",
            name=f"{MARKER} uploader",
            status="ACTIVE",
        )
        self.db.add(row)
        self.db.flush()
        return str(row.id)

    def product_row(self, code: str | None = None) -> Product:
        uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZTU{_n():04d}", uom_name=f"{MARKER} unit")
        category = ProductCategory(
            id=_uid(),
            category_code=f"{MARKER}-C{_n():04d}",
            category_name=f"{MARKER} category",
        )
        self.db.add_all([uom, category])
        self.db.flush()
        row = Product(
            id=_uid(),
            product_code=code or f"{MARKER}-P{_n():04d}",
            product_name=f"{MARKER} product",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal("100.00"),
            is_active=True,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def warehouse_row(self, code: str | None = None) -> Warehouse:
        row = Warehouse(
            id=_uid(),
            warehouse_code=code or f"ZZTW{_n():04d}",
            warehouse_name=f"{MARKER} location",
            company_id=self.company_id,
            is_active=True,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def supplier(self) -> Supplier:
        row = Supplier(
            id=_uid(),
            company_id=self.company_id,
            supplier_code=f"ZZTS{_n():04d}",
            supplier_name=f"{MARKER} supplier",
        )
        self.db.add(row)
        self.db.flush()
        return row

    # -- the book AutoCount owns

    def order(
        self,
        *,
        demand_class: str = "project",
        status: str = "open",
        number: str | None = None,
    ) -> SalesOrder:
        row = SalesOrder(
            id=_uid(),
            company_id=self.company_id,
            # Nameable so two companies can hold the SAME sales order number, which is the
            # whole of AC-S1-43.
            so_number=number or f"{MARKER}-SO{_n():04d}",
            status=status,
            demand_class=demand_class,
            order_type=demand_class,
            source_system="autocount",
            order_date=date(2026, 6, 1),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def line(
        self,
        order: SalesOrder,
        *,
        product: Product | None = None,
        warehouse: Warehouse | None = "default",
        qty_ordered: str = "50",
        qty_delivered: str = "0",
        required_date: date | None = D_OCT,
        line_status: str = "open",
    ) -> SalesOrderLine:
        if warehouse == "default":
            warehouse = self.warehouse
        row = SalesOrderLine(
            id=_uid(),
            company_id=self.company_id,
            sales_order_id=order.id,
            product_id=(product or self.product).id,
            warehouse_id=warehouse.id if warehouse is not None else None,
            qty_ordered=Decimal(qty_ordered),
            qty_delivered=Decimal(qty_delivered),
            unit_price=Decimal("12.50"),
            required_date=required_date,
            line_status=line_status,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def po_line(
        self,
        *,
        qty_ordered: str = "50",
        qty_received: str = "0",
        product: Product | None = None,
        line_status: str = "open",
        number: str | None = None,
    ) -> tuple[PurchaseOrder, PurchaseOrderLine]:
        order = PurchaseOrder(
            id=_uid(),
            company_id=self.company_id,
            po_number=number or _po_number(),
            supplier_id=self.supplier().id,
            issue_date=date(2026, 6, 1),
            status="active",
        )
        self.db.add(order)
        self.db.flush()
        line = PurchaseOrderLine(
            id=_uid(),
            company_id=self.company_id,
            purchase_order_id=order.id,
            product_id=(product or self.product).id,
            warehouse_id=self.warehouse.id,
            qty_ordered=Decimal(qty_ordered),
            qty_received=Decimal(qty_received),
            expected_date=date(2026, 9, 1),
            line_status=line_status,
        )
        self.db.add(line)
        self.db.flush()
        return order, line

    def spo_allocation(
        self,
        *,
        quantity: int = 50,
        received: int = 0,
        product: Product | None = None,
        number: str | None = None,
        from_po_number: str | None = None,
        from_so_line_ref: str | None = None,
        line_status: str = "open",
    ) -> SPOAllocation:
        row = SPOAllocation(
            id=_uid(),
            company_id=self.company_id,
            spo_number=number or _spo_number(),
            spo_line_number=1,
            product_id=(product or self.product).id,
            warehouse_id=self.warehouse.id,
            location_code=self.warehouse.warehouse_code,
            allocated_quantity=quantity,
            quantity_received=received,
            receipt_status="received" if received else "pending",
            line_status=line_status,
            source_system="autocount",
            issue_date=date(2026, 6, 1),
            expected_date=date(2026, 9, 1),
            supplier_id=self.supplier().id,
            from_po_number=from_po_number,
            from_so_line_ref=from_so_line_ref,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def claim(
        self,
        *,
        order: SalesOrder,
        core_line: SalesOrderLine,
        document: str,
        po_line: PurchaseOrderLine | None = None,
        allocation: SPOAllocation | None = None,
        source: str = "autocount",
        item_code: str | None = None,
    ) -> OrderLinkClaim:
        """One RESOLVED pairing, as the AutoCount ingest writes it (AC-S1-30)."""
        row = OrderLinkClaim(
            id=_uid(),
            company_id=self.company_id,
            so_number=order.so_number,
            po_number=document,
            item_code=item_code or self.product.product_code,
            source=source,
            so_line_id=str(core_line.id),
            po_line_id=str(po_line.id) if po_line is not None else None,
            spo_allocation_id=str(allocation.id) if allocation is not None else None,
            claimed_at=datetime(2026, 6, 2, 9, 0, 0),
            resolved_at=datetime(2026, 6, 2, 9, 0, 0),
        )
        self.db.add(row)
        self.db.flush()
        return row

    # -- the board's own writer, for the "already raised" case (AC-S1-10)

    def board_row(self, mirror_line: ProjectSalesOrderLine, *, qty: str = "5") -> OrderInquiryRow:
        inquiry = (
            self.db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == mirror_line.project_sales_order_id)
            .first()
        )
        if inquiry is None:
            inquiry = OrderInquiry(
                id=_uid(),
                company_id=self.company_id,
                project_sales_order_id=mirror_line.project_sales_order_id,
                state=INQUIRY_RAISED,
            )
            self.db.add(inquiry)
            self.db.flush()
        row = OrderInquiryRow(
            id=_uid(),
            company_id=self.company_id,
            order_inquiry_id=inquiry.id,
            so_line_id=mirror_line.id,
            item_code=mirror_line.product_id and self.product.product_code,
            qty=Decimal(qty),
            delivery_date=D_OCT,
            stock_location=self.warehouse.warehouse_code,
            verb=IV_ORDER,
            state=INQUIRY_RAISED,
            ack_state=ACK_ACKNOWLEDGED,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # -- readers

    def apply(self, data: bytes, *, actor: str | None = "default", outcome=None) -> dict:
        return importer.apply(
            self.db,
            data,
            actor=self.actor if actor == "default" else actor,
            outcome=outcome,
        )

    def preview(self, data: bytes) -> dict:
        return importer.preview(self.db, data)

    def rows(self) -> list[OrderInquiryRow]:
        return (
            self.db.query(OrderInquiryRow)
            .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
            .all()
        )

    def one_row(self) -> OrderInquiryRow:
        rows = self.rows()
        assert len(rows) == 1, f"expected exactly one raised row, got {len(rows)}"
        return rows[0]

    def links(self, row: OrderInquiryRow) -> list[OrderInquiryLink]:
        return (
            self.db.query(OrderInquiryLink)
            .filter(OrderInquiryLink.row_id == row.id)
            .order_by(OrderInquiryLink.linked_at.asc(), OrderInquiryLink.id.asc())
            .all()
        )

    def mirror_of(self, core_line: SalesOrderLine) -> ProjectSalesOrderLine | None:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.core_sales_order_line_id == str(core_line.id))
            .first()
        )

    def book_counts(self) -> tuple[int, int]:
        return (
            self.db.query(SalesOrder).count(),
            self.db.query(SalesOrderLine).count(),
        )


@contextmanager
def world(factory=blank_session):
    with factory() as db:
        company_id = db.execute(
            sa.text("select id from companies where code = 'SRT'")
        ).scalar()
        with company_scope(db, frozenset({company_id})):
            yield World(db, company_id)


# --------------------------------------------------------------------------- #
# matching a sheet row to its sales order line                                 #
# --------------------------------------------------------------------------- #


def test_row_raises_against_matching_line():
    """AC-S1-1. One row, one line, same location: one order inquiry row on the MIRROR line,
    carrying the sheet's quantity, delivery date and location."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        mirror = w.mirror_of(line)
        assert mirror is not None, "the sales order was never adopted"
        assert str(row.so_line_id) == str(mirror.id)
        assert Decimal(str(row.qty)) == Decimal("30")
        assert row.delivery_date == D_OCT
        assert row.stock_location == w.warehouse.warehouse_code
        assert row.ack_state == ACK_ACKNOWLEDGED
        assert str(row.acknowledged_by) == w.actor


def test_two_rows_split_one_line():
    """AC-S1-2. 30 + 20 against a 50 line: two rows, both on that line. The SHEET splits a
    line; the importer never does."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 20, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        mirror = w.mirror_of(line)
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {str(mirror.id)}
        assert sorted(Decimal(str(row.qty)) for row in rows) == [Decimal("20"), Decimal("30")]


def test_line_without_warehouse_accepts_location():
    """AC-S1-3. A line with NO warehouse matches any location, and the raised row carries
    the sheet's own."""
    with world() as w:
        order = w.order()
        w.line(order, warehouse=None, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_OCT, "BRW-IB", ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        assert w.one_row().stock_location == "BRW-IB"


def test_location_mismatch_reports_not_found():
    """AC-S1-4. The only line is at another warehouse: nothing raised, reason
    `location_differs`."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_OCT, "BRW-IB", ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert w.rows() == []
        assert result["rows_line_not_found"] == 1
        assert [entry["reason"] for entry in result["line_not_found"]] == ["location_differs"]
        assert result["line_not_found"][0]["so_number"] == order.so_number
        assert result["line_not_found"][0]["item_code"] == w.product.product_code


def test_qty_over_ordered_reports_not_found():
    """AC-S1-5. 60 against a 50 line: reason `qty_exceeds_ordered`. The quantity is what the
    line ORDERED, less what earlier rows of this same file already took."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 60, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert [entry["reason"] for entry in result["line_not_found"]] == [
            "qty_exceeds_ordered"
        ]


def test_unknown_so_creates_nothing():
    """AC-S1-6. A sales order the CRM does not hold creates NOTHING (D4: AutoCount owns the
    book) and is named on the result."""
    with world() as w:
        before = w.book_counts()
        data = sheet([
            (f"{MARKER}-SO-ABSENT", w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert w.book_counts() == before, "the importer created a sales order"
        assert result["rows_raised"] == 0
        assert result["sales_orders_not_found"] == [f"{MARKER}-SO-ABSENT"]


def test_retail_order_not_plannable():
    """AC-S1-7. Retail demand is refused with its code and raises nothing; a CLOSED
    project-class order is NOT refused (D8) - it is adopted and its rows are raised."""
    with world() as w:
        retail = w.order(demand_class="retail")
        w.line(retail, qty_ordered="50")
        data = sheet([
            (retail.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert w.rows() == []
        assert result["orders_not_plannable"] == [
            {"so_number": retail.so_number, "code": "sales_order_not_project_class"}
        ]

    with world() as w:
        closed = w.order(status="closed")
        w.line(closed, qty_ordered="50", qty_delivered="50", line_status="closed")
        data = sheet([
            (closed.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["orders_not_plannable"] == []
        assert result["rows_raised"] == 1, result


def test_prefers_line_with_same_required_date():
    """AC-S1-8. The line whose required date equals the sheet's wins; an undated row takes
    the open line before the closed one."""
    with world() as w:
        order = w.order()
        october = w.line(order, qty_ordered="50", required_date=D_OCT)
        november = w.line(order, qty_ordered="50", required_date=D_NOV)
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_NOV,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        assert str(w.one_row().so_line_id) == str(w.mirror_of(november).id)
        assert w.mirror_of(october) is not None, "a still-owed line is mirrored"

    with world() as w:
        order = w.order()
        closed = w.line(order, qty_ordered="50", required_date=None, line_status="closed")
        open_line = w.line(order, qty_ordered="50", required_date=None)
        data = sheet([
            (order.so_number, w.product.product_code, 10, None,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        assert str(w.one_row().so_line_id) == str(w.mirror_of(open_line).id)
        # AC-S1-26 as amended (review finding 4, 14 Sep): a CLOSED line the sheet did not
        # name is not mirrored - an unasked-for mirror line moves the planning record's own
        # reconciliation figures.
        assert w.mirror_of(closed) is None


def test_verb_from_date_cell():
    """AC-S1-9. `ORDER BACK` in the date cell is the verb, a date is `ORDER` - and BOTH are
    raised. A sheet full of dated rows used to raise nothing at all."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 10, "ORDER BACK",
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        assert sorted(row.verb for row in w.rows()) == sorted([IV_ORDER_BACK, IV_ORDER])


def test_identical_rows_across_tabs_raise_once():
    """AC-S1-38 (D7), as amended by AC-R-11 (owner ruling R3, 14 Sep 2026).

    The customer keeps a month tab, a roll-up tab covering that month and a dated working
    snapshot in one book, so the same delivery is written out two and three times by
    design. Both rows are still accounted for - the second rides on `unchanged` with its
    own code - and, crucially, the restatement does NOT take the line's quantity from the
    row it restates: 30 and 30 against a 50 line is one row of 30, not one row and one
    `qty_exceeds_ordered`.

    The REMARK is not part of what makes two rows the same instruction. The owner:
    "what we need from the order inquiries tab is just the sales order, location, quantity,
    delivery date, product ... the remark doesn't really matter, differing remark is same
    also as long as other keys are the same". So the second block here - a roll-up tab that
    carries the purchase order number the month tab left blank - is the SAME restatement,
    which is what this test used to read the other way round.
    `tests/test_oi_sheet_pairing_repair.py::test_ac_r_12_restatement_lends_its_citation`
    holds the other half of that ruling: the citation is merged onto the row that was kept.
    """
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        stated = (order.so_number, w.product.product_code, 30, D_OCT,
                  w.warehouse.warehouse_code, "")
        outcome = ImportOutcome(None, persist=False)

        result = w.apply(book(JAN26=[stated], ROLLUP=[stated]), outcome=outcome)

        assert result["rows"] == 2, "the file's own row count keeps both"
        assert result["rows_raised"] == 1, result
        assert len(w.rows()) == 1
        assert result["rows_line_not_found"] == 0, "the restatement took the line's quantity"
        assert outcome.processed == 2, outcome.breakdown()
        assert outcome.count_of("restates_an_instalment") == 1
        assert outcome.successful == 2, "a restatement is not a skip - its quantity is raised"
        assert [entry["code"] for entry in outcome.breakdown()["skipped"]] == []

    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        cited, _cited_line = w.po_line(qty_ordered="50")
        blank = (order.so_number, w.product.product_code, 30, D_OCT,
                 w.warehouse.warehouse_code, "")
        remarked = (order.so_number, w.product.product_code, 30, D_OCT,
                    w.warehouse.warehouse_code, cited.po_number)
        outcome = ImportOutcome(None, persist=False)

        result = w.apply(book(JAN26=[blank], ROLLUP=[remarked]), outcome=outcome)

        assert result["rows"] == 2
        assert result["rows_raised"] == 1, result
        assert len(w.rows()) == 1
        assert outcome.count_of("restates_an_instalment") == 1, outcome.breakdown()
        assert result["rows_line_not_found"] == 0, "the restatement took the line's quantity"


# --------------------------------------------------------------------------- #
# skipping a line that already carries an inquiry                              #
# --------------------------------------------------------------------------- #


def test_line_with_existing_row_is_skipped():
    """AC-S1-10. A line whose mirror already carries a non-cancelled row is left alone -
    the row, and its links, untouched."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        adopted = ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        held = w.board_row(mirror, qty="5")
        held_id, held_qty = str(held.id), Decimal(str(held.qty))
        assert adopted["project_sales_order_id"]

        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])
        result = w.apply(data)

        assert result["rows_already_raised"] == 1, result
        assert result["rows_raised"] == 0
        rows = w.rows()
        assert [str(row.id) for row in rows] == [held_id], "a second row was raised anyway"
        assert Decimal(str(rows[0].qty)) == held_qty
        assert w.links(rows[0]) == []


def test_second_apply_is_a_noop():
    """AC-S1-11. Re-uploading the same sheet writes nothing new (D2 is skip-only)."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        first = w.apply(data)
        second = w.apply(data)

        assert first["rows_raised"] == 1, first
        assert second["rows_raised"] == 0, second
        assert second["rows_already_raised"] == first["rows_raised"]
        assert len(w.rows()) == 1


# --------------------------------------------------------------------------- #
# pairing to the cited document (the sheet's remark, source 2)                 #
# --------------------------------------------------------------------------- #


def test_cited_po_is_linked_in_full():
    """AC-S1-12. The cited PO line has room for the whole row: one link, the uploader's
    name on it, and the row reads `placed`."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1, [link.document for link in links]
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert links[0].document == po.po_number
        assert str(links[0].linked_by) == w.actor
        assert row.state == INQUIRY_PLACED
        assert result["links_written"] == 1
        assert result["links_partial"] == 0


def test_cited_spo_is_linked():
    """AC-S1-13. A cited SPO lands on the ALLOCATION, and a plain `ORDER` row may hold one
    (R5 of `PLAN-scm-oi-draft-links.md`)."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        allocation = w.spo_allocation(quantity=50)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, allocation.spo_number),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1, [link.document for link in links]
        assert str(links[0].spo_allocation_id) == str(allocation.id)
        assert links[0].po_line_id is None
        assert row.verb == IV_ORDER
        assert result["links_written"] == 1


def test_short_po_line_links_partial():
    """AC-S1-14. Capacity 10 against a need of 30: the link is written for the capacity and
    the row reads `partly_linked`."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _line = w.po_line(qty_ordered="10")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1
        assert Decimal(str(links[0].qty)) == Decimal("10")
        assert row.state == INQUIRY_PARTLY_LINKED
        assert result["links_partial"] == 1
        assert result["links_written"] == 1


def test_unknown_document_leaves_row_unlinked():
    """AC-S1-15. A document the CRM does not hold is reported, the row is still raised, and
    the citation stays on it so the worklist shows where the sheet and the book disagree."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        absent = _po_number()
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, absent),
        ])

        result = w.apply(data)

        row = w.one_row()
        assert w.links(row) == []
        assert row.cited_document == absent
        assert row.state == INQUIRY_RAISED
        assert result["documents_not_linkable"] == [absent]
        assert result["links_written"] == 0


def test_two_cited_documents_in_order():
    """AC-S1-16. `A & B`: A is tried first for the whole need, B takes what A left."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        first_po, _a = w.po_line(qty_ordered="10")
        second_po, _b = w.po_line(qty_ordered="30")
        data = sheet([
            (order.so_number, w.product.product_code, 25, D_OCT,
             w.warehouse.warehouse_code, f"{first_po.po_number} & {second_po.po_number}"),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert [link.document for link in links] == [
            first_po.po_number,
            second_po.po_number,
        ]
        assert [Decimal(str(link.qty)) for link in links] == [Decimal("10"), Decimal("15")]
        assert row.state == INQUIRY_PLACED
        assert result["links_written"] == 1, "one ROW gained links, not two"


def test_order_remark_raises_unlinked_no_cascade():
    """AC-S1-17 (D5). `ORDER` states that nothing is placed. A fitting open PO line sitting
    right there must NOT be taken: auto-link stays the worklist's button."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, "ORDER"),
        ])

        result = w.apply(data)

        row = w.one_row()
        assert w.links(row) == [], "the retired cascade linked whatever fitted"
        assert row.state == INQUIRY_RAISED
        assert result["links_written"] == 0


def test_dedicated_line_still_links_when_cited():
    """AC-S1-18. Another sales order's claim dedicates the cited line; the sheet is a person
    naming a document, so the link is written anyway (manual semantics)."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, po_line = w.po_line(qty_ordered="50")

        other = w.order()
        other_line = w.line(other, qty_ordered="50")
        w.claim(order=other, core_line=other_line, document=po.po_number, po_line=po_line)

        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])
        result = w.apply(data)

        raised = [r for r in w.rows() if r.stock_location == w.warehouse.warehouse_code]
        assert len(raised) == 1, f"expected one raised row, got {len(raised)}"
        links = w.links(raised[0])
        assert len(links) == 1, "a claim from another SO refused a document the sheet names"
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert result["links_written"] == 1


# --------------------------------------------------------------------------- #
# what the importer no longer does                                             #
# --------------------------------------------------------------------------- #


def _scenario_plain(w):
    order = w.order()
    w.line(order, qty_ordered="50")
    return sheet([
        (order.so_number, w.product.product_code, 30, D_OCT,
         w.warehouse.warehouse_code, ""),
    ])


def _scenario_absent_order(w):
    return sheet([
        (f"{MARKER}-SO-GONE", w.product.product_code, 30, D_OCT,
         w.warehouse.warehouse_code, "ORDER"),
    ])


def _scenario_cited(w):
    order = w.order()
    w.line(order, qty_ordered="50")
    po, _line = w.po_line(qty_ordered="50")
    return sheet([
        (order.so_number, w.product.product_code, 30, D_OCT,
         w.warehouse.warehouse_code, po.po_number),
    ])


def _scenario_order_back(w):
    order = w.order()
    w.line(order, qty_ordered="50")
    return sheet([
        (order.so_number, w.product.product_code, 30, "ORDER BACK",
         w.warehouse.warehouse_code, "ORDER"),
    ])


@pytest.mark.parametrize(
    "build",
    [_scenario_plain, _scenario_absent_order, _scenario_cited, _scenario_order_back],
    ids=["matched row", "unknown sales order", "cited document", "order back"],
)
def test_no_sales_order_writes(build):
    """AC-S1-19 (D4). Under EVERY input, the book's own tables are untouched. AutoCount owns
    `sales_orders` and `sales_order_lines`; `_create_orders` and its refresh and withdrawal
    paths are gone."""
    with world() as w:
        data = build(w)
        before = w.book_counts()

        w.apply(data)

        assert w.book_counts() == before


def test_warehouse_id_untouched():
    """AC-S1-20. The sheet no longer writes a stock location onto the book's line."""
    with world() as w:
        order = w.order()
        line = w.line(order, warehouse=None, qty_ordered="50")
        w.warehouse_row(code="BRW-IB")
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_OCT, "BRW-IB", ""),
        ])

        w.apply(data)

        w.db.refresh(line)
        assert line.warehouse_id is None


def test_no_direct_claim_rows():
    """AC-S1-21. The importer opens no claim of its own; the only claims afterwards are the
    ones `_write_link` wrote for its links (`source = 'order_inquiry'`)."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])

        w.apply(data)

        claims = w.db.query(OrderLinkClaim).all()
        assert [claim.source for claim in claims] == ["order_inquiry"], [
            (claim.source, claim.po_number) for claim in claims
        ]
        assert len(claims) == len(w.links(w.one_row()))


# --------------------------------------------------------------------------- #
# result and outcomes                                                          #
# --------------------------------------------------------------------------- #


def test_result_keys_exact():
    """AC-S1-22. The result is exactly this set - the retired counters are gone, so no
    screen can print a number the importer no longer means."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert set(result) == RESULT_KEYS, sorted(set(result) ^ RESULT_KEYS)
        assert not (set(result) & RETIRED_KEYS)


def test_one_outcome_per_row():
    """AC-S1-23. One outcome per SOURCE row, with the codes the criterion lists - a job that
    reports 83 rows processed out of 69 is a job nobody can read."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        w.board_row(w.mirror_of(line), qty="5")

        second = w.order()
        w.line(second, qty_ordered="50")

        retail = w.order(demand_class="retail")
        w.line(retail, qty_ordered="50")

        data = sheet([
            # raised
            (second.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
            # the line already carries a row
            (order.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
            # no line at that location
            (second.so_number, w.product.product_code, 5, D_OCT, "BRW-XX", ""),
            # no such sales order
            (f"{MARKER}-SO-NONE", w.product.product_code, 5, D_OCT,
             w.warehouse.warehouse_code, ""),
            # not project demand
            (retail.so_number, w.product.product_code, 5, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])
        outcome = ImportOutcome(None, persist=False)

        w.apply(data, outcome=outcome)

        assert outcome.processed == 5, outcome.breakdown()
        assert outcome.count_of("created") == 1
        assert outcome.count_of("already_raised") == 1
        assert outcome.count_of("location_differs") == 1
        assert outcome.count_of("order_not_found") == 1
        assert outcome.count_of("order_not_plannable") == 1


def test_preview_writes_nothing_and_matches_apply():
    """AC-S1-24. `preview` runs the same match and writes nothing; a second preview after an
    apply reports every line as already raised."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])
        counted = (
            "rows",
            "rows_raised",
            "rows_already_raised",
            "rows_line_not_found",
            "links_written",
            "links_partial",
            "links_from_autocount",
        )

        before = w.preview(data)

        assert w.db.query(OrderInquiryRow).count() == 0, "preview wrote a row"
        assert w.db.query(OrderInquiryLink).count() == 0, "preview wrote a link"
        assert set(before) == RESULT_KEYS, sorted(set(before) ^ RESULT_KEYS)

        applied = w.apply(data)
        assert {key: before[key] for key in counted} == {
            key: applied[key] for key in counted
        }

        after = w.preview(data)
        assert after["rows_raised"] == 0
        assert after["rows_already_raised"] == applied["rows_raised"]


def test_missing_header_refused():
    """AC-S1-25. A file whose header names neither a sales order nor an item code is refused
    by both entry points, with the reader's own problem on it and none of the retired keys.

    The reader names the two columns in prose (it has no `missing_columns` list of its own),
    so the criterion's "the missing columns named" is asserted on that sentence.
    """
    with world() as w:
        data = sheet(
            [("x", 1, 2, 3)],
            headers=("QTY", "DELIVERY DATE", "STOCK LOCATION", "REMARK"),
        )

        for result in (w.preview(data), w.apply(data)):
            assert result["ok"] is False, result
            assert result["problems"], "a refusal with no reason"
            assert "sales order" in result["problems"][0].lower()
            assert "item code" in result["problems"][0].lower()
            assert set(result) == RESULT_KEYS, sorted(set(result) ^ RESULT_KEYS)


# --------------------------------------------------------------------------- #
# history migrates too (D8)                                                    #
# --------------------------------------------------------------------------- #


def test_closed_delivered_order_migrates():
    """AC-S1-26. A closed, fully delivered project order is adopted FOR THE MIGRATION: one
    mirror line per core line, closed ones included, and the core book untouched."""
    with world() as w:
        order = w.order(status="closed")
        delivered = w.line(
            order, qty_ordered="40", qty_delivered="40", line_status="closed"
        )
        other = w.line(
            order,
            product=w.product_row(),
            qty_ordered="10",
            qty_delivered="10",
            line_status="closed",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 40, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["orders_not_plannable"] == []
        assert result["rows_raised"] == 1, result
        record = (
            w.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.so_id == str(order.id))
            .one()
        )
        mirrors = (
            w.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == str(record.id))
            .all()
        )
        assert {str(m.core_sales_order_line_id) for m in mirrors} == {
            str(delivered.id),
        }, "the line the sheet NAMED is mirrored, and only it (AC-S1-26 as amended)"
        assert str(other.id) not in {
            str(m.core_sales_order_line_id) for m in mirrors
        }, "a delivered line nobody named stays unmirrored"
        mirrored = next(
            m for m in mirrors if str(m.core_sales_order_line_id) == str(delivered.id)
        )
        assert Decimal(str(mirrored.qty)) == Decimal("40"), "the mirror states the ORDERED qty"
        assert str(w.one_row().so_line_id) == str(mirrored.id)

        w.db.refresh(order)
        w.db.refresh(delivered)
        assert order.status == "closed"
        assert delivered.line_status == "closed"
        assert Decimal(str(delivered.qty_ordered)) == Decimal("40")


def test_adopt_for_migration_mirrors_every_line_and_keeps_one_refusal():
    """AC-S1-26 / AC-S1-7, at the adoption service itself.

    `adopt_for_migration` is `adopt`'s sibling: the same record and the same `_mirror`, with
    the open and outstanding refusals dropped (history has neither) and only the
    project-class one kept. `adopt` itself must be untouched, so the board's gate still
    refuses a closed order.
    """
    with world() as w:
        order = w.order(status="closed")
        closed_line = w.line(
            order, qty_ordered="40", qty_delivered="40", line_status="closed"
        )
        service = ProjectSOAdoptionService(w.db)

        result = service.adopt_for_migration(str(order.id), w.actor)

        mirrors = (
            w.db.query(ProjectSalesOrderLine)
            .filter(
                ProjectSalesOrderLine.project_sales_order_id
                == str(result["project_sales_order_id"])
            )
            .all()
        )
        assert [str(m.core_sales_order_line_id) for m in mirrors] == [str(closed_line.id)]

        again = service.adopt_for_migration(str(order.id), w.actor)
        assert again["project_sales_order_id"] == result["project_sales_order_id"]

    with world() as w:
        from app.services.error_handler import AppException

        retail = w.order(demand_class="retail")
        w.line(retail, qty_ordered="10")

        with pytest.raises(AppException) as refused:
            ProjectSOAdoptionService(w.db).adopt_for_migration(str(retail.id), w.actor)

        assert refused.value.detail["code"] == "sales_order_not_project_class"


def test_an_existing_record_gains_only_the_lines_the_sheet_names():
    """AC-S1-26, second half (review finding 4, 14 Sep), restated for AC-S2-15.

    THE PURPOSE IS UNCHANGED: the upload adds nothing beyond what it names. What changed is
    what the record already holds when it arrives.

    The original reading was that `adopt` mirrored only `is_open_demand()` lines, so a
    delivered one had no mirror and the sheet's own row created it. Since the 14 September
    2026 ruling `adopt` mirrors every UNDECIDED line, delivered or not - the board has to be
    able to confirm a line nobody sourced, and `confirm` names a line by its mirror - so all
    three lines below are already mirrored before the sheet is read.

    That also retires the premise the old docstring rested on. `_authored_line_totals` used
    to sum mirror `qty` with no status filter, which was safe only while every mirror line
    was a still-owed one by construction; it now filters explicitly, so a delivered mirror
    line does not move the record's reconciliation figures and there is nothing to protect
    the record FROM on that score.

    What the upload must still not do is invent a mirror. It raises its one row against the
    mirror that is already there - the SAME row, by id - and leaves the record's line count
    exactly as adoption left it. A second mirror for a line that already has one would give
    the board two rows for one piece of demand.
    """
    with world() as w:
        order = w.order()
        open_line = w.line(order, qty_ordered="50")
        named = w.product_row()
        delivered = w.line(
            order, product=named, qty_ordered="10", qty_delivered="10",
            line_status="closed",
        )
        unnamed = w.line(
            order, product=w.product_row(), qty_ordered="7", qty_delivered="7",
            line_status="closed",
        )
        record = ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        record_id = record["project_sales_order_id"]

        # AC-S2-15: delivery is not a decision, so every one of the three is mirrored.
        assert w.mirror_of(open_line) is not None, "the board mirrored the owed line"
        assert w.mirror_of(delivered) is not None, "and the delivered undecided one"
        assert w.mirror_of(unnamed) is not None, "and the one the sheet will not name"
        before = str(w.mirror_of(delivered).id)
        lines_before = _mirror_count(w, record_id)
        assert lines_before == 3

        data = sheet([
            (order.so_number, named.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])
        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        # ON THE EXISTING MIRROR, not on one the upload made for itself.
        assert str(w.one_row().so_line_id) == before
        assert str(w.mirror_of(delivered).id) == before
        assert _mirror_count(w, record_id) == 3, (
            "the upload added a mirror line nobody asked for"
        )


def _mirror_count(w, project_sales_order_id: str) -> int:
    return (
        w.db.query(ProjectSalesOrderLine)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == str(project_sales_order_id)
        )
        .count()
    )


def test_closed_received_po_line_links():
    """AC-S1-27. Capacity is `qty_ordered` less OTHER LINKS, never the outstanding, so a
    closed and fully received PO line links exactly like an open one."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _line = w.po_line(qty_ordered="20", qty_received="20", line_status="closed")
        data = sheet([
            (order.so_number, w.product.product_code, 20, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1, "a received line was treated as having nothing left"
        assert Decimal(str(links[0].qty)) == Decimal("20")
        assert row.state == INQUIRY_PLACED
        assert result["links_written"] == 1


def test_row_note_carries_migration_stamp():
    """AC-S1-28. A migrated row is tellable from a board-raised one on the worklist without
    a new column, and the operator's own remark is kept after the stamp."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, "CUSTOMER HOLD"),
        ])

        w.apply(data)

        note = w.one_row().note or ""
        assert note.startswith("Migrated from order inquiry sheet"), note
        assert "CUSTOMER HOLD" in note


def test_closed_line_row_not_open_demand():
    """AC-S1-29. A row raised against a CLOSED line is not demand: `scm.committed_v` counts
    the LINE, and a closed line is not owed.

    On the real database, because the view is installed by a migration rather than by
    `create_all`. A retail order at the same product and location is seeded beside it so the
    snapshot has something in it to be identical about.
    """
    with world(pg_session) as w:
        order = w.order(status="closed")
        w.line(order, qty_ordered="40", qty_delivered="40", line_status="closed")
        neighbour = w.order(demand_class="retail")
        w.line(neighbour, qty_ordered="7")
        w.db.flush()

        def snapshot():
            return w.db.execute(
                sa.text(
                    "select product_id, warehouse_id, committed, project_committed, "
                    "retail_committed from scm.committed_v where product_id = :p "
                    "order by warehouse_id"
                ),
                {"p": str(w.product.id)},
            ).fetchall()

        before = snapshot()
        assert before, "the retail neighbour must be counted before the sheet is applied"

        data = sheet([
            (order.so_number, w.product.product_code, 40, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])
        result = w.apply(data)
        w.db.flush()

        assert result["rows_raised"] == 1, result
        assert snapshot() == before
        # The state the view ignores, and the honest word for it: purchasing dealt with
        # this instruction and the goods went out.
        #
        # Read by THIS test's own item code rather than through `one_row()`. This is the one
        # case on the real database (`pg_session`, for the view), where the tables are not
        # empty - a browser run against the same lane database leaves rows of its own, and an
        # assertion that says "the only row there is" would then be measuring somebody else's
        # upload.
        mine = (
            w.db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.item_code == w.product.product_code)
            .all()
        )
        assert len(mine) == 1, [row.item_code for row in mine]
        assert mine[0].state == INQUIRY_ACTIONED


# --------------------------------------------------------------------------- #
# what a bad cell may not do (security review, 14 Sep)                         #
# --------------------------------------------------------------------------- #


def test_a_row_with_no_quantity_is_skipped_and_frees_nothing():
    """AC-S1-40 (security review N2). A quantity of zero is not an instruction, and a
    NEGATIVE one must not hand capacity back to the line: charged to the ledger it would
    let the row after it take more of the order than the order holds.

    The three rows are deliberately in this order - take the whole line, then a negative,
    then ask for the whole line again. The third row fits only if the second one gave
    something back.

    The third row states a DIFFERENT delivery date, which is what makes it a second
    instruction rather than a restatement of the first. It used to differ only by its
    remark, and under R3 (owner ruling, 14 Sep 2026, AC-R-11) the remark is no longer part
    of the restatement key - so the row would be counted into the first one and never reach
    the quantity test this criterion is about. The date is one of the five fields that IS
    the key, and varying it leaves the invariant exactly as it was.
    """
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 50, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, -50, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 50, date(2026, 12, 1),
             w.warehouse.warehouse_code, "SECOND"),
        ])
        outcome = ImportOutcome(None, persist=False)

        result = w.apply(data, outcome=outcome)

        assert result["rows_raised"] == 1, result
        assert outcome.count_of("invalid_quantity") == 1
        assert outcome.processed == 3, outcome.breakdown()
        assert [entry["reason"] for entry in result["line_not_found"]] == [
            "qty_exceeds_ordered"
        ], "the negative row handed the line's quantity back"


def test_an_over_long_location_is_reported_not_raised():
    """AC-S1-41 (security review N3). `order_inquiry_rows.stock_location` is 80 characters,
    so a longer cell cannot be raised - and the line here has NO warehouse, which is exactly
    the case that would otherwise match it and abort the whole job on the insert."""
    with world() as w:
        order = w.order()
        w.line(order, warehouse=None, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_OCT, "BRW-" + "X" * 120, ""),
        ])

        result = w.apply(data)

        assert result["ok"] is True, "one bad cell must not fail the upload"
        assert result["rows_raised"] == 0, result
        assert w.rows() == []
        assert [entry["reason"] for entry in result["line_not_found"]] == ["location_differs"]


def test_an_upload_with_no_actor_is_refused(monkeypatch):
    """AC-S1-42 (security review N1). Every row this raises is born acknowledged and every
    link records who made it, so an upload with nobody to attribute it to would write a page
    of decisions nobody can be asked about. The route always has an actor; this is the
    direct caller's guard."""
    from app.config import settings

    monkeypatch.setattr(settings, "external_api_key_act_as_user_id", None, raising=False)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data, actor=None)

        assert result["ok"] is False, result
        assert any("attribute" in problem for problem in result["problems"]), result
        assert result["rows_raised"] == 0
        assert w.rows() == []
        assert set(result) == RESULT_KEYS, sorted(set(result) ^ RESULT_KEYS)


def test_an_upload_touches_only_its_own_companys_order():
    """AC-S1-43 (security review N6). Two companies, one sales order NUMBER.

    The sheet carries numbers, not ids, and every lookup this importer makes is by number -
    so the only thing standing between an upload and another company's order is the scope
    the job runs under. Asserted rather than assumed.
    """
    with blank_session() as db:
        srt = db.execute(
            sa.text("select id from companies where code = 'SRT'")
        ).scalar()
        other = _uid()
        db.execute(
            sa.text(
                "insert into companies (id, name, code, is_active) "
                "values (:id, :name, :code, true)"
            ),
            {"id": other, "name": f"{MARKER} other company", "code": f"ZZTC{_n():04d}"},
        )
        number = f"{MARKER}-SHARED{_n():04d}"

        with company_scope(db, frozenset({other})):
            far = World(db, other)
            far_order = far.order(number=number)
            far_line = far.line(far_order, qty_ordered="50")

        with company_scope(db, frozenset({srt})):
            near = World(db, srt)
            near_order = near.order(number=number)
            near_line = near.line(near_order, qty_ordered="50")
            result = near.apply(sheet([
                (number, near.product.product_code, 30, D_OCT,
                 near.warehouse.warehouse_code, ""),
            ]))

            assert result["rows_raised"] == 1, result
            assert result["orders_adopted"] == 1
            assert result["orders_stamped"] == 1
            assert str(near.one_row().so_line_id) == str(near.mirror_of(near_line).id)
            assert near_order.demand_origin == importer.SOURCE_SYSTEM

        with company_scope(db, frozenset({other})):
            assert far.mirror_of(far_line) is None, "the other company's order was adopted"
            assert far.rows() == [], "a row was raised under the other company"
            db.refresh(far_order)
            assert far_order.demand_origin is None, "the other company's header was stamped"


# --------------------------------------------------------------------------- #
# the pairing AutoCount already states (D9, D10)                               #
# --------------------------------------------------------------------------- #


def test_autocount_claim_pairs_row_first():
    """AC-S1-30. The linkage the ingest wrote is the source of truth: a resolved `autocount`
    claim on the row's core line is followed, with no remark in the sheet at all, and the
    link's stamp names where it came from."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        po, po_line = w.po_line(qty_ordered="50")
        w.claim(order=order, core_line=line, document=po.po_number, po_line=po_line)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1, [link.document for link in links]
        assert str(links[0].po_line_id) == str(po_line.id)
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert "auto: autocount linkage" in (row.note or "")
        assert result["links_from_autocount"] == 1


def test_autocount_first_then_citation_fills_rest():
    """AC-S1-31. AutoCount covers 20 of 30; the remark's document takes the remaining 10,
    and the AutoCount link is the FIRST one on the row."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        stated, stated_line = w.po_line(qty_ordered="20")
        cited, _cited_line = w.po_line(qty_ordered="50")
        w.claim(order=order, core_line=line, document=stated.po_number, po_line=stated_line)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, cited.po_number),
        ])

        result = w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert [link.document for link in links] == [stated.po_number, cited.po_number]
        assert [Decimal(str(link.qty)) for link in links] == [Decimal("20"), Decimal("10")]
        assert row.state == INQUIRY_PLACED
        # `po_ref` is the FIRST link's document, so it is what says which source won.
        assert row.po_ref == stated.po_number
        assert result["links_from_autocount"] == 1


def test_autocount_wins_over_remark():
    """AC-S1-31b. AutoCount says A, the sheet says B, A covers the row: the link is to A and
    B is kept on the row as the citation, so the worklist shows the disagreement."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        stated, stated_line = w.po_line(qty_ordered="50")
        cited, _cited_line = w.po_line(qty_ordered="50")
        w.claim(order=order, core_line=line, document=stated.po_number, po_line=stated_line)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, cited.po_number),
        ])

        w.apply(data)

        row = w.one_row()
        links = w.links(row)
        assert [link.document for link in links] == [stated.po_number]
        assert row.cited_document == cited.po_number


def test_autocount_spo_before_po():
    """AC-S1-32. Two stated pairings on one core line: the SPO allocation is taken first
    (R5, "SPO first then PO")."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        po, po_line = w.po_line(qty_ordered="10")
        allocation = w.spo_allocation(quantity=10)
        w.claim(order=order, core_line=line, document=po.po_number, po_line=po_line)
        w.claim(
            order=order,
            core_line=line,
            document=allocation.spo_number,
            allocation=allocation,
        )
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        w.apply(data)

        links = w.links(w.one_row())
        assert len(links) == 1, [link.document for link in links]
        assert str(links[0].spo_allocation_id) == str(allocation.id)
        assert links[0].po_line_id is None


def test_own_and_crm_claims_ignored():
    """AC-S1-33. This feature's own echo (`order_inquiry`) and the CRM's own decisions
    (`crm_supply`, `planner`) are not AutoCount's record, so they pair nothing."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        for source in ("order_inquiry", "crm_supply", "planner"):
            po, po_line = w.po_line(qty_ordered="50")
            w.claim(
                order=order,
                core_line=line,
                document=po.po_number,
                po_line=po_line,
                source=source,
            )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert w.links(w.one_row()) == []
        assert result["links_written"] == 0
        assert result["links_from_autocount"] == 0


def test_po_pairing_follows_from_po_number_to_spo():
    """AC-S1-35 (D10). AutoCount states SO line -> PO line, and the SPO carries that PO as
    `from_po_number`: the link lands on the ALLOCATION first, so the worklist shows the SPO
    with its source PO beside it. The PO line takes only what the SPO cannot cover."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        po, po_line = w.po_line(qty_ordered="30")
        allocation = w.spo_allocation(quantity=10, from_po_number=po.po_number)
        w.claim(order=order, core_line=line, document=po.po_number, po_line=po_line)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        w.apply(data)

        links = w.links(w.one_row())
        assert [str(link.spo_allocation_id or "") for link in links] == [
            str(allocation.id),
            "",
        ], [link.document for link in links]
        assert [Decimal(str(link.qty)) for link in links] == [Decimal("10"), Decimal("20")]
        assert str(links[1].po_line_id) == str(po_line.id)


def test_direct_spo_claim_wins_over_chain():
    """AC-S1-36. The ingest wrote a DIRECT SO -> SPO claim and the PO chain names the same
    allocation: it is linked once, and the chain adds nothing."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        po, po_line = w.po_line(qty_ordered="30")
        allocation = w.spo_allocation(
            quantity=10,
            from_po_number=po.po_number,
            from_so_line_ref=str(line.id),
        )
        w.claim(
            order=order,
            core_line=line,
            document=allocation.spo_number,
            allocation=allocation,
        )
        w.claim(order=order, core_line=line, document=po.po_number, po_line=po_line)
        data = sheet([
            (order.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        w.apply(data)

        links = w.links(w.one_row())
        assert len(links) == 1, [link.document for link in links]
        assert str(links[0].spo_allocation_id) == str(allocation.id)
        assert Decimal(str(links[0].qty)) == Decimal("10")


def test_links_from_autocount_counted():
    """AC-S1-34. The operator can see how much the BOOK paired versus the sheet."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="50")
        po, po_line = w.po_line(qty_ordered="50")
        w.claim(order=order, core_line=line, document=po.po_number, po_line=po_line)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        assert w.apply(data)["links_from_autocount"] == 1

    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        assert result["links_written"] == 1
        assert result["links_from_autocount"] == 0
