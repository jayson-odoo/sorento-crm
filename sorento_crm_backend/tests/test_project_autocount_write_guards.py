"""AC-QTSO-CRM fix round 1: who may write, in which company, and what the screen is told.

* the project guard (`assert_can_write_project`): a user who is neither owner nor collaborator,
  and a project that is not approved, are refused with no Shared Service call;
* company scope: another company's order, amendment or quotation answers the SAME 404 code as a
  missing id (no existence leak), on all five write routes;
* authentication: an `X-API-Key`-only call is 401 on all six routes; a malformed id is 404;
* a non-application error is answered with one fixed sentence;
* the cancel is recorded; the stale date is in Malaysia time; SS texts are capped.
"""
from __future__ import annotations

import uuid

import pytest

from tests._ac_write_support import (
    BOOK,
    BASE,
    EDIT,
    VIEW,
    WRITE,
    SO_CREATE_PATH,
    DOC_KEY,
    add_amendment,
    api_fixture,
    caps_with,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    order_row,
    put_in_autocount,
)
from tests.test_project_so_draft import _user

PERMS = [VIEW, EDIT, WRITE]
CAPS = "/api/v1/autocount/write-capabilities"


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", PERMS, switch=True)


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", PERMS, switch=True)


def _so_urls(db, world):
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()
    return {
        "create": f"{BASE}/sales-orders/{world.order.id}/autocount",
        "update": f"{BASE}/sales-orders/amendments/{amendment.id}/autocount",
        "cancel": f"{BASE}/sales-orders/{world.order.id}/autocount/cancel",
    }


def _qt_urls(world):
    return {
        "send": f"{BASE}/quotation-documents/{world.document.id}/autocount",
        "cancel": f"{BASE}/quotation-documents/{world.document.id}/autocount/cancel",
    }


def _act_as(user_id: str):
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)


# --------------------------------------------------------------------------- the project guard


@pytest.mark.parametrize("route", ["create", "update", "cancel"])
def test_a_user_who_is_not_owner_or_collaborator_is_refused_on_the_so_routes(so_api, fake_ss, route):
    client, db, world = so_api
    urls = _so_urls(db, world)
    _act_as(_user(db, "zzt-acwrite stranger"))
    db.commit()

    response = client.post(urls[route])

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "project_not_editable"
    assert fake_ss.calls == []


@pytest.mark.parametrize("route", ["send", "cancel"])
def test_a_user_who_is_not_owner_or_collaborator_is_refused_on_the_quotation_routes(qt_api, fake_ss, route):
    client, db, world = qt_api
    _act_as(_user(db, "zzt-acwrite stranger"))
    db.commit()

    response = client.post(_qt_urls(world)[route])

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "project_not_editable"
    assert fake_ss.calls == []


@pytest.mark.parametrize("route", ["create", "update", "cancel"])
def test_a_project_that_is_not_approved_is_refused_on_the_so_routes(so_api, fake_ss, route):
    from app.services.project_service import APPROVAL_PENDING

    client, db, world = so_api
    urls = _so_urls(db, world)
    world.project.approval_state = APPROVAL_PENDING
    db.commit()

    response = client.post(urls[route])

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "project_not_approved"
    assert fake_ss.calls == []


@pytest.mark.parametrize("route", ["send", "cancel"])
def test_a_project_that_is_not_approved_is_refused_on_the_quotation_routes(qt_api, fake_ss, route):
    from app.services.project_service import APPROVAL_PENDING

    client, db, world = qt_api
    world.project.approval_state = APPROVAL_PENDING
    db.commit()

    response = client.post(_qt_urls(world)[route])

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "project_not_approved"
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- company scope


def _other_company(db):
    from app.models.company import Company

    other = Company(id=str(uuid.uuid4()), name="ZZT Other", code=f"ZZT{uuid.uuid4().hex[:6]}".upper(), is_active=True)
    db.add(other)
    db.commit()
    return other


