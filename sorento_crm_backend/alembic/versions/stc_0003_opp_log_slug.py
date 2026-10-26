"""Register and grant `integration.sales_opportunity.log` (SALES-TARGET-CHAT slice 2).

The chatbot logs a salesperson's opportunity through `/api/v1/external/sales-opportunities`
(the customer options read and the create), which every /external route guards with an
integration slug. Registering a permission is not enough: grants are computed at role-provision
time and do not reach existing roles, so a slug with no grant path silently 403s the feature.
Granted, with the idempotent insert 357 (`integration.chatbot_media.process`) uses, to `admin`
(what the shared key resolves to today) and to the chatbot's two integration roles only
(`integration_sorento_mcp`, the MCP server the lane calls through, and `integration_n8n`): a
write on a contact's behalf is not handed to every integration (the ESB has no business here).
Downgrade removes the grants and the permission row.

Revision ID: stc_0003_opp_log_slug
Revises: stc_0002_opp_source_chat
Create Date: 2026-10-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "stc_0003_opp_log_slug"
down_revision = "stc_0002_opp_source_chat"
branch_labels = None
depends_on = None

SLUG = "integration.sales_opportunity.log"
NAME = "Log sales opportunities from chat"
#: The roles that may call the chatbot's opportunity routes: admin and the chatbot's integrations.
ROLES = ("admin", "integration_sorento_mcp", "integration_n8n")
DESCRIPTION = (
    "Log a sales opportunity for a salesperson contact over the chat, and read that "
    "salesperson's own customers to pick from."
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": SLUG, "name": NAME, "descr": DESCRIPTION},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id)
            SELECT gen_random_uuid()::text, r.id, p.id
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE p.slug = :slug
              AND r.slug = ANY(:roles)
              AND NOT EXISTS (
                  SELECT 1 FROM user_role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ),
        {"slug": SLUG, "roles": list(ROLES)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :slug)"
        ),
        {"slug": SLUG},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": SLUG})
