"""Start planning: adopting a core AutoCount sales order (plan sections 5.1, 6).

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md`,
AC-FP07 to AC-FP12 and AC-FP09's demand invariant.

Adoption is the whole of journey step 2. CS picks an outstanding project-class sales order
off the worklist and presses Start planning; one thin `projects.sales_orders` row is
written with one mirror line per still-owed core line, and nothing else is asked for. The
mirror holds NO facts of its own - product, quantity, required date and fulfilment location
are read off the core line at read time - so these tests assert what the mirror ADDRESSES
(`core_sales_order_line_id`, `line_no`) and that the core book is untouched.

TEST-FIRST. Written before `app/services/project_so_adoption_service.py` existed, so the
red state was `ModuleNotFoundError` on the import, and each behavioural test then failed on
the behaviour rather than on the import once the module was stubbed.

Postgres, blank scratch schema via `tests/_pg_fixture.py::blank_session`, rolled back at
teardown, except the `committed_v` invariant which needs the VIEW and therefore the real
database (`pg_session`, also rolled back). Every FK target is seeded here with a `ZZT-ADOPT`
marker; nothing is borrowed from an existing row, because CI's database is empty.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.base import company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_ADOPTED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services.error_handler import AppException
from app.services.project_so_adoption_service import ProjectSOAdoptionService

from ._pg_fixture import blank_session, pg_session

MARKER = "ZZT-ADOPT"

D1 = date(2027, 3, 1)
D2 = date(2027, 4, 1)
D3 = date(2027, 5, 1)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(sa.text("select id from companies where code = 'SRT'")).scalar()


def _product(db, *, code: str | None = None) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"{MARKER}-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code or f"{MARKER}-{_uid()[:8]}",
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, company_id: str) -> Warehouse:
    row = Warehouse(
        id=_uid(),
        warehouse_code=f"{MARKER}-{_uid()[:6]}",
        warehouse_name=f"{MARKER} location",
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, company_id: str, name: str) -> Customer:
    row = Customer(
        id=_uid(),
        customer_code=f"{MARKER}{_uid()[:6]}",
        customer_name=name,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _core_order(
    db,
    company_id: str,
    *,
    demand_class: str | None = "project",
    status: str = "open",
    customer: Customer | None = None,
    internal_note: str | None = None,
) -> SalesOrder:
    row = SalesOrder(
        id=_uid(),
        so_number=f"{MARKER}-SO-{_uid()[:8]}",
        status=status,
        demand_class=demand_class,
        demand_origin="scm_order_inquiry",
        source_system="scm_upload",
        order_date=date(2026, 1, 5),
        customer_id=customer.id if customer else None,
        internal_note=internal_note,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _core_line(
    db,
    order: SalesOrder,
    product: Product,
    *,
    warehouse: Warehouse | None = None,
    required_date: date | None = D1,
    qty_ordered: str = "10",
    qty_delivered: str = "0",
    qty_required: str | None = None,
    line_status: str = "open",
    purchasing_status: str = "not_reviewed",
) -> SalesOrderLine:
    row = SalesOrderLine(
        id=_uid(),
        sales_order_id=order.id,
        product_id=product.id,
        warehouse_id=warehouse.id if warehouse else None,
        qty_ordered=Decimal(qty_ordered),
        qty_delivered=Decimal(qty_delivered),
        qty_required=Decimal(qty_required) if qty_required is not None else None,
        unit_price=Decimal("12.50"),
        required_date=required_date,
        line_status=line_status,
        purchasing_status=purchasing_status,
        company_id=order.company_id,
    )
    db.add(row)
    db.flush()
    return row


def _mirror_lines(db, order_id: str) -> list[ProjectSalesOrderLine]:
    return (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == order_id)
        .order_by(ProjectSalesOrderLine.line_no.asc())
        .all()
    )


# --------------------------------------------------------------------------- #
# AC-FP07: one decision, one record                                           #
# --------------------------------------------------------------------------- #


def test_adopt_writes_one_planning_record_with_one_mirror_line_per_open_core_line():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product_a = _product(db, code=f"{MARKER}-AAA")
            product_b = _product(db, code=f"{MARKER}-BBB")
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            line_b = _core_line(
                db, core, product_b, warehouse=warehouse, required_date=D2
            )
            line_a = _core_line(
                db, core, product_a, warehouse=warehouse, required_date=D1
            )
            db.flush()

            result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)

            assert result["already_adopted"] is False
            assert result["so_number"] == core.so_number
            assert result["review_state"] == "needs_cs_review"

            order = db.query(ProjectSalesOrder).get(result["project_sales_order_id"])
            assert order is not None
            assert order.status == SO_STATUS_ADOPTED
            assert str(order.so_id) == str(core.id)
            # The AutoCount document number IS the sales-order number for an order that
            # came out of the book; nobody authored a second reference for it.
            assert order.provisional_ref == core.so_number
            assert order.autocount_doc_no == core.so_number
            # No project registration is invented (AC-FP07).
            assert order.project_id is None
            # Nobody published it, so the publish stamp stays empty.
            assert order.published_at is None

            mirror = _mirror_lines(db, order.id)
            assert [row.line_no for row in mirror] == [1, 2]
            # Deterministic order: required date first, so line 1 is the soonest.
            assert [str(row.core_sales_order_line_id) for row in mirror] == [
                str(line_a.id),
                str(line_b.id),
            ]
            assert [row.delivery_date for row in mirror] == [D1, D2]
            assert mirror[0].stock_location == warehouse.warehouse_code


def test_adopt_mirrors_only_the_lines_that_are_still_owed():
    """`is_open_demand()` verbatim: a delivered, closed or covered line is not planning."""
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            open_line = _core_line(db, core, product, warehouse=warehouse)
            _core_line(db, core, product, warehouse=warehouse, line_status="closed")
            _core_line(
                db, core, product, warehouse=warehouse, purchasing_status="covered"
            )
            _core_line(
                db,
                core,
                product,
                warehouse=warehouse,
                qty_ordered="10",
                qty_delivered="10",
            )
            db.flush()

            result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)

            mirror = _mirror_lines(db, result["project_sales_order_id"])
            assert [str(row.core_sales_order_line_id) for row in mirror] == [
                str(open_line.id)
            ]


# --------------------------------------------------------------------------- #
# AC-FP08: idempotent                                                         #
# --------------------------------------------------------------------------- #


def test_adopting_twice_answers_with_the_record_that_exists():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse)
            db.flush()

            service = ProjectSOAdoptionService(db)
            first = service.adopt(core.id, actor_user_id=None)
            second = service.adopt(core.id, actor_user_id=None)

            assert second["project_sales_order_id"] == first["project_sales_order_id"]
            assert second["already_adopted"] is True
            assert (
                db.query(ProjectSalesOrder)
                .filter(ProjectSalesOrder.so_id == core.id)
                .count()
                == 1
            )
            assert len(_mirror_lines(db, first["project_sales_order_id"])) == 1


# --------------------------------------------------------------------------- #
# AC-FP10: one planning record per core sales order, refused by the index     #
# --------------------------------------------------------------------------- #


def test_a_second_planning_record_for_one_core_order_is_a_named_refusal():
    """The partial unique index is the guarantee; the service turns it into a sentence.

    An IntegrityError reaching the client is a 500 that names a constraint, which tells CS
    nothing about what to do.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse)
            db.flush()

            # A record already holds this core order, written around the service so the
            # service's own idempotent lookup cannot be what answers.
            db.add(
                ProjectSalesOrder(
                    id=_uid(),
                    company_id=company_id,
                    project_id=None,
                    so_id=core.id,
                    provisional_ref=f"{MARKER}-HELD-{_uid()[:6]}",
                    status=SO_STATUS_ADOPTED,
                )
            )
            db.flush()

            service = ProjectSOAdoptionService(db)
            with pytest.raises(AppException) as excinfo:
                # Forcing the write past the idempotent lookup is what proves the index
                # is the backstop rather than the error path.
                service._insert_record(core)

            assert excinfo.value.status_code == 409
            assert core.so_number in str(excinfo.value.detail["message"])
            assert "uq_projects_so_core_order" not in str(excinfo.value.detail["message"])


