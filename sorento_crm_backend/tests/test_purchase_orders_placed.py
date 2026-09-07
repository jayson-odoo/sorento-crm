"""A5 - PO placed (AC-907, AC-909).

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
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.purchase_order_service import (
    PO_GROUP_BY_AXES,
    group_rows,
    purchase_orders_placed_rows,
    purchase_orders_placed_summary,
)

from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/procurement/purchase-orders"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _supplier(db, *, name="Acme Supplies"):
    row = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("SUP")[:50],
        supplier_name=name,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _po_line(
    db,
    *,
    supplier_id=None,
    product_id,
    ordered,
    received,
    status="open",
    line_expected=None,
    header_expected=None,
    po_number=None,
):
    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=po_number or unique_code("PO"),
        supplier_id=supplier_id,
        expected_date=header_expected,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=str(uuid.uuid4()),
            purchase_order_id=po.id,
            product_id=product_id,
            qty_ordered=ordered,
            qty_received=received,
            line_status=status,
            expected_date=line_expected,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return po


# --------------------------------------------------------------------- service


def test_placed_rows_only_open_positive_delta(db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=10, received=3,
             line_expected=date(2026, 6, 1))
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=5, received=5)  # fully received
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=8, received=0, status="closed")
    db.commit()

    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["outstanding_qty"] == 7
    assert rows[0]["supplier"] == "Acme Supplies"
    assert rows[0]["expected_date"] == "2026-06-01"


def test_placed_rows_never_nets_against_incoming():
    """AC-907: PO and SPO are never netted - this function reads ONLY
    purchase_order_lines, so an incoming SPO receipt (a different table)
    cannot reduce outstanding_qty. Documented by construction: the ORM class
    `SPOAllocation` is never imported into purchase_order_service.py (the
    module's own docstring names the TABLE in prose, which is why this checks
    the class, not the string)."""
    import inspect

    from app.services import purchase_order_service

    src = inspect.getsource(purchase_order_service)
    assert "SPOAllocation" not in src


def test_placed_rows_uses_header_expected_date_when_line_has_none(db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=5, received=0,
             header_expected=date(2026, 7, 1))
    db.commit()

    rows = purchase_orders_placed_rows(db, product_ids=[prod.id])
    assert rows[0]["expected_date"] == "2026-07-01"


def test_placed_summary_scoped_by_product(db):
    sup = _supplier(db)
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="P2")
    _po_line(db, supplier_id=sup.id, product_id=p1.id, ordered=10, received=4)  # +6
    _po_line(db, supplier_id=sup.id, product_id=p2.id, ordered=5, received=0)  # +5, other product
    db.commit()

    summary = purchase_orders_placed_summary(db, product_ids=[p1.id])
    assert summary == {"po_placed_qty": 6, "po_placed_count": 1}


def test_group_rows_by_supplier():
    rows = [{"supplier": "A"}, {"supplier": "A"}, {"supplier": "B"}]
    groups = group_rows(rows, group_by="supplier")
    assert {g["key"] for g in groups} == {"A", "B"}


# --------------------------------------------------------------------- route


@pytest.fixture
def client(db, monkeypatch):
    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-po-placed@test.com"}
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


def test_route_lists_placed_lines(client, db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=10, received=3)
    db.commit()

    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"][0]["outstanding_qty"] == 7
    assert body["data"][0]["supplier"] == "Acme Supplies"


def test_route_group_by_unknown_axis_422(client, db):
    resp = client.get(f"{BASE}/placed", params={"group_by": "not-a-real-axis"})
    assert resp.status_code == 422
    body = resp.json()
    for axis in PO_GROUP_BY_AXES:
        assert axis in body["detail"]


def test_route_group_by_supplier(client, db):
    s1 = _supplier(db, name="Acme")
    s2 = _supplier(db, name="Beta")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _po_line(db, supplier_id=s1.id, product_id=prod.id, ordered=5, received=0)
    _po_line(db, supplier_id=s2.id, product_id=prod.id, ordered=3, received=0)
    db.commit()

    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id, "group_by": "supplier"})
    assert resp.status_code == 200, resp.text
    groups = resp.json()["groups"]
    assert {g["key"] for g in groups} == {"Acme", "Beta"}


def test_route_include_summary(client, db):
    sup = _supplier(db)
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _po_line(db, supplier_id=sup.id, product_id=prod.id, ordered=10, received=4)
    db.commit()

    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id, "include_summary": "true"})
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary["po_placed_qty"] == 6
    assert summary["po_placed_count"] == 1
