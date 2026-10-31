"""Logging a sales opportunity over the chat (SALES-TARGET-CHAT slice 2).

`documentation/plans/sales/PLAN-sales-opportunity-chat-25oct.md`, "Backend". The chatbot's two
API-key routes (`app/api/v1/external/sales_opportunities.py`) call this: one gate, the customer
options and the save. Nothing here re-implements the portal: the options are
`opportunity_service.customer_options`, the owner is `agent_owning_customer` /
`default_portal_agent`, the company is `resolve_company`, and the row is
`create_opportunity` with source 'chat'.

The gate is per contact (there is no permission slug: the portal has none either), in this order:
both ids given (422 `contact_identity_required`), the contact known, a salesperson by the one asker
rule and not revoked, at least one active agent (403 `not_a_salesperson` for each), and the
portal's own "sales_opportunity" form visible to the contact (403 `opportunity_not_enabled`).
"""
from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.services import status_service
from app.services.error_handler import AppException
from app.services.sales import opportunity_service as svc

FORM_TYPE = "sales_opportunity"
SOURCE = "chat"


def _refused(code: str) -> AppException:
    if code == "opportunity_not_enabled":
        return AppException(
            status_code=403, message="Logging an opportunity is not enabled for your account.", code=code
        )
    return AppException(status_code=403, message="Logging an opportunity is for salespeople only.", code=code)


def _unprocessable(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


def gate(db: Session, *, contact_id: Optional[str], space_id: Optional[str]) -> Tuple[str, List[SalesAgent]]:
    """The contact's INTERNAL id and its active agents (by code), or the refusal."""
    from app.audit_context import AuditActor, get_actor, stamp_actor
    from app.services.contact_asker import classify
    from app.services.field_access import resolve_contact_with_null_workspace_fallback
    from app.services.portal_form_visibility_service import require_form_visible
    from app.services.sales.portal_agent import agents_for_contact
    from app.services.sales.target_chat_scope import _user_revoked

    contact_id = (contact_id or "").strip()
    space_id = (space_id or "").strip()
    if not contact_id or not space_id:
        raise _unprocessable("contact_id and space_id are required", "contact_identity_required")
    resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=contact_id, space_id=space_id)
    if not resolved:
        raise _refused("not_a_salesperson")
    resolved = str(resolved)
    if classify(db, resolved) != "salesperson" or _user_revoked(db, resolved):
        raise _refused("not_a_salesperson")
    agents = agents_for_contact(db, resolved)
    if not agents:
        raise _refused("not_a_salesperson")
    try:
        require_form_visible(db, resolved, FORM_TYPE)
    except AppException as exc:
        raise _refused("opportunity_not_enabled") from exc
    # An audited write in this request is the contact's (the portal's `_require_agents` stamp). The
    # integration actor the key stamped keeps every other field (user, integration, ip, agent, tool).
    actor = get_actor(db)
    if actor is None:
        stamp_actor(AuditActor(actor_type="contact", auth_method="api_key", contact_id=resolved), db=db)
    elif actor.actor_type != "contact" or actor.contact_id != resolved:
        stamp_actor(dataclasses.replace(actor, actor_type="contact", contact_id=resolved), db=db)
    _scope_to_contact(db, resolved, agents)
    return resolved, agents


def _scope_to_contact(db: Session, contact_id: str, agents: List[SalesAgent]) -> None:
    """The request's company scope is the RESOLVED contact's, whatever the call carried (the
    portal's `_require_agents`): its own companies, narrowed to the scope already set when the two
    overlap, then to its agents' companies when every agent has one and they overlap."""
    from app.models.base import get_company_scope, set_company_scope
    from app.services.company_scope_resolver import portal_contact_scope

    scope = portal_contact_scope(db, contact_id)
    existing = get_company_scope(db)
    if isinstance(existing, frozenset) and scope & existing:
        scope = frozenset(scope & existing)
    companies = {agent.company_id for agent in agents}
    if None not in companies and scope & companies:
        scope = frozenset(scope & companies)
    set_company_scope(db, scope)


def staff_agents(db: Session, user_id: str) -> List[SalesAgent]:
    """The user's own active agents, through their linked contact (`own_scope.me`)."""
    from app.services import own_scope
    from app.services.sales.portal_agent import agents_for_contact

    contact_id = own_scope.me(db, user_id).contact_id
    return agents_for_contact(db, contact_id) if contact_id else []


