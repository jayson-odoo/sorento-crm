"""AC-1..AC-5 (`PLAN-oi-worklist-split-customer-project.md`,
`oi-worklist-split-customer-project-acceptance-criteria.md`): red tests written before
the coder, against the contract only.

Reuses `tests/test_order_inquiry_worklist.py`'s harness wholesale (`api` fixture, `_seed`
and its helpers) rather than rebuilding it: `api`'s own seed already carries one project
row (a customer-less authored order, project `ZZT Tuju Residence`) and two customer-only
rows (an adopted core order for `ZZT Optad Sdn Bhd`, no project) - exactly the shape
needed to prove `customer_name` and `project_title` are independent columns rather than
one string. `pre_order_api` below adds the one shape that harness does not carry: a
pre-order row, for AC-3.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models.project_so import (
    SO_STATUS_DRAFT,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services import project_seed_service
from tests._pg_fixture import blank_session

from ..test_order_inquiry_worklist import (
    LIST,
    MARKER,
    READ_ONLY,
    _client,
    _inquiry_for,
    _product,
    _restore,
    _row,
    _sorento,
    _uid,
    _user,
    api,
)

__all__ = ["api"]  # re-exported fixture; keeps linters from calling it unused


@pytest.fixture()
def pre_order_api():
    """One project, one pre-order `ProjectSalesOrder`, one row - the shape `api`'s own
    seed does not carry (nothing there is a pre-order)."""
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Rina")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=user_id,
            developer_party_id=None,
            title=f"{MARKER} Bandar Puteri",
        )
        pre_order = ProjectSalesOrder(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            area_group="TOWER",
            provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
            status=SO_STATUS_DRAFT,
            grouping_origin="area",
            is_pre_order=True,
            published_at=datetime(2025, 9, 1, 9, 0),
        )
        db.add(pre_order)
        db.flush()
        product = _product(db, f"ZZT-PREORD-{_uid()[:6]}", f"{MARKER} Pre-order basin")
        line = ProjectSalesOrderLine(
            id=_uid(),
            company_id=company_id,
            project_sales_order_id=pre_order.id,
            line_no=1,
            product_id=product.id,
            description=f"{MARKER} pre-order line",
            qty=Decimal("20"),
            uom="UNIT",
            unit_price=Decimal("10.00"),
            amount=Decimal("200.00"),
            delivery_date=date(2026, 4, 1),
        )
        db.add(line)
        db.flush()
        inquiry = _inquiry_for(db, company_id, pre_order)
        row = _row(
            db,
            company_id,
            inquiry,
            so_line_id=line.id,
            item_code=product.product_code,
            qty="20",
            delivery_date=date(2026, 4, 1),
        )
        db.commit()
        client, originals = _client(db, user_id, READ_ONLY)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, {"project": project, "row": row}
        finally:
            _restore(originals)


# ----------------------------------------------------- AC-1: two separate fields


def test_the_row_carries_customer_name_and_project_title_as_separate_fields(api):
    client, _db, _company_id, seeded = api

    body = client.get(LIST).json()
    by_id = {row["id"]: row for row in body["data"]}

    authored = by_id[seeded["authored_row"].id]
    adopted = by_id[seeded["adopted_row"].id]

    # The authored (project) row: a project, no customer.
    assert authored["project_title"] == f"{MARKER} Tuju Residence"
    assert authored["customer_name"] is None

    # The adopted (core order) row: a customer, no project.
    assert adopted["customer_name"] == seeded["customer"].customer_name
    assert adopted["project_title"] is None

    # `project_customer` stays on the row unchanged (AC-4: export + search).
    assert authored["project_customer"] == f"{MARKER} Tuju Residence"
    assert adopted["project_customer"] == seeded["customer"].customer_name


def test_the_worklist_row_schema_declares_customer_name_and_project_title():
    """`response_model` silently drops an undeclared field - a bare dict assertion above
    would pass even if the wire never carried it."""
    from app.schemas.project_order_inquiry import OrderInquiryWorklistRow

    fields = OrderInquiryWorklistRow.model_fields
    assert "customer_name" in fields
    assert "project_title" in fields


# --------------------------------------------------------- AC-2: each sorts on its own


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_customer_name_places_the_project_only_row_last(api, direction):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"sort": "customer_name", "dir": direction}).json()

    assert body["data"][-1]["id"] == seeded["authored_row"].id
    leading = [row["customer_name"] for row in body["data"][:-1]]
    assert all(value == seeded["customer"].customer_name for value in leading)


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_project_title_places_the_customer_only_rows_last(api, direction):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"sort": "project_title", "dir": direction}).json()

    assert body["data"][0]["id"] == seeded["authored_row"].id
    trailing = [row["project_title"] for row in body["data"][1:]]
    assert all(value is None for value in trailing)


def test_the_route_and_the_service_still_agree_on_the_sortable_set():
    from typing import get_args

    from app.api.v1.projects.order_inquiries import WorklistSort
    from app.services.order_inquiry_worklist_service import SORTABLE_FIELDS

    assert "customer_name" in set(get_args(WorklistSort))
    assert "project_title" in set(get_args(WorklistSort))
    assert set(get_args(WorklistSort)) == set(SORTABLE_FIELDS)


# ----------------------------------------------------- AC-3: the pre-order note


def test_a_pre_order_rows_note_moves_onto_the_project_cell(pre_order_api):
    client, _db, _company_id, seeded = pre_order_api

    body = client.get(LIST).json()
    row = next(r for r in body["data"] if r["id"] == seeded["row"].id)

    expected = f"{seeded['project'].title} / PRE-ORDER"
    assert row["project_title"] == expected
    # The combined column (export + search, AC-4) still carries the same note.
    assert row["project_customer"] == expected
    assert row["customer_name"] is None
