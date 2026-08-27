"""The planning board says what purchasing has already been TOLD about each line.

The board answers "what should we do about this demand". It could not answer "what has
already been done about it": the decision travelled with the row, but the instruction that
decision produced - the order inquiry - did not, so a planner looking at a decided line
still had to open another screen to learn whether anybody had acted on it.

The chain is the mirror, the same one every other planning read uses:
`projects.order_inquiry_rows.so_line_id` -> `projects.sales_order_lines` ->
`core_sales_order_line_id` -> the core line the board is built from. ONE query for the
whole board, never one per row.

A line nobody has raised anything for states `None`, never an empty object: "nobody has
been told about this line" and "told, about nothing" are different answers.

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    SO_STATUS_ADOPTED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)

from ._pg_fixture import blank_session

MARKER = "zzt-board-oi"
TODAY = date(2026, 8, 19)
#: The week bucket a 2026-09-03 required date lands in.
BUCKET = "2026-08-31"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db) -> Warehouse:
    code = f"ZZT-{_uid()[:6]}"
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True,
        segment="project",
    )
    db.add(row)
    db.flush()
    return row


def _order(db) -> SalesOrder:
    row = SalesOrder(
        id=_uid(),
        so_number=f"ZZT-SO-{_uid()[:8]}",
        order_date=date(2026, 1, 1),
        demand_class="project",
        status="open",
    )
    db.add(row)
    db.flush()
    return row


def _line(db, order: SalesOrder, product: Product, warehouse: Warehouse) -> SalesOrderLine:
    row = SalesOrderLine(
        id=_uid(),
        sales_order_id=order.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal("10"),
        qty_delivered=Decimal("0"),
        required_date=date(2026, 9, 3),
        line_status="open",
        purchasing_status="not_reviewed",
    )
    db.add(row)
    db.flush()
    return row


def _adopted(db, company_id: str, order: SalesOrder) -> ProjectSalesOrder:
    """The planning record for an order out of the AutoCount book: no project
    registration, `so_id` is the whole link."""
    record = ProjectSalesOrder(
        id=_uid(), company_id=company_id, project_id=None, so_id=order.id,
        provisional_ref=order.so_number, autocount_doc_no=order.so_number,
        status=SO_STATUS_ADOPTED,
    )
    db.add(record)
    db.flush()
    return record


def _mirror(db, company_id: str, record: ProjectSalesOrder, core_line: SalesOrderLine):
    row = ProjectSalesOrderLine(
        id=_uid(), company_id=company_id, project_sales_order_id=record.id, line_no=1,
        product_id=core_line.product_id, qty=Decimal("10"), uom="UNIT",
        unit_price=Decimal("1.00"), amount=Decimal("10.00"),
        core_sales_order_line_id=core_line.id,
    )
    db.add(row)
    db.flush()
    return row


def _inquiry(db, company_id: str, record: ProjectSalesOrder, mirror, *, state,
             created_at=None):
    inquiry = OrderInquiry(
        id=_uid(), company_id=company_id, project_sales_order_id=record.id,
        state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id,
        so_line_id=mirror.id, item_code=f"{MARKER}-ITEM", qty=Decimal("10"),
        verb=IV_ORDER, state=state,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return inquiry


def _service(db):
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    return FulfilmentBoardService(db)


def _contribution(board, item_code: str) -> dict:
    cell = next(
        c for c in board["cells"]
        if c["item_code"] == item_code and c["bucket_key"] == BUCKET
    )
    return cell["contributions"][0]


def test_a_contribution_names_the_inquiry_raised_for_its_line():
    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db)
        order = _order(db)
        core_line = _line(db, order, product, _warehouse(db))
        record = _adopted(db, company_id, order)
        mirror = _mirror(db, company_id, record, core_line)
        inquiry = _inquiry(db, company_id, record, mirror, state=INQUIRY_PLACED)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _contribution(board, product.product_code)
        # The HANDSHAKE rides in the same cell since `PLAN-scm-oi-handshake.md`: `state`
        # is where the supply stands, `ack_state` (and the refusal beside it) is whether
        # purchasing has taken the instruction on. A row nobody has read says `awaiting`
        # and names no refusal, which is exactly what an untouched cell must say.
        assert contribution["order_inquiry"] == {
            "inquiry_no": inquiry.inquiry_no,
            "state": INQUIRY_PLACED,
            "ack_state": "awaiting",
            "rejected_reason": None,
            "rejected_by_name": None,
        }
        # Stamped by the model's own listener, not invented here.
        assert inquiry.inquiry_no.startswith("OI-")


def test_a_line_nobody_has_raised_an_inquiry_for_states_none():
    """Not an empty object: an adopted order with a mirror line and no instruction has had
    nothing said about it, and that is a different answer from "said, about nothing"."""
    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db)
        order = _order(db)
        core_line = _line(db, order, product, _warehouse(db))
        record = _adopted(db, company_id, order)
        _mirror(db, company_id, record, core_line)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        assert _contribution(board, product.product_code)["order_inquiry"] is None


def test_a_line_with_no_planning_record_at_all_states_none():
    """Most of the book: nobody has adopted the order, so there is no mirror to reach an
    inquiry through and no query can invent one."""
    with blank_session() as db:
        product = _product(db)
        order = _order(db)
        _line(db, order, product, _warehouse(db))

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        assert _contribution(board, product.product_code)["order_inquiry"] is None


def test_the_latest_instruction_wins_when_a_line_carries_several():
    """The G2 cascade splits a line's rows - a placed allocation and the raised remainder -
    and an amendment raises a second inquiry entirely. The column answers "what is the
    current instruction", so the newest row is the one it names.

    Both timestamps are PINNED, and that is the point rather than fixture noise: inside one
    transaction `now()` is a constant, so two rows written together carry the same
    `created_at` and only an explicitly later one is actually later.
    """
    from datetime import datetime

    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db)
        order = _order(db)
        core_line = _line(db, order, product, _warehouse(db))
        record = _adopted(db, company_id, order)
        mirror = _mirror(db, company_id, record, core_line)
        first = _inquiry(
            db, company_id, record, mirror, state=INQUIRY_PLACED,
            created_at=datetime(2026, 8, 1, 9, 0),
        )
        db.add(OrderInquiryRow(
            id=_uid(), company_id=company_id, order_inquiry_id=first.id,
            so_line_id=mirror.id, item_code=f"{MARKER}-ITEM", qty=Decimal("4"),
            verb=IV_ORDER, state=INQUIRY_RAISED,
            created_at=datetime(2026, 8, 12, 9, 0),
        ))
        db.flush()

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        assert _contribution(board, product.product_code)["order_inquiry"]["state"] == (
            INQUIRY_RAISED
        )


def test_two_answered_refusals_leave_the_LATEST_inquiry_number_on_the_cell():
    """A refusal CS has already answered never outranks a live row - but against ANOTHER
    answered refusal it is the later of the two that stands.

    The scan reads oldest first, and it used to skip every answered refusal once the line
    had an entry at all, so a line whose only rows were two answered refusals kept the
    FIRST one's inquiry number: the cell named an instruction two refusals ago. It says
    what it was last told about.
    """
    from datetime import datetime

    from app.models.project_so import ACK_REJECTED, SOAmendment

    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db)
        order = _order(db)
        core_line = _line(db, order, product, _warehouse(db))
        record = _adopted(db, company_id, order)
        mirror = _mirror(db, company_id, record, core_line)

        older = _inquiry(
            db, company_id, record, mirror, state=INQUIRY_RAISED,
            created_at=datetime(2026, 8, 1, 9, 0),
        )
        # The second inquiry belongs to an AMENDMENT, which is the only way one sales order
        # carries two of them (`uq_project_order_inquiry_per_sales_order`) and exactly how
        # this shape arises on the book: purchasing refuses, CS amends, purchasing refuses
        # the amendment, CS decides again.
        amendment = SOAmendment(
            id=_uid(), company_id=company_id, project_sales_order_id=record.id,
        )
        db.add(amendment)
        db.flush()
        newer = OrderInquiry(
            id=_uid(), company_id=company_id, project_sales_order_id=record.id,
            amendment_id=amendment.id, inquiry_no="OI-000002", state=INQUIRY_RAISED,
        )
        db.add(newer)
        db.flush()
        db.add(OrderInquiryRow(
            id=_uid(), company_id=company_id, order_inquiry_id=newer.id,
            so_line_id=mirror.id, item_code=f"{MARKER}-ITEM", qty=Decimal("10"),
            verb=IV_ORDER, state=INQUIRY_RAISED,
            created_at=datetime(2026, 8, 12, 9, 0),
        ))
        db.flush()
        rejected_at = {
            str(older.id): datetime(2026, 8, 2, 9, 0),
            str(newer.id): datetime(2026, 8, 13, 9, 0),
        }
        for row in (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == mirror.id)
            .all()
        ):
            row.ack_state = ACK_REJECTED
            row.rejected_at = rejected_at[str(row.order_inquiry_id)]
            row.rejected_reason = "Factory closed"
        db.flush()

        # CS decided the line again AFTER both refusals, so both are answered.
        cell = _service(db)._order_inquiries(
            [str(core_line.id)],
            decided_at={str(core_line.id): datetime(2026, 8, 14, 9, 0)},
        )[str(core_line.id)]

    assert cell["inquiry_no"] == newer.inquiry_no
    assert cell["inquiry_no"] != older.inquiry_no
    # Answered, so the objection itself is not repeated: no reason, no name.
    assert cell["rejected_reason"] is None
    assert cell["rejected_by_name"] is None
    # PINNED, and NOT ruled: the seeded entry still carries the refused row's own
    # `ack_state`, because it is the only row this line has and the entry is copied off it
    # whole. Every other shape re-seeds from a live row, so this is the one case where the
    # word survives its answer. Left for the captain, because suppressing it is a decision
    # about what an answered refusal's cell should SAY, not a defect in this scan.
    assert cell["ack_state"] == ACK_REJECTED
