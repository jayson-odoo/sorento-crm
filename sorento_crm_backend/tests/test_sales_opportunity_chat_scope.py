"""SALES-TARGET-CHAT slice 2, UAC O1-6: the gate sets the company scope from the RESOLVED contact.

Deliberately does NOT override `apply_company_scope`: the scope the request carried is whatever the
real resolver gives an API-key call, and the gate must narrow it to the contact's own companies
(the portal's `_require_agents`). Two companies: A (Sorento, default) and B (Mocha).
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db, get_external_api_user
from app.models.base import set_company_scope
from app.models.company import RespondContactCompany
from app.models.sales import SalesOpportunity
from app.models.sales_agent import SalesAgent
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests.test_sales_opportunity_chat_routes import CREATE, OPTIONS, _body, _enable_form, _me
from tests.test_sales_target_progress import _contact, _customer


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _client(db):
    user = User(id=_uid(), email=f"{unique_code('A')}@integrations.local", name="Act as", status="ACTIVE")
    db.add(user)
    db.flush()
    principal = {"id": user.id, "email": user.email}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_external_api_user] = lambda: principal
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    from unittest.mock import patch

    try:
        with patch("app.api.v1.external.permissions.UserPermissionService") as service:
            service.return_value.check_user_has_permission.return_value = True
            yield TestClient(app, headers={"X-API-Key": "k"})
    finally:
        app.dependency_overrides.clear()


def test_opp_company_scope_is_the_contacts():
    with blank_session() as db:
        set_company_scope(db, None)
        from app.services.sales import sales_seed_service

        sales_seed_service.run(db)
        seed_mocha(db)
        contact = _contact(db, companies=(MOCHA_ID,))
        shared = SalesAgent(
            id=_uid(), sales_agent=f"ZZTSH{unique_code('S')[-6:]}", description="Shared", company_id=None,
            is_active=True, contact_id=contact.id,
        )
        db.add(shared)
        db.flush()
        _enable_form(db, contact)
        in_a = _customer(db, "ZZT SCOPE DEALER ALPHA", 1, agent=shared, company_id=DEFAULT_COMPANY_ID)
        in_b = _customer(db, "ZZT SCOPE DEALER BRAVO", 1, agent=shared, company_id=MOCHA_ID)
        set_company_scope(db, None)

        with _client(db) as c:
            options = c.get(OPTIONS, params={**_me(contact), "q": "ZZT SCOPE DEALER"})
            assert options.status_code == 200, options.text
            assert [i["customer_id"] for i in options.json()["items"]] == [in_b.id], options.text
            assert in_a.customer_name not in options.text

            created = c.post(CREATE, json=_body(contact))
            assert created.status_code == 201, created.text
            set_company_scope(db, None)
            row = db.query(SalesOpportunity).filter(
                SalesOpportunity.opportunity_no == created.json()["opportunity_no"]
            ).one()
            assert row.company_id == MOCHA_ID
