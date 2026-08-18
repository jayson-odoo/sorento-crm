"""The fulfilment-planning worklist, as a UNION of two arms (plan sections 5.2, 6).

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md`,
AC-FP01 to AC-FP06.

One list, two kinds of subject, EXACTLY ONE ROW EACH:

* arm 1 - an outstanding project-class CORE sales order, whether or not anybody has planned
  it. It appears without a row being written for it, which is the whole point: the 605
  orders in the book are work that needs planning today and nothing had to be published to
  make them visible.
* arm 2 - a planning record this system authored that no arm-1 row already carries. Stage
  1B's Awaiting reconciliation, unchanged.

"Outstanding" is `app.services.scm.demand.is_open_demand()` VERBATIM plus
`sales_orders.status = 'open'` plus `demand_class = 'project'`, so this screen and the SCM
sales-order book cannot disagree about which orders are still owed.

TEST-FIRST. Written against `ProjectSOReconciliationService.list_fulfilment_planning`
before it grew arm 1, so the red state was every arm-1 assertion failing on an empty list
(`0 rows`) while the arm-2 assertions passed - the union being absent, not the module.

Postgres, blank scratch schema via `tests/_pg_fixture.py::blank_session`, rolled back at
teardown. Seeding helpers come from `tests/test_project_so_adoption.py` rather than being
copied, per this suite's established idiom; every row carries a marker and nothing is
borrowed from an existing one.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.project_so import ProjectSalesOrder, SO_STATUS_PUBLISHED
from app.services import project_seed_service
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.project_so_reconciliation_service import ProjectSOReconciliationService

from ._pg_fixture import blank_session
from .test_project_so_adoption import (
    MARKER,
    _core_line,
    _core_order,
    _customer,
    _product,
    _sorento,
    _uid,
    _warehouse,
)

D_EARLY = date(2026, 1, 5)
D_MID = date(2026, 6, 9)
D_LATE = date(2027, 2, 2)


def _user(db) -> str:
    from app.models.user import User

    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} owner"))
    db.flush()
    return user_id


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} project {_uid()[:6]}",
    )


def _authored_order(db, project, *, so_id=None, status=SO_STATUS_PUBLISHED):
    row = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        provisional_ref=f"{MARKER}-PSO-{_uid()[:8]}",
        so_id=so_id,
        status=status,
        area_group="TOWER",
    )
    db.add(row)
    db.flush()
    return row


def _authored_line(db, order, product, *, line_no=1, qty="4", delivery_date=D_MID):
    from app.models.project_so import ProjectSalesOrderLine

    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        line_no=line_no,
        product_id=product.id,
        qty=Decimal(qty),
        unit_price=Decimal("1"),
        amount=Decimal(qty),
        delivery_date=delivery_date,
    )
    db.add(row)
    db.flush()
    return row


def _list(db, **kwargs):
    return ProjectSOReconciliationService(db).list_fulfilment_planning(**kwargs)


# --------------------------------------------------------------------------- #
# AC-FP01: the book appears without anybody publishing anything               #
# --------------------------------------------------------------------------- #


def test_an_outstanding_project_sales_order_appears_as_a_not_started_row():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            customer = _customer(db, company_id, f"{MARKER} OIB CONSTRUCTION")
            core = _core_order(
                db,
                company_id,
                customer=customer,
                internal_note="Order Inquiry project: OIB / MYRA DAHLIA",
            )
            _core_line(
                db, core, product, warehouse=warehouse, required_date=D_MID, qty_ordered="12"
            )
            _core_line(
                db, core, product, warehouse=warehouse, required_date=D_EARLY, qty_ordered="30"
            )
            db.flush()

            rows = _list(db)["data"]
            row = next(r for r in rows if r["so_number"] == core.so_number)

            assert row["row_kind"] == "sales_order"
            assert row["review_state"] == "not_started"
            # Nothing exists to carry these, so the row states their absence rather than
            # inventing a planning record's fields for it.
            assert row["id"] is None
            assert row["provisional_ref"] is None
            assert row["status"] is None
            assert row["origin"] is None
            assert row["project_id"] is None
            assert str(row["sales_order_id"]) == str(core.id)
            assert row["customer_name"] == f"{MARKER} OIB CONSTRUCTION"
            # The project the Order Inquiry sheet named, without its machine prefix.
            assert row["project_label"] == "OIB / MYRA DAHLIA"
            assert row["line_count"] == 2
            assert row["earliest_required_date"] == D_EARLY
            assert Decimal(str(row["outstanding_qty"])) == Decimal("42")


def test_a_project_order_with_nothing_still_owed_never_appears():
    """AC-FP02: `is_open_demand()` verbatim, over the whole order."""
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)

            delivered = _core_order(db, company_id)
            _core_line(
                db,
                delivered,
                product,
                warehouse=warehouse,
                qty_ordered="10",
                qty_delivered="10",
            )
            covered = _core_order(db, company_id)
            _core_line(
                db, covered, product, warehouse=warehouse, purchasing_status="covered"
            )
            closed_lines = _core_order(db, company_id)
            _core_line(db, closed_lines, product, warehouse=warehouse, line_status="closed")
            retired = _core_order(db, company_id, status="closed")
            _core_line(db, retired, product, warehouse=warehouse)
            retail = _core_order(db, company_id, demand_class="retail")
            _core_line(db, retail, product, warehouse=warehouse)
            db.flush()

            numbers = {row["so_number"] for row in _list(db)["data"]}
            for absent in (delivered, covered, closed_lines, retired, retail):
                assert absent.so_number not in numbers


# --------------------------------------------------------------------------- #
# AC-FP03: the authored arm, and exactly once                                 #
# --------------------------------------------------------------------------- #


def test_an_authored_order_with_no_core_sales_order_still_appears_once():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        with company_scope(db, frozenset({company_id})):
            owner = _user(db)
            project = _project(db, company_id, owner)
            product = _product(db)
            authored = _authored_order(db, project)
            _authored_line(db, authored, product)
            db.flush()

            rows = [r for r in _list(db)["data"] if r["id"] == authored.id]
            assert len(rows) == 1
            assert rows[0]["row_kind"] == "planning_record"
            assert rows[0]["review_state"] == "awaiting_reconciliation"
            assert rows[0]["origin"] == "authored"
            assert rows[0]["sales_order_id"] is None


def test_an_adopted_order_is_one_row_not_two():
    """The arms are disjoint: the planned core order stays an arm-1 row and gains an id."""
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse, required_date=D_MID)
            db.flush()

            result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
            db.flush()

            rows = [r for r in _list(db)["data"] if r["so_number"] == core.so_number]
            assert len(rows) == 1
            row = rows[0]
            assert row["row_kind"] == "sales_order"
            assert row["id"] == result["project_sales_order_id"]
            assert row["origin"] == "adopted"
            assert row["status"] == "adopted"
            assert row["review_state"] == "needs_cs_review"
            assert row["provisional_ref"] == core.so_number
            assert row["lines_linked"] == row["line_count"] == 1
            assert row["exception_count"] == 0


def test_an_authored_order_linked_to_a_core_order_appears_once_on_the_core_arm():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        with company_scope(db, frozenset({company_id})):
            owner = _user(db)
            project = _project(db, company_id, owner)
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse, required_date=D_MID)
            authored = _authored_order(db, project, so_id=core.id)
            _authored_line(db, authored, product)
            db.flush()

            rows = _list(db)["data"]
            mine = [
                r
                for r in rows
                if r["so_number"] == core.so_number or r["id"] == authored.id
            ]
            assert len(mine) == 1
            assert mine[0]["row_kind"] == "sales_order"
            assert mine[0]["id"] == authored.id
            assert mine[0]["origin"] == "authored"
            assert mine[0]["project_id"] == project.id


# --------------------------------------------------------------------------- #
# AC-FP04: ordering is total and stable across pages                          #
# --------------------------------------------------------------------------- #


def test_rows_are_ordered_by_earliest_outstanding_required_date_nulls_last():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)

            late = _core_order(db, company_id)
            _core_line(db, late, product, warehouse=warehouse, required_date=D_LATE)
            early = _core_order(db, company_id)
            _core_line(db, early, product, warehouse=warehouse, required_date=D_EARLY)
            undated = _core_order(db, company_id)
            _core_line(db, undated, product, warehouse=warehouse, required_date=None)
            mid = _core_order(db, company_id)
            _core_line(db, mid, product, warehouse=warehouse, required_date=D_MID)
            db.flush()

            numbers = [row["so_number"] for row in _list(db)["data"]]
            assert numbers == [
                early.so_number,
                mid.so_number,
                late.so_number,
                undated.so_number,
            ]


def test_rows_sharing_a_date_are_tie_broken_on_the_sales_order_number():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            second = _core_order(db, company_id)
            second.so_number = f"{MARKER}-SO-BBB"
            first = _core_order(db, company_id)
            first.so_number = f"{MARKER}-SO-AAA"
            for order in (second, first):
                _core_line(db, order, product, warehouse=warehouse, required_date=D_MID)
            db.flush()

            numbers = [row["so_number"] for row in _list(db)["data"]]
            assert numbers == [first.so_number, second.so_number]


def test_paging_the_worklist_puts_no_row_on_two_pages_or_on_neither():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        with company_scope(db, frozenset({company_id})):
            owner = _user(db)
            project = _project(db, company_id, owner)
            product = _product(db)
            warehouse = _warehouse(db, company_id)

            # Five core orders all due on the SAME day, so the tie-break is the only thing
            # holding the order together, plus one authored order on the other arm.
            for _ in range(5):
                core = _core_order(db, company_id)
                _core_line(db, core, product, warehouse=warehouse, required_date=D_MID)
            authored = _authored_order(db, project)
            _authored_line(db, authored, product, delivery_date=D_MID)
            db.flush()

            whole = _list(db, limit=50)
            assert whole["pagination"]["total"] == 6

            paged = []
            for page in (1, 2, 3):
                body = _list(db, page=page, limit=2)
                assert body["pagination"]["total"] == 6
                paged.extend(
                    row["id"] or row["sales_order_id"] for row in body["data"]
                )

            assert len(paged) == 6
            assert len(set(paged)) == 6
            assert paged == [row["id"] or row["sales_order_id"] for row in whole["data"]]


# --------------------------------------------------------------------------- #
# AC-FP05: the state filter covers the new value                              #
# --------------------------------------------------------------------------- #


def test_the_not_started_filter_lists_only_unplanned_core_orders():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        with company_scope(db, frozenset({company_id})):
            owner = _user(db)
            project = _project(db, company_id, owner)
            product = _product(db)
            warehouse = _warehouse(db, company_id)

            unplanned = _core_order(db, company_id)
            _core_line(db, unplanned, product, warehouse=warehouse, required_date=D_MID)
            planned = _core_order(db, company_id)
            _core_line(db, planned, product, warehouse=warehouse, required_date=D_MID)
            authored = _authored_order(db, project)
            _authored_line(db, authored, product)
            db.flush()
            ProjectSOAdoptionService(db).adopt(planned.id, actor_user_id=None)
            db.flush()

            body = _list(db, review_state="not_started")
            numbers = {row["so_number"] for row in body["data"]}
            assert numbers == {unplanned.so_number}
            assert body["pagination"]["total"] == 1
            assert all(row["review_state"] == "not_started" for row in body["data"])


def test_the_filtered_total_is_the_filtered_count_not_the_page_size():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            for _ in range(3):
                core = _core_order(db, company_id)
                _core_line(db, core, product, warehouse=warehouse, required_date=D_MID)
            db.flush()

            body = _list(db, review_state="not_started", page=1, limit=1)
            assert len(body["data"]) == 1
            assert body["pagination"]["total"] == 3


# --------------------------------------------------------------------------- #
# AC-FP06: company scoped on BOTH arms                                        #
# --------------------------------------------------------------------------- #


def test_neither_arm_leaks_another_companys_work():
    with blank_session() as db:
        company_id = _sorento(db)
        other_company_id = _uid()
        db.add(
            Company(id=other_company_id, name=f"{MARKER} other", code=f"ZZT{_uid()[:6]}")
        )
        db.flush()
        project_seed_service.run(db, company_id=company_id)
        project_seed_service.run(db, company_id=other_company_id)

        with company_scope(db, frozenset({other_company_id})):
            owner = _user(db)
            their_project = _project(db, other_company_id, owner)
            their_product = _product(db)
            their_warehouse = _warehouse(db, other_company_id)
            their_core = _core_order(db, other_company_id)
            _core_line(
                db,
                their_core,
                their_product,
                warehouse=their_warehouse,
                required_date=D_MID,
            )
            their_authored = _authored_order(db, their_project)
            _authored_line(db, their_authored, their_product)
            db.flush()

        with company_scope(db, frozenset({company_id})):
            owner = _user(db)
            our_project = _project(db, company_id, owner)
            our_product = _product(db)
            our_warehouse = _warehouse(db, company_id)
            our_core = _core_order(db, company_id)
            _core_line(
                db, our_core, our_product, warehouse=our_warehouse, required_date=D_MID
            )
            our_authored = _authored_order(db, our_project)
            _authored_line(db, our_authored, our_product)
            db.flush()

            body = _list(db, limit=100)
            numbers = {row["so_number"] for row in body["data"]}
            ids = {row["id"] for row in body["data"]}
            assert our_core.so_number in numbers
            assert our_authored.id in ids
            assert their_core.so_number not in numbers
            assert their_authored.id not in ids
            # The count has to agree with the rows, or a paged screen reports work the
            # caller may not see.
            assert body["pagination"]["total"] == len(body["data"])


# --------------------------------------------------------------------------- #
# search                                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("needle_of", ["so_number", "customer", "project_string"])
def test_the_search_box_matches_what_an_arm_one_row_prints(needle_of):
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            customer = _customer(db, company_id, f"{MARKER} PEMBINAAN TEGUH MAJU")
            core = _core_order(
                db,
                company_id,
                customer=customer,
                internal_note="Order Inquiry project: PASAR BESAR CHERAS",
            )
            _core_line(db, core, product, warehouse=warehouse, required_date=D_MID)
            other = _core_order(db, company_id)
            _core_line(db, other, product, warehouse=warehouse, required_date=D_MID)
            db.flush()

            needle = {
                "so_number": core.so_number,
                "customer": "TEGUH MAJU",
                "project_string": "PASAR BESAR",
            }[needle_of]

            numbers = {row["so_number"] for row in _list(db, query=needle)["data"]}
            assert numbers == {core.so_number}
