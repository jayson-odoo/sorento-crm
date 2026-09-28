"""Phase 3 fix S3: schema bounds on both the CRM and portal opportunity bodies.

Plan: documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md, section 16.

Before this fix `expected_amount`/`qty` had no upper bound or scale, `title`/`prospect_name`/
`lost_reason` had no (or too generous a) length cap, `lines` had no cap on item count, and every
id field (`customer_id`, `sales_agent_id`, `status_id`, `sales_order_id`, `product_id`) accepted
any string - a non-UUID id reached the ORM layer and failed as a raw `::uuid` cast error (a 500
with a Postgres error string in it) rather than a 422 the caller can act on.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.sales_agent import SalesAgent
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


def _customer(db, company_id, *, name: str = "ZZT S3 Customer"):
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


def _base_payload(**over):
    payload = {
        "title": "ZZT S3 Opportunity",
        "expected_amount": "1000.00",
        "expected_close_date": "2026-11-01",
        "prospect_name": "ZZT Prospect",
    }
    payload.update(over)
    return payload


def test_fix_s3_negative_amount_is_422(api):
    client, _db, _company_id = api
    res = client.post(CRM_BASE, json=_base_payload(expected_amount="-1.00"))
    assert res.status_code == 422, res.text


def test_fix_s3_empty_title_is_422(api):
    client, _db, _company_id = api
    res = client.post(CRM_BASE, json=_base_payload(title="   "))
    assert res.status_code == 422, res.text


def test_fix_s3_title_over_200_chars_is_422(api):
    client, _db, _company_id = api
    res = client.post(CRM_BASE, json=_base_payload(title="a" * 201))
    assert res.status_code == 422, res.text


def test_fix_s3_prospect_name_over_200_chars_is_422(api):
    client, _db, _company_id = api
    res = client.post(CRM_BASE, json=_base_payload(prospect_name="a" * 201))
    assert res.status_code == 422, res.text


def test_fix_s3_non_uuid_customer_id_is_422(api):
    client, _db, _company_id = api
    payload = _base_payload()
    payload.pop("prospect_name")
    payload["customer_id"] = "not-a-uuid"
    res = client.post(CRM_BASE, json=payload)
    assert res.status_code == 422, res.text


def test_fix_s3_non_uuid_product_id_in_line_is_422(api):
    client, _db, _company_id = api
    res = client.post(
        CRM_BASE, json=_base_payload(lines=[{"product_id": "not-a-uuid", "qty": "1.00"}])
    )
    assert res.status_code == 422, res.text


def test_fix_s3_zero_qty_is_422(api):
    client, _db, _company_id = api
    res = client.post(
        CRM_BASE, json=_base_payload(lines=[{"product_id": _uid(), "qty": "0"}])
    )
    assert res.status_code == 422, res.text


def test_fix_s3_more_than_100_lines_is_422(api):
    client, _db, _company_id = api
    lines = [{"product_id": _uid(), "qty": "1.00"} for _ in range(101)]
    res = client.post(CRM_BASE, json=_base_payload(lines=lines))
    assert res.status_code == 422, res.text


def test_fix_s3_non_uuid_status_id_on_update_is_422(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT S3 Update Target",
            "expected_amount": "500.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    opp_id = created.json()["id"]

    res = client.patch(f"{CRM_BASE}/{opp_id}", json={"status_id": "not-a-uuid"})
    assert res.status_code == 422, res.text


def test_fix_s3_lost_reason_over_150_chars_is_422(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT S3 Lost Reason Target",
            "expected_amount": "500.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    opp_id = created.json()["id"]

    res = client.patch(f"{CRM_BASE}/{opp_id}", json={"lost_reason": "a" * 151})
    assert res.status_code == 422, res.text