def staff_customer_options(db: Session, *, user_id: str, may_add: bool, q: Optional[str]) -> dict:
    """AGENTIC-UNIFY AC-12: the customers a holder of `sales.opportunities.add` may log for. A
    salesperson's are their own agents' (the chat rule). Anyone else picks as the CRM's own form does,
    from every customer of the active company (`customer_options`' CRM arm)."""
    if not may_add:
        raise _refused("opportunity_not_enabled")
    agents = staff_agents(db, user_id)
    if agents:
        return customer_options(db, agents, q)
    found = svc.customer_options(db, q=q, sales_agent_id=None)
    ids = [row["customer_id"] for row in found["items"]]
    rows = {c.id: c for c in db.query(Customer).filter(Customer.id.in_(ids)).all()} if ids else {}
    items = [{"customer_id": rows[i].id, **(_customer_out(rows[i]) or {})} for i in ids if i in rows]
    return {"items": items, "prospect": bool(found["prospect"]), "blocked": bool(found["blocked"])}


def staff_create(
    db: Session,
    *,
    user_id: str,
    may_add: bool,
    customer_id: Optional[str],
    prospect_name: Optional[str],
    title: Optional[str],
    expected_amount: Optional[Decimal],
    expected_close_date: Optional[date],
    dry_run: bool,
) -> dict:
    """AGENTIC-UNIFY AC-12: `create` as the staff member, in process: their own
    `sales.opportunities.add`, their own company, and an audit row naming them, not the integration."""
    from app.audit_context import AuditActor, actor_scope

    if not may_add:
        raise _refused("opportunity_not_enabled")
    actor = AuditActor(
        actor_type="user", user_id=user_id, real_user_id=user_id, auth_method="agent",
        tool_name="crm_sales_opportunity_log",
    )
    with actor_scope(actor, db=db):
        return create(
            db,
            contact_id=None,
            agents=staff_agents(db, user_id),
            customer_id=customer_id,
            prospect_name=prospect_name,
            title=title,
            expected_amount=expected_amount,
            expected_close_date=expected_close_date,
            dry_run=dry_run,
            created_by_user_id=user_id,
        )


def _customer_out(customer: Optional[Customer]) -> Optional[dict]:
    from app.services.sales.target_service import account_label

    if customer is None:
        return None
    return {"code": customer.customer_code, "name": customer.customer_name, "label": account_label(customer)}


def _matches(db: Session, words: str):
    """The company's customers (any agent, or none) whose code or name CONTAINS `words`, both sides
    normalised the way `opportunity_service.customer_options` searches."""
    from sqlalchemy import or_

    like = f"%{svc._normalize(words)}%"
    return db.query(Customer.id).filter(
        or_(
            svc._normalize_expr(Customer.customer_code).like(like),
            svc._normalize_expr(Customer.customer_name).like(like),
        )
    )


def _not_yours(db: Session, words: str, agents: List[SalesAgent]) -> bool:
    """Crew a43805183, O2-4: the words name (contain-match) a customer of the company that is not
    the salesperson's: another agent's, or one with no agent at all."""
    from sqlalchemy import or_

    own = [a.id for a in agents]
    return (
        _matches(db, words)
        .filter(or_(Customer.sales_agent_id.is_(None), Customer.sales_agent_id.notin_(own)))
        .first()
        is not None
    )


def customer_options(db: Session, agents: List[SalesAgent], q: Optional[str]) -> dict:
    """The salesperson's OWN customers matching `q`, each labelled (A/C I ...). With no own match,
    `blocked` is true when the same search finds a customer that is not theirs (another agent's,
    or one with no agent), and `prospect` only when it finds no customer at all (crew a43805183,
    O2-4: a partial name of a customer that is not theirs is never a prospect)."""
    found = svc.customer_options(db, q=q, sales_agent_id=[a.id for a in agents])
    ids = [row["customer_id"] for row in found["items"]]
    rows = {c.id: c for c in db.query(Customer).filter(Customer.id.in_(ids)).all()} if ids else {}
    items = []
    for row in found["items"]:
        customer = rows.get(row["customer_id"])
        if customer is None:
            continue
        items.append({"customer_id": customer.id, **(_customer_out(customer) or {})})
    words = (q or "").strip()
    if items or not words:
        return {"items": items, "prospect": bool(found["prospect"]), "blocked": bool(found["blocked"])}
    blocked = _not_yours(db, words, agents) or bool(found["blocked"])
    prospect = not blocked and _matches(db, words).first() is None
    return {"items": [], "prospect": prospect, "blocked": blocked}


