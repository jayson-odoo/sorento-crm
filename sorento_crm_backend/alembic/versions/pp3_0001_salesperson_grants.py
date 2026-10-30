"""Salesperson grants for the CRM role menu: `projects.projects.view_own` and
`sla_management.conversations.view_own`.

Plan: documentation/plans/portal/PLAN-portal-p3-role-menu-28oct.md (slice 1).

Both permissions exist (registry sync); this grants them to role `salesperson` only, so a
salesperson reaches Projects and Conversations in the CRM, scoped to their own rows. A role
absent on an install is skipped. Downgrade removes exactly those two pairs.

Revision ID: pp3_0001_salesperson_grants
Revises: agp1_0001_agent_foundation
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "pp3_0001_salesperson_grants"
down_revision = "agp1_0001_agent_foundation"
branch_labels = None
depends_on = None

_SLUGS = ("projects.projects.view_own", "sla_management.conversations.view_own")


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE r.slug = 'salesperson' AND p.slug = ANY(:slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slugs": list(_SLUGS)},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE role_id IN (SELECT id FROM user_roles WHERE slug = 'salesperson')
              AND permission_id IN (SELECT id FROM user_permissions WHERE slug = ANY(:slugs))
            """
        ),
        {"slugs": list(_SLUGS)},
    )
