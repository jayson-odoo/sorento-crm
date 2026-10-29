"""Shared world for the "only theirs" tests (PORTAL-P2-ONLY-THEIRS).

Two salespeople, A and B. A is linked to WhatsApp contact CA and sales agent AG-A; B to agent
AG-B through contact CB. Each agent has a customer with a WhatsApp contact of its own. Every
name is fictional and prefixed with the test marker.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import text

from app.models.access import RespondContact, RespondContactCustomer
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.models.user import User

MARKER = "zzt-own"


def uid() -> str:
    return str(uuid.uuid4())


def sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def contact(db, name: str) -> RespondContact:
    row = RespondContact(
        id=uid(),
        name=f"{MARKER} {name}",
        phone_number=f"+6000{uuid.uuid4().int % 10**8:08d}",
        respond_io_id=f"{MARKER}-{uuid.uuid4().hex[:10]}",
    )
    db.add(row)
    db.flush()
    return row


def user(db, name: str, contact_id: str | None = None) -> str:
    user_id = uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} {name}", respond_contact_id=contact_id))
    db.flush()
    return user_id


def agent(db, company_id: str, code: str, contact_id: str | None) -> SalesAgent:
    row = SalesAgent(
        id=uid(), company_id=company_id, sales_agent=f"ZZ{code}{uuid.uuid4().hex[:4]}",
        contact_id=contact_id, is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def customer(db, company_id: str, name: str, agent_id: str) -> Customer:
    row = Customer(
        id=uid(), company_id=company_id, customer_code=f"ZZT-{uuid.uuid4().hex[:6]}",
        customer_name=f"{MARKER} {name}", sales_agent_id=agent_id,
    )
    db.add(row)
    db.flush()
    return row


def link(db, company_id: str, contact_row: RespondContact, customer_row: Customer) -> None:
    db.add(
        RespondContactCustomer(
            id=uid(), company_id=company_id, contact_id=contact_row.id,
            customer_id=customer_row.id, is_primary=True,
        )
    )
    db.flush()


@dataclass
class World:
    company_id: str
    a: str
    b: str
    ca: RespondContact
    cb: RespondContact
    ag_a: SalesAgent
    ag_b: SalesAgent
    cust_a: Customer
    cust_b: Customer
    k1: RespondContact  # cust_a's WhatsApp contact
    k2: RespondContact  # cust_b's WhatsApp contact


def world(db) -> World:
    company_id = sorento(db)
    ca, cb = contact(db, "CA"), contact(db, "CB")
    a = user(db, "Salesperson A", ca.id)
    b = user(db, "Salesperson B", cb.id)
    ag_a, ag_b = agent(db, company_id, "A", ca.id), agent(db, company_id, "B", cb.id)
    cust_a = customer(db, company_id, "Customer One", ag_a.id)
    cust_b = customer(db, company_id, "Customer Two", ag_b.id)
    k1, k2 = contact(db, "K1"), contact(db, "K2")
    link(db, company_id, k1, cust_a)
    link(db, company_id, k2, cust_b)
    return World(company_id, a, b, ca, cb, ag_a, ag_b, cust_a, cust_b, k1, k2)


@contextmanager
def acting(db, user_id: str, perms, *, roles=()):
    """A TestClient acting as ``user_id`` and holding exactly ``perms`` (and ``roles``).

    Unlike the older harnesses this answers EVERY permission check from ``perms``, so the
    route gates (``require_permission``, ``require_any_permission``) are under test too.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    slugs = set(perms)
    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "name": "Tester"}
    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
        UserPermissionService.get_user_role_slugs,
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    UserPermissionService.check_user_has_permission = lambda self, uid_, slug: slug in slugs
    UserPermissionService.get_user_permission_slugs = lambda self, uid_: list(slugs)
    UserPermissionService.get_user_role_slugs = lambda self, uid_: set(roles)
    try:
        yield TestClient(app)
    finally:
        (
            UserPermissionService.check_user_has_permission,
            UserPermissionService.get_user_permission_slugs,
            UserPermissionService.get_user_role_slugs,
        ) = originals
        app.dependency_overrides.clear()
