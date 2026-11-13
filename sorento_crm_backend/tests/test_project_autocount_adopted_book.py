"""AC-QTSO-CRM round 3 (owner ruling R7): an ADOPTED order only updates / cancels in AutoCount
when SS names its book.

Adopted = the doc key comes from the core order's `source_ref` (`{book}:{DocKey}`), not from our
own stored `autocount_doc_key`. Update and Cancel are allowed only when `/write-capabilities`
carries a top-level string `book` equal (trimmed, case-insensitive) to that `{book}`. Until then
both are 409 `ac_waiting` "Waiting for AutoCount" with no write call. A CRM-created order is
unaffected. `in_autocount` stays true for an adopted order; `autocount_adopted` says why it waits.
"""
from __future__ import annotations

import pytest

from app.models.order import SalesOrder
from tests._ac_write_support import (
    BASE,
    CAPS_PATH,
    DOC_KEY,
    EDIT,
    SO_CREATE_PATH,
    VIEW,
    WAITING,
    WRITE,
    add_amendment,
    api_fixture,
    caps_with,
    delay_row,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
)

BOOK = "AED_SRT"
DOC_PATH = f"{SO_CREATE_PATH}/{DOC_KEY}"


@pytest.fixture
def api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def _feed(fake_ss, book, *, cancel=True):
    body = {"capabilities": caps_with(cancel_doc=(cancel, None if cancel else "VENDOR_UNSUPPORTED"))}
    if book is not False:
        body["book"] = book
    fake_ss.answers[("GET", CAPS_PATH)] = (200, body)


def _adopt(db, world):
    put_in_autocount(db, world)
    core = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core.source_ref = f"{BOOK}:{DOC_KEY}"
    world.order.autocount_doc_key = None
    world.order.autocount_last_modified = "2026-10-01T09:30:00"
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    return amendment


def _update(client, amendment):
    return client.post(f"{BASE}/sales-orders/amendments/{amendment.id}/autocount")


def _cancel(client, world):
    return client.post(f"{BASE}/sales-orders/{world.order.id}/autocount/cancel")


def _answers(fake_ss):
    fake_ss.answers[("PATCH", DOC_PATH)] = (200, done_body(last_modified="2026-11-05T11:00:00"))
    fake_ss.answers[("POST", f"{DOC_PATH}/cancel")] = (200, done_body())


@pytest.mark.parametrize("book", [False, None, "", "   "])
def test_an_adopted_order_with_no_book_in_the_feed_waits_on_update_and_cancel(api, fake_ss, book):
    client, db, world = api
    amendment = _adopt(db, world)
    _feed(fake_ss, book)
    _answers(fake_ss)

    for response in (_update(client, amendment), _cancel(client, world)):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "ac_waiting"
        assert response.json()["message"] == WAITING
    assert [r for r in fake_ss.writes() if r.method != "GET"] == []


def test_an_adopted_order_whose_book_differs_waits(api, fake_ss):
    client, db, world = api
    amendment = _adopt(db, world)
    _feed(fake_ss, "db1")
    _answers(fake_ss)

    for response in (_update(client, amendment), _cancel(client, world)):
        assert response.status_code == 409 and response.json()["code"] == "ac_waiting"
    assert [r for r in fake_ss.writes() if r.method != "GET"] == []


@pytest.mark.parametrize("named", [BOOK, f"  {BOOK.lower()}  "])
def test_an_adopted_order_whose_book_matches_is_allowed(api, fake_ss, named):
    client, db, world = api
    amendment = _adopt(db, world)
    _feed(fake_ss, named)
    _answers(fake_ss)

    assert _update(client, amendment).status_code == 200
    assert fake_ss.to("PATCH", DOC_PATH)
    assert _cancel(client, world).status_code == 200
    assert fake_ss.to("POST", f"{DOC_PATH}/cancel")


def test_a_crm_created_order_waits_when_the_feed_names_no_book(api, fake_ss):
    """R8 replaces R7's "CRM-created unaffected": every update / cancel needs SS's book."""
    client, db, world = api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    _feed(fake_ss, False)
    _answers(fake_ss)

    for response in (_update(client, amendment), _cancel(client, world)):
        assert response.status_code == 409 and response.json()["code"] == "ac_waiting"
    assert [r for r in fake_ss.writes() if r.method != "GET"] == []


def test_the_capabilities_route_passes_the_book_through(api, fake_ss):
    client, _db, _world = api
    _feed(fake_ss, BOOK)

    assert client.get(f"{BASE}/autocount-write/capabilities").json()["book"] == BOOK
    _feed(fake_ss, False)
    assert client.get(f"{BASE}/autocount-write/capabilities").json()["book"] is None


def test_the_payload_says_adopted_and_still_in_autocount(api, fake_ss):
    client, db, world = api
    _adopt(db, world)

    row = client.get(f"{BASE}/sales-orders/{world.order.id}").json()
    row = row.get("data", row)

    assert row["in_autocount"] is True and row["autocount_adopted"] is True


def test_a_crm_created_order_is_not_adopted_on_the_wire(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    db.commit()

    row = client.get(f"{BASE}/sales-orders/{world.order.id}").json()
    row = row.get("data", row)

    assert row["in_autocount"] is True and row["autocount_adopted"] is False