@pytest.mark.parametrize("route", ["create", "update", "cancel"])
def test_another_companys_order_answers_the_same_404_as_a_missing_id(so_api, fake_ss, route):
    from app.models.base import company_scope

    client, db, world = so_api
    urls = _so_urls(db, world)
    other = _other_company(db)
    missing = {
        "create": f"{BASE}/sales-orders/{uuid.uuid4()}/autocount",
        "update": f"{BASE}/sales-orders/amendments/{uuid.uuid4()}/autocount",
        "cancel": f"{BASE}/sales-orders/{uuid.uuid4()}/autocount/cancel",
    }[route]

    with company_scope(db, frozenset({other.id})):
        foreign = client.post(urls[route])
        absent = client.post(missing)

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json()["code"] == absent.json()["code"]
    assert fake_ss.calls == []


@pytest.mark.parametrize("route", ["send", "cancel"])
def test_another_companys_quotation_answers_the_same_404_as_a_missing_id(qt_api, fake_ss, route):
    from app.models.base import company_scope

    client, db, world = qt_api
    other = _other_company(db)
    absent_url = f"{BASE}/quotation-documents/{uuid.uuid4()}/autocount" + ("/cancel" if route == "cancel" else "")

    with company_scope(db, frozenset({other.id})):
        foreign = client.post(_qt_urls(world)[route])
        absent = client.post(absent_url)

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json()["code"] == absent.json()["code"]
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- authentication, ids


# Fixed ids, not uuid4() at import: pytest-xdist workers each collect the module, and a random id
# in a parametrize value gives every worker a different test list ("Different tests were collected").
_ID = "00000000-0000-4000-8000-0000000000a1"
ALL_ROUTES = [
    ("GET", f"{BASE}/autocount-write/capabilities"),
    ("POST", f"{BASE}/sales-orders/{_ID}/autocount"),
    ("POST", f"{BASE}/sales-orders/amendments/{_ID}/autocount"),
    ("POST", f"{BASE}/sales-orders/{_ID}/autocount/cancel"),
    ("POST", f"{BASE}/quotation-documents/{_ID}/autocount"),
    ("POST", f"{BASE}/quotation-documents/{_ID}/autocount/cancel"),
]


@pytest.mark.parametrize("method,path", ALL_ROUTES)
def test_an_api_key_alone_is_401(fake_ss, method, path):
    from fastapi.testclient import TestClient

    from app.main import app

    app.dependency_overrides.clear()
    response = TestClient(app).request(method, path, headers={"X-API-Key": "fxa_not_a_session"})

    assert response.status_code == 401, response.text
    assert fake_ss.calls == []


@pytest.mark.parametrize(
    "tail",
    ["sales-orders/not-a-uuid/autocount", "sales-orders/amendments/not-a-uuid/autocount",
     "sales-orders/not-a-uuid/autocount/cancel", "quotation-documents/not-a-uuid/autocount",
     "quotation-documents/not-a-uuid/autocount/cancel"],
)
def test_a_malformed_id_is_404_with_no_call(so_api, fake_ss, tail):
    client, _db, _world = so_api

    response = client.post(f"{BASE}/{tail}")

    assert response.status_code == 404
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- what the screen is told


def test_a_non_application_error_gets_one_fixed_sentence(so_api, fake_ss, monkeypatch):
    from app.services.project_autocount_write_service import ProjectAutocountWriteService

    def boom(self, *a, **k):
        raise RuntimeError("password=hunter2 relation \"x\" does not exist")

    monkeypatch.setattr(ProjectAutocountWriteService, "create_sales_order", boom)
    client, _db, world = so_api

    response = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    assert response.status_code == 500
    assert response.json()["message"] == "Something went wrong talking to AutoCount."
    assert "hunter2" not in response.text


def test_ss_warning_text_is_capped_at_500_characters(so_api, fake_ss):
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        200, done_body(warnings=[{"code": "W", "message": "w" * 900}])
    )

    body = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount").json()

    assert len(body["warnings"][0]["message"]) == 500


