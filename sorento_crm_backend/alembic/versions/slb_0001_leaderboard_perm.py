"""SALES-LEADERBOARD: the `sales.leaderboard.view` slug, granted to admin and superadmin.

Plan: documentation/plans/sales/PLAN-sales-leaderboard-07nov.md. Insert-only and guarded
(ON CONFLICT DO NOTHING), precedent ``sales_unified_0001``.

Revision ID: slb_0001_leaderboard_perm
Revises: ptag_0016_accessories
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "slb_0001_leaderboard_perm"
down_revision = "ptag_0016_accessories"
branch_labels = None
depends_on = None

SLUG = "sales.leaderboard.view"
SLUG_NAME = "View the sales leaderboard"
SLUG_DESC = "Open Sales > Leaderboard: invoiced sales ranked by sales person. Shows no commission."
GRANT_ROLES = ("superadmin", "admin")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bind.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "VALUES (:id, :slug, :name, :desc, :now) ON CONFLICT (slug) DO NOTHING"
        ),
        {"id": str(uuid.uuid4()), "slug": SLUG, "name": SLUG_NAME, "desc": SLUG_DESC, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "SELECT gen_random_uuid()::text, r.id, p.id, :now "
            "  FROM user_roles r CROSS JOIN user_permissions p "
            " WHERE r.slug = ANY(:roles) AND p.slug = :slug "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        ),
        {"roles": list(GRANT_ROLES), "slug": SLUG, "now": now},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id = "
            "(SELECT id FROM user_permissions WHERE slug = :s)"
        ),
        {"s": SLUG},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": SLUG})
