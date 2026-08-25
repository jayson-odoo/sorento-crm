"""An order inquiry has a NUMBER, not just an id.

`OI-000001`, the same shape and width as `ProjectSalesOrder.provisional_ref` (`PSO-000001`):
the highest number this company has issued, plus one. Until this existed the only way to
name what purchasing had been handed was a UUID, which nothing in this product is allowed to
show a person - and "the inquiry on SO414033" stops being an answer the moment an amendment
raises the second one.

The number is stamped by a `before_insert` listener on the model rather than by each writer,
so "no inquiry exists without a number" is structural: the two creation sites in the service
never mention it, and neither does any future one.

Postgres, blank scratch schema, rolled back at teardown, and every FK target real: the
uniqueness this slice leans on is a database constraint, so a test that ran anywhere else
would prove nothing about it.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.project_so import OrderInquiry, ProjectSalesOrder
from app.models.user import User
from app.services import project_order_inquiry_service as svc

from ._pg_fixture import blank_session

MARKER = "zzt-oino"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _company(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _order(db, company_id: str) -> ProjectSalesOrder:
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        status="draft",
    )
    db.add(order)
    db.flush()
    return order


def _inquiry(db, order: ProjectSalesOrder, *, amendment_id=None) -> OrderInquiry:
    row = OrderInquiry(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        amendment_id=amendment_id,
        state="raised",
    )
    db.add(row)
    db.flush()
    return row


def test_the_first_inquiry_is_oi_000001(db):
    company_id = _company(db)

    number = svc.next_inquiry_no(db, company_id)

    assert number == "OI-000001"


def test_each_inquiry_takes_the_next_number(db):
    company_id = _company(db)
    first = _inquiry(db, _order(db, company_id))

    second = _inquiry(db, _order(db, company_id))

    assert first.inquiry_no == "OI-000001"
    assert second.inquiry_no == "OI-000002"


def test_a_gap_in_the_series_is_never_refilled(db):
    """The next number is the HIGHEST plus one, never the count.

    Counting would hand a departed inquiry's number to a different one the moment anything
    was removed, and the old number is already in somebody's email. (Removing the highest
    number of all does free it again - the same property `PSO-000001` has, and the same
    non-event: nothing in this system deletes an inquiry, rows are cancelled.)
    """
    company_id = _company(db)
    dropped = _inquiry(db, _order(db, company_id))
    kept = _inquiry(db, _order(db, company_id))
    assert (dropped.inquiry_no, kept.inquiry_no) == ("OI-000001", "OI-000002")
    db.delete(dropped)
    db.flush()

    assert svc.next_inquiry_no(db, company_id) == "OI-000003"


def test_the_number_is_unique_in_the_database(db):
    """Enforced by the table, not by remembering to check: a document number two records
    share is worth less than no number at all."""
    company_id = _company(db)
    first = _inquiry(db, _order(db, company_id))
    order = _order(db, company_id)

    db.add(OrderInquiry(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        state="raised",
        inquiry_no=first.inquiry_no,
    ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_confirmation_stamps_the_number_on_the_inquiry_it_raises(db):
    """The confirmed Buy handoff is one of the two places an inquiry is born, and it says
    nothing about numbering: the stamp does that, which is the point of putting it there."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.models.project_so import ProjectSalesOrderLine, SOSupplyDecision
    from datetime import datetime

    company_id = _company(db)
    order = _order(db, company_id)
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat")
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(), product_code=f"ZZT-{_uid()[:8]}", product_name=f"{MARKER} item",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("10.00"))
    db.add(product)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=company_id, project_sales_order_id=order.id, line_no=1,
        product_id=product.id, description=f"{MARKER} line", qty=Decimal("5"), uom="UNIT",
        unit_price=Decimal("10.00"), amount=Decimal("50.00"),
        delivery_date=date(2026, 9, 1))
    db.add(line)
    db.flush()
    actor = User(id=_uid(), email=f"{_uid()}@zzt.test", name=f"{MARKER} Yana")
    db.add(actor)
    db.flush()
    decision = SOSupplyDecision(
        id=_uid(), company_id=company_id, project_sales_order_id=order.id, revision_no=1,
        state="active", line_snapshots=[{"line_no": 1}], confirmed_by=actor.id,
        confirmed_at=datetime.utcnow())
    db.add(decision)
    db.flush()

    result = svc.ProjectOrderInquiryService(db).refresh_for_decision(
        order, decision,
        [{"line": line, "line_no": 1, "item_code": product.product_code,
          "buy_qty": Decimal("5"), "required_date": line.delivery_date,
          "stock_location": None}],
        actor_user_id=actor.id,
    )

    assert result["inquiry"].inquiry_no == "OI-000001"


def test_the_detail_read_names_the_inquiry(db):
    """It is what the screen prints, so it has to survive the serialiser as well as the
    column - the same lesson `response_model` teaches every time it drops a field."""
    company_id = _company(db)
    order = _order(db, company_id)
    inquiry = _inquiry(db, order)

    detail = svc.ProjectOrderInquiryService(db).get_for_sales_order(order.id)

    assert detail is not None
    assert detail["inquiry_no"] == inquiry.inquiry_no
