"""AC-4..AC-8 (chatbot-warehouse-entity-and-last-in): the last SPO line PER PRODUCT, GR
ignored entirely.

`documentation/plans/chatbot/PLAN-chatbot-warehouse-entity-and-last-in.md` section
"Last in"; `chatbot-warehouse-entity-and-last-in-acceptance-criteria.md` AC-4..AC-8.

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


def _shipment(db, *, warehouse_arrival=None):
    """Only used to prove AC-4: an inbound shipment's arrival date must NOT be read as
    the ordering key any more - GR is ignored entirely."""
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=unique_code("SHP")[:50],
        shipment_date=date(2026, 1, 1),
        warehouse_arrival_date=warehouse_arrival,
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
    expected_date=None,
    issue_date=None,
    quantity=10,
    qty_received=0,
    status="pending",
    spo_number=None,
    created_at=None,
):
    row = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=spo_number or unique_code("SPO")[:50],
        product_id=product_id,
        warehouse_id=warehouse_id,
        inbound_shipment_id=shipment_id,
        allocated_quantity=quantity,
        quantity_received=qty_received,
        expected_date=expected_date,
        issue_date=issue_date,
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


def test_last_spo_line_gr_ignored_entirely(db):
    """AC-4: three lines (A dated + fully received, B dated + PENDING, C undated +
    fully received with a shipment arrival date). B wins - the shipment arrival is
    never read as the key, and `receipt_status` is not filtered on."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    ship = _shipment(db, warehouse_arrival=date(2026, 8, 26))
    _allocation(
        db, product_id=prod.id, expected_date=date(2026, 2, 22), status="fully_received",
        spo_number="A",
    )
    _allocation(
        db, product_id=prod.id, expected_date=date(2026, 8, 30), status="pending",
        spo_number="B",
    )
    _allocation(
        db, product_id=prod.id, shipment_id=ship.id, status="fully_received",
        created_at=datetime(2026, 8, 21, 9, 0, 0), spo_number="C",
    )
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert len(rows) == 1
    assert rows[0]["spo_number"] == "B"
    assert rows[0]["date"] == "2026-08-30"
    assert rows[0]["date_label"] == "Expected"

    rows3 = last_receipt_rows(db, product_ids=[prod.id], top_n=3)
    assert [r["spo_number"] for r in rows3] == ["B", "C", "A"]
    assert rows3[1]["date"] == "2026-08-21"
    assert rows3[1]["date_label"] == "Recorded"
    # The shipment's warehouse_arrival_date (2026-08-26) never appears anywhere.
    assert all(r["date"] != "2026-08-26" for r in rows3)


