"""Phase 3 nit: the opportunities list search also matches customer and prospect names,
not just title/number.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

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


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _customer(db, company_id, *, name: str):
    from app.models.order import Customer

    customer = Customer(
        id=_uid(), company_id=company_id, customer_code=f"ZZT-{_uid()[:6]}", customer_name=name
    )
    db.add(customer)
    db.flush()
    return customer


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


def test_fix_nit_list_search_matches_customer_name(api):
    client, db, company_id = api
    customer = _customer(db, company_id, name="ZZT Kedai Mine")
    created = client.post(
        CRM_BASE,
        json={
            "title": "Totally unrelated title",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text

    res = client.get(CRM_BASE, params={"query": "Kedai Mine"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pagination"]["total"] == 1, body
    assert body["data"][0]["id"] == created.json()["id"]


def test_fix_nit_list_search_matches_prospect_name(api):
    client, _db, _company_id = api
    created = client.post(
        CRM_BASE,
        json={
            "title": "Also unrelated",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "prospect_name": "ZZT Seri Indah Renovation",
        },
    )
    assert created.status_code == 201, created.text

    res = client.get(CRM_BASE, params={"query": "Seri Indah"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pagination"]["total"] == 1, body