# --------------------------------------------------------------------------- #
# AC-FP11: never across a company                                             #
# --------------------------------------------------------------------------- #


def test_adopting_a_sales_order_of_another_company_is_a_404_and_writes_nothing():
    with blank_session() as db:
        company_id = _sorento(db)
        other_company_id = _uid()
        db.add(
            Company(id=other_company_id, name=f"{MARKER} other", code=f"ZZT{_uid()[:6]}")
        )
        db.flush()

        with company_scope(db, frozenset({other_company_id})):
            product = _product(db)
            warehouse = _warehouse(db, other_company_id)
            foreign = _core_order(db, other_company_id)
            _core_line(db, foreign, product, warehouse=warehouse)
            db.flush()

        with company_scope(db, frozenset({company_id})):
            with pytest.raises(AppException) as excinfo:
                ProjectSOAdoptionService(db).adopt(foreign.id, actor_user_id=None)
            assert excinfo.value.status_code == 404
            assert str(foreign.id) not in str(excinfo.value.detail["message"])

        assert (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.so_id == foreign.id)
            .count()
            == 0
        )


# --------------------------------------------------------------------------- #
# What adoption refuses, and why                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"demand_class": "retail"}, "sales_order_not_project_class"),
        ({"status": "closed"}, "sales_order_not_open"),
    ],
)
def test_adoption_refuses_an_order_that_is_not_planning_work(kwargs, code):
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id, **kwargs)
            _core_line(db, core, product, warehouse=warehouse)
            db.flush()

            with pytest.raises(AppException) as excinfo:
                ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
            assert excinfo.value.status_code == 409
            assert excinfo.value.detail["code"] == code


