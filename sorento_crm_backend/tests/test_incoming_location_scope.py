"""CHAT-INCOMING-LOCATION-SCOPE, Phase 2 red tests: the incoming-stock routes under a contact's
stock-visibility policy. Covers AC-1 to AC-6, AC-8 and AC-9 (AC-7 is in
test_spo_last_receipt_location_scope.py, AC-10 in tests/chatbot/test_lookup_location_scope.py).

UAC: documentation/plans/chatbot/chat-incoming-location-scope-acceptance-criteria.md
Plan: documentation/plans/chatbot/PLAN-chat-incoming-location-scope.md

Rule under test: supply shown to a contact respects the contact's allowed locations. For a
contact whose policy names locations, `/incoming-stock/{list,by-product,shipments,
shipments/{id}/products}` never print an allocation outside the scope, count a line as
min(line remainder, in-scope OUTSTANDING allocation), withhold `unallocated_quantity`, and
drop a line (then a shipment / product) with no in-scope outstanding quantity. No contact, or a
policy naming no location list, is today's output exactly (the AC-9 guards pass before the fix).

Postgres only, blank schema, every row seeded here. Shipments are tagged `west` (a contact's
default region set) so they are not filtered for region reasons.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.access import ContactAccessType, StockVisibilityPolicy, respond_contact_access_types
from app.models.procurement import SPOAllocation
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import product
from tests._pg_fixture import unique_code
from tests.test_incoming_region_filter import (  # noqa: F401 - fixtures
    _contact,
    _tag,
    client,
    db,
)
from tests.test_stock_availability_block import _incoming_line, _incoming_shipment, _wh

BASE = "/api/v1/incoming-stock"


# --------------------------------------------------------------------- seeding


def _ship(db, *, eta=date(2026, 10, 10)):
    s = _incoming_shipment(db, eta=eta)
    s.shipping_container_number = unique_code("CONT")[:30]
    db.flush()
    _tag(db, s, ["west"])
    return s


def _alloc(db, shipment, prod, wh, qty, *, received=0):
    row = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=unique_code("SPO")[:50],
        inbound_shipment_id=shipment.id,
        product_id=prod.id,
        warehouse_id=wh.id,
        allocated_quantity=qty,
        quantity_received=received,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _policy(db, contact, *, mode="compact", warehouse_ids=None, excluded=None):
    db.add(
        StockVisibilityPolicy(
            id=str(uuid.uuid4()),
            contact_id=contact.id,
            mode=mode,
            warehouse_ids=warehouse_ids,
            excluded_warehouse_ids=excluded,
        )
    )
    db.flush()


class World:
    """Contact C is allowed BRW and MWH. BRW-BB / BRW-NTC are their own warehouse rows.

    K1: P  line 100 -> BRW 30 / BRW-BB 50 (20 unallocated)        AC-1
        Q  line 40  -> BRW-NTC 40 only                            AC-2 line
        R  line 25  -> no allocation at all                       AC-3
    K2: S  line 60  -> BRW-NTC 60 only                            AC-2 shipment / product
    """

    def __init__(self, db, *, mode="compact", include=True):
        self.brw = _wh(db, unique_code("BRW")[:20])
        self.bb = _wh(db, f"{self.brw.warehouse_code}-BB")
        self.ntc = _wh(db, f"{self.brw.warehouse_code}-NTC")
        self.mwh = _wh(db, unique_code("MWH")[:20])
        self.p, self.q, self.r, self.s = (product(db, company_id=DEFAULT_COMPANY_ID) for _ in range(4))
        self.k1 = _ship(db, eta=date(2026, 10, 10))
        self.k2 = _ship(db, eta=date(2026, 10, 20))
        _incoming_line(db, shipment_id=self.k1.id, product_id=self.p.id, shipped=100)
        _incoming_line(db, shipment_id=self.k1.id, product_id=self.q.id, shipped=40)
        _incoming_line(db, shipment_id=self.k1.id, product_id=self.r.id, shipped=25)
        _incoming_line(db, shipment_id=self.k2.id, product_id=self.s.id, shipped=60)
        _alloc(db, self.k1, self.p, self.brw, 30)
        _alloc(db, self.k1, self.p, self.bb, 50)
        _alloc(db, self.k1, self.q, self.ntc, 40)
        _alloc(db, self.k2, self.s, self.ntc, 60)
        self.contact = _contact(db)
        if include:
            _policy(db, self.contact, mode=mode, warehouse_ids=[self.brw.id, self.mwh.id])
        self.ids = f"{self.k1.id},{self.k2.id}"


def _get(client, path, **params):
    resp = client.get(f"{BASE}{path}", params=params)
    assert resp.status_code == 200, resp.text
    return resp, resp.json()


def _codes(allocs):
    return {a["warehouse_code"]: a["allocated_quantity"] for a in allocs}


# --------------------------------------------------------------------- AC-1


def test_ac1_list_shows_only_the_in_scope_allocation_and_no_gap(client, db):
    w = World(db)
    resp, body = _get(client, "/list", product_ids=w.p.id, contact_id=w.contact.id)
    (ship,) = body["data"]
    (line,) = ship["lines"]
    assert _codes(line["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
    assert line["remaining_incoming_quantity"] == 30
    assert line.get("unallocated_quantity") is None
    assert w.bb.warehouse_code not in resp.text


def test_ac1_by_product_shows_only_the_in_scope_allocation_and_no_gap(client, db):
    w = World(db)
    resp, body = _get(client, "/by-product", product_ids=w.p.id, contact_id=w.contact.id)
    (bucket,) = body["data"]
    (ship,) = bucket["shipments"]
    assert _codes(ship["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
    assert ship["remaining_incoming_quantity"] == 30
    assert ship.get("unallocated_quantity") is None
    assert w.bb.warehouse_code not in resp.text


def test_ac1_shipment_products_shows_only_the_in_scope_allocation_and_no_gap(client, db):
    w = World(db)
    resp, body = _get(client, f"/shipments/{w.k1.id}/products", contact_id=w.contact.id)
    products = {p["product_code"]: p for p in body["data"]["products"]}
    line = products[w.p.product_code]
    assert _codes(line["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
    assert line["remaining_incoming_quantity"] == 30
    assert line.get("unallocated_quantity") is None
    assert w.bb.warehouse_code not in resp.text


def test_ac1_remaining_is_the_smaller_of_line_remainder_and_in_scope_outstanding(client, db):
    """Q1: the line has 100 left, but BRW's allocation of 50 has already received 30, so only
    20 is still to come to a location the contact may be told about."""
    w = World(db)
    db.query(SPOAllocation).filter(
        SPOAllocation.inbound_shipment_id == w.k1.id,
        SPOAllocation.warehouse_id == w.brw.id,
    ).update({"allocated_quantity": 50, "quantity_received": 30})
    db.flush()
    _, body = _get(client, "/list", product_ids=w.p.id, contact_id=w.contact.id)
    (line,) = body["data"][0]["lines"]
    assert _codes(line["warehouse_allocations"]) == {w.brw.warehouse_code: 20}
    assert line["remaining_incoming_quantity"] == 20


# --------------------------------------------------------------------- AC-2 / AC-3


def test_ac2_ac3_list_drops_out_of_scope_and_unallocated_lines_and_empty_shipments(client, db):
    w = World(db)
    resp, body = _get(client, "/list", shipment_ids=w.ids, contact_id=w.contact.id, limit=50)
    assert [s["shipment_number"] for s in body["data"]] == [w.k1.shipment_number]
    assert [ln["product_code"] for ln in body["data"][0]["lines"]] == [w.p.product_code]
    assert body["pagination"]["total"] == 1
    for gone in (w.q, w.r, w.s):
        assert gone.product_code not in resp.text


def test_ac2_list_for_a_product_allocated_only_outside_scope_is_empty(client, db):
    w = World(db)
    for prod in (w.q, w.s):
        _, body = _get(client, "/list", product_ids=prod.product_code, contact_id=w.contact.id)
        assert body["data"] == [] and body["empty"] is True


def test_ac2_ac3_by_product_for_hidden_products_is_empty(client, db):
    w = World(db)
    for prod in (w.q, w.r, w.s):
        _, body = _get(client, "/by-product", product_ids=prod.id, contact_id=w.contact.id)
        assert body["data"] == [] and body["empty"] is True, prod.product_code


def test_ac2_ac3_shipment_products_drops_hidden_lines(client, db):
    w = World(db)
    _, body = _get(client, f"/shipments/{w.k1.id}/products", contact_id=w.contact.id)
    assert [p["product_code"] for p in body["data"]["products"]] == [w.p.product_code]


def test_ac2_shipment_products_for_a_shipment_with_no_visible_line_is_empty(client, db):
    w = World(db)
    _, body = _get(client, f"/shipments/{w.k2.id}/products", contact_id=w.contact.id)
    assert body["empty"] is True
    assert not (body.get("data") or {}).get("products")


# --------------------------------------------------------------------- AC-4


def test_ac4_exclusion_policy_decides_the_same_way(client, db):
    w = World(db, include=False)
    _policy(db, w.contact, mode="detailed", excluded=[w.bb.id, w.ntc.id])
    resp, body = _get(client, "/list", shipment_ids=w.ids, contact_id=w.contact.id, limit=50)
    assert [s["shipment_number"] for s in body["data"]] == [w.k1.shipment_number]
    (line,) = body["data"][0]["lines"]
    assert line["product_code"] == w.p.product_code
    assert _codes(line["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
    assert w.bb.warehouse_code not in resp.text


def test_ac4_merged_access_type_policy_decides_through_the_shared_scope(client, db):
    """One access type includes BRW + BRW-BB, the other excludes BRW-BB: merged = BRW alone."""
    w = World(db, include=False)
    wide, narrow = unique_code("WIDE")[:50], unique_code("NARROW")[:50]
    db.add_all([ContactAccessType(code=wide, name="ZZT wide"), ContactAccessType(code=narrow, name="ZZT narrow")])
    db.flush()
    db.execute(
        respond_contact_access_types.insert(),
        [{"contact_id": w.contact.id, "access_type_code": c} for c in (wide, narrow)],
    )
    db.add_all(
        [
            StockVisibilityPolicy(
                id=str(uuid.uuid4()), access_type_code=wide, mode="compact", warehouse_ids=[w.brw.id, w.bb.id]
            ),
            StockVisibilityPolicy(
                id=str(uuid.uuid4()), access_type_code=narrow, mode="compact", excluded_warehouse_ids=[w.bb.id]
            ),
        ]
    )
    db.flush()
    resp, body = _get(client, "/by-product", product_ids=w.p.id, contact_id=w.contact.id)
    (ship,) = body["data"][0]["shipments"]
    assert _codes(ship["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
    assert w.bb.warehouse_code not in resp.text


def test_ac4_brw_does_not_include_its_sub_location(client, db):
    """Policy names BRW alone; the BRW-BB share (its own warehouse row) is not told."""
    w = World(db, include=False)
    _policy(db, w.contact, warehouse_ids=[w.brw.id])
    resp, body = _get(client, "/list", product_ids=w.p.id, contact_id=w.contact.id)
    (line,) = body["data"][0]["lines"]
    assert _codes(line["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
    assert w.bb.warehouse_code not in resp.text


def test_ac4_empty_include_list_returns_no_rows(client, db):
    w = World(db, include=False)
    _policy(db, w.contact, warehouse_ids=[])
    _, body = _get(client, "/list", shipment_ids=w.ids, contact_id=w.contact.id)
    assert body["data"] == []


# --------------------------------------------------------------------- AC-5


def test_ac5_shipments_totals_count_only_in_scope_quantity(client, db):
    w = World(db)
    _, body = _get(client, "/shipments", shipment_ids=w.ids, contact_id=w.contact.id, limit=50)
    (row,) = body["data"]
    assert row["shipment_number"] == w.k1.shipment_number
    assert row["total_remaining_incoming_quantity"] == 30
    assert row["distinct_products_incoming"] == 1
    assert body["pagination"]["total"] == 1


def test_ac5_list_pagination_total_counts_only_visible_shipments(client, db):
    w = World(db)
    _, body = _get(client, "/list", shipment_ids=w.ids, contact_id=w.contact.id, page=1, limit=1)
    assert body["pagination"]["total"] == 1
    assert [s["shipment_number"] for s in body["data"]] == [w.k1.shipment_number]
    _, page2 = _get(client, "/list", shipment_ids=w.ids, contact_id=w.contact.id, page=2, limit=1)
    assert page2["data"] == []


# --------------------------------------------------------------------- AC-6


def _dealer_world(db):
    """Dealer allowed BRW + MWH; P arrives on three containers, in scope on one only."""
    w = World(db, mode="availability")
    k3 = _ship(db, eta=date(2026, 10, 25))
    _incoming_line(db, shipment_id=k3.id, product_id=w.p.id, shipped=20)
    _alloc(db, k3, w.p, w.bb, 20)
    # K2 (20 Oct) also carries P, allocated to NTC only.
    _incoming_line(db, shipment_id=w.k2.id, product_id=w.p.id, shipped=15)
    _alloc(db, w.k2, w.p, w.ntc, 15)
    return w


def test_ac6_dealer_is_told_only_etas_of_shipments_with_in_scope_quantity(client, db):
    w = _dealer_world(db)
    for path, params in (
        ("/list", {"product_ids": w.p.product_code}),
        ("/by-product", {"product_ids": w.p.id}),
    ):
        _, body = _get(client, path, contact_id=w.contact.id, **params)
        assert body["dealer_view"] is True
        (row,) = [r for r in body["data"] if r["product_code"] == w.p.product_code]
        assert row["etas"] == ["10/10/2026"], path


def test_ac6_control_dealer_with_every_location_is_told_every_eta(client, db):
    """Guard: a dealer whose policy names no location list sees all three ETAs."""
    w = _dealer_world(db)
    db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == w.contact.id).update(
        {"warehouse_ids": None}
    )
    db.flush()
    _, body = _get(client, "/list", product_ids=w.p.product_code, contact_id=w.contact.id)
    (row,) = [r for r in body["data"] if r["product_code"] == w.p.product_code]
    assert row["etas"] == ["10/10/2026", "20/10/2026", "25/10/2026"]


# --------------------------------------------------------------------- AC-8


def test_ac8_unresolvable_contact_gets_no_incoming_rows(client, db):
    w = World(db)
    ghost = "no-such-contact"
    _, lst = _get(client, "/list", product_ids=w.p.product_code, contact_id=ghost)
    assert lst["data"] == []
    _, by = _get(client, "/by-product", product_ids=w.p.id, contact_id=ghost)
    assert by["data"] == []
    _, ships = _get(client, "/shipments", shipment_ids=w.ids, contact_id=ghost)
    assert ships["data"] == []
    _, prods = _get(client, f"/shipments/{w.k1.id}/products", contact_id=ghost)
    assert prods["empty"] is True
    assert not (prods.get("data") or {}).get("products")


# --------------------------------------------------------------------- AC-9 (guards)


def test_ac9_no_contact_gets_every_allocation_and_the_gap(client, db):
    w = World(db)
    _, body = _get(client, "/list", shipment_ids=w.ids, limit=50)
    assert len(body["data"]) == 2
    k1 = next(s for s in body["data"] if s["shipment_number"] == w.k1.shipment_number)
    lines = {ln["product_code"]: ln for ln in k1["lines"]}
    assert set(lines) == {w.p.product_code, w.q.product_code, w.r.product_code}
    p = lines[w.p.product_code]
    assert _codes(p["warehouse_allocations"]) == {w.brw.warehouse_code: 30, w.bb.warehouse_code: 50}
    assert p["remaining_incoming_quantity"] == 100
    assert p["unallocated_quantity"] == 20
    _, ships = _get(client, "/shipments", shipment_ids=w.ids, limit=50)
    assert ships["pagination"]["total"] == 2


def test_ac9_policy_naming_no_location_list_is_unchanged(client, db):
    w = World(db, include=False)
    _policy(db, w.contact, mode="compact")
    _, body = _get(client, "/list", shipment_ids=w.ids, contact_id=w.contact.id, limit=50)
    assert len(body["data"]) == 2
    k1 = next(s for s in body["data"] if s["shipment_number"] == w.k1.shipment_number)
    lines = {ln["product_code"]: ln for ln in k1["lines"]}
    assert set(lines) == {w.p.product_code, w.q.product_code, w.r.product_code}
    p = lines[w.p.product_code]
    assert _codes(p["warehouse_allocations"]) == {w.brw.warehouse_code: 30, w.bb.warehouse_code: 50}
    assert p["unallocated_quantity"] == 20
    _, prods = _get(client, f"/shipments/{w.k1.id}/products", contact_id=w.contact.id)
    assert len(prods["data"]["products"]) == 3


# --------------------------------------------------------------------- NULL-workspace contact


def test_null_workspace_contact_is_scoped_on_its_own_policy_not_read_as_nobody(client, db):
    """Fix round 1: a Respond.io id + space_id for a contact with a NULL `workspace_id` is
    admitted by the fallback resolver, so its include-list policy applies (BRW 30), rather than
    the policy lookup reading nobody and failing closed with an empty answer."""
    w = World(db)
    w.contact.respond_io_id = unique_code("RIO")
    db.flush()
    _, body = _get(
        client, "/list", product_ids=w.p.id, contact_id=w.contact.respond_io_id, space_id="364817"
    )
    (line,) = body["data"][0]["lines"]
    assert _codes(line["warehouse_allocations"]) == {w.brw.warehouse_code: 30}
