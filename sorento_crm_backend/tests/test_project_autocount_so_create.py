"""AC-QTSO-CRM Phase 2, RED: create a project sales order in AutoCount.

UAC U5-U9, U19. Route: `POST /api/v1/project-sales/sales-orders/{pso_id}/autocount`.

The fake Shared Service records every request, so the body is asserted field by field against the
plan's field map ("Field map, corrected to the pinned contract") and the Idempotency-Key against
"Idempotency-Key: crm-pso-{pso_id}-create".

Result wording (plan, "Results and refusals"): the route answers 200 with the result dict
`{outcome, message, doc_no, lines[], warnings[], skipped[], exploded[], waiting[]}` for every
answer the Shared Service gave, including a refusal, a 202 and an unreachable gateway, so the
dialog can render them. Only `outcome == "done"` writes to the CRM (U8, U9).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import pytest

from app.models.project_so import SEVERITY_HARD, ProjectSalesOrder, SODraftFinding
from tests._ac_write_support import (
    BASE,
    EDIT,
    SO_CREATE_PATH,
    SWITCHED_OFF_HERE,
    UNREACHABLE_TEXT,
    PENDING_TEXT,
    VIEW,
    WRITE,
    DOC_KEY,
    api_fixture,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    myt_today_candidates,
    put_in_autocount,
    refused_body,
)


def D(value) -> Decimal:
    return Decimal(str(value))


@pytest.fixture
def api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def api_no_agent(fake_ss):
    """No sales agent on the customer, so line 1 has neither its own nor a derived location."""
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True, with_agent=False)


@pytest.fixture
def api_blank_debtor(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True, debtor_code="   ")


@pytest.fixture
def api_draft(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True, publish=False)


def _url(world) -> str:
    return f"{BASE}/sales-orders/{world.order.id}/autocount"


def _read_back(world):
    return [
        detail(12009, world.product.product_code, "100", "392.85", "BRW-BB", "2026-07-01", 1),
        detail(12010, world.product2.product_code, "20", "50.00", "MWH-BB", "2026-08-01", 2),
    ]


def _done(world, **kw):
    return done_body(doc_no="SO412345", details=_read_back(world), **kw)


# --------------------------------------------------------------------------- U6: the body


def test_the_header_is_sent_field_by_field(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, _done(world))

    response = client.post(_url(world))

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    body = fake_ss.body(request)
    header = body["header"]
    assert body["companyCode"] == "SRT"
    assert header["debtorCode"] == world.customer.customer_code == "ZZT-DEBT-01"
    assert header["docDate"] in myt_today_candidates()
    assert header["currencyCode"] == "MYR"
    assert D(header["currencyRate"]) == 1
    assert header["yourPONo"] == world.po.po_number
    assert header["ref"] == world.project.title
    # Round 5 (owner): the term is the debtor's own in AutoCount; the CRM sends none.
    assert "displayTerm" not in header
    assert header["salesAgent"] == world.agent.sales_agent
    assert header["remark1"] == world.order.provisional_ref
    # AutoCount numbers the document, and refDocNo is create-never.
    assert "docNo" not in header and "refDocNo" not in header
    assert "docNo" not in body


def test_the_lines_carry_item_uom_qty_price_location_and_delivery_date(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, _done(world))

    client.post(_url(world))

    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    lines = fake_ss.body(request)["lines"]
    assert [l["itemCode"] for l in lines] == [
        world.product.product_code,
        world.product2.product_code,
    ]
    first, second = lines
    assert first["description"] == world.line1.description
    assert first["uom"] == world.line1.uom == "UNIT"
    assert D(first["qty"]) == 100
    assert D(first["unitPrice"]) == D("392.85")
    assert first["deliveryDate"] == "2026-07-01"
    assert D(second["qty"]) == 20 and D(second["unitPrice"]) == D("50.00")
    assert second["deliveryDate"] == "2026-08-01"
    # Discount is blank: not sent as a number.
    assert not first.get("discount") and not second.get("discount")


def test_location_is_the_lines_own_else_the_derived_one(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, _done(world))

    client.post(_url(world))

    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    first, second = fake_ss.body(request)["lines"]
    assert first["location"] == "BRW-BB"   # derived: agent group BB at the master site
    assert second["location"] == "MWH-BB"  # the line's own stock_location wins


def test_the_idempotency_key_is_built_from_the_order_id(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, _done(world))

    client.post(_url(world))

    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    assert request.headers["Idempotency-Key"] == f"crm-pso-{world.order.id}-create"
    assert request.headers["X-API-Key"]


def test_a_second_press_replays_with_the_same_key_and_body(api, fake_ss):
    """Pending leaves the CRM untouched, so the press can be repeated: SS replays its stored answer."""
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (202, {**_done(world), "outcome": "pending_verification"})

    client.post(_url(world))
    client.post(_url(world))

    first, second = fake_ss.to("POST", SO_CREATE_PATH)
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert first.content == second.content


# --------------------------------------------------------------------------- U7: refused in the CRM


def test_a_missing_debtor_code_is_refused_naming_the_customer_with_no_ss_call(api_blank_debtor, fake_ss):
    client, _db, world = api_blank_debtor

    response = client.post(_url(world))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "ac_missing_debtor"
    assert response.json()["message"] == f"No debtor code on {world.customer.customer_name}."
    assert fake_ss.calls == []


def test_a_line_with_no_location_is_refused_naming_the_line_with_no_ss_call(api_no_agent, fake_ss):
    client, _db, world = api_no_agent

    response = client.post(_url(world))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "ac_missing_location"
    assert response.json()["message"] == f"No location on line {world.line1.line_no}."
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- U8: done


def test_done_writes_the_document_number_key_and_last_modified(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        200, _done(world, last_modified="2026-11-05T10:15:00")
    )

    response = client.post(_url(world))

    assert response.status_code == 200, response.text
    db.refresh(world.order)
    assert world.order.autocount_doc_no == "SO412345"
    assert world.order.autocount_doc_key == str(DOC_KEY)
    assert world.order.autocount_last_modified == "2026-11-05T10:15:00"


def test_done_answers_the_read_back_lines_and_the_plain_sentence(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, _done(world))

    body = client.post(_url(world)).json()

    assert body["outcome"] == "done"
    assert body["message"] == "SO412345 created in AutoCount"
    assert body["doc_no"] == "SO412345"
    assert [(l["line_no"], l["item_code"]) for l in body["lines"]] == [
        (1, world.product.product_code),
        (2, world.product2.product_code),
    ]
    first = body["lines"][0]
    assert D(first["qty"]) == 100 and D(first["unit_price"]) == D("392.85")
    assert first["location"] == "BRW-BB" and first["delivery_date"] == "2026-07-01"
    # The lists the dialog renders exist even when empty.
    assert body["skipped"] == [] and body["exploded"] == [] and body["waiting"] == []


def test_ss_warnings_reach_the_result(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        200, _done(world, warnings=[{"code": "QT_ROW_VALUES_INHERITED", "message": "copied from QT"}])
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] == "done"
    assert "QT_ROW_VALUES_INHERITED" in str(body["warnings"])


# --------------------------------------------------------------------------- U9: nothing written unless done


def _assert_untouched(db, world):
    db.refresh(world.order)
    assert world.order.autocount_doc_no is None
    assert world.order.autocount_doc_key is None
    assert world.order.autocount_last_modified is None


def test_a_refusal_says_what_autocount_said_and_writes_nothing(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        422, refused_body("ITEM_NOT_FOUND", "Item code ZZT-X is not in AutoCount")
    )

    response = client.post(_url(world))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "refused"
    assert body["message"] == "AutoCount refused: Item code ZZT-X is not in AutoCount. Nothing was changed."
    _assert_untouched(db, world)


def test_a_202_pending_says_not_confirmed_yet_and_writes_nothing(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        202, {**_done(world), "outcome": "pending_verification"}
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] == "pending_verification"
    assert body["message"] == PENDING_TEXT
    _assert_untouched(db, world)


@pytest.mark.parametrize("code", ["WRITE_DISABLED", "WRITE_NOT_ALLOWED"])
def test_a_403_write_disabled_reads_as_switched_off_here_and_writes_nothing(api, fake_ss, code):
    client, db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (403, refused_body(code, "writes are off"))

    body = client.post(_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == SWITCHED_OFF_HERE
    _assert_untouched(db, world)


def test_a_502_mismatch_is_shown_as_autocounts_answer_and_writes_nothing(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        502, refused_body("READ_BACK_MISMATCH", "read-back differs", outcome="mismatch")
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] != "done"
    _assert_untouched(db, world)


def test_an_unreachable_gateway_says_so_and_writes_nothing(api, fake_ss):
    client, db, world = api
    fake_ss.transport_error = httpx.ConnectError("boom")

    response = client.post(_url(world))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "unreachable"
    assert body["message"] == UNREACHABLE_TEXT
    _assert_untouched(db, world)


# --------------------------------------------------------------------------- eligibility (409, no call)


def test_a_draft_order_is_not_eligible(api_draft, fake_ss):
    client, _db, world = api_draft

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_an_order_with_an_unacknowledged_hard_finding_is_not_eligible(api, fake_ss):
    client, db, world = api
    db.add(
        SODraftFinding(
            id=str(uuid.uuid4()), company_id=world.company_id,
            project_sales_order_id=world.order.id, severity=SEVERITY_HARD,
            code="line_arithmetic", detail="Line 1 does not add up.",
        )
    )
    db.commit()

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_an_order_already_in_autocount_is_not_eligible(api, fake_ss):
    client, db, world = api
    put_in_autocount(db, world)
    db.commit()

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_an_unknown_order_is_a_404_and_one_in_another_company_is_invisible(api, fake_ss):
    from app.models.company import Company
    from app.models.project_so import SO_STATUS_PUBLISHED

    client, db, world = api
    other = Company(id=str(uuid.uuid4()), name="ZZT Other", code=f"ZZT{uuid.uuid4().hex[:6]}".upper(), is_active=True)
    db.add(other)
    db.flush()
    foreign = ProjectSalesOrder(
        id=str(uuid.uuid4()), company_id=other.id, project_id=None,
        provisional_ref=f"ZZT-PSO-{uuid.uuid4().hex[:8]}", status=SO_STATUS_PUBLISHED,
    )
    db.add(foreign)
    db.commit()

    for target in (uuid.uuid4(), foreign.id):
        response = client.post(f"{BASE}/sales-orders/{target}/autocount")
        assert response.status_code == 404
        # An application 404 carries a code; a missing route answers a bare {"detail": "Not Found"}.
        assert response.json().get("code"), response.text
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- U19: server-resolved identity


def test_company_code_comes_from_the_orders_company_not_the_request(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, _done(world))

    response = client.post(
        _url(world),
        json={"companyCode": "MCH", "company_id": str(uuid.uuid4()), "docKey": 999, "docNo": "SO000001"},
    )

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    body = fake_ss.body(request)
    assert body["companyCode"] == "SRT"
    assert "999" not in request.content.decode() and "SO000001" not in request.content.decode()
    for cap in fake_ss.to("GET", "/api/v1/autocount/write-capabilities"):
        assert cap.url.params["companyCode"] == "SRT"
