"""AC-QTSO-CRM Phase 2, RED: the capability mapping, and Cancel in AutoCount.

UAC U14, U19, U20, R4. Plan, "Service" and "Cancel (U14)":

* `ProjectAutocountWriteService(db, client=None).capabilities(company_id)` returns
  `{"sales_orders": {op: {enabled, reason}}, "quotations": {...}}` over the ops
  `create_doc, edit_doc, add_line, delete_line, cancel_doc`. Reasons:
    VENDOR_UNSUPPORTED (and any unknown code)                      -> "Waiting for AutoCount"
    WRITE_DISABLED / WRITE_NOT_ALLOWED / WRITE_COMPANY_NOT_TEST    -> "Changes to AutoCount are switched off here"
    gateway unreachable                                            -> every op "Could not reach AutoCount"
* Cancel reads the feed: `cancel_doc` off -> 409 `ac_waiting` "Waiting for AutoCount" with NO
  write call; `cancel_doc` on -> the cancel POST goes. Nothing is hard-coded off.
"""
from __future__ import annotations

import httpx
import pytest

from tests._pg_fixture import blank_session
from tests._ac_write_support import (
    BASE,
    CAPS_PATH,
    DOC_KEY,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    SWITCHED_OFF_HERE,
    UNREACHABLE_TEXT,
    VIEW,
    WAITING,
    WRITE,
    api_fixture,
    cap_entry,
    caps_with,
    default_capabilities,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
    refused_body,
    SS_API_KEY,
    SS_BASE_URL,
)
from tests.support.fake_foundryx import seed_foundryx_connection

OPS = ("create_doc", "edit_doc", "add_line", "delete_line", "cancel_doc")
KIND_KEYS = {"sales_orders": "sales-orders", "quotations": "quotations"}


@pytest.fixture
def svc(fake_ss):
    from tests.test_project_so_draft import _sorento

    with blank_session() as db:
        company_id = _sorento(db)
        seed_foundryx_connection(db, base_url=SS_BASE_URL, api_key=SS_API_KEY)
        db.flush()
        from app.services.project_autocount_write_service import ProjectAutocountWriteService

        yield ProjectAutocountWriteService(db), company_id


# --------------------------------------------------------------------------- the mapping


def test_the_pinned_feed_maps_to_enabled_and_waiting(svc, fake_ss):
    service, company_id = svc

    caps = service.capabilities(company_id)

    assert set(caps) == {"sales_orders", "quotations"}
    for group in caps.values():
        assert set(group) == set(OPS)
        for op in ("create_doc", "edit_doc", "add_line"):
            assert group[op] == {"enabled": True, "reason": None}
        for op in ("delete_line", "cancel_doc"):
            assert group[op] == {"enabled": False, "reason": WAITING}


def test_the_company_code_is_the_records_company_code(svc, fake_ss):
    service, company_id = svc

    service.capabilities(company_id)

    [request] = fake_ss.to("GET", CAPS_PATH)
    assert request.url.params["companyCode"] == "SRT"
    assert request.headers["X-API-Key"] == SS_API_KEY


@pytest.mark.parametrize(
    "code,reason",
    [
        ("VENDOR_UNSUPPORTED", WAITING),
        ("SOMETHING_SS_ADDED_LATER", WAITING),
        (None, WAITING),
        ("WRITE_DISABLED", SWITCHED_OFF_HERE),
        ("WRITE_NOT_ALLOWED", SWITCHED_OFF_HERE),
        ("WRITE_COMPANY_NOT_TEST", SWITCHED_OFF_HERE),
    ],
)
def test_each_reason_code_reads_in_plain_words(svc, fake_ss, code, reason):
    service, company_id = svc
    fake_ss.answers[("GET", CAPS_PATH)] = (
        200, {"capabilities": caps_with(create_doc=(False, code))}
    )

    caps = service.capabilities(company_id)

    assert caps["sales_orders"]["create_doc"] == {"enabled": False, "reason": reason}
    assert caps["quotations"]["create_doc"] == {"enabled": False, "reason": reason}


def test_an_op_the_feed_does_not_list_is_waiting_not_enabled(svc, fake_ss):
    service, company_id = svc
    feed = [e for e in default_capabilities() if e["op"] != "add_line"]
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"capabilities": feed})

    caps = service.capabilities(company_id)

    assert caps["sales_orders"]["add_line"] == {"enabled": False, "reason": WAITING}


