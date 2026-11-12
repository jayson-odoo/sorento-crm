"""Seed helpers for COST-ACCESS-UNIFIED tests (not a test module).

A contact sees cost iff its linked user (`users.respond_contact_id`) is ACTIVE and holds
`products.cost.view`. These build that chain with real rows (role, permission, assignment), so the
permission check runs for real and nothing borrows an existing row.
"""
from __future__ import annotations

import uuid

from app.models.user import User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from tests._pg_fixture import unique_code

COST_PERM = "products.cost.view"


def link_user(db, contact_pk: str, *, slugs=(), status: str = "ACTIVE", role_slug: str | None = None) -> str:
    """A user linked to ``contact_pk`` holding exactly ``slugs`` through a private role.

    ``role_slug="admin"`` gives the admin role instead (the permission check bypasses for it).
    """
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('cu').lower()}@zzt.test",
        name="ZZT Cost Linked User",
        status=status,
        respond_contact_id=str(contact_pk),
    )
    db.add(user)
    db.flush()
    if slugs or role_slug:
        role = db.query(UserRole).filter(UserRole.slug == role_slug).first() if role_slug else None
        if role is None:
            role = UserRole(
                id=str(uuid.uuid4()), slug=role_slug or unique_code("role").lower(), name=unique_code("Role")
            )
            db.add(role)
            db.flush()
        for slug in dict.fromkeys(slugs):
            perm = db.query(UserPermission).filter(UserPermission.slug == slug).first()
            if perm is None:
                perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
                db.add(perm)
                db.flush()
            db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
        db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
        db.flush()
    return user.id


def cost_viewer(db, contact_pk: str) -> str:
    return link_user(db, contact_pk, slugs=(COST_PERM,))
