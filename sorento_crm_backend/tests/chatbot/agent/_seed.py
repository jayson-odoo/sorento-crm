"""Seed helpers for the AGENTIC-P1 tests (not a test module).

Every row is created here on the blank Postgres schema, because CI's database is empty.
A contact is raw SQL (the chatbot tests do the same); users, roles and permissions are ORM
rows so `UserPermissionService.check_user_has_permission` runs for real.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from app.models.user import User, UserPermission, UserRole, UserRolePermission, UserRoleAssignment
from tests._pg_fixture import unique_code


def seed_contact(
    db,
    *,
    chatbot_allowed: bool = True,
    agent_enabled: bool = True,
) -> dict:
    """A respond contact. Returns {"pk", "respond_id"}."""
    pk = str(uuid.uuid4())
    respond_id = unique_code("rc")
    db.execute(
        text(
            "INSERT INTO respond_contacts "
            "(id, respond_io_id, phone_number, session_vars, chatbot_allowed, chatbot_agent_enabled) "
            "VALUES (:id, :cid, :phone, CAST(:sv AS jsonb), :allowed, :agent)"
        ),
        {
            "id": pk,
            "cid": respond_id,
            "phone": "+6001" + uuid.uuid4().hex[:8],
            "sv": json.dumps({}),
            "allowed": chatbot_allowed,
            "agent": agent_enabled,
        },
    )
    db.flush()
    return {"pk": pk, "respond_id": respond_id}


def seed_user(db, *, contact_pk: str | None, slugs=(), status: str = "ACTIVE") -> str:
    """A user linked to `contact_pk`, holding exactly `slugs` through one private role."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('u').lower()}@zzt.test",
        name="ZZT Agent User",
        status=status,
        respond_contact_id=contact_pk,
    )
    db.add(user)
    db.flush()
    if slugs:
        role = UserRole(id=str(uuid.uuid4()), slug=unique_code("role").lower(), name=unique_code("Role"))
        db.add(role)
        db.flush()
        for slug in slugs:
            perm = db.query(UserPermission).filter(UserPermission.slug == slug).first()
            if perm is None:
                perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
                db.add(perm)
                db.flush()
            db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
        db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
        db.flush()
    return user.id


def seed_agent_contact(db, *, slugs=("inventory.stock.view", "order_management.orders.view")) -> dict:
    """Contact (switch on, AI replies on) plus a linked active user holding `slugs`."""
    contact = seed_contact(db)
    contact["user_id"] = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    return contact
