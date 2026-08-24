"""Canonical reference data required for a working install.

This is *application* data, not test fixtures: a fresh environment cannot
function without base roles and the order-status vocabulary, and several code
paths look them up by their stable codes. Keeping the canonical set in code (and
therefore in review, and in git history) is what makes an environment
reproducible - previously these rows existed only in whichever database happened
to have them.

Every seeder is idempotent and matches on the stable business key (role `slug`,
order status `status_code`), never on id, so re-running never duplicates and
never clobbers an operator's edits to names/descriptions.

Business data - customers, products, orders - is deliberately NOT seeded here.
Tests that need those must create their own, so they stay independent of
whatever rows a given environment happens to hold.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Base roles. `purchasing` is referenced by the SCM module (migration 274 grants
# it the scm.* permissions); `guest` is the lowest-privilege principal.
BASE_ROLES: list[dict[str, str]] = [
    {"slug": "superadmin", "name": "Super Admin", "description": "Full unrestricted access; bypasses permission checks."},
    {"slug": "admin", "name": "Admin", "description": "Administrative access across enabled modules."},
    {"slug": "purchasing", "name": "Purchasing", "description": "Procurement and reorder planning."},
    {"slug": "guest", "name": "Guest", "description": "Minimal read-only access."},
]

# Order lifecycle vocabulary. `sequence` drives display ordering;
# `is_final_status` marks terminal states.
ORDER_STATUSES: list[dict[str, Any]] = [
    {"status_code": "NEW", "status_name": "New Order", "description": "Newly created order", "sequence": 1, "is_final_status": False},
    {"status_code": "PENDING", "status_name": "Pending Approval", "description": "Awaiting approval", "sequence": 2, "is_final_status": False},
    {"status_code": "APPROVED", "status_name": "Approved", "description": "Order approved", "sequence": 3, "is_final_status": False},
    {"status_code": "PROCESSING", "status_name": "Processing", "description": "Order in process", "sequence": 4, "is_final_status": False},
    {"status_code": "SHIPPED", "status_name": "Shipped", "description": "Order shipped", "sequence": 5, "is_final_status": False},
    {"status_code": "DELIVERED", "status_name": "Picked Up / In Transit", "description": "Order delivered to customer", "sequence": 6, "is_final_status": True},
    {"status_code": "CANCELLED", "status_name": "Cancelled", "description": "Order cancelled", "sequence": 7, "is_final_status": True},
    {"status_code": "COMPLETED", "status_name": "Completed", "description": "Order completed", "sequence": 8, "is_final_status": True},
]


def seed_roles(db: Session) -> int:
    """Insert any missing base role. Returns the number created."""
    from app.models.user import UserRole

    created = 0
    for role in BASE_ROLES:
        if db.query(UserRole).filter(UserRole.slug == role["slug"]).first():
            continue
        db.add(
            UserRole(
                id=str(uuid.uuid4()),
                slug=role["slug"],
                name=role["name"],
                description=role["description"],
                is_trashed=False,
                is_protected=True,   # base roles must not be deletable
                is_default=False,
            )
        )
        created += 1
    db.flush()
    return created


def seed_order_statuses(db: Session) -> int:
    """Insert any missing order status. Returns the number created."""
    from app.models.order import OrderStatus

    created = 0
    for status in ORDER_STATUSES:
        if (
            db.query(OrderStatus)
            .filter(OrderStatus.status_code == status["status_code"])
            .first()
        ):
            continue
        db.add(
            OrderStatus(
                id=str(uuid.uuid4()),
                status_code=status["status_code"],
                status_name=status["status_name"],
                description=status["description"],
                sequence=status["sequence"],
                is_final_status=status["is_final_status"],
            )
        )
        created += 1
    db.flush()
    return created


def grant_all_permissions_to_admin_roles(db: Session) -> int:
    """Give `admin` / `superadmin` every registered permission.

    Both bypass `require_permission` at runtime, but explicit grants keep the
    admin UI honest and let permission-driven queries resolve.
    """
    created = 0
    for slug in ("admin", "superadmin"):
        role_id = db.execute(
            text("SELECT id FROM user_roles WHERE slug = :slug"), {"slug": slug}
        ).scalar()
        if not role_id:
            continue
        result = db.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id) "
                "SELECT gen_random_uuid(), :role_id, p.id FROM user_permissions p "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM user_role_permissions rp "
                "  WHERE rp.role_id = :role_id AND rp.permission_id = p.id"
                ")"
            ),
            {"role_id": role_id},
        )
        created += result.rowcount or 0
    return created


# Roles that must hold the SCM permission set. Migration 274 grants these when it
# runs; a bootstrapped database never replays it, so the grant is reproduced here.
SCM_GRANT_ROLE_SLUGS = ("admin", "superadmin", "purchasing")


def grant_scm_permissions(db: Session) -> int:
    """Grant every `scm.*` permission to the SCM operator roles."""
    created = 0
    for slug in SCM_GRANT_ROLE_SLUGS:
        role_id = db.execute(
            text("SELECT id FROM user_roles WHERE slug = :slug"), {"slug": slug}
        ).scalar()
        if not role_id:
            continue
        result = db.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id) "
                "SELECT gen_random_uuid(), :role_id, p.id FROM user_permissions p "
                "WHERE p.slug LIKE 'scm.%' AND NOT EXISTS ("
                "  SELECT 1 FROM user_role_permissions rp "
                "  WHERE rp.role_id = :role_id AND rp.permission_id = p.id"
                ")"
            ),
            {"role_id": role_id},
        )
        created += result.rowcount or 0
    return created


def run(db: Session) -> dict[str, int]:
    """Seed all canonical reference data. Idempotent."""
    summary = {
        "roles": seed_roles(db),
        "order_statuses": seed_order_statuses(db),
        "admin_permission_grants": grant_all_permissions_to_admin_roles(db),
        "scm_permission_grants": grant_scm_permissions(db),
    }
    logger.info("Reference seed: %s", summary)
    return summary
