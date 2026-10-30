"""AGENTIC-P3 W0: the `user_management.contacts.edit_own` permission, granted to no role.

Holding it lets the agent change the role or end the access of dealer contacts linked to customers
of the user's own sales agents. Insert-only and guarded, so it is safe to re-run on the dev copy of
production; a role is given it by hand in Users & Access.

Revision ID: agp3_0002_contacts_edit_own
Revises: agp3_0001_agent_actions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "agp3_0002_contacts_edit_own"
down_revision = "agp3_0001_agent_actions"
branch_labels = None
depends_on = None

# Copied, not imported from app.rbac.permission_registry: a migration must keep working when
# the registry later moves on.
_SLUG = "user_management.contacts.edit_own"
_NAME = "Edit Own Dealer Contacts' Access"
_DESCR = (
    "Change the role or end the access of dealer contacts linked to customers of your own sales "
    "agents, through the agent. Ignored when Edit Contacts is also held."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _SLUG, "name": _NAME, "descr": _DESCR},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :slug)"
        ),
        {"slug": _SLUG},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": _SLUG})
