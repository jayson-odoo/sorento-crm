"""Portal / public-view token requests must resolve to a real company scope.

The contact-facing surfaces authenticate with a ``token`` QUERY PARAM: no Bearer
JWT, no ``X-API-Key``. Those requests fell through the resolver to ``UNSET``
(fail-closed), which silently emptied every company-scoped read behind the
submission form - the debtor lookup and the delivery-order picker both returned
zero rows against a database holding 30k orders.

Scope is the INCUMBENT company, never ``None``: an all-companies portal would
show one company's customer another company's delivery orders.
"""
from __future__ import annotations

import os

import pytest
from fastapi import Request
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import UNSET
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import resolve_company_scope

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _request(path: str, query: str = "", portal_token: str | None = None) -> Request:
    headers = []
    if portal_token is not None:
        headers.append((b"x-portal-token", portal_token.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": query.encode(),
        }
    )


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/public/portal/lookups/debtors",
        "/api/v1/public/portal/lookups/delivery-orders",
        "/api/v1/public/portal/submissions",
        "/api/v1/public/view/stock-inquiry",
    ],
)
def test_portal_token_request_scopes_to_incumbent_company(db, path):
    scope = resolve_company_scope(_request(path, "token=abc123"), db)
    assert scope == frozenset({DEFAULT_COMPANY_ID})


def test_portal_scope_is_never_all_companies(db):
    """``None`` would mean every company - a cross-company leak on a public page."""
    scope = resolve_company_scope(
        _request("/api/v1/public/portal/lookups/debtors", "token=abc123"), db
    )
    assert scope is not None
    assert len(scope) == 1


def test_public_path_without_a_token_stays_fail_closed(db):
    scope = resolve_company_scope(_request("/api/v1/public/portal/lookups/debtors"), db)
    assert scope is UNSET


def test_blank_token_stays_fail_closed(db):
    scope = resolve_company_scope(
        _request("/api/v1/public/portal/lookups/debtors", "token=%20"), db
    )
    assert scope is UNSET


def test_non_public_path_with_a_token_param_stays_fail_closed(db):
    """The token param alone must not widen scope on an internal route: those
    authenticate with a JWT, and a stray ?token= must not buy any visibility."""
    scope = resolve_company_scope(
        _request("/api/v1/order-management/orders", "token=abc123"), db
    )
    assert scope is UNSET


# ---------------------------------------------------------------------------
# The submission portal (/portal/c/<slug>/...) sends X-Portal-Token, never
# ?token= - checking only the query param left that whole surface fail-closed
# while the /view links worked, which is why "customer name" stayed empty there.
# ---------------------------------------------------------------------------


def test_portal_header_token_resolves_a_scope(db):
    scope = resolve_company_scope(
        _request("/api/v1/public/portal/lookups/debtors", portal_token="abc123"), db
    )
    assert scope == frozenset({DEFAULT_COMPANY_ID})


def test_header_token_scopes_to_the_contacts_own_companies(db):
    """A contact mapped to a company reads THAT company, not the incumbent."""
    import uuid
    from datetime import datetime, timedelta

    from app.models.access import RespondContact
    from app.models.company import Company, RespondContactCompany
    from app.models.portal import PortalToken

    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name="ZZT Scope Co", code=f"zzt{uuid.uuid4().hex[:6]}"))
    contact_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=contact_id, phone_number=f"+6011{uuid.uuid4().hex[:8]}", name="Scoped Contact"
        )
    )
    db.flush()
    db.add(
        RespondContactCompany(
            id=str(uuid.uuid4()), respond_contact_id=contact_id, company_id=company_id
        )
    )
    token = f"zzt-{uuid.uuid4().hex}"
    db.add(
        PortalToken(
            id=str(uuid.uuid4()),
            token=token,
            contact_id=contact_id,
            space_id="zzt-space",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
    )
    db.flush()

    scope = resolve_company_scope(
        _request("/api/v1/public/portal/lookups/debtors", portal_token=token), db
    )
    assert scope == frozenset({company_id})


def test_unknown_header_token_falls_back_to_incumbent_not_zero_rows(db):
    """The route's own auth 401s an invalid token, so this is not an authorisation
    decision - only which company a VALID token reads. Zero rows here would show
    a contact an empty customer list instead of the legacy default."""
    scope = resolve_company_scope(
        _request("/api/v1/public/portal/submissions", portal_token="not-a-real-token"), db
    )
    assert scope == frozenset({DEFAULT_COMPANY_ID})


def test_internal_route_ignores_a_portal_token_header(db):
    scope = resolve_company_scope(
        _request("/api/v1/order-management/orders", portal_token="abc123"), db
    )
    assert scope is UNSET