def test_an_unreachable_gateway_disables_every_op_with_could_not_reach(svc, fake_ss):
    service, company_id = svc
    fake_ss.transport_error = httpx.ConnectError("down")

    caps = service.capabilities(company_id)

    for group in caps.values():
        assert set(group) == set(OPS)
        assert all(v == {"enabled": False, "reason": UNREACHABLE_TEXT} for v in group.values())


def test_a_feed_that_turns_cancel_on_is_believed(svc, fake_ss):
    """No hard-coded off (U14): the day SS ships cancel_doc, the CRM follows the feed."""
    service, company_id = svc
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"capabilities": caps_with(cancel_doc=(True, None))})

    caps = service.capabilities(company_id)

    assert caps["sales_orders"]["cancel_doc"] == {"enabled": True, "reason": None}
    assert caps["quotations"]["cancel_doc"] == {"enabled": True, "reason": None}


# --------------------------------------------------------------------------- cancel a sales order


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


def _so_cancel_url(world) -> str:
    return f"{BASE}/sales-orders/{world.order.id}/autocount/cancel"


def test_so_cancel_with_cancel_doc_off_is_409_ac_waiting_and_makes_no_write_call(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()

    response = client.post(_so_cancel_url(world))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ac_waiting"
    assert response.json()["message"] == WAITING
    assert fake_ss.writes() == []
    assert fake_ss.to("GET", CAPS_PATH), "the feed is read, not assumed"


def test_so_cancel_with_cancel_doc_on_posts_the_cancel(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"capabilities": caps_with(cancel_doc=(True, None))})
    cancel_path = f"{SO_CREATE_PATH}/{DOC_KEY}/cancel"
    fake_ss.answers[("POST", cancel_path)] = (200, done_body())

    response = client.post(_so_cancel_url(world))

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", cancel_path)
    assert request.headers["Idempotency-Key"] == f"crm-pso-{world.order.id}-cancel"
    assert fake_ss.body(request)["companyCode"] == "SRT"
    assert response.json()["outcome"] == "done"
    assert [r for r in fake_ss.calls if r.method == "DELETE"] == [], "never delete a document"


def test_so_cancel_shows_a_refusal_as_autocounts_answer(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{SO_CREATE_PATH}/{DOC_KEY}/cancel")] = (
        422, refused_body("HAS_DELIVERIES", "Document has delivered lines")
    )

    body = client.post(_so_cancel_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == "AutoCount refused: Document has delivered lines. Nothing was changed."


def test_so_cancel_of_an_order_not_in_autocount_is_409_with_no_call(so_api, fake_ss):
    client, _db, world = so_api

    response = client.post(_so_cancel_url(world))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- cancel a quotation


def _qt_in_autocount(db, world) -> None:
    world.document.autocount_doc_no = "QT000777"
    world.document.autocount_doc_key = "5001"
    world.document.autocount_last_modified = "2026-10-21T08:00:00"
    world.document.autocount_issue_id = world.issue.id
    db.commit()


def _qt_cancel_url(world) -> str:
    return f"{BASE}/quotation-documents/{world.document.id}/autocount/cancel"


def test_quotation_cancel_with_cancel_doc_off_is_409_ac_waiting_and_makes_no_write_call(qt_api, fake_ss):
    client, db, world = qt_api
    _qt_in_autocount(db, world)

    response = client.post(_qt_cancel_url(world))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ac_waiting"
    assert response.json()["message"] == WAITING
    assert fake_ss.writes() == []


def test_quotation_cancel_with_cancel_doc_on_posts_the_cancel(qt_api, fake_ss):
    client, db, world = qt_api
    _qt_in_autocount(db, world)
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"capabilities": caps_with(cancel_doc=(True, None))})
    cancel_path = f"{QT_CREATE_PATH}/5001/cancel"
    fake_ss.answers[("POST", cancel_path)] = (200, done_body(doc_no="QT000777", doc_key=5001))

    response = client.post(_qt_cancel_url(world))

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", cancel_path)
    assert request.headers["Idempotency-Key"] == f"crm-qt-{world.document.id}-cancel"
    assert fake_ss.body(request)["companyCode"] == "SRT"


def test_quotation_cancel_of_a_quotation_not_in_autocount_is_409_with_no_call(qt_api, fake_ss):
    client, _db, world = qt_api

    response = client.post(_qt_cancel_url(world))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []
