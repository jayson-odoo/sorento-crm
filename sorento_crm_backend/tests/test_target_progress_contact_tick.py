"""CHATBOT-SALES-REPORT-TICK round 2 (owner 7 Nov, "strict"): the sales target route follows the
Respond contact's "Sales target" tick (`sales.sales_target`) on a chatbot call ONLY, through the
invoiced gate's helper (`invoiced_sales.contact_tick_or_slug`); everyone else keeps
`sales.reports.view`.

Plan: `documentation/plans/chatbot/PLAN-chatbot-sales-report-tick-07nov.md`. Postgres only, every
row seeded here (the seed helpers are `tests/test_sales_target_progress.py`'s).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.base import set_company_scope
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import unique_code
from tests.test_sales_target_progress import (  # noqa: F401  (db and _pin_today are fixtures)
    GRANT,
    ROUTE,
    _customer,
    _dealer_contact,
    _dealer_target,
    _me,
    _pin_today,
    _uid,
    db,
)

SHARED = "zzt-shared-chatbot-key"
OTHER = "zzt-another-integrations-key"
SLUG = "sales.reports.view"
#: What the chatbot's act-as user holds in the owner's case: no `sales.reports.view`.
NO_SLUG = ("order_management.orders.view",)
WITH_SLUG = (SLUG, "order_management.orders.view")


@pytest.fixture(autouse=True)
def _shared_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "external_api_key", SHARED, raising=False)


@contextmanager
def _client(db, *, allow, key=SHARED, auth_method="integration_api_key", **extra):
    from app.services.user_service import UserPermissionService

    user = User(id=_uid(), email=f"{unique_code('A')}@integrations.local", name="Act as", status="ACTIVE")
    db.add(user)
    db.flush()
    principal = {"id": user.id, "email": user.email, "auth_method": auth_method, **extra}

    def _override_db():
        yield db

    async def _scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _scope
    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in allow
    try:
        yield TestClient(app, headers={"X-API-Key": key})
    finally:
        UserPermissionService.check_user_has_permission = original
        app.dependency_overrides.clear()


def _dealer(db, *, ticked: bool):
    acct = _customer(db, "ZZT TICK DEALER", 1)
    target = _dealer_target(db, [acct])
    contact = _dealer_contact(db, acct, granted=(GRANT,) if ticked else ())
    return contact, target


def test_a_ticked_contact_gets_its_targets_when_act_as_lacks_the_slug(db):
    contact, target = _dealer(db, ticked=True)
    with _client(db, allow=NO_SLUG) as client:
        resp = client.get(ROUTE, params=_me(contact))
    assert resp.status_code == 200, resp.text
    assert target.target_no in resp.text


def test_an_unticked_contact_is_refused_even_when_act_as_holds_the_slug(db):
    contact, target = _dealer(db, ticked=False)
    with _client(db, allow=WITH_SLUG) as client:
        resp = client.get(ROUTE, params=_me(contact))
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "sales_target_not_enabled"
    assert target.target_no not in resp.text


def test_an_unticked_contact_without_the_slug_is_refused_as_not_enabled(db):
    contact, _ = _dealer(db, ticked=False)
    with _client(db, allow=NO_SLUG) as client:
        resp = client.get(ROUTE, params=_me(contact))
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "sales_target_not_enabled"


def test_another_integrations_key_naming_a_ticked_contact_still_needs_the_slug(db):
    contact, target = _dealer(db, ticked=True)
    with _client(db, allow=NO_SLUG, key=OTHER) as client:
        refused = client.get(ROUTE, params=_me(contact))
    assert refused.status_code == 403, refused.text
    assert target.target_no not in refused.text
    with _client(db, allow=WITH_SLUG, key=OTHER) as client:
        assert client.get(ROUTE, params=_me(contact)).status_code == 200


def test_an_identity_read_keeps_the_slug(db):
    """The AI panel (`key_user_id`) has no contact: permissions decide, the slug included."""
    with _client(db, allow=("sales.targets.view",), key_user_id="zzt-act-as") as client:
        refused = client.get(ROUTE)
    assert refused.status_code == 403, refused.text
    with _client(db, allow=(SLUG, "sales.targets.view"), key_user_id="zzt-act-as") as client:
        assert client.get(ROUTE).status_code == 200


def test_a_session_user_naming_a_ticked_contact_still_needs_the_slug(db):
    """A Bearer session is no chatbot call; the route stays API-key only, and the slug still stands."""
    contact, _ = _dealer(db, ticked=True)
    with _client(db, allow=NO_SLUG, auth_method="jwt") as client:
        resp = client.get(ROUTE, params=_me(contact))
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") != "sales_target_not_enabled"


def test_an_identity_read_without_the_staff_target_slug_is_refused(db):
    """The slug alone is not enough on an identity read: the staff member's `sales.targets.view` stands in
    for the contact's tick (reviewer kill test T7)."""
    with _client(db, allow=(SLUG,), key_user_id="zzt-act-as") as client:
        resp = client.get(ROUTE)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "sales_target_not_enabled"
