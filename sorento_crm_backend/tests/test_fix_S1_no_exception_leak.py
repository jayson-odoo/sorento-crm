"""Phase 3 fix S1: an unexpected error is a 500 with NO exception text in the body.

`_reraise` in both `app/api/v1/sales/opportunities.py` and
`app/api/v1/public/portal_sales_opportunity.py` re-raises an `AppException`/`HTTPException` (a
deliberate, already-shaped response) as-is, but anything else used to become
`handle_internal_error(str(exc))` - the raw exception text, straight into the response body. A
DB-layer failure's `str()` is a SQL/psycopg string (table names, sometimes literal values), and
that is not something a 500 should ever show a caller.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.base import company_scope

from ._pg_fixture import blank_session

CRM_BASE = "/api/v1/sales/opportunities"

ALL = [
    "sales.opportunities.view",
    "sales.opportunities.add",
    "sales.opportunities.edit",
    "sales.opportunities.delete",
]

FORCED_MESSAGE = 'psycopg2.errors.UndefinedColumn: column "sql_injected_secret" does not exist'


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _client(db, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user_id = _uid()
    actor = {"id": user_id, "email": f"{user_id}@zzo.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture
def api():
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            sales_seed_service.run(db)
            db.flush()
            client, originals = _client(db, ALL)
            try:
                yield client, db, company_id
            finally:
                _restore(originals)


def test_fix_s1_crm_unexpected_error_is_500_with_no_exception_text(api, monkeypatch):
    from app.services.sales import opportunity_service as svc

    def _boom(*args, **kwargs):
        raise RuntimeError(FORCED_MESSAGE)

    monkeypatch.setattr(svc, "list_opportunities", _boom)

    client, _db, _company_id = api
    res = client.get(CRM_BASE)
    assert res.status_code == 500, res.text
    body_text = res.text
    assert "psycopg" not in body_text
    assert "sql_injected_secret" not in body_text
    assert FORCED_MESSAGE not in body_text


def test_fix_s1_portal_unexpected_error_is_500_with_no_exception_text(monkeypatch):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.main import app
    from app.models.access import RespondContact
    from app.models.portal import PortalToken
    from app.models.price_tag import ContactPortalFormOverride
    from app.models.sales_agent import SalesAgent
    from app.services.sales import opportunity_service as svc
    from app.services.sales import sales_seed_service

    @contextmanager
    def _portal_client(db, contact_id: str):
        def _override_get_db():
            yield db

        def _override_portal_token():
            return PortalToken(id=_uid(), contact_id=contact_id, space_id="zzt-space")

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = _override_portal_token
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                yield c
        finally:
            app.dependency_overrides.clear()

    def _boom(*args, **kwargs):
        raise RuntimeError(FORCED_MESSAGE)

    # `create_opportunity` runs inside the route's own try/except -> `_reraise`, unlike
    # the list route (an unwrapped read, caught by the app's generic handler instead) -
    # this is the endpoint that actually exercises the fix under test.
    monkeypatch.setattr(svc, "create_opportunity", _boom)

    with blank_session() as db:
        sales_seed_service.run(db)
        contact = RespondContact(
            id=_uid(), phone_number=f"+60{_uid().replace('-', '')[:9]}", name="ZZT S1 Contact"
        )
        db.add(contact)
        db.flush()
        db.add(
            ContactPortalFormOverride(
                id=_uid(), contact_id=contact.id, form_type="sales_opportunity", is_enabled=True
            )
        )
        agent = SalesAgent(
            id=_uid(),
            sales_agent=f"ZZO-{_uid()[:8]}".upper(),
            description="ZZT S1 Agent",
            is_active=True,
            contact_id=contact.id,
        )
        db.add(agent)
        db.flush()

        with _portal_client(db, contact.id) as client:
            res = client.post(
                "/api/v1/public/portal/sales-opportunities",
                json={
                    "title": "ZZT S1 Opp",
                    "expected_amount": "100.00",
                    "expected_close_date": "2026-11-01",
                    "prospect_name": "ZZT S1 Prospect",
                },
            )
            assert res.status_code == 500, res.text
            body_text = res.text
            assert "psycopg" not in body_text
            assert "sql_injected_secret" not in body_text
            assert FORCED_MESSAGE not in body_text
