"""The reconciled Project-line to core-line link (PLAN-scm-front-planning.md 6.1, AC-A02).

Stage 0 adds `projects.sales_order_lines.core_sales_order_line_id` and nothing reads it
yet. What the column has to promise before Stage 1B reconciles anything is the UNIQUENESS
of the link: one Project line per core line. Two Project lines pointing at the same core
`sales_order_lines` row would let the same committed quantity be promised twice, and the
whole balance invariant in section 3.1 is written against "every Project line has a unique
reconciled core SO line".

The rule is a partial unique index rather than a plain one because the column is nullable
for the whole of Stage 0 and 1A: an unreconciled line carries NULL, Postgres treats NULLs
as distinct anyway, and stating the predicate keeps the index off the rows that have not
been reconciled yet.

Postgres, blank scratch schema, rolled back at teardown. Every FK target is real.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_DRAFT,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-core-link"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} CS"))
    db.flush()
    return user_id


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


def _core_line(db, product: Product) -> SalesOrderLine:
    """One core `public.sales_order_lines` row, with its own header."""
    order = SalesOrder(id=_uid(), so_number=f"ZZT-SO-{_uid()[:8]}", status="open")
    db.add(order)
    db.flush()
    line = SalesOrderLine(
        id=_uid(),
        sales_order_id=order.id,
        product_id=product.id,
        qty_ordered=Decimal("10"),
        qty_delivered=Decimal("0"),
        required_date=date(2027, 1, 7),
    )
    db.add(line)
    db.flush()
    return line


def _project_order(db, company_id: str, owner: str) -> ProjectSalesOrder:
    from app.services.project_service import register_project

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tuju Residences {_uid()[:12]}",
    )
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        area_group="TOWER",
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        status=SO_STATUS_DRAFT,
        grouping_origin="area",
    )
    db.add(order)
    db.flush()
    return order


def _project_line(
    db,
    order: ProjectSalesOrder,
    product: Product,
    *,
    line_no: int,
    core_sales_order_line_id: str | None = None,
) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        line_no=line_no,
        product_id=product.id,
        description=f"{MARKER} line {line_no}",
        qty=Decimal("10"),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal("100.00"),
        delivery_date=date(2027, 1, 7),
        core_sales_order_line_id=core_sales_order_line_id,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        yield db, company_id, _user(db)


def test_two_project_lines_cannot_claim_the_same_core_line(seeded):
    """Section 3.1 step 2: the reconciled link is UNIQUE, enforced by the database.

    Claiming one core line twice is claiming the same committed quantity twice, which is
    the failure the atomic confirmation is built to prevent. Enforced here rather than in
    the reconciliation service because a service check races with itself.
    """
    db, company_id, owner = seeded
    product = _product(db)
    core = _core_line(db, product)
    order = _project_order(db, company_id, owner)
    _project_line(db, order, product, line_no=1, core_sales_order_line_id=str(core.id))

    with pytest.raises(IntegrityError):
        _project_line(db, order, product, line_no=2, core_sales_order_line_id=str(core.id))


def test_any_number_of_lines_may_stay_unreconciled(seeded):
    """NULL is the normal state until Stage 1B reconciles the AutoCount upload.

    The partial predicate is what makes that legal at scale: a plain unique index would be
    satisfied by Postgres's NULL semantics too, but stating the predicate keeps the index
    off every unreconciled row rather than carrying them all.
    """
    db, company_id, owner = seeded
    product = _product(db)
    order = _project_order(db, company_id, owner)

    lines = [_project_line(db, order, product, line_no=n) for n in (1, 2, 3)]

    assert [line.core_sales_order_line_id for line in lines] == [None, None, None]


def test_a_reconciled_line_points_at_the_core_row_it_names(seeded):
    """The link is a real FK: the id has to be a core `sales_order_lines` row."""
    db, company_id, owner = seeded
    product = _product(db)
    core = _core_line(db, product)
    order = _project_order(db, company_id, owner)

    line = _project_line(db, order, product, line_no=1, core_sales_order_line_id=str(core.id))

    db.refresh(line)
    assert str(line.core_sales_order_line_id) == str(core.id)
    linked = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.id == line.core_sales_order_line_id)
        .one()
    )
    assert str(linked.id) == str(core.id)
