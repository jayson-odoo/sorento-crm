"""GET /api/v1/scm/reorder-runs/location-stock - the Buy row's expand panel (20 Aug live ask).

`location_stock_service.location_stock_for_product` composes the SAME per-location readers
`ProjectFulfilmentBoardService.stock_detail` uses, so this popup and the fulfilment board can
never disagree on what a location is carrying. One product, every ACTIVE warehouse carrying a
nonzero figure, `available` signed and never clamped.

Every test seeds its own chain under a marker-prefixed tag (CI's database is empty). The route
is auth-checked through `scm_app` + `as_company_user`, which also gives the session the active
company a direct `SessionLocal` read would need and not have - a bare unscoped session fails
closed (the company predicate renders `1=0`).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import InboundShipment, SPOAllocation
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZLS"

URL = "/api/v1/scm/reorder-runs/location-stock"


def _warehouse(db) -> Warehouse:
    wh = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=f"{MARKER}-WH-{uuid.uuid4().hex[:8]}",
        warehouse_name=f"{MARKER} warehouse",
        is_active=True,
    )
    db.add(wh)
    db.flush()
    return wh


def _on_hand(db, product_id, wh, qty) -> None:
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=product_id,
            warehouse_id=wh.id,
            quantity_on_hand=qty,
        )
    )
    db.flush()


def _open_so_line(db, product_id, wh, qty) -> None:
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status="open",
        demand_class="retail",
        order_date=date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=product_id,
            warehouse_id=wh.id,
            qty_ordered=qty,
            qty_delivered=0,
            line_status="open",
            purchasing_status="not_reviewed",
        )
    )
    db.flush()


def _incoming_spo(db, supplier_id, product_id, wh, qty) -> None:
    ship = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:8]}",
        supplier_id=supplier_id,
        shipment_date=date(2026, 1, 1),
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    db.add(
        SPOAllocation(
            id=str(uuid.uuid4()),
            spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
            inbound_shipment_id=ship.id,
            product_id=product_id,
            warehouse_id=wh.id,
            allocated_quantity=qty,
            quantity_received=0,
        )
    )
    db.flush()


def test_location_stock_composes_on_hand_so_and_spo_into_a_signed_available(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")
    wh = _warehouse(db)
    _on_hand(db, product.id, wh, 50)
    _open_so_line(db, product.id, wh, 20)
    _incoming_spo(db, w.supplier.id, product.id, wh, 5)

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_id"] == str(product.id)
    assert body["as_of"]
    assert len(body["locations"]) == 1
    loc = body["locations"][0]
    assert loc["warehouse_id"] == str(wh.id)
    assert loc["warehouse_code"] == wh.warehouse_code
    assert loc["on_hand"] == 50
    assert loc["reserved"] == 0
    assert loc["held_by_decisions"] == 0
    assert loc["free"] == 50
    assert loc["so_qty"] == 20
    assert loc["spo_qty"] == 5
    # Signed, never clamped: on_hand - so_qty + spo_qty.
    assert loc["available"] == 35


def test_location_stock_for_a_product_with_no_stock_anywhere_is_empty_locations(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")  # on the world, but no stock/SO/SPO row anywhere

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_id"] == str(product.id)
    assert body["locations"] == []


def test_location_stock_requires_the_view_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).get(URL, params={"product_id": str(uuid.uuid4())})

    assert r.status_code == 403, r.text


def test_location_stock_with_a_malformed_product_id_is_a_404_not_a_500(scm_app):
    # BL-1: a non-id-shaped value reached the UUID columns raw and 500'd.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).get(URL, params={"product_id": "not-a-uuid"})

    assert r.status_code == 404, r.text