def test_adoption_refuses_an_order_with_nothing_still_owed():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(
                db,
                core,
                product,
                warehouse=warehouse,
                qty_ordered="10",
                qty_delivered="10",
            )
            db.flush()

            with pytest.raises(AppException) as excinfo:
                ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
            assert excinfo.value.status_code == 409
            assert excinfo.value.detail["code"] == "sales_order_nothing_outstanding"


# --------------------------------------------------------------------------- #
# AC-FP09: adoption changes no demand                                         #
# --------------------------------------------------------------------------- #


def test_adoption_writes_no_order_inquiry_row():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse)
            db.flush()

            result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)

            assert (
                db.query(OrderInquiryRow)
                .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
                .filter(
                    OrderInquiry.project_sales_order_id
                    == result["project_sales_order_id"]
                )
                .count()
                == 0
            )
            assert (
                db.query(OrderInquiry)
                .filter(
                    OrderInquiry.project_sales_order_id
                    == result["project_sales_order_id"]
                )
                .count()
                == 0
            )


def test_adoption_leaves_committed_v_byte_identical_for_that_order():
    """AC-FP09 / AC-FP24: adopting is not a decision, so it moves no demand anywhere.

    Runs against the real database because `scm.committed_v` is a VIEW, and views are
    installed by migrations rather than by `Base.metadata.create_all`. Scoped to a product
    this test seeds, so nothing it asserts depends on a row it did not write.

    A RETAIL order is seeded at the same product and location beside the project one, and
    it is what makes this test say anything. Only a project-class order can be adopted
    (`_assert_plannable`), and since P3 a project-class order contributes nothing to the
    view from the book - so with the project order alone the snapshot would be empty
    before and empty after, and "byte identical" would be a claim about nothing. The
    neighbour is a real commitment at the very row adoption could disturb.
    """
    with pg_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse, qty_ordered="7")
            neighbour = _core_order(db, company_id, demand_class="retail")
            _core_line(db, neighbour, product, warehouse=warehouse, qty_ordered="3")
            db.flush()

            def _snapshot():
                return db.execute(
                    sa.text(
                        "select product_id, warehouse_id, committed, project_committed, "
                        "retail_committed, unclassified_committed, "
                        "project_confirmed_committed "
                        "from scm.committed_v where product_id = :p order by warehouse_id"
                    ),
                    {"p": product.id},
                ).fetchall()

            before = _snapshot()
            assert before, "the neighbouring retail line must be counted before adoption"

            ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
            db.flush()

            assert _snapshot() == before


def test_adoption_leaves_the_plan_demand_predicate_selecting_the_same_orders():
    """`is_plan_demand_order()` is the other demand reader AC-FP09 names.

    Which orders it selects is a fact about demand CLASS since P3 and about nothing else:
    the book speaks for retail, the adopted project order is not in it either side of the
    adoption, and the retail order beside it is in it both times. Asserted over the pair
    rather than over the adopted order alone, so "the same orders" is a set that has
    something in it.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            from app.services.scm.demand import is_plan_demand_order

            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse)
            neighbour = _core_order(db, company_id, demand_class="retail")
            _core_line(db, neighbour, product, warehouse=warehouse)
            db.flush()

            def _selected():
                return {
                    str(row[0])
                    for row in db.query(SalesOrder.id)
                    .filter(
                        SalesOrder.id.in_([core.id, neighbour.id]),
                        is_plan_demand_order(),
                    )
                    .all()
                }

            before = _selected()
            assert before == {str(neighbour.id)}

            ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
            db.flush()

            assert _selected() == before


# --------------------------------------------------------------------------- #
# AC-FP12: line numbers are stable                                            #
# --------------------------------------------------------------------------- #


def test_a_later_mirrored_line_takes_the_next_number_and_moves_nobody():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            first = _core_line(db, core, product, warehouse=warehouse, required_date=D2)
            db.flush()

            service = ProjectSOAdoptionService(db)
            result = service.adopt(core.id, actor_user_id=None)
            order = db.query(ProjectSalesOrder).get(result["project_sales_order_id"])

            # A later upload adds a line that is due EARLIER than the one already
            # mirrored: it must still take the next number, not push the first one down.
            later = _core_line(db, core, product, warehouse=warehouse, required_date=D1)
            db.flush()
            service.mirror_missing_lines(order)
            db.flush()

            mirror = _mirror_lines(db, order.id)
            assert [row.line_no for row in mirror] == [1, 2]
            assert [str(row.core_sales_order_line_id) for row in mirror] == [
                str(first.id),
                str(later.id),
            ]
