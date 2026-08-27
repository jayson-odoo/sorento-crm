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


def _warehouse(db, *, segment: str | None = None) -> Warehouse:
    wh = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=f"{MARKER}-WH-{uuid.uuid4().hex[:8]}",
        warehouse_name=f"{MARKER} warehouse",
        is_active=True,
        segment=segment,
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
    # Every OTHER row is a site pool sitting at zero (R16) - this product is stocked
    # nowhere else, and the pool rows are listed anyway.
    loc = next(l for l in body["locations"] if l["warehouse_id"] == str(wh.id))
    assert all(l["is_pool"] for l in body["locations"] if l["warehouse_id"] != str(wh.id))
    assert loc["warehouse_id"] == str(wh.id)
    assert loc["warehouse_code"] == wh.warehouse_code
    # No segment set, so it counts (captain, 20 Aug) - a site nobody has classified is
    # not assumed to be a project bin.
    assert loc["is_pool"] is True
    assert loc["on_hand"] == 50
    assert loc["reserved"] == 0
    assert loc["held_by_decisions"] == 0
    assert loc["free"] == 50
    assert loc["so_qty"] == 20
    assert loc["spo_qty"] == 5
    # Signed, never clamped: on_hand - so_qty + spo_qty.
    assert loc["available"] == 35


def test_location_stock_flags_a_project_segment_location_as_not_pool(scm_app):
    """Captain, 20 Aug: `on_hand` shown here is a per-location fact and is never zeroed -
    a project bin's own stock is real and visible. `is_pool` is the discriminator the
    reorder engine's OWN counted `on_hand` uses (a project-segment location's stock is
    not usable supply there), so this panel and the engine's figure for the same location
    can never disagree about which side of the line it sits on."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")
    wh = _warehouse(db, segment="project")
    _on_hand(db, product.id, wh, 80)

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    assert r.status_code == 200, r.text
    loc = next(l for l in r.json()["locations"] if l["warehouse_id"] == str(wh.id))
    assert loc["is_pool"] is False
    assert loc["on_hand"] == 80, "still shown - the panel never hides it"


def test_every_site_pool_is_listed_even_holding_nothing(scm_app):
    """R16 (captain, 28 Aug): the On hand lightbox lists EVERY site-pool location, zeros
    included.

    Dropping the all-zero rows answered a different question. "DC1 has none" is a fact a
    buyer deciding where to buy into needs to read; a missing row says only that nobody
    told them, and the buyer cannot tell the two apart.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")
    holding = _warehouse(db, segment="dealer")
    empty_a = _warehouse(db, segment="dealer")
    empty_b = _warehouse(db)  # no segment set - a site nobody classified is a pool
    _on_hand(db, product.id, holding, 12)

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    assert r.status_code == 200, r.text
    by_id = {l["warehouse_id"]: l for l in r.json()["locations"]}
    for empty in (empty_a, empty_b):
        assert str(empty.id) in by_id, "a pool holding nothing still says so"
        assert by_id[str(empty.id)]["on_hand"] == 0
        assert by_id[str(empty.id)]["available"] == 0
        assert by_id[str(empty.id)]["po_qty"] == 0
    assert by_id[str(holding.id)]["on_hand"] == 12


def test_an_empty_project_bin_is_still_dropped(scm_app):
    """Only the POOL rows are unconditional. A project bin holding nothing is one of
    fifty-five, and listing them all would turn the dialog into the warehouse list."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")
    empty_bin = _warehouse(db, segment="project")

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    assert r.status_code == 200, r.text
    assert str(empty_bin.id) not in {l["warehouse_id"] for l in r.json()["locations"]}


def test_locations_come_back_pool_first_then_by_code(scm_app):
    """One reading order, so the dialog and the fulfilment board's own table are walked
    the same way rather than in whatever order Postgres felt like."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")
    bin_ = _warehouse(db, segment="project")
    _on_hand(db, product.id, bin_, 7)

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    rows = r.json()["locations"]
    pools = [l["warehouse_code"] for l in rows if l["is_pool"]]
    bins = [l["warehouse_code"] for l in rows if not l["is_pool"]]
    assert pools == sorted(pools)
    assert bins == sorted(bins)
    assert [l["is_pool"] for l in rows] == sorted(
        (l["is_pool"] for l in rows), reverse=True
    ), "pools first"


def test_location_stock_for_a_product_with_no_stock_anywhere_lists_only_pools(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")  # on the world, but no stock/SO/SPO row anywhere

    r = TestClient(app).get(URL, params={"product_id": str(product.id)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_id"] == str(product.id)
    # Never an empty answer any more: the pools say zero (R16). Nothing else appears.
    assert all(l["is_pool"] for l in body["locations"])
    assert all(l["on_hand"] == 0 for l in body["locations"])


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
