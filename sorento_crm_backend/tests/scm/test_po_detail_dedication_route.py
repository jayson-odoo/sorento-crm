"""D3 and the confirm's own count, over HTTP (B4 + S1, review of PR #490).

The standing lesson: `response_model` silently drops a field the schema does not declare,
so a value the service computes can be correct in a unit test and absent on the wire for
ever. Both fields this asserts were exactly that -
`PurchaseOrderLineAllocation.dedicated_to` (the frontend types declare it REQUIRED) and
`BulkConfirmResult.claimed_lines` - so the assertions here are made through the route, not
against the service.

`scm_app` (savepoint-per-test, rolled back) with every row behind the `ZZTPDR` marker.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import order_link_service
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTPDR"
SOON = date.today() + timedelta(days=45)


def _u() -> str:
    return str(uuid.uuid4())


def _as(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db, uid


def _project_bin(db) -> str:
    wid = _u()
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "segment, created_at, updated_at) "
            "VALUES (:i, :c, :c, true, 'project', now(), now())"
        ),
        {"i": wid, "c": f"{MARKER}{uuid.uuid4().hex[:6].upper()}"},
    )
    db.flush()
    return wid


def _active_po(db, *, product_id, warehouse_id, qty) -> tuple[str, str, str]:
    po_id, number = _u(), f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
            "source_system) VALUES (:i, :n, 'active', :d, 'MYR', 'scm_upload')"
        ),
        {"i": po_id, "n": number, "d": date(2026, 8, 1)},
    )
    line_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status, "
            "expected_date) VALUES (:i, :po, :p, :w, :q, 0, 10, 'MYR', 'open', :e)"
        ),
        {"i": line_id, "po": po_id, "p": product_id, "w": warehouse_id, "q": qty,
         "e": SOON},
    )
    db.flush()
    return po_id, line_id, number


def test_the_detail_route_ships_dedicated_to_and_a_netted_free(scm_app):
    """A line the book dedicates wholly to another sales order reads `free 0` with that
    order NAMED, over the wire. Before the schema declared the field, the panel was sent
    a line reading `free 0` and nothing at all to explain it."""
    app, db, _ = _as(scm_app, "purchasing")
    from tests.scm.test_channel_read_model import _core_so_line
    from tests.scm.test_m3_run import _mk_product

    bin_id = _project_bin(db)
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id, number = _active_po(db, product_id=pid, warehouse_id=bin_id, qty=114)

    claiming, claiming_line = _core_so_line(
        db, product_id=pid, warehouse_id=bin_id, qty=114, demand_class="project",
    )
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=claiming.so_number, po_number=number,
        item_code=None, so_line_id=str(claiming_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text

    blocks = res.json().get("allocations") or []
    block = next(b for b in blocks if b["line_id"] == line_id)
    assert block["outstanding"] == 114
    assert block["allocated"] == 0
    assert block["free"] == 0, "a line the book dedicates elsewhere is not free"
    assert [d["so_number"] for d in block["dedicated_to"]] == [claiming.so_number], (
        "response_model dropped the dedication on the way out"
    )
    assert block["dedicated_to"][0]["unplaced"] == 114
    assert block["dedicated_to"][0]["source"] == order_link_service.SOURCE_PO_UPLOAD


def test_a_lines_own_placement_reserves_nothing_further_on_top_of_it(scm_app):
    """The other direction, and the one that would double-count. Every placement writes an
    audit claim beside it, so a fully-linked line IS named as dedicated - to the order that
    placed it. What must not happen is that claim taking a second bite: its `unplaced` is
    0, because the order has already put the whole thing where it wanted it, and `free`
    reads the allocation once."""
    app, db, actor = _as(scm_app, "purchasing")
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse

    pool = _mk_warehouse(db, f"{MARKER}POOL{uuid.uuid4().hex[:5].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    leg = _confirmed_leg(db, product_id=pid, warehouse_id=pool, buy_qty=8)
    po_id, line_id, _ = _active_po(db, product_id=pid, warehouse_id=pool, qty=8)

    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    ProjectOrderInquiryService(db).place_on_po_allocations(
        str(leg["inquiry_row"].id), [{"po_line_id": line_id, "qty": 8}],
        actor_user_id=actor,
    )

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    block = next(
        b for b in (res.json().get("allocations") or []) if b["line_id"] == line_id
    )
    assert block["allocated"] == 8
    assert block["free"] == 0
    assert len(block["dedicated_to"]) == 1, "the placing order is named, not hidden"
    assert block["dedicated_to"][0]["unplaced"] == 0, (
        "the placement was counted once by `allocated` and again by its own claim"
    )
    assert block["dedicated_to"][0]["source"] == order_link_service.SOURCE_ORDER_INQUIRY


def test_bulk_confirm_reports_how_many_rows_it_attributed(scm_app):
    """S1. The confirm's write-time claiming is invisible unless it says so, and
    `BulkConfirmResult` did not declare the count, so `response_model` dropped it."""
    app, db, actor = _as(scm_app, "purchasing")
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product

    bin_id = _project_bin(db)
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=30)
    _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=84)

    po_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
            "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
            "'scm_recommendation')"
        ),
        {"i": po_id, "n": f"{MARKER}-{uuid.uuid4().hex[:8].upper()}",
         "d": date(2026, 8, 1)},
    )
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
            "VALUES (:i, :po, :p, :w, 114, 0, 10, 'MYR', 'open')"
        ),
        {"i": _u(), "po": po_id, "p": pid, "w": bin_id},
    )
    db.flush()

    with TestClient(app) as c:
        res = c.post("/api/v1/scm/purchase-orders/bulk-confirm", json={"ids": [po_id]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["confirmed_count"] == 1
    assert body["claimed_lines"] == 2, (
        "both sizing rows were attributed, and the count has to reach the wire"
    )
