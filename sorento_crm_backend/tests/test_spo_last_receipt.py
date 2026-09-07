"""A6 - SPO last receipt (AC-908, AC-911).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.procurement import InboundShipment, SPOAllocation
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.spo_last_receipt_service import last_receipt_rows

from tests._mc_lookup_seed import product, warehouse
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/procurement/spo-allocations"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _shipment(db, *, warehouse_arrival=None, actual_arrival=None):
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=unique_code("SHP")[:50],
        shipment_date=date(2026, 1, 1),
        warehouse_arrival_date=warehouse_arrival,
        actual_arrival_date=actual_arrival,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _allocation(
    db,
    *,
    product_id,
    warehouse_id=None,
    shipment_id=None,
    qty_received=10,
    status="fully_received",
    spo_number=None,
    created_at=None,
):
    row = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=spo_number or unique_code("SPO")[:50],
        product_id=product_id,
        warehouse_id=warehouse_id,
        inbound_shipment_id=shipment_id,
        allocated_quantity=qty_received,
        quantity_received=qty_received,
        receipt_status=status,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    if created_at is not None:
        db.query(SPOAllocation).filter(SPOAllocation.id == row.id).update({"created_at": created_at})
        db.flush()
    return row


# --------------------------------------------------------------------- service


def test_last_receipt_uses_warehouse_arrival_date_when_populated(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    ship = _shipment(db, warehouse_arrival=date(2026, 6, 10), actual_arrival=date(2026, 6, 5))
    _allocation(db, product_id=prod.id, shipment_id=ship.id, qty_received=20)
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-10"
    assert rows[0]["date_label"] == "Arrived"
    assert rows[0]["quantity_received"] == 20


def test_last_receipt_falls_back_to_actual_arrival_date(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    ship = _shipment(db, warehouse_arrival=None, actual_arrival=date(2026, 6, 5))
    _allocation(db, product_id=prod.id, shipment_id=ship.id)
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows[0]["date"] == "2026-06-05"
    assert rows[0]["date_label"] == "Arrived (port)"


def test_last_receipt_falls_back_to_created_at_when_no_shipment_dates(db):
    """A0 measurement: both shipment date columns are ~0% populated on received
    rows today, so this rung is the one that actually fires in practice."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    ship = _shipment(db, warehouse_arrival=None, actual_arrival=None)
    alloc = _allocation(db, product_id=prod.id, shipment_id=ship.id)
    db.commit()
    db.refresh(alloc)

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows[0]["date_label"] == "Received (recorded)"
    assert rows[0]["date"] == alloc.created_at.date().isoformat()


def test_last_receipt_excludes_pending_allocations(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _allocation(db, product_id=prod.id, status="pending")
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows == []


def test_last_receipt_top_n_returns_n_newest(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    for i, d in enumerate([date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 10)]):
        ship = _shipment(db, warehouse_arrival=d)
        _allocation(db, product_id=prod.id, shipment_id=ship.id, spo_number=f"SPO-{i}")
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id], top_n=3)
    assert len(rows) == 3
    assert [r["date"] for r in rows] == ["2026-06-10", "2026-06-05", "2026-06-01"]

    rows_default = last_receipt_rows(db, product_ids=[prod.id])
    assert len(rows_default) == 1
    assert rows_default[0]["date"] == "2026-06-10"


def test_last_receipt_names_warehouse(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="BRW")
    _allocation(db, product_id=prod.id, warehouse_id=wh.id)
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows[0]["warehouse"] == "BRW"


# AC-911's DEFAULT_UNSUPPORTED_DOMAINS assertion lives in
# tests/chatbot/test_crossdomain_ladder.py, not here - this file sits outside
# tests/chatbot/, and importing app.services.chatbot from there trips
# tests/chatbot/test_import_boundary.py's module-boundary guard.


# --------------------------------------------------------------------- route


@pytest.fixture
def client(db, monkeypatch):
    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-spo-last-receipt@test.com"}
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


def test_route_last_receipt_default_top_n_one(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    ship = _shipment(db, warehouse_arrival=date(2026, 6, 10))
    _allocation(db, product_id=prod.id, shipment_id=ship.id, qty_received=15)
    db.commit()

    resp = client.get(f"{BASE}/last-receipt", params={"product_ids": prod.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["quantity_received"] == 15


def test_route_last_receipt_top_n_three(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    for d in [date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 10), date(2026, 6, 12)]:
        ship = _shipment(db, warehouse_arrival=d)
        _allocation(db, product_id=prod.id, shipment_id=ship.id)
    db.commit()

    resp = client.get(f"{BASE}/last-receipt", params={"product_ids": prod.id, "top_n": 3})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]) == 3
