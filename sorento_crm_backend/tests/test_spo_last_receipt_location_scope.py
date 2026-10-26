"""CHAT-INCOMING-LOCATION-SCOPE, Phase 2 red tests: `GET /procurement/spo-allocations/last-receipt`
under a contact's stock-visibility policy. Covers AC-7, AC-8 and the last-in half of AC-4 / AC-9.

UAC: documentation/plans/chatbot/chat-incoming-location-scope-acceptance-criteria.md
Plan: documentation/plans/chatbot/PLAN-chat-incoming-location-scope.md (design item 4)

The route gains `contact_id` / `space_id`. The contact's scope
(`stock_visibility.scope_warehouse_ids(resolve_policy(...))`) narrows `warehouse_ids` BEFORE the
per-product pick, so an out-of-scope line never displaces an in-scope one; an empty scope or an
unresolvable contact returns no rows; `availability` mode withholds `warehouse`. No contact, or a
policy naming no location list, is today's output (the guards pass before the fix).

Postgres only, blank schema, every row seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.access import StockVisibilityPolicy

from tests._mc_lookup_seed import product, warehouse
from tests._pg_fixture import unique_code
from tests.test_spo_last_receipt import (  # noqa: F401 - fixtures
    BASE,
    DEFAULT_COMPANY_ID,
    _allocation,
    client,
    db,
)
from tests.test_incoming_region_filter import _contact


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


def _world(db):
    """P with SPO lines at BRW-BB (newest), MWH, BRW (oldest); BRW-BB is its own warehouse row."""
    brw = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("BRW")[:20])
    bb = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=f"{brw.warehouse_code}-BB")
    mwh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("MWH")[:20])
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    for wh, day, number in ((bb, 30, "SPO-BB"), (mwh, 20, "SPO-MWH"), (brw, 10, "SPO-BRW")):
        _allocation(
            db, product_id=prod.id, warehouse_id=wh.id, expected_date=date(2026, 8, day), spo_number=number
        )
    db.commit()
    contact = _contact(db)
    return brw, bb, mwh, prod, contact


def _rows(client, prod, contact=None, **params):
    if contact is not None:
        params["contact_id"] = contact if isinstance(contact, str) else contact.id
    resp = client.get(f"{BASE}/last-receipt", params={"product_ids": prod.id, "top_n": 2, **params})
    assert resp.status_code == 200, resp.text
    return resp, resp.json()["data"]


def test_ac7_scope_narrows_before_the_per_product_pick(client, db):
    brw, bb, mwh, prod, contact = _world(db)
    _policy(db, contact, warehouse_ids=[brw.id, mwh.id])
    resp, rows = _rows(client, prod, contact)
    assert [r["spo_number"] for r in rows] == ["SPO-MWH", "SPO-BRW"]
    assert [r["warehouse"] for r in rows] == [mwh.warehouse_code, brw.warehouse_code]
    assert bb.warehouse_code not in resp.text


def test_ac7_unscoped_product_branch_is_narrowed_too(client, db):
    """No `product_ids`: the plain top_n cap must also come from in-scope lines only."""
    brw, bb, mwh, _prod, contact = _world(db)
    _policy(db, contact, warehouse_ids=[brw.id, mwh.id])
    resp = client.get(f"{BASE}/last-receipt", params={"top_n": 5, "contact_id": contact.id})
    assert resp.status_code == 200, resp.text
    assert [r["spo_number"] for r in resp.json()["data"]] == ["SPO-MWH", "SPO-BRW"]


def test_ac7_availability_mode_is_scoped_and_withholds_the_warehouse(client, db):
    brw, bb, mwh, prod, contact = _world(db)
    _policy(db, contact, mode="availability", warehouse_ids=[brw.id, mwh.id])
    resp, rows = _rows(client, prod, contact)
    assert [r["spo_number"] for r in rows] == ["SPO-MWH", "SPO-BRW"]
    assert all(r["warehouse"] is None for r in rows)
    assert bb.warehouse_code not in resp.text and mwh.warehouse_code not in resp.text


def test_ac4_exclusion_policy_scopes_last_in_the_same_way(client, db):
    brw, bb, mwh, prod, contact = _world(db)
    _policy(db, contact, mode="detailed", excluded=[bb.id])
    _, rows = _rows(client, prod, contact)
    assert [r["spo_number"] for r in rows] == ["SPO-MWH", "SPO-BRW"]


def test_ac4_a_named_warehouse_never_widens_the_contact_scope(client, db):
    brw, bb, mwh, prod, contact = _world(db)
    _policy(db, contact, warehouse_ids=[brw.id, mwh.id])
    _, rows = _rows(client, prod, contact, warehouse_ids=bb.id)
    assert rows == []


def test_ac4_empty_include_list_returns_no_rows(client, db):
    _brw, _bb, _mwh, prod, contact = _world(db)
    _policy(db, contact, warehouse_ids=[])
    _, rows = _rows(client, prod, contact)
    assert rows == []


def test_ac8_unresolvable_contact_gets_no_rows(client, db):
    _brw, _bb, _mwh, prod, _contact_row = _world(db)
    resp, rows = _rows(client, prod, "no-such-contact")
    assert rows == []
    assert resp.json()["empty"] is True


def test_ac9_no_contact_is_unchanged(client, db):
    brw, bb, mwh, prod, _contact_row = _world(db)
    _, rows = _rows(client, prod)
    assert [r["spo_number"] for r in rows] == ["SPO-BB", "SPO-MWH"]
    assert rows[0]["warehouse"] == bb.warehouse_code


def test_ac9_policy_naming_no_location_list_is_unchanged(client, db):
    brw, bb, mwh, prod, contact = _world(db)
    _policy(db, contact, mode="compact")
    _, rows = _rows(client, prod, contact)
    assert [r["spo_number"] for r in rows] == ["SPO-BB", "SPO-MWH"]
    assert rows[0]["warehouse"] == bb.warehouse_code


def test_null_workspace_contact_is_scoped_on_its_own_policy_not_read_as_nobody(client, db):
    """Fix round 1: a Respond.io id + space_id for a NULL-workspace contact resolves through
    the fallback, so its include list applies instead of failing closed with no rows."""
    brw, bb, mwh, prod, contact = _world(db)
    _policy(db, contact, warehouse_ids=[brw.id, mwh.id])
    contact.respond_io_id = unique_code("RIO")
    db.commit()
    resp, rows = _rows(client, prod, contact.respond_io_id, space_id="364817")
    assert [r["spo_number"] for r in rows] == ["SPO-MWH", "SPO-BRW"]
    assert bb.warehouse_code not in resp.text
