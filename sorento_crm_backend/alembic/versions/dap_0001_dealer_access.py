"""Dealer access through the agent: grant `user_management.contacts.edit_own` to role `salesperson`, and seed
the two Business owner tags.

Plan: documentation/plans/contacts/PLAN-dealer-access-portal-09nov.md (UAC D1).

A salesperson then grants, changes and ends dealer access on customers of their own sales agents through the
agent tools. Business owner is a tag: "Sorento Business Owner" (access types dealer + cabana_dealer) and "Mocha
Business Owner" (mocha_dealer), each inserted only when no tag of that name (any case) exists, so a tag the
office already made is left as it is. A role absent on an install is skipped. Rerunning is a no-op.

Downgrade removes the role grant, and each seeded tag only while it still carries the seeded settings and no
contact holds it.

Revision ID: dap_0001_dealer_access
Revises: sales_0008_no_replace_payee
Create Date: 2026-11-09
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "dap_0001_dealer_access"
down_revision = "sales_0008_no_replace_payee"
branch_labels = None
depends_on = None

_SLUG = "user_management.contacts.edit_own"
_TAGS = (
    ("Sorento Business Owner", {"access_types": ["dealer", "cabana_dealer"]}),
    ("Mocha Business Owner", {"access_types": ["mocha_dealer"]}),
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE r.slug = 'salesperson' AND p.slug = :slug
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slug": _SLUG},
    )
    for name, settings in _TAGS:
        bind.execute(
            sa.text(
                """
                INSERT INTO contact_tags (id, name, is_active, sort_order, settings)
                SELECT gen_random_uuid(), :name, true, 0, CAST(:settings AS jsonb)
                WHERE NOT EXISTS (SELECT 1 FROM contact_tags WHERE lower(name) = lower(:name))
                """
            ),
            {"name": name, "settings": json.dumps(settings)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE role_id IN (SELECT id FROM user_roles WHERE slug = 'salesperson')
              AND permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _SLUG},
    )
    for name, settings in _TAGS:
        bind.execute(
            sa.text(
                """
                DELETE FROM contact_tags t
                WHERE t.name = :name AND t.settings = CAST(:settings AS jsonb)
                  AND NOT EXISTS (SELECT 1 FROM respond_contact_tags m WHERE m.tag_id = t.id)
                """
            ),
            {"name": name, "settings": json.dumps(settings)},
        )