def test_issue_date_fallback_when_expected_date_is_null(db):
    """AC-5."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _allocation(db, product_id=prod.id, expected_date=None, issue_date=date(2026, 7, 1))
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows[0]["date"] == "2026-07-01"
    assert rows[0]["date_label"] == "Issued"


def test_created_at_fallback_when_neither_date_is_set(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    alloc = _allocation(db, product_id=prod.id)
    db.commit()
    db.refresh(alloc)

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows[0]["date_label"] == "Recorded"
    assert rows[0]["date"] == alloc.created_at.date().isoformat()


def test_one_row_per_product_grouped_by_product_code(db):
    """AC-6: two products, two lines each; top_n=1 -> one row per product, newest
    first within the (implicit, single-row) group; top_n=2 -> four rows, two per
    product, newest first within each, products in `product_code` order."""
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="P2")
    _allocation(db, product_id=p1.id, expected_date=date(2026, 6, 1), spo_number="P1-OLD")
    _allocation(db, product_id=p1.id, expected_date=date(2026, 6, 10), spo_number="P1-NEW")
    _allocation(db, product_id=p2.id, expected_date=date(2026, 6, 2), spo_number="P2-OLD")
    _allocation(db, product_id=p2.id, expected_date=date(2026, 6, 12), spo_number="P2-NEW")
    db.commit()

    rows1 = last_receipt_rows(db, product_ids=[p1.id, p2.id], top_n=1)
    assert len(rows1) == 2
    assert [r["product_code"] for r in rows1] == ["P1", "P2"]
    assert [r["spo_number"] for r in rows1] == ["P1-NEW", "P2-NEW"]

    rows2 = last_receipt_rows(db, product_ids=[p1.id, p2.id], top_n=2)
    assert len(rows2) == 4
    assert [r["spo_number"] for r in rows2] == ["P1-NEW", "P1-OLD", "P2-NEW", "P2-OLD"]


def test_unscoped_call_is_a_plain_cap_not_one_row_per_product(db):
    """AC-6b: with NO `product_ids`, one-row-per-product would fan out to a row for
    every product in the table (thousands of rows; the AI assistant can call this tool
    unscoped). `top_n` is instead a plain cap over every line, newest first, any
    product."""
    p1 = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    p2 = product(db, company_id=DEFAULT_COMPANY_ID, code="P2")
    p3 = product(db, company_id=DEFAULT_COMPANY_ID, code="P3")
    _allocation(db, product_id=p1.id, expected_date=date(2026, 6, 1), spo_number="P1-LINE")
    _allocation(db, product_id=p2.id, expected_date=date(2026, 6, 20), spo_number="P2-NEWEST")
    _allocation(db, product_id=p3.id, expected_date=date(2026, 6, 15), spo_number="P3-2ND-NEWEST")
    db.commit()

    rows = last_receipt_rows(db, top_n=2)
    assert len(rows) == 2
    assert [r["spo_number"] for r in rows] == ["P2-NEWEST", "P3-2ND-NEWEST"]


def test_warehouse_filter_before_per_product_pick(db):
    """AC-7."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    brw = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="BRW")
    brw_ib = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="BRW-IB")
    _allocation(
        db, product_id=prod.id, warehouse_id=brw.id, expected_date=date(2026, 8, 20),
        spo_number="AT-BRW-NEWER",
    )
    _allocation(
        db, product_id=prod.id, warehouse_id=brw_ib.id, expected_date=date(2026, 8, 10),
        spo_number="AT-BRW-IB-OLDER",
    )
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id], warehouse_ids=[brw_ib.id])
    assert len(rows) == 1
    assert rows[0]["spo_number"] == "AT-BRW-IB-OLDER"
    assert rows[0]["warehouse"] == "BRW-IB"


def test_quantity_is_the_ordered_quantity_not_received(db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="P1")
    _allocation(db, product_id=prod.id, quantity=25, qty_received=10, status="pending")
    db.commit()

    rows = last_receipt_rows(db, product_ids=[prod.id])
    assert rows[0]["quantity"] == 25
    assert rows[0]["quantity_received"] == 10


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
    _allocation(db, product_id=prod.id, expected_date=date(2026, 6, 10), quantity=15)
    db.commit()

    resp = client.get(f"{BASE}/last-receipt", params={"product_ids": prod.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["quantity"] == 15
    assert body["empty"] is False


def test_route_last_receipt_with_warehouse_filter_and_top_n(client, db):
    """AC-8."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8517")
    brw = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="BRW")
    for d in [date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 10)]:
        _allocation(db, product_id=prod.id, warehouse_id=brw.id, expected_date=d)
    db.commit()

    resp = client.get(
        f"{BASE}/last-receipt",
        params={"product_ids": prod.id, "warehouse_ids": brw.id, "top_n": 3},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["data"]) == 3
    assert body["data"][0]["date_label"] is not None
    assert body["empty"] is False


# ------------------------------------- blocker 3: the company scope actually narrows


def test_a_mocha_scoped_read_returns_no_sorento_receipts(db):
    """AC-F7 for the new tool. `spo_allocations` is `CompanyScopedMixin`, so the session
    scope narrows the read - what was missing was the MCP forwarding `contact_id` /
    `space_id` at all (the ToolSpec did not declare them, so FastMCP dropped them under
    `extra="ignore"` and `_resolve_api_key_scope` fell through to EVERY company). This
    pins the backend half: given the scope, a Mocha contact sees no Sorento row.
    """
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    sorento_product = product(db, company_id=DEFAULT_COMPANY_ID, code="SRT-SCOPE")
    _allocation(db, product_id=sorento_product.id, quantity=99, spo_number="SPO-SORENTO")
    db.commit()

    # Sorento sees its own row.
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert [r["spo_number"] for r in last_receipt_rows(db, top_n=10)] == ["SPO-SORENTO"]

    # Mocha sees nothing of it.
    set_company_scope(db, frozenset({MOCHA_ID}))
    assert last_receipt_rows(db, top_n=10) == []