def test_a_done_so_cancel_is_recorded_with_when_and_by_whom(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    fake_ss.answers[("GET", CAPS)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{SO_CREATE_PATH}/{DOC_KEY}/cancel")] = (200, done_body())

    assert client.post(f"{BASE}/sales-orders/{world.order.id}/autocount/cancel").status_code == 200

    db.refresh(world.order)
    assert world.order.autocount_cancelled_at is not None
    assert str(world.order.autocount_cancelled_by) == str(world.owner)


def test_a_done_quotation_cancel_is_recorded(qt_api, fake_ss):
    client, db, world = qt_api
    world.document.autocount_doc_no, world.document.autocount_doc_key = "QT000777", "5001"
    world.document.autocount_book = BOOK
    db.commit()
    fake_ss.answers[("GET", CAPS)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", "/api/v1/autocount/documents/quotations/5001/cancel")] = (
        200, done_body(doc_no="QT000777", doc_key=5001)
    )

    assert client.post(_qt_urls(world)["cancel"]).status_code == 200

    db.refresh(world.document)
    assert world.document.autocount_cancelled_at is not None
    assert str(world.document.autocount_cancelled_by) == str(world.owner)


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2026-10-01T09:30:00", "01/10/2026"),
        ("2026-10-01T16:30:00Z", "02/10/2026"),   # 16:30Z is 00:30 the next day in Malaysia
        ("2026-10-01T16:30:00", "02/10/2026"),    # no zone: read as UTC
        ("2026-10-01T16:30:00+08:00", "01/10/2026"),
    ],
)
def test_the_stale_date_is_in_malaysia_time(stamp, expected):
    from app.services.project_autocount_write_service import _since

    assert _since(stamp) == expected


# --------------------------------------------------------------------------- fix round 2: cancel once, capped reason


def _cancel_on(fake_ss):
    fake_ss.answers[("GET", CAPS)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})


def test_a_second_so_cancel_is_409_already_cancelled_with_no_call(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    _cancel_on(fake_ss)
    fake_ss.answers[("POST", f"{SO_CREATE_PATH}/{DOC_KEY}/cancel")] = (200, done_body())
    url = f"{BASE}/sales-orders/{world.order.id}/autocount/cancel"
    assert client.post(url).status_code == 200
    calls = len(fake_ss.calls)

    again = client.post(url)

    assert again.status_code == 409 and again.json()["message"] == "Already cancelled in AutoCount."
    assert len(fake_ss.calls) == calls


def test_a_second_quotation_cancel_is_409_already_cancelled_with_no_call(qt_api, fake_ss):
    client, db, world = qt_api
    world.document.autocount_doc_no, world.document.autocount_doc_key = "QT000777", "5001"
    world.document.autocount_book = BOOK
    db.commit()
    _cancel_on(fake_ss)
    fake_ss.answers[("POST", "/api/v1/autocount/documents/quotations/5001/cancel")] = (
        200, done_body(doc_no="QT000777", doc_key=5001)
    )
    assert client.post(_qt_urls(world)["cancel"]).status_code == 200
    calls = len(fake_ss.calls)

    again = client.post(_qt_urls(world)["cancel"])

    assert again.status_code == 409 and again.json()["message"] == "Already cancelled in AutoCount."
    assert len(fake_ss.calls) == calls


def test_the_payloads_say_when_a_document_is_cancelled(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()

    def flag():
        return client.get(f"{BASE}/sales-orders/{world.order.id}").json()

    before = flag()
    world.order.autocount_cancelled_at = __import__("datetime").datetime.utcnow()
    db.commit()
    after = flag()

    assert (before.get("data", before)["autocount_cancelled"], after.get("data", after)["autocount_cancelled"]) == (False, True)


def test_the_quotation_payload_says_when_it_is_cancelled(qt_api, fake_ss):
    client, db, world = qt_api
    url = f"{BASE}/projects/{world.project.id}/quotation-documents/{world.document.id}"

    before = client.get(url).json()
    world.document.autocount_cancelled_at = __import__("datetime").datetime.utcnow()
    db.commit()
    after = client.get(url).json()

    assert (before.get("data", before)["autocount_cancelled"], after.get("data", after)["autocount_cancelled"]) == (False, True)


def test_a_capability_reason_from_a_gateway_error_is_capped(so_api, fake_ss):
    client, _db, _world = so_api
    fake_ss.answers[("GET", CAPS)] = (400, {"code": "BAD_REQUEST", "message": "z" * 900})

    body = client.get(f"{BASE}/autocount-write/capabilities").json()

    reason = body["sales_orders"]["create_doc"]["reason"]
    assert len(reason) == 500
