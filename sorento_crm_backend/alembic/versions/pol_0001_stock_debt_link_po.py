"""AC-LINK-CRM-UI: `projects.stock_debt.link_po`, granted to the admin roles.

Link, unlink or move a PO line to an SO line from a Stock Debt snapshot (writes to AutoCount
through the Shared Service). Seeded here and in `app/rbac/permission_registry.py`; the admin
roles get it (grant sweep), and an admin grants it to purchasing.

Revision ID: pol_0001_stock_debt_link_po
Revises: oiod_0002_pending_restore
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "pol_0001_stock_debt_link_po"
down_revision = "oiod_0002_pending_restore"
branch_labels = None
depends_on = None

_SLUG = "projects.stock_debt.link_po"
_NAME = "Link PO lines from Stock Debt"
_DESCR = (
    "Link, unlink or move a purchase order line to a sales order line from a Stock Debt "
    "snapshot. Writes to AutoCount."
)
_ADMIN_ROLES = ("superadmin", "admin")


def upgrade() -> None:
    bind = op.get_bind()
    # AutoCount's own PO line number (`Seq`), so the PO picker matches AutoCount.
    bind.execute(sa.text("ALTER TABLE purchase_order_lines ADD COLUMN IF NOT EXISTS line_no INTEGER"))
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _SLUG, "name": _NAME, "descr": _DESCR},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, tgt.id, now()
              FROM user_roles r
             CROSS JOIN user_permissions tgt
             WHERE r.slug = ANY(:roles)
               AND tgt.slug = :slug
               AND NOT EXISTS (
                   SELECT 1 FROM user_role_permissions existing
                    WHERE existing.role_id = r.id
                      AND existing.permission_id = tgt.id
               )
            """
        ),
        {"slug": _SLUG, "roles": list(_ADMIN_ROLES)},
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
    bind.execute(sa.text("ALTER TABLE purchase_order_lines DROP COLUMN IF EXISTS line_no"))
