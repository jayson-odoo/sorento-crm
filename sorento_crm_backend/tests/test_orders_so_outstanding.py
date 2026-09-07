"""A3 - SO outstanding bucket, group_by, three-line summary
(AC-905, AC-905b, AC-906, AC-909).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.order_service import (
    ORDER_GROUP_BY_AXES,
    group_rows,
    so_outstanding_rows,
    so_outstanding_summary,
)

from tests._mc_lookup_seed import customer, order, order_line, product, warehouse
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/order-management/orders"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _so_line(db, *, customer_id, product_id, ordered, delivered, status="open", order_date=None, requested=None, so_number=None):
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=so_number or unique_code("SO"),
        customer_id=customer_id,
        order_date=order_date,
        requested_delivery_date=requested,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=product_id,
            qty_ordered=ordered,
            qty_delivered=delivered,
            line_status=status,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return so


# --------------------------------------------------------------------- service


def test_so_outstanding_rows_only_open_positive_delta(db):
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC SDN BHD")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=10, delivered=3,
             order_date=date(2026, 6, 1), requested=date(2026, 6, 15))
    _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=5, delivered=5)  # fully delivered
    _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=8, delivered=0, status="closed")
    db.commit()

    rows = so_outstanding_rows(db, customer_ids=[cust.id])
    assert len(rows) == 1
    row = rows[0]
    assert row["outstanding_qty"] == 7
    assert row["product_code"] == "SRTWC8517"
    assert row["customer"] == "ABC SDN BHD"
    assert row["order_date"] == "2026-06-01"
    assert row["requested_delivery_date"] == "2026-06-15"


def test_so_outstanding_summary_scoped_by_customer_and_product(db):
    cust1 = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC")
    cust2 = customer(db, company_id=DEFAULT_COMPANY_ID, name="XYZ")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    other_prod = product(db, company_id=DEFAULT_COMPANY_ID, code="OTHER")
    _so_line(db, customer_id=cust1.id, product_id=prod.id, ordered=10, delivered=3)  # +7
    _so_line(db, customer_id=cust2.id, product_id=prod.id, ordered=4, delivered=0)  # +4, other customer
    _so_line(db, customer_id=cust1.id, product_id=other_prod.id, ordered=6, delivered=0)  # +6, other product
    db.commit()

    summary = so_outstanding_summary(db, customer_ids=[cust1.id], product_ids=[prod.id])
    assert summary == {"so_outstanding_qty": 7, "so_outstanding_count": 1}


def test_group_rows_by_product_and_date():
    rows = [
        {"product_code": "A", "order_date": "2026-06-01"},
        {"product_code": "A", "order_date": "2026-06-02"},
        {"product_code": "B", "order_date": "2026-06-01"},
    ]
    by_product = group_rows(rows, group_by="product")
    assert [g["key"] for g in by_product] == ["A", "B"]
    assert len(by_product[0]["rows"]) == 2

    by_date = group_rows(rows, group_by="date")
    assert {g["key"] for g in by_date} == {"2026-06-01", "2026-06-02"}


def test_group_rows_missing_axis_value_buckets_as_not_specified():
    rows = [{"customer": None}, {"customer": "ABC"}]
    groups = group_rows(rows, group_by="customer")
    keys = {g["key"] for g in groups}
    assert keys == {"Not specified", "ABC"}


# --------------------------------------------------------------------- route


@pytest.fixture
def client(db, monkeypatch):
    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-so-outstanding@test.com"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_route_so_outstanding_bucket_lists_open_lines(client, db):
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC SDN BHD")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=10, delivered=3)
    db.commit()

    resp = client.get(BASE, params={"order_status": "so_outstanding", "customer_ids": cust.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["outstanding_qty"] == 7
    assert body["data"][0]["so_number"]


def test_route_so_outstanding_group_by_product(client, db):
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC")
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="P2")
    _so_line(db, customer_id=cust.id, product_id=p1.id, ordered=5, delivered=0)
    _so_line(db, customer_id=cust.id, product_id=p2.id, ordered=3, delivered=0)
    db.commit()

    resp = client.get(
        BASE,
        params={"order_status": "so_outstanding", "customer_ids": cust.id, "group_by": "product"},
    )
    assert resp.status_code == 200, resp.text
    groups = resp.json()["groups"]
    assert {g["key"] for g in groups} == {"P1", "P2"}


def test_route_group_by_unknown_axis_422(client, db):
    resp = client.get(BASE, params={"group_by": "not-a-real-axis"})
    assert resp.status_code == 422
    body = resp.json()
    for axis in ORDER_GROUP_BY_AXES:
        assert axis in body["detail"]


def test_route_do_bucket_group_by_customer(client, db):
    cust1 = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC")
    cust2 = customer(db, company_id=DEFAULT_COMPANY_ID, name="XYZ")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    o1 = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust1.id)
    o1.debtor_name = "ABC"
    o2 = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust2.id)
    o2.debtor_name = "XYZ"
    order_line(db, company_id=DEFAULT_COMPANY_ID, order_id=o1.id, product_id=prod.id, warehouse_id=wh.id)
    order_line(db, company_id=DEFAULT_COMPANY_ID, order_id=o2.id, product_id=prod.id, warehouse_id=wh.id)
    db.commit()

    resp = client.get(BASE, params={"group_by": "customer"})
    assert resp.status_code == 200, resp.text
    groups = resp.json()["groups"]
    assert {g["key"] for g in groups} == {"ABC", "XYZ"}


def test_route_include_summary_adds_so_outstanding_pipeline_leg(client, db):
    """AC-905b: `include_summary=true` on the plain DO bucket also carries the
    SO-outstanding leg of the three-line pipeline, scoped by the same filters."""
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    o1 = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust.id)
    o1.debtor_name = "ABC"
    order_line(db, company_id=DEFAULT_COMPANY_ID, order_id=o1.id, product_id=prod.id, warehouse_id=wh.id)
    _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=9, delivered=2)  # +7 outstanding
    db.commit()

    resp = client.get(
        BASE,
        params={"customer_ids": cust.id, "product_ids": prod.id, "include_summary": "true"},
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary["so_outstanding_qty"] == 7
    assert summary["so_outstanding_count"] == 1


def test_route_list_do_without_include_summary_has_no_pipeline(client, db):
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ABC")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    o1 = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust.id)
    order_line(db, company_id=DEFAULT_COMPANY_ID, order_id=o1.id, product_id=prod.id, warehouse_id=wh.id)
    db.commit()

    resp = client.get(BASE, params={"customer_ids": cust.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "summary" not in body or body.get("summary") is None
    assert "groups" not in body or body.get("groups") is None


# ----------------------------- should-fix 7: the external cap applies to this bucket too


def test_route_so_outstanding_takes_the_external_cap(client, db, monkeypatch):
    """Every DO bucket hard-caps an external/AI caller at 20 rows; the new bucket returned
    up to 500. That cap is what stops one WhatsApp turn pulling a five-hundred-row page
    through the MCP and into a message, and a new bucket is exactly where it is forgotten.
    """
    from app.api.v1.order_management import orders as orders_mod

    monkeypatch.setattr(orders_mod.app_settings, "external_api_key", "zzt-console-key")
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Cap Customer")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517-CAP")
    for _ in range(25):
        _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=5, delivered=0)
    db.commit()

    params = {"order_status": "so_outstanding", "customer_ids": cust.id, "limit": 500}
    external = client.get(BASE, params=params, headers={"X-API-Key": "zzt-console-key"})
    assert external.status_code == 200, external.text
    assert len(external.json()["data"]) == 20, "the external cap did not reach this bucket"

    # A staff caller (no API key) is unchanged: the cap is about the external surface.
    staff = client.get(BASE, params=params)
    assert staff.status_code == 200, staff.text
    assert len(staff.json()["data"]) == 25


def test_route_so_outstanding_cap_lifts_for_a_date_scoped_read(client, db, monkeypatch):
    """The same relaxation the DO buckets get: a date-narrowed question wants the whole
    window, not a truncated top-20.

    What is graded here is the CAP LIFTING, not date filtering: `so_outstanding_rows` takes
    no date window of its own today (it reads `sales_order_lines`, which the DO date
    columns do not describe), so every seeded row comes back either way. The assertion is
    that 25 come back rather than 20 - i.e. `date_scoped` reached `_external_orders_limit`
    for this bucket exactly as it does for the others."""
    from datetime import date

    from app.api.v1.order_management import orders as orders_mod

    monkeypatch.setattr(orders_mod.app_settings, "external_api_key", "zzt-console-key")
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Window Customer")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517-WINDOW")
    for _ in range(25):
        _so_line(
            db,
            customer_id=cust.id,
            product_id=prod.id,
            ordered=5,
            delivered=0,
            order_date=date(2026, 6, 10),
        )
    db.commit()

    resp = client.get(
        BASE,
        params={
            "order_status": "so_outstanding",
            "customer_ids": cust.id,
            "limit": 500,
            "order_date_from": "2026-06-01",
            "order_date_to": "2026-06-30",
        },
        headers={"X-API-Key": "zzt-console-key"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]) == 25
