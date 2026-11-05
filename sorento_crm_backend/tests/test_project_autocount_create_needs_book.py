"""AC-QTSO-CRM round 4b (owner ruling R9): no AutoCount write of any kind without a book.

SO create and QT create answer 409 `ac_waiting` "Waiting for AutoCount" with no write call while
`/write-capabilities` names no book (missing, null, empty or blank). With a book named, create
proceeds and stores that book (R8).
"""
from __future__ import annotations

import pytest

from tests._ac_write_support import (
    BASE,
    CAPS_PATH,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WAITING,
    WRITE,
    api_fixture,
    caps_with,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
)

MISSING = "<missing>"
NO_BOOK = [
    pytest.param(MISSING, id="missing"),
    pytest.param(None, id="null"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="blank"),
]


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


def _feed(fake_ss, named):
    body = {"capabilities": caps_with()}
    if named != MISSING:
        body["book"] = named
    fake_ss.answers[("GET", CAPS_PATH)] = (200, body)


def _writes(fake_ss):
    return [r for r in fake_ss.writes() if r.method != "GET"]


@pytest.mark.parametrize("named", NO_BOOK)
def test_so_create_waits_when_no_book_is_named(so_api, fake_ss, named):
    client, db, world = so_api
    _feed(fake_ss, named)
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    response = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ac_waiting" and response.json()["message"] == WAITING
    assert _writes(fake_ss) == []
    db.refresh(world.order)
    assert world.order.autocount_doc_key is None and world.order.autocount_book is None


@pytest.mark.parametrize("named", NO_BOOK)
def test_qt_create_waits_when_no_book_is_named(qt_api, fake_ss, named):
    client, db, world = qt_api
    _feed(fake_ss, named)
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777", doc_key=5001))

    response = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ac_waiting" and response.json()["message"] == WAITING
    assert _writes(fake_ss) == []
    db.refresh(world.document)
    assert world.document.autocount_doc_key is None and world.document.autocount_book is None


def test_so_create_goes_and_stores_the_book_when_one_is_named(so_api, fake_ss):
    client, db, world = so_api
    _feed(fake_ss, " db3 ")
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body(doc_no="SO412345"))

    assert client.post(f"{BASE}/sales-orders/{world.order.id}/autocount").status_code == 200

    db.refresh(world.order)
    assert world.order.autocount_book == "db3"


def test_qt_create_goes_and_stores_the_book_when_one_is_named(qt_api, fake_ss):
    client, db, world = qt_api
    _feed(fake_ss, "db3")
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777", doc_key=5001))

    assert client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount").status_code == 200

    db.refresh(world.document)
    assert world.document.autocount_book == "db3"


def test_a_create_validation_error_still_makes_no_call_at_all(qt_api, fake_ss):
    """Eligibility (not accepted, missing debtor) is checked before the feed is read."""
    client, db, world = qt_api
    world.customer.customer_code = "  "
    db.commit()

    response = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    assert response.status_code == 422
    assert fake_ss.calls == []
