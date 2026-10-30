"""PORTAL-P2-ONLY-THEIRS: the five `view_own` permissions, granted to no role.

Holding a module's `view_own` without its `view` narrows every read of that module to the
user's own rows (`app/services/own_scope.py`). P2 only creates the slugs; the salesperson role
gets them in P3, so on its own this revision changes nothing for anybody. Insert-only and
guarded, so it is safe to re-run on the dev copy of production.

Revision ID: pp2_0001_view_own_perms
Revises: oitc_0001_fake_reconfirms
Create Date: 2026-10-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Kept <= 32 chars: alembic_version.version_num is varchar(32).
revision = "pp2_0001_view_own_perms"
down_revision = "oitc_0001_fake_reconfirms"
branch_labels = None
depends_on = None

# Copied, not imported from app.rbac.permission_registry: a migration must keep working when
# the registry later moves on.
_PERMS = (
    (
        "projects.projects.view_own",
        "View Own Projects",
        "See only the projects you own, collaborate on or registered from the portal, and "
        "everything under them. Ignored when View Projects is also held.",
    ),
    (
        "sales.opportunities.view_own",
        "View Own Sales Opportunities",
        "See only the sales opportunities of your own sales agents. Ignored when View Sales "
        "Opportunities is also held.",
    ),
    (
        "projects.sample_requests.view_own",
        "View Own Sample Requests",
        "See only the sample requests you raised, or your own contact raised from the portal. "
        "Ignored when View Sample Requests is also held.",
    ),
    (
        "procurement.new_product_applications.view_own",
        "View Own New Product Applications",
        "See only the new product applications you raised, or your own contact raised from the "
        "portal. Ignored when View New Product Applications is also held.",
    ),
    (
        "sla_management.conversations.view_own",
        "View Own Conversations",
        "See only the conversations of your own sales agents' customers in the Conversations "
        "inbox. Ignored when View Conversations is also held.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, descr in _PERMS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": name, "descr": descr},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text(
                "DELETE FROM user_role_permissions WHERE permission_id IN "
                "(SELECT id FROM user_permissions WHERE slug = :slug)"
            ),
            {"slug": slug},
        )
        bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug})
