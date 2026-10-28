"""chatbot integration: a dedicated role gives the act-as user `finance.billing_documents.view`

Owner ruling 28 Oct 2026: `basis=unpaid` on the chatbot report ask needs BOTH the contact's
Outstanding reveal AND `finance.billing_documents.view` on the act-as user (unpaid invoices are
receivables, finance data). The chatbot reaches the route as the act-as user of the `n8n`
integration (the shared env key lives there) or of `sorento-mcp`, so those two users, and only
those, get a dedicated role holding that one slug. Found by integration name through
`integrations.act_as_user_id`, never by a hard-coded id or email. Additive and idempotent; a no-op
when an integration or its act-as user is absent. Downgrade removes the assignments and the role
(the permission row may predate this migration and stays).

Revision ID: unpaid_0001_chatbot_ar_role
Revises: report_unify_0001_retire
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "unpaid_0001_chatbot_ar_role"
down_revision = "report_unify_0001_retire"
branch_labels = None
depends_on = None

SLUG = "finance.billing_documents.view"
ROLE_SLUG = "chatbot_integration_unpaid_read"
ROLE_NAME = "Chatbot integration: unpaid invoices read"
INTEGRATIONS = ("n8n", "sorento-mcp")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, created_at) "
            "SELECT gen_random_uuid()::text, :slug, :slug, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)"
        ),
        {"slug": SLUG},
    )
    bind.execute(
        sa.text(
            "INSERT INTO user_roles (id, slug, name, description, is_trashed, is_protected, is_default, created_at) "
            "SELECT gen_random_uuid()::text, :rslug, :rname, :descr, false, false, false, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM user_roles WHERE slug = :rslug)"
        ),
        {
            "rslug": ROLE_SLUG,
            "rname": ROLE_NAME,
            "descr": "Lets the chatbot integration read unpaid invoices (finance.billing_documents.view) and nothing else.",
        },
    )
    bind.execute(
        sa.text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "SELECT gen_random_uuid()::text, r.id, p.id, now() FROM user_roles r, user_permissions p "
            "WHERE r.slug = :rslug AND p.slug = :slug AND NOT EXISTS ("
            "SELECT 1 FROM user_role_permissions x WHERE x.role_id = r.id AND x.permission_id = p.id)"
        ),
        {"rslug": ROLE_SLUG, "slug": SLUG},
    )
    bind.execute(
        sa.text(
            "INSERT INTO user_role_assignments (id, user_id, role_id, assigned_at) "
            "SELECT gen_random_uuid()::text, u.id, r.id, now() FROM user_roles r "
            "JOIN users u ON u.id IN (SELECT i.act_as_user_id FROM integrations i WHERE i.name IN :names) "
            "WHERE r.slug = :rslug AND NOT EXISTS ("
            "SELECT 1 FROM user_role_assignments a WHERE a.user_id = u.id AND a.role_id = r.id)"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"rslug": ROLE_SLUG, "names": list(INTEGRATIONS)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    params = {"rslug": ROLE_SLUG}
    bind.execute(
        sa.text("DELETE FROM user_role_assignments WHERE role_id IN (SELECT id FROM user_roles WHERE slug = :rslug)"),
        params,
    )
    bind.execute(
        sa.text("DELETE FROM user_role_permissions WHERE role_id IN (SELECT id FROM user_roles WHERE slug = :rslug)"),
        params,
    )
    bind.execute(sa.text("DELETE FROM user_roles WHERE slug = :rslug"), params)
