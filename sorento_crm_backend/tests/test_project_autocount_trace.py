"""Owner (crew, 12 Nov): every AutoCount write is traced to the person who pressed.

Every write call of a press (QT create / update / cancel, SO create / amendment update / cancel)
sends `X-Request-ID` (one per press, shared by all its writes) and the pressing user, with the
names SS plan 63 fixed (lane AC-DB1-READY): `X-Acting-User-Id` (1..64 printable ASCII) and
`X-Acting-User-Name` (UTF-8 percent-encoded with `quote(name, safe="")`, at most 128 characters
decoded). Each write call is stored as an audit EVENT `autocount_write` with that user, the
request id and the outcome.
"""
from __future__ import annotations

import re

import pytest

from tests._ac_write_support import (
    BASE,
    BOOK,
    CAPS_PATH,
    DOC_KEY,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    add_amendment,
    add_issue,
    api_fixture,
    caps_with,
    delay_row,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
)
from tests.test_project_autocount_qt_send import QT_DOC_PATH, _created, _mark_sent

HEX32 = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def _traced(request):
    request_id = request.headers.get("X-Request-ID")
    actor = request.headers.get("X-Acting-User-Id")
    assert request_id and HEX32.fullmatch(request_id), request.headers
    assert actor and len(actor) <= 64, request.headers
    assert request.headers.get("X-Acting-User-Name"), request.headers
    return request_id, actor


def _audit_rows(db):
    from app.models.audit import AuditLog

    return db.query(AuditLog).filter(AuditLog.event == "autocount_write").all()


def test_a_quotation_create_is_traced_and_stored_with_the_user(qt_api, fake_ss):
    client, db, world = qt_api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world))

    client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    [request] = fake_ss.to("POST", QT_CREATE_PATH)
    request_id, actor = _traced(request)
    [row] = _audit_rows(db)
    assert row.user_id == actor
    assert row.new_values["request_id"] == request_id
    assert row.new_values["outcome"] == "done"
    assert row.new_values["idempotency_key"] == request.headers["Idempotency-Key"]


def test_every_write_of_one_press_shares_its_request_id_and_the_next_press_gets_another(qt_api, fake_ss):
    client, db, world = qt_api
    _mark_sent(db, world)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _created(world))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (409, {"outcome": "refused", "errorCode": "DOC_BUSY", "message": "busy"})
    url = f"{BASE}/quotation-documents/{world.document.id}/autocount"

    client.post(url)
    client.post(url)

    first, second = fake_ss.to("PATCH", QT_DOC_PATH)
    assert _traced(first)[0] != _traced(second)[0], "one request id per press"
    assert len(_audit_rows(db)) == 2


def test_a_sales_order_amendment_update_and_cancel_are_traced(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    doc = f"{SO_CREATE_PATH}/{DOC_KEY}"
    fake_ss.answers[("PATCH", doc)] = (200, done_body())
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{doc}/cancel")] = (200, done_body())

    client.post(f"{BASE}/sales-orders/amendments/{amendment.id}/autocount")
    client.post(f"{BASE}/sales-orders/{world.order.id}/autocount/cancel")

    [patch] = fake_ss.to("PATCH", doc)
    [cancel] = fake_ss.to("POST", f"{doc}/cancel")
    assert _traced(patch)[1] == _traced(cancel)[1]
    assert {r.new_values["request_id"] for r in _audit_rows(db)} == {_traced(patch)[0], _traced(cancel)[0]}


def test_a_sales_order_create_is_traced(so_api, fake_ss):
    client, db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    _traced(request)
    assert len(_audit_rows(db)) == 1


def test_a_read_carries_no_actor(qt_api, fake_ss):
    """Only writes are traced to a person; the capability read and document reads stay plain."""
    client, _db, world = qt_api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world))

    client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    [caps] = fake_ss.to("GET", CAPS_PATH)
    assert "X-Acting-User-Id" not in caps.headers


def test_the_name_is_percent_encoded_and_capped_at_128_characters():
    from urllib.parse import unquote

    from app.services.foundryx_autocount_client import FoundryxAutocountClient

    client = FoundryxAutocountClient.__new__(FoundryxAutocountClient)
    client.trace_writes("a" * 32, {"id": "u" * 80, "name": "Siti Nur'aini binti Ahmad / Ops" + "é" * 200})

    headers = client.trace_headers
    assert headers["X-Request-ID"] == "a" * 32
    assert headers["X-Acting-User-Id"] == "u" * 64
    name = headers["X-Acting-User-Name"]
    assert name.isascii() and " " not in name and "/" not in name
    assert unquote(name).startswith("Siti Nur'aini binti Ahmad / Ops") and len(unquote(name)) == 128


def test_a_failing_audit_row_never_fails_a_write_that_landed(qt_api, fake_ss, monkeypatch):
    """Review (12 Nov): the audit row is best-effort; a write AutoCount accepted is still recorded."""
    from app.services import audit_service

    def broken(*_args, **_kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(audit_service, "log_audit", broken)
    client, db, world = qt_api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world))

    response = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "done"
    db.refresh(world.document)
    assert world.document.autocount_doc_no == "QT000777"
