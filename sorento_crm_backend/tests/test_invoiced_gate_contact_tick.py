"""CHATBOT-SALES-REPORT-TICK (owner 7 Nov): the invoiced sales gate follows the Respond contact's
"Sales report" tick (`sales_orders.sales_report`) on a chatbot call, and stays the
`sales.reports.view` slug for everyone else.

Plan: `documentation/plans/chatbot/PLAN-chatbot-sales-report-tick-07nov.md`. Postgres only,
every row seeded here.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  (import order)
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session
from tests.test_sales_yearly_routes import _client, _user
from tests.test_top_selling_report import _access, _as_contact, _contact

REPORT_ASK = "/api/v1/order-management/report-ask"
TOP = "/api/v1/order-management/top-selling"
PERIOD = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
KEY = {"X-API-Key": "k"}
#: The act-as user of the chatbot's key holds the orders slug only: no `sales.reports.view`.
ORDERS_ONLY = ("order_management.orders.view",)
WITH_REPORTS = ("order_management.orders.view", "sales.reports.view")
REFUSED = "invoiced_needs_sales_reports"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _key_user(db) -> dict:
    """The chatbot's principal: an integration key's act-as user."""
    return {**_user(db, DEFAULT_COMPANY_ID), "auth_method": "integration_api_key", "integration_id": "zzt-int"}


def _staff_contact(db, *, ticked: bool):
    """An office contact (every customer), ticked or not: the owner's Mr Loo."""
    contact = _contact(db, granted=ticked)
    _access(db, contact, "Sorento Office")
    db.commit()
    return contact


def _ask(client, contact, **params):
    q = {**PERIOD, "basis": "invoiced", **_as_contact(contact), **params}
    return client.get(REPORT_ASK, params=q, headers=KEY)


# ------------------------------------------------------------------ the helper


def test_a_ticked_contact_opens_invoiced_whatever_the_act_as_user_holds(db):
    from app.services.sales.invoiced_sales import may_read_invoiced

    contact = _staff_contact(db, ticked=True)
    with _client(db, _key_user(db), allow=ORDERS_ONLY):
        assert may_read_invoiced(db, _key_user(db), **_as_contact(contact)) is True


def test_an_unticked_contact_is_refused_even_when_the_act_as_user_holds_the_slug(db):
    from app.services.sales.invoiced_sales import require_invoiced_access

    contact = _staff_contact(db, ticked=False)
    with _client(db, _key_user(db), allow=WITH_REPORTS):
        with pytest.raises(AppException) as refused:
            require_invoiced_access(db, _key_user(db), **_as_contact(contact))
    assert refused.value.status_code == 403
    assert refused.value.code == REFUSED


def test_a_contact_the_crm_does_not_know_is_refused(db):
    from app.services.sales.invoiced_sales import may_read_invoiced

    with _client(db, _key_user(db), allow=WITH_REPORTS):
        assert may_read_invoiced(db, _key_user(db), contact_id="zzt-nobody", space_id="zzt-space") is False


def test_a_session_user_naming_a_ticked_contact_still_needs_the_slug(db):
    """The CRM UI (a Bearer session) keeps the role slug: a contact pair is no way past it."""
    from app.services.sales.invoiced_sales import may_read_invoiced

    contact = _staff_contact(db, ticked=True)
    session_user = {**_user(db, DEFAULT_COMPANY_ID), "auth_method": "jwt"}
    with _client(db, session_user, allow=ORDERS_ONLY):
        assert may_read_invoiced(db, session_user, **_as_contact(contact)) is False
        assert may_read_invoiced(db, session_user) is False
    with _client(db, session_user, allow=WITH_REPORTS):
        assert may_read_invoiced(db, session_user) is True


def test_an_identity_read_keeps_the_slug_on_both_users(db):
    """The AI panel (`key_user_id`) is answered by permissions, never a contact tick."""
    from app.services.sales.invoiced_sales import may_read_invoiced

    contact = _staff_contact(db, ticked=True)
    staff = {**_user(db, DEFAULT_COMPANY_ID), "auth_method": "integration_api_key", "key_user_id": "zzt-act-as"}
    with _client(db, staff, allow=ORDERS_ONLY):
        assert may_read_invoiced(db, staff, **_as_contact(contact)) is False
    with _client(db, staff, allow=WITH_REPORTS):
        assert may_read_invoiced(db, staff) is True


def test_a_key_with_no_contact_keeps_the_slug(db):
    from app.services.sales.invoiced_sales import may_read_invoiced

    user = _key_user(db)
    with _client(db, user, allow=ORDERS_ONLY):
        assert may_read_invoiced(db, user) is False
        assert may_read_invoiced(db, user, contact_id="x", space_id=None) is False
    with _client(db, user, allow=WITH_REPORTS):
        assert may_read_invoiced(db, user) is True


# ------------------------------------------------------------------ the chatbot routes


def test_report_ask_invoiced_answers_a_ticked_contact_when_act_as_lacks_the_slug(db):
    contact = _staff_contact(db, ticked=True)
    with _client(db, _key_user(db), allow=ORDERS_ONLY) as client:
        resp = _ask(client, contact)
    assert resp.status_code == 200, resp.text
    assert resp.json()["basis"] == "invoiced"


def test_report_ask_invoiced_refuses_an_unticked_contact_with_todays_reply(db):
    contact = _staff_contact(db, ticked=False)
    with _client(db, _key_user(db), allow=WITH_REPORTS) as client:
        resp = _ask(client, contact)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == REFUSED
    assert "sales reports permission" in resp.json()["message"]


def test_report_ask_delivered_is_unchanged_for_an_unticked_contact(db):
    """Only the invoiced gate moved: the other sales bases keep the route's own reveal check."""
    contact = _staff_contact(db, ticked=False)
    with _client(db, _key_user(db), allow=WITH_REPORTS) as client:
        resp = _ask(client, contact, basis="delivered")
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "sales_report_not_enabled"


def test_top_selling_invoiced_answers_a_ticked_contact_when_act_as_lacks_the_slug(db):
    contact = _staff_contact(db, ticked=True)
    with _client(db, _key_user(db), allow=ORDERS_ONLY) as client:
        resp = client.get(TOP, params={"rank_by": "amount", **PERIOD, **_as_contact(contact)}, headers=KEY)
    assert resp.status_code == 200, resp.text


def test_top_selling_invoiced_refuses_an_unticked_contact(db):
    contact = _staff_contact(db, ticked=False)
    with _client(db, _key_user(db), allow=WITH_REPORTS) as client:
        resp = client.get(TOP, params={"rank_by": "amount", **PERIOD, **_as_contact(contact)}, headers=KEY)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == REFUSED


def test_top_selling_invoiced_for_a_ui_user_still_needs_the_slug(db):
    session_user = {**_user(db, DEFAULT_COMPANY_ID), "auth_method": "jwt"}
    with _client(db, session_user, allow=ORDERS_ONLY) as client:
        refused = client.get(TOP, params={"rank_by": "amount", **PERIOD})
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == REFUSED
    with _client(db, session_user, allow=WITH_REPORTS) as client:
        assert client.get(TOP, params={"rank_by": "amount", **PERIOD}).status_code == 200
