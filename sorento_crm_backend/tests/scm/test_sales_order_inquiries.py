"""The sales-order list names the order inquiries raised against each order.

The business sees SOs and order inquiries, and nothing else: no plan entity, no "Planning"
column. So the link between the two has to be readable from the order itself - which
inquiry, what state it is in, who raised it and how much of it purchasing has placed - or a
buyer looking at an order has no way to tell whether anything has been done about it.

Attached in ONE query per page, the same shape `with_links` uses for the purchase-order
claims: per-row would be an N+1 across a 15,000-order list.

Postgres, the prod-copy database, everything inside a rolled-back savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.order import SalesOrder
from app.models.project_so import (
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.services.scm.sales_order_service import SalesOrderService
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTSOOI"


def _uid() -> str:
    return str(uuid.uuid4())


def _as(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db, uid


def _core_order(db) -> SalesOrder:
    order = SalesOrder(
        id=_uid(),
        so_number=f"{MARKER}-{_uid()[:8].upper()}",
        order_date=date(2026, 5, 4),
        status="open",
        source_system="scm_upload",
    )
    db.add(order)
    db.flush()
    return order


def _planned(db, core: SalesOrder) -> ProjectSalesOrder:
    """The planning record for an ADOPTED order: no project registration, just the link."""
    pso = ProjectSalesOrder(
        id=_uid(),
        company_id=core.company_id,
        project_id=None,
        so_id=core.id,
        provisional_ref=f"{MARKER}-PSO-{_uid()[:8]}",
        status="published",
    )
    db.add(pso)
    db.flush()
    return pso


def _inquiry(db, pso, *, number, raised_by=None, raised_at=None, amendment_id=None,
             rows=((INQUIRY_RAISED, 3), (INQUIRY_PLACED, 1))) -> OrderInquiry:
    inquiry = OrderInquiry(
        id=_uid(),
        company_id=pso.company_id,
        project_sales_order_id=pso.id,
        amendment_id=amendment_id,
        state=INQUIRY_RAISED,
        inquiry_no=number,
        raised_by=raised_by,
    )
    if raised_at is not None:
        inquiry.raised_at = raised_at
    db.add(inquiry)
    db.flush()
    for state, count in rows:
        for _ in range(count):
            db.add(OrderInquiryRow(
                id=_uid(),
                company_id=pso.company_id,
                order_inquiry_id=inquiry.id,
                item_code=f"{MARKER}-ITEM",
                qty=1,
                verb=IV_ORDER,
                state=state,
            ))
    db.flush()
    return inquiry


def _row_for(body, so_number):
    return next(r for r in body["data"] if r["so_number"] == so_number)


def test_the_list_names_each_inquiry_raised_on_the_order(scm_app):
    app, db, uid = _as(scm_app)
    core = _core_order(db)
    pso = _planned(db, core)
    _inquiry(db, pso, number=f"{MARKER}-OI-1", raised_by=uid,
             raised_at=datetime(2026, 6, 1, 9, 0))

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={"query": core.so_number})

    assert res.status_code == 200, res.text
    row = _row_for(res.json(), core.so_number)
    # It survives `response_model`, which silently drops anything undeclared.
    assert "order_inquiries" in row, row.keys()
    assert len(row["order_inquiries"]) == 1
    inquiry = row["order_inquiries"][0]
    assert inquiry["inquiry_no"] == f"{MARKER}-OI-1"
    assert inquiry["state"] == INQUIRY_RAISED
    assert inquiry["raised_at"]
    assert inquiry["raised_by_name"] == "SCM Test"
    assert inquiry["rows_total"] == 4
    assert inquiry["rows_placed"] == 1


def test_an_order_nobody_has_planned_carries_an_empty_list(scm_app):
    """Never null and never absent: an empty list is what lets the column render "-"
    instead of the screen having to tell an unplanned order from a broken payload."""
    app, db, _uid_ = _as(scm_app)
    core = _core_order(db)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={"query": core.so_number})

    assert res.status_code == 200, res.text
    assert _row_for(res.json(), core.so_number)["order_inquiries"] == []


def test_the_sales_order_own_read_carries_them_too(scm_app):
    """The detail page shows the same fact, so it comes off the same service rather than a
    second query that could answer differently."""
    app, db, uid = _as(scm_app)
    core = _core_order(db)
    pso = _planned(db, core)
    _inquiry(db, pso, number=f"{MARKER}-OI-9", raised_by=uid)

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/sales-orders/{core.id}")

    assert res.status_code == 200, res.text
    assert [i["inquiry_no"] for i in res.json()["order_inquiries"]] == [f"{MARKER}-OI-9"]


def test_the_sales_order_inquiry_comes_before_its_amendments(scm_app):
    """The order's own inquiry first, then whatever amended it, oldest first: that is the
    sequence purchasing was told things in, and any other order makes the list read as
    arbitrary."""
    app, db, uid = _as(scm_app)
    core = _core_order(db)
    pso = _planned(db, core)
    from app.models.project_so import SOAmendment

    amendment = SOAmendment(
        id=_uid(), company_id=pso.company_id, project_sales_order_id=pso.id,
        status="published")
    db.add(amendment)
    db.flush()
    amendment_id = amendment.id
    # The amendment is raised FIRST in wall-clock terms, so an ordering that only sorted by
    # time would put it above the order's own inquiry.
    _inquiry(db, pso, number=f"{MARKER}-OI-B", raised_by=uid, amendment_id=amendment_id,
             raised_at=datetime(2026, 6, 1, 9, 0), rows=())
    _inquiry(db, pso, number=f"{MARKER}-OI-A", raised_by=uid,
             raised_at=datetime(2026, 7, 1, 9, 0), rows=())

    service = SalesOrderService(db)
    rows = service.with_order_inquiries([service.serialize(core)])

    assert [i["inquiry_no"] for i in rows[0]["order_inquiries"]] == [
        f"{MARKER}-OI-A", f"{MARKER}-OI-B",
    ]
