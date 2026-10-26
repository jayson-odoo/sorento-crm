"""The zero-stock reply's on-order note (the `crm_procurement_po_placed_list` rung) under a
contact's stock-visibility policy.

STOCK-TOTAL-OS-SCOPE (#1431) first stopped the note NAMING a hidden location, but it kept the
row and only withheld `location`. CHAT-PO-LOCATION-SCOPE (owner report, 26 Oct 2026): a
contact allowed BRW and MWH was still shown the PO lines on BRW-BB and BRW-NTC, printed with
no location line. The on-order rows a contact sees are now scoped exactly like its stock
lines: the active warehouses `stock_visibility.warehouse_criterion` allows. A row outside that
scope is not returned at all, and neither is a PO line with no warehouse (it is in no named
location; same ruling as open SO with no warehouse in #1431). A sub-location (BRW-BB) is its
own warehouse row, so a contact scoped to BRW does not see it. `availability` mode is scoped
the same way and still names no location; an unresolvable contact fails closed with no rows,
as the stock list does. No `contact_id` (staff, n8n) and a policy naming no location list are
unchanged.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid

from app.models.access import RespondContact, StockVisibilityPolicy
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import product
from tests._pg_fixture import unique_code
from tests.test_purchase_orders_placed import (  # noqa: F401 - fixtures
    BASE,
    _po_line,
    _spo,
    _warehouse,
    client,
    db,
)


def _contact(db) -> RespondContact:
    row = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
    )
    db.add(row)
    db.flush()
    return row


def _policy(db, contact, *, mode, warehouse_ids=None, excluded_warehouse_ids=None):
    db.add(
        StockVisibilityPolicy(
            id=str(uuid.uuid4()),
            contact_id=contact.id,
            mode=mode,
            warehouse_ids=warehouse_ids,
            excluded_warehouse_ids=excluded_warehouse_ids,
        )
    )
    db.flush()


def _seed(db):
    """PO lines on visible VIS and hidden HID, an SPO allocation on HID by location code
    only, and a PO line with no warehouse."""
    vis = _warehouse(db, code=unique_code("VIS"))
    hid = _warehouse(db, code=unique_code("BRW-NTC"))
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=10, received=0, po_number="PO-VIS", warehouse_id=vis.id)
    _po_line(db, product_id=prod.id, ordered=7, received=0, po_number="PO-HID", warehouse_id=hid.id)
    _po_line(db, product_id=prod.id, ordered=5, received=0, po_number="PO-NONE")
    _spo(db, product_id=prod.id, allocated=4, number="SPO-HID", location_code=hid.warehouse_code)
    db.flush()
    return vis, hid, prod


def _rows(client, prod, **params):
    resp = client.get(f"{BASE}/placed", params={"product_ids": prod.id, **params})
    assert resp.status_code == 200, resp.text
    return resp, {r["po_number"]: r for r in resp.json()["data"]}


def test_owner_report_contact_on_brw_and_mwh_sees_only_the_brw_lines(client, db):
    """The owner's 26 Oct case: scoped to BRW + MWH, 0 stock, open PO lines on BRW, on its
    sub-locations BRW-BB and BRW-NTC (their own warehouse rows, pooled to BRW), and none on
    MWH. Only the BRW lines come back, each naming BRW, and the summary counts them alone."""
    brw = _warehouse(db, code=unique_code("BRW"))
    mwh = _warehouse(db, code=unique_code("MWH"))
    bb = _warehouse(db, code=f"{brw.warehouse_code}-BB")
    ntc = _warehouse(db, code=f"{brw.warehouse_code}-NTC")
    bb.pool_warehouse_id = brw.id
    ntc.pool_warehouse_id = brw.id
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, product_id=prod.id, ordered=72, received=0, po_number="PO-BB", warehouse_id=bb.id)
    _po_line(db, product_id=prod.id, ordered=32, received=0, po_number="PO-BRW-1", warehouse_id=brw.id)
    _po_line(db, product_id=prod.id, ordered=57, received=0, po_number="PO-NTC", warehouse_id=ntc.id)
    _po_line(db, product_id=prod.id, ordered=8, received=0, po_number="PO-BRW-2", warehouse_id=brw.id)
    db.flush()
    contact = _contact(db)
    _policy(db, contact, mode="compact", warehouse_ids=[brw.id, mwh.id])

    resp, rows = _rows(client, prod, contact_id=contact.id, include_summary="true")

    assert set(rows) == {"PO-BRW-1", "PO-BRW-2"}
    assert {r["location"] for r in rows.values()} == {brw.warehouse_code}
    assert bb.warehouse_code not in resp.text
    assert ntc.warehouse_code not in resp.text
    summary = resp.json()["summary"]
    assert summary["po_placed_qty"] == 40
    assert summary["po_placed_count"] == 2


def test_restricted_contact_never_sees_a_row_outside_its_locations(client, db):
    vis, hid, prod = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="compact", warehouse_ids=[vis.id])

    resp, rows = _rows(client, prod, contact_id=contact.id)

    # The hidden PO line, the hidden SPO allocation (by location code) and the line with no
    # warehouse are all outside the contact's locations: none of them is returned.
    assert set(rows) == {"PO-VIS"}
    assert rows["PO-VIS"]["location"] == vis.warehouse_code
    assert hid.warehouse_code not in resp.text


def test_exclusion_policy_drops_the_excluded_location(client, db):
    vis, hid, prod = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="detailed", excluded_warehouse_ids=[hid.id])

    resp, rows = _rows(client, prod, contact_id=contact.id)

    assert set(rows) == {"PO-VIS"}
    assert rows["PO-VIS"]["location"] == vis.warehouse_code
    assert hid.warehouse_code not in resp.text


def test_empty_include_list_returns_no_rows(client, db):
    _vis, _hid, prod = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="compact", warehouse_ids=[])

    resp, rows = _rows(client, prod, contact_id=contact.id, include_summary="true")

    assert rows == {}
    assert resp.json()["summary"]["po_placed_count"] == 0


def test_a_named_warehouse_never_widens_the_contact_scope(client, db):
    vis, hid, prod = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="compact", warehouse_ids=[vis.id])

    _resp, rows = _rows(client, prod, contact_id=contact.id, warehouse_ids=hid.id)

    assert rows == {}


def test_every_warehouse_policy_keeps_every_row(client, db):
    vis, hid, prod = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="compact")

    _resp, rows = _rows(client, prod, contact_id=contact.id)

    assert set(rows) == {"PO-VIS", "PO-HID", "PO-NONE", "SPO-HID"}
    assert rows["PO-VIS"]["location"] == vis.warehouse_code
    assert rows["PO-HID"]["location"] == hid.warehouse_code
    assert rows["SPO-HID"]["location"] == hid.warehouse_code


def test_availability_mode_is_scoped_and_names_no_location(client, db):
    vis, _hid, prod = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="availability", warehouse_ids=[vis.id])

    _resp, rows = _rows(client, prod, contact_id=contact.id)

    assert set(rows) == {"PO-VIS"}
    assert rows["PO-VIS"]["location"] is None


def test_unresolvable_contact_fails_closed(client, db):
    _vis, _hid, prod = _seed(db)

    _resp, rows = _rows(client, prod, contact_id="no-such-contact")

    assert rows == {}


def test_staff_call_without_contact_is_unchanged(client, db):
    vis, hid, prod = _seed(db)

    _resp, rows = _rows(client, prod)

    assert set(rows) == {"PO-VIS", "PO-HID", "PO-NONE", "SPO-HID"}
    assert rows["PO-VIS"]["location"] == vis.warehouse_code
    assert rows["PO-HID"]["location"] == hid.warehouse_code
    assert rows["SPO-HID"]["location"] == hid.warehouse_code
