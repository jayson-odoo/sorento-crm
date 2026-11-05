"""AC-QTSO-CRM round 5 (owner, hand test on db3): the credit term comes from the AutoCount debtor.

* the CRM sends NO `displayTerm` on a create or an update (SS fills it from the debtor's term);
* a refusal for a missing term (`DEBTOR_TERM_MISSING`, or today's `FIELD_REQUIRED` naming
  `displayTerm`) reads "AutoCount needs a credit term on debtor <our debtor code>. Set it in
  AutoCount and try again." using the debtor code WE sent, not text from SS.
"""
from __future__ import annotations

import pytest

from tests._ac_write_support import (
    BASE,
    DOC_KEY,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    add_amendment,
    api_fixture,
    delay_row,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
    refused_body,
)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


def _term_message(debtor):
    return f"AutoCount needs a credit term on debtor {debtor}. Set it in AutoCount and try again."


def test_an_so_with_a_po_term_creates_with_no_display_term(so_api, fake_ss):
    client, _db, world = so_api
    assert world.po.term_days == 60
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    assert "displayTerm" not in fake_ss.body(request)["header"]


def test_a_quotation_creates_with_no_display_term(qt_api, fake_ss):
    client, _db, world = qt_api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777", doc_key=5001))

    client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    [request] = fake_ss.to("POST", QT_CREATE_PATH)
    assert "displayTerm" not in fake_ss.body(request)["header"]


def test_an_so_update_never_sends_a_display_term(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    fake_ss.answers[("PATCH", f"{SO_CREATE_PATH}/{DOC_KEY}")] = (200, done_body())

    client.post(f"{BASE}/sales-orders/amendments/{amendment.id}/autocount")

    [request] = fake_ss.to("PATCH", f"{SO_CREATE_PATH}/{DOC_KEY}")
    assert "displayTerm" not in fake_ss.body(request)["header"]


TERM_REFUSALS = [
    pytest.param(refused_body("DEBTOR_TERM_MISSING", "debtor has no term"), id="debtor-term-missing"),
    pytest.param(refused_body("FIELD_REQUIRED", "displayTerm is required"), id="field-required-display-term"),
]


@pytest.mark.parametrize("answer", TERM_REFUSALS)
def test_an_so_create_refused_for_a_missing_term_names_our_debtor(so_api, fake_ss, answer):
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (422, answer)

    body = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount").json()

    assert body["outcome"] == "refused"
    assert body["message"] == _term_message(world.customer.customer_code)


@pytest.mark.parametrize("answer", TERM_REFUSALS)
def test_a_quotation_create_refused_for_a_missing_term_names_our_debtor(qt_api, fake_ss, answer):
    client, _db, world = qt_api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (422, answer)

    body = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount").json()

    assert body["outcome"] == "refused"
    assert body["message"] == _term_message(world.customer.customer_code)


def test_field_required_for_another_field_keeps_the_ordinary_refusal(so_api, fake_ss):
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (422, refused_body("FIELD_REQUIRED", "salesAgent is required"))

    body = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount").json()

    assert body["message"] == "AutoCount refused: salesAgent is required. Nothing was changed."