def _money(value) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def _pipeline(db: Session, agent_id: str) -> Optional[dict]:
    """The owning agent's current agent target (the first to end): its end date and the open
    pipeline closing within it. None when the agent has no current target."""
    from app.services.sales import target_service

    targets = target_service.agent_progress(db, agent_id)["targets"]
    if not targets:
        return None
    first = targets[0]
    return {"target_end_date": first["end_date"].isoformat(), "pipeline_value": _money(first["pipeline_value"])}


def create(
    db: Session,
    *,
    contact_id: Optional[str],
    agents: List[SalesAgent],
    customer_id: Optional[str],
    prospect_name: Optional[str],
    title: Optional[str],
    expected_amount: Optional[Decimal],
    expected_close_date: Optional[date],
    dry_run: bool,
    created_by_user_id: Optional[str] = None,
) -> dict:
    """Save one opportunity in stage New under the agent owning the customer (a prospect: the
    first agent by code), the portal's own sequence. `dry_run` runs every check inside a
    savepoint that is rolled back: nothing is inserted and no number is consumed.

    `created_by_user_id` is a staff member logging from the AI panel (`staff_create`), who may have no
    agent at all: the agent then comes from the customer, as on the CRM's own form."""
    if expected_amount is None or Decimal(expected_amount) <= 0:
        raise _unprocessable("The expected amount must be more than zero.", "amount_required")
    if Decimal(expected_amount) > svc._MAX_AMOUNT:
        raise _unprocessable("The expected amount is more than an opportunity can hold.", "amount_too_large")
    title = (title or "").strip()
    if not title:
        raise _unprocessable("A title is required.", "title_required")
    if expected_close_date is None:
        raise _unprocessable("An expected close date is required.", "close_date_required")
    customer_id = (customer_id or "").strip() or None
    prospect_name = (prospect_name or "").strip() or None
    if prospect_name and not customer_id and _not_yours(db, prospect_name, agents):
        # Crew a43805183, O2-4: a "prospect" whose name is a customer that is not theirs is that customer.
        raise _unprocessable("That customer is not yours.", "CUSTOMER_NOT_YOURS")
    body = {
        "customer_id": customer_id,
        "prospect_name": prospect_name,
        "title": title,
        "expected_amount": Decimal(expected_amount),
        "expected_close_date": expected_close_date,
    }
    agent = svc.agent_owning_customer(db, agents, customer_id) or (svc.default_portal_agent(db, agents) if agents else None)
    company_id = svc.resolve_company(db, customer_id=customer_id, agent=agent)

    def _save():
        with company_scope(db, frozenset({company_id})):
            return svc.create_opportunity(
                db,
                company_id=company_id,
                payload=body,
                sales_agent_id=agent.id if agent is not None else None,
                source=SOURCE,
                created_by_contact_id=contact_id,
                restrict_customer_to_agent_id=[a.id for a in agents] if agents else None,
                created_by_user_id=created_by_user_id,
                stamp_agent_from_customer=agent is None,
            )

    if dry_run:
        savepoint = db.begin_nested()
        try:
            _save()
        finally:
            savepoint.rollback()
        opportunity_no = None
        stage = status_service.initial_status(db, svc.SALES_OPPORTUNITY_ENTITY).label
    else:
        # A savepoint, so a refusal rolls back this write only (never the caller's session).
        with db.begin_nested():
            opportunity = _save()
        db.commit()
        db.refresh(opportunity)
        opportunity_no = opportunity.opportunity_no
        stage = status_service.initial_status(db, svc.SALES_OPPORTUNITY_ENTITY).label
        if opportunity.status_id:
            from app.models.status import Status

            stage = db.query(Status.label).filter(Status.id == opportunity.status_id).scalar() or stage
    customer = db.query(Customer).filter(Customer.id == customer_id).first() if customer_id else None
    return {
        "opportunity_no": opportunity_no,
        "stage": stage,
        "customer": _customer_out(customer),
        "prospect_name": prospect_name,
        "title": title,
        "expected_amount": _money(expected_amount),
        "expected_close_date": expected_close_date.isoformat(),
        "pipeline": _pipeline(db, agent.id) if agent is not None else None,
        "dry_run": bool(dry_run),
    }
