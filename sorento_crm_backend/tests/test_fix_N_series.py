"""Phase 3 fix N2/N3/N5/N6/N7: guards `opportunity_service.py` did not have.

N2: customer_id must exist in scope (422); sales_agent_id must be a visible agent - own
    company or shared (422).
N3: a Won sales order must be in the opportunity's own company and non-cancelled (422
    SALES_ORDER_NOT_FOUND, reviewer should-fix 4).
N5: `created_by_label` never carries a staff email - a name, else "Sorento".
N6: a line's product must be active (422).
N7: once `outcome != 'open'`, further field edits are 422 OPPORTUNITY_CLOSED, on both the
    CRM PATCH and the portal PATCH (they share one `update_opportunity`).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.sales_agent import SalesAgent

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


def _company(db, *, name: str) -> str:
    from app.models.company import Company

    company = Company(id=_uid(), name=name, code=f"ZZT{_uid()[:6].upper()}")
    db.add(company)
    db.flush()
    return company.id


def _customer(db, company_id, *, name: str = "ZZT N Customer", agent_id=None):
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


def _product(db, *, name: str = "ZZT N Product", active: bool = True):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(id=_uid(), category_code=f"ZZT-{_uid()[:6]}", category_name="ZZT N Cat")
    brand = Brand(id=_uid(), brand_code=f"ZZT-{_uid()[:6]}", brand_name="ZZT N Brand")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT-{_uid()[:6]}", uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:6]}",
        product_name=name,
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal("50.00"),
        is_active=active,
    )
    db.add(product)
    db.flush()
    return product


def _sales_order(db, company_id, customer_id, *, status: str = "open"):
    from app.models.order import SalesOrder

    order = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=f"ZZT-{_uid()[:6]}",
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
    return TestClient(app), originals, user_id


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
            client, originals, user_id = _client(db, ALL)
            try:
                yield client, db, company_id, user_id
            finally:
                _restore(originals)


def _status_id(db, key: str) -> str:
    from app.models.status import Status

    return (
        db.query(Status)
        .filter(Status.entity_type == "sales_opportunity", Status.key == key)
        .one()
        .id
    )


# --------------------------------------------------------------------------- #
# N2: customer_id must exist; sales_agent_id must be a visible agent
# --------------------------------------------------------------------------- #


def test_fix_n2_nonexistent_customer_id_is_422(api):
    client, _db, _company_id, _user_id = api
    res = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N2 Opp",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": _uid(),
        },
    )
    assert res.status_code == 422, res.text


def test_fix_n2_sales_agent_from_another_company_is_422(api):
    client, db, company_id, _user_id = api
    other_company = _company(db, name="ZZT N2 Other Co")
    foreign_agent = SalesAgent(
        id=_uid(), sales_agent="ZZO-N2", description="ZZT N2 Agent", is_active=True,
        company_id=other_company,
    )
    db.add(foreign_agent)
    db.flush()
    customer = _customer(db, company_id)

    res = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N2 Opp Agent",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
            "sales_agent_id": foreign_agent.id,
        },
    )
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------- #
# N3: Won sales order must be this opportunity's own company and non-cancelled
# --------------------------------------------------------------------------- #


def test_fix_n3_won_with_a_cancelled_sales_order_is_422(api):
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id)
    order = _sales_order(db, company_id, customer.id, status="cancelled")

    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N3 Opp",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    opp_id = created.json()["id"]

    res = client.patch(
        f"{CRM_BASE}/{opp_id}",
        json={"status_id": _status_id(db, "won"), "sales_order_id": order.id},
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "SALES_ORDER_NOT_FOUND", res.text


def test_fix_n3_won_with_a_sales_order_from_another_company_is_422(api):
    client, db, company_id, _user_id = api
    other_company = _company(db, name="ZZT N3 Other Co")
    customer = _customer(db, company_id)
    foreign_order = _sales_order(db, other_company, customer.id, status="open")

    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N3 Opp B",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    opp_id = created.json()["id"]

    res = client.patch(
        f"{CRM_BASE}/{opp_id}",
        json={"status_id": _status_id(db, "won"), "sales_order_id": foreign_order.id},
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "SALES_ORDER_NOT_FOUND", res.text


# --------------------------------------------------------------------------- #
# N5: created_by_label never carries a staff email
# --------------------------------------------------------------------------- #


def test_fix_n5_created_by_label_hides_a_staff_email_behind_sorento(api):
    client, db, company_id, user_id = api
    from app.models.user import User

    # The acting user has no `name` on record - only an email, exactly the case that
    # used to fall through to `user.email`.
    db.add(User(id=user_id, email=f"{user_id}@zzo.test", name=None))
    db.flush()
    customer = _customer(db, company_id)

    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N5 Opp",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created_by_label"] == "Sorento", body
    assert "@" not in (body["created_by_label"] or ""), body


# --------------------------------------------------------------------------- #
# N6: line products must be active
# --------------------------------------------------------------------------- #


def test_fix_n6_inactive_product_in_a_line_is_422(api):
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id)
    inactive_product = _product(db, active=False)

    res = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N6 Opp",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
            "lines": [{"product_id": inactive_product.id, "qty": "1.00"}],
        },
    )
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------- #
# N7: once closed (outcome != 'open'), field edits are 422 OPPORTUNITY_CLOSED
# --------------------------------------------------------------------------- #


def test_fix_n7_editing_a_won_opportunity_is_422_opportunity_closed(api):
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N7 Opp",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    opp_id = created.json()["id"]

    won = client.patch(f"{CRM_BASE}/{opp_id}", json={"status_id": _status_id(db, "won")})
    assert won.status_code == 200, won.text

    res = client.patch(f"{CRM_BASE}/{opp_id}", json={"title": "ZZT N7 Renamed"})
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "OPPORTUNITY_CLOSED", res.text


def test_fix_n7_editing_a_lost_opportunity_is_422_on_the_portal_too(api):
    """update_opportunity is one shared function - proving the CRM side blocks it is not
    proof the portal PATCH route (a different router, same service call) does too."""
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT N7 Portal Opp",
            "expected_amount": "100.00",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    )
    assert created.status_code == 201, created.text
    opp_id = created.json()["id"]
    lost = client.patch(
        f"{CRM_BASE}/{opp_id}",
        json={"status_id": _status_id(db, "lost"), "lost_reason": "price"},
    )
    assert lost.status_code == 200, lost.text

    from app.services.sales import opportunity_service as svc

    opportunity = svc.get_opportunity_or_404(db, opp_id)
    with pytest.raises(Exception) as exc_info:
        svc.update_opportunity(db, opportunity, {"title": "ZZT Should Not Apply"})
    assert getattr(exc_info.value, "status_code", None) == 422
    assert getattr(exc_info.value, "code", None) == "OPPORTUNITY_CLOSED"
