"""Phase 3 fix round 2, BLOCKER B-new: switching customer <-> prospect on an edit.

`opportunity_service.update_opportunity` fills whichever of customer_id/prospect_name the
caller did not send from the row already on the opportunity (`payload.get(key,
opportunity.<key>)`) - correct for "this field was not touched", wrong the moment a caller
means "clear the other side", which looks identical over `exclude_unset=True`: the untouched
key is just absent either way. The contract is: an explicit `null` on the other key clears it;
omitting it leaves it alone. These tests pin BOTH directions on BOTH routers directly against
that contract - the frontend fix (sending the explicit null) is proven by the vitest specs
alongside `SalesOpportunityDetail.tsx`/`SalesOpportunityPortalForm.tsx`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.sales_agent import SalesAgent
from app.models.base import company_scope

from ._pg_fixture import blank_session

CRM_BASE = "/api/v1/sales/opportunities"
PORTAL_BASE = "/api/v1/public/portal/sales-opportunities"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _customer(db, company_id, *, name: str = "ZZT Fix2 Customer", agent_id=None):
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


def _crm_client(db, permissions):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
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


def _restore_crm(originals) -> None:
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture
def crm_world():
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            sales_seed_service.run(db)
            db.flush()
            yield db, company_id


@pytest.fixture
def crm_api(crm_world):
    from app.services.audit_service import register_audit_listeners

    db, company_id = crm_world
    register_audit_listeners()
    perms = [
        "sales.opportunities.view",
        "sales.opportunities.add",
        "sales.opportunities.edit",
    ]
    client, originals = _crm_client(db, perms)
    try:
        yield client, db, company_id
    finally:
        _restore_crm(originals)


def test_fix2_bnew_crm_prospect_to_customer_sends_explicit_null(crm_api):
    client, db, company_id = crm_api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT Fix2 Prospect Opp",
            "expected_amount": "1000",
            "expected_close_date": "2026-11-01",
            "prospect_name": "ZZT Fix2 Prospect",
        },
    ).json()
    assert created["prospect_name"] == "ZZT Fix2 Prospect"

    res = client.patch(
        f"{CRM_BASE}/{created['id']}",
        json={"customer_id": customer.id, "prospect_name": None},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["customer_id"] == customer.id
    assert body["prospect_name"] is None


def test_fix2_bnew_crm_customer_to_prospect_sends_explicit_null(crm_api):
    client, db, company_id = crm_api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT Fix2 Customer Opp",
            "expected_amount": "1000",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    ).json()
    assert created["customer_id"] == customer.id

    res = client.patch(
        f"{CRM_BASE}/{created['id']}",
        json={"prospect_name": "ZZT Fix2 New Prospect", "customer_id": None},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["prospect_name"] == "ZZT Fix2 New Prospect"
    assert body["customer_id"] is None


def test_fix2_bnew_crm_switching_without_the_explicit_null_still_422s(crm_api):
    """Not a bug: proves the two tests above are exercising the real branch - omitting the
    other key (the old, broken frontend behaviour) still 422s CUSTOMER_AND_PROSPECT_TOGETHER,
    because the row's own value fills the gap. The frontend fix is sending the null."""
    client, db, company_id = crm_api
    customer = _customer(db, company_id)
    created = client.post(
        CRM_BASE,
        json={
            "title": "ZZT Fix2 Omit Opp",
            "expected_amount": "1000",
            "expected_close_date": "2026-11-01",
            "customer_id": customer.id,
        },
    ).json()

    res = client.patch(
        f"{CRM_BASE}/{created['id']}",
        json={"prospect_name": "ZZT Fix2 Whatever"},
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "CUSTOMER_AND_PROSPECT_TOGETHER"


# --------------------------------------------------------------------------- #
# Portal side
# --------------------------------------------------------------------------- #


def _contact(db, *, name: str = "ZZT Fix2 Salesperson"):
    from app.models.access import RespondContact

    contact = RespondContact(id=_uid(), phone_number=f"+60{_uid().replace('-', '')[:9]}", name=name)
    db.add(contact)
    db.flush()
    return contact


def _grant_kind(db, contact_id: str, kind: str = "sales_opportunity") -> None:
    from app.models.price_tag import ContactPortalFormOverride

    db.add(ContactPortalFormOverride(id=_uid(), contact_id=contact_id, form_type=kind, is_enabled=True))
    db.flush()


def _agent(db, *, contact_id=None, active: bool = True, company_id=None):
    row = SalesAgent(
        id=_uid(),
        sales_agent=f"ZZO-{_uid()[:8]}".upper(),
        description="ZZT Fix2 Agent",
        is_active=active,
        contact_id=contact_id,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture(autouse=True)
def _clear_overrides_after():
    yield
    app.dependency_overrides.clear()


def _portal_client(db, contact_id: str):
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    def _override_get_db():
        yield db

    def _override_portal_token():
        return PortalToken(id=_uid(), contact_id=contact_id, space_id="zzt-space")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_portal_token] = _override_portal_token
    return TestClient(app, headers={"X-Portal-Token": "zzt-token"})


def test_fix2_bnew_portal_prospect_to_customer_sends_explicit_null():
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        sales_seed_service.run(db)
        db.flush()
        company_id = _sorento(db)
        contact = _contact(db)
        _grant_kind(db, contact.id)
        agent = _agent(db, contact_id=contact.id, company_id=company_id)
        customer = _customer(db, company_id, agent_id=agent.id)

        with _portal_client(db, contact.id) as c:
            created = c.post(
                PORTAL_BASE,
                json={
                    "title": "ZZT Fix2 Portal Prospect",
                    "expected_amount": "500",
                    "expected_close_date": "2026-11-01",
                    "prospect_name": "ZZT Fix2 Portal Prospect Co",
                },
            ).json()
            assert created["prospect_name"] == "ZZT Fix2 Portal Prospect Co"

            res = c.patch(
                f"{PORTAL_BASE}/{created['id']}",
                json={"customer_id": customer.id, "prospect_name": None},
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["customer_id"] == customer.id
            assert body["prospect_name"] is None


def test_fix2_bnew_portal_customer_to_prospect_sends_explicit_null():
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        sales_seed_service.run(db)
        db.flush()
        company_id = _sorento(db)
        contact = _contact(db)
        _grant_kind(db, contact.id)
        agent = _agent(db, contact_id=contact.id, company_id=company_id)
        customer = _customer(db, company_id, agent_id=agent.id)

        with _portal_client(db, contact.id) as c:
            created = c.post(
                PORTAL_BASE,
                json={
                    "title": "ZZT Fix2 Portal Customer",
                    "expected_amount": "500",
                    "expected_close_date": "2026-11-01",
                    "customer_id": customer.id,
                },
            ).json()
            assert created["customer_id"] == customer.id

            res = c.patch(
                f"{PORTAL_BASE}/{created['id']}",
                json={"prospect_name": "ZZT Fix2 Portal New Prospect", "customer_id": None},
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["prospect_name"] == "ZZT Fix2 Portal New Prospect"
            assert body["customer_id"] is None
