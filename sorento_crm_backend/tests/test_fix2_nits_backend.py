"""Phase 3 fix round 2, backend nits.

- `sales_order_options` honours `q` for a customer-backed opportunity too, not only a
  prospect's (the customer-backed branch used to ignore `q` entirely, returning every one
  of that customer's orders no matter what was typed).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.sales_agent import SalesAgent
from app.models.base import company_scope

from ._pg_fixture import blank_session

BASE = "/api/v1/sales/opportunities"

ALL = [
    "sales.opportunities.view",
    "sales.opportunities.add",
    "sales.opportunities.edit",
    "sales.opportunities.delete",
]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    from sqlalchemy import text

    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _customer(db, company_id, *, name: str = "ZZT Fix2 Nit Customer", agent_id=None):
    from app.models.order import Customer

    customer = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{_uid()[:6]}",
        customer_name=name,
        sales_agent_id=agent_id,
    )
    db.add(customer)
    db.flush()
    return customer


def _sales_order(db, company_id, customer_id, *, status: str = "open", so_number=None):
    from app.models.order import SalesOrder

    order = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=so_number or f"ZZT-{_uid()[:6]}",
        customer_id=customer_id,
        status=status,
        order_date=date(2026, 10, 1),
    )
    db.add(order)
    db.flush()
    return order


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
    from app.services.audit_service import register_audit_listeners
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            sales_seed_service.run(db)
            db.flush()
            register_audit_listeners()
            client, originals = _client(db, ALL)
            try:
                yield client, db, company_id
            finally:
                _restore(originals)


def _create(client, *, customer_id, title="ZZT Fix2 Nit Opp", amount="1000.00", close_date="2026-11-01"):
    payload = {
        "title": title,
        "expected_amount": amount,
        "expected_close_date": close_date,
        "customer_id": customer_id,
    }
    res = client.post(BASE, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_fix2_nit_sales_order_options_honours_q_for_a_customer_backed_opportunity(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    findable = _sales_order(db, company_id, customer.id, so_number="ZZT-FINDME")
    other = _sales_order(db, company_id, customer.id, so_number="ZZT-OTHER")
    created = _create(client, customer_id=customer.id)

    res = client.get(f"{BASE}/{created['id']}/sales-order-options", params={"q": "FINDME"})
    assert res.status_code == 200, res.text
    ids = {o["id"] for o in res.json()["data"]}
    assert findable.id in ids
    assert other.id not in ids
