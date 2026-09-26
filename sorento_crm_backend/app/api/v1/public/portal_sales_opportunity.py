"""Portal opportunity logging for salespeople (plan 3.5; section 16, slice S2).

Mounted at ``/api/v1/public/portal`` BEFORE ``portal.router``, same reason `portal_price_tag`
is (D49): both declare ``/sales-opportunities...`` shaped paths under one prefix, and the
first router whose path matches wins.

Gates, in order (section 16): the `sales` module off under strict mode (403
``MODULE_NOT_ENABLED``, the same semantics `require_module_enabled` gives a JWT caller, minus
the role bypass a portal contact has no role to claim), the kind not visible (403
``FORM_TYPE_NOT_VISIBLE``, ``require_form_visible``), no active linked agent (403
``NOT_A_SALES_AGENT``). Another agent's id is 404, never 403, so ids cannot be probed.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.database import get_db
from app.models.base import company_scope, get_company_scope, set_company_scope
from app.models.portal import PortalToken
from app.models.sales_agent import SalesAgent
from app.schemas.sales import (
    PortalSalesOpportunityCreate,
    PortalSalesOpportunityUpdate,
    SalesOpportunityCustomerOptionsResponse,
    SalesOpportunityMeta,
)
from app.services.error_handler import AppException, handle_internal_error
from app.services.portal_form_visibility_service import require_form_visible
from app.services.sales import opportunity_service as svc
from app.services.sales.portal_agent import agent_for_contact
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter(tags=["public-portal-sales-opportunity"])
logger = logging.getLogger(__name__)

_FORM_TYPE = "sales_opportunity"


def _require_module_enabled(db: Session) -> None:
    """Same semantics as `app.modules.runtime.guards.require_module_enabled`, minus the
    admin/superadmin role bypass - a portal contact has no CRM role to claim one with."""
    from app.config import settings
    from app.modules.runtime.installer import (
        DEFAULT_TENANT_ID,
        is_module_enabled,
        tenant_has_any_module_row,
    )

    if not getattr(settings, "module_guard_strict", False):
        return
    if not tenant_has_any_module_row(db, DEFAULT_TENANT_ID):
        return
    if not is_module_enabled(db, DEFAULT_TENANT_ID, "sales"):
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Module not enabled: sales",
            code="MODULE_NOT_ENABLED",
        )


def _require_agent(db: Session, token: PortalToken) -> SalesAgent:
    _require_module_enabled(db)
    require_form_visible(db, token.contact_id, _FORM_TYPE)
    agent = agent_for_contact(db, token.contact_id)
    if agent is None or not agent.is_active:
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You are not set up as a sales agent yet.",
            code="NOT_A_SALES_AGENT",
        )
    # Attribute an audited write in this request to the acting contact, the same stamp
    # `get_portal_token` itself makes - set here too so it holds even when a caller (a
    # test) overrides that dependency directly (LESSONS: db.info survives the thread hop
    # a contextvar would not).
    db.info["actor_contact_id"] = str(token.contact_id)
    # Phase 3 fix S2: scope the WHOLE request to this agent's own company as soon as the
    # agent is known (or leave it unrestricted - `None` - for a single-tenant install
    # where the agent carries no company_id), so every query for the rest of the request
    # - the customer lookup inside `_resolve_company` included - runs under the
    # company-scope auto-filter and can never widen past it.
    set_company_scope(db, frozenset({agent.company_id}) if agent.company_id else None)
    return agent


def _resolve_company(db: Session, *, customer_id: Optional[str], agent: SalesAgent) -> str:
    """Never widens past what `_require_agent` already scoped this request to (Phase 3
    fix S2): the customer's own company (a SCOPED lookup - `Customer` is
    `CompanyScopedMixin`, so a customer outside the current scope resolves to nothing
    rather than to its real, out-of-scope company), else the agent's own company but
    only when the current scope already permits it (an agent whose `company_id` somehow
    disagrees with the request's own scope must never widen it), else the scope's one
    company if it names exactly one, else the single-tenant default.

    No unordered `Company.first()`: a `LIMIT 1` with no `ORDER BY` is Postgres's choice,
    not a business rule, and it can hand back a company neither the customer nor the
    agent has any connection to at all.
    """
    from app.models.order import Customer
    from app.services.company_scope import DEFAULT_COMPANY_ID

    scope = get_company_scope(db)

    if customer_id:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if customer is not None and customer.company_id:
            return customer.company_id

    if agent.company_id and (scope is None or (isinstance(scope, frozenset) and agent.company_id in scope)):
        return agent.company_id

    if isinstance(scope, frozenset) and len(scope) == 1:
        return next(iter(scope))

    return DEFAULT_COMPANY_ID


def _reraise(db: Session, exc: Exception):
    """See `app.api.v1.sales.opportunities._reraise` - same contract, same reason
    (Phase 3 fix S1): a bare `str(exc)` on an unexpected error is a SQL/psycopg
    string, which a portal-facing 500 must not leak.
    """
    db.rollback()
    if hasattr(exc, "status_code"):
        raise exc
    logger.error("Unexpected error in portal sales opportunity route: %s", exc, exc_info=True)
    raise handle_internal_error()


@router.get("/sales-opportunities")
def portal_list_sales_opportunities(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    # The gate runs unwrapped (LESSONS: a bare `db.rollback()` on a savepoint-mode test
    # session discards every uncommitted fixture the caller set up, not just this
    # request's own writes - reads never write, so there is nothing here to roll back).
    agent = _require_agent(db, token)
    rows, _total = svc.list_opportunities(db, sales_agent_id=agent.id, limit=1000)
    return {"items": [svc.serialize(db, row) for row in rows]}


# Declared before `/sales-opportunities/{opportunity_id}`, which would otherwise capture them.
@router.get("/sales-opportunities/meta", response_model=SalesOpportunityMeta)
def portal_opportunity_meta(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    _require_agent(db, token)
    return svc.meta(db)


@router.get(
    "/sales-opportunities/customer-options", response_model=SalesOpportunityCustomerOptionsResponse
)
def portal_customer_options(
    q: Optional[str] = Query(None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    agent = _require_agent(db, token)
    return svc.customer_options(db, q=q, sales_agent_id=agent.id)


@router.post("/sales-opportunities", status_code=status.HTTP_201_CREATED)
def portal_create_sales_opportunity(
    payload: PortalSalesOpportunityCreate,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    # Gated before the try: same reasoning as the reads above - nothing has been
    # written yet, so a gate failure must never roll the session back.
    agent = _require_agent(db, token)
    try:
        body = payload.model_dump(exclude_unset=True)
        company_id = _resolve_company(db, customer_id=body.get("customer_id"), agent=agent)
        with company_scope(db, frozenset({company_id})):
            opportunity = svc.create_opportunity(
                db,
                company_id=company_id,
                payload=body,
                sales_agent_id=agent.id,
                source="portal",
                created_by_contact_id=token.contact_id,
                restrict_customer_to_agent_id=agent.id,
            )
        db.commit()
        db.refresh(opportunity)
        return svc.serialize(db, opportunity)
    except Exception as exc:
        _reraise(db, exc)


@router.get("/sales-opportunities/{opportunity_id}")
def portal_get_sales_opportunity(
    opportunity_id: str,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    opportunity_id = validate_uuid_path(opportunity_id, resource="Sales Opportunity")
    agent = _require_agent(db, token)
    opportunity = svc.get_opportunity_for_agent_or_404(db, opportunity_id, agent.id)
    return svc.serialize(db, opportunity)


@router.patch("/sales-opportunities/{opportunity_id}")
def portal_update_sales_opportunity(
    opportunity_id: str,
    payload: PortalSalesOpportunityUpdate,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    opportunity_id = validate_uuid_path(opportunity_id, resource="Sales Opportunity")
    agent = _require_agent(db, token)
    opportunity = svc.get_opportunity_for_agent_or_404(db, opportunity_id, agent.id)
    try:
        with company_scope(db, frozenset({opportunity.company_id})):
            svc.update_opportunity(
                db,
                opportunity,
                payload.model_dump(exclude_unset=True),
                restrict_customer_to_agent_id=agent.id,
            )
        db.commit()
        db.refresh(opportunity)
        return svc.serialize(db, opportunity)
    except Exception as exc:
        _reraise(db, exc)
