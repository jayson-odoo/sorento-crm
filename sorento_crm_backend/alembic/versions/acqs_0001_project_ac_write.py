"""AC-QTSO-CRM: AutoCount quotation + sales order writes from Project sales.

* `system_settings.project_autocount_write_enabled` (seeded OFF).
* The AutoCount document key / last-modified on project sales orders and quotation documents.
* Permission `projects.autocount.write`, granted to the admin roles.

Revision ID: acqs_0001_project_ac_write
Revises: npasi_0001_lineage
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "acqs_0001_project_ac_write"
down_revision = "npasi_0001_lineage"
branch_labels = None
depends_on = None

_SLUG = "projects.autocount.write"
_NAME = "Send quotations and sales orders to AutoCount"
_DESCR = (
    "Create, update or cancel a project quotation or sales order in AutoCount from "
    "Project sales. Writes to AutoCount."
)
_ADMIN_ROLES = ("superadmin", "admin")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
            "project_autocount_write_enabled BOOLEAN NOT NULL DEFAULT false"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.sales_orders "
            "ADD COLUMN IF NOT EXISTS autocount_doc_key VARCHAR(80), "
            "ADD COLUMN IF NOT EXISTS autocount_last_modified VARCHAR(64), "
            "ADD COLUMN IF NOT EXISTS autocount_cancelled_at TIMESTAMP, "
            "ADD COLUMN IF NOT EXISTS autocount_cancelled_by VARCHAR(100), "
            "ADD COLUMN IF NOT EXISTS autocount_book VARCHAR(40)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.so_amendments "
            "ADD COLUMN IF NOT EXISTS autocount_edit_sent_at TIMESTAMP"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.quotation_documents "
            "ADD COLUMN IF NOT EXISTS autocount_doc_no VARCHAR(80), "
            "ADD COLUMN IF NOT EXISTS autocount_doc_key VARCHAR(80), "
            "ADD COLUMN IF NOT EXISTS autocount_last_modified VARCHAR(64), "
            "ADD COLUMN IF NOT EXISTS autocount_issue_id UUID, "
            "ADD COLUMN IF NOT EXISTS autocount_edit_issue_id UUID, "
            "ADD COLUMN IF NOT EXISTS autocount_lines_issue_id UUID, "
            "ADD COLUMN IF NOT EXISTS autocount_cancelled_at TIMESTAMP, "
            "ADD COLUMN IF NOT EXISTS autocount_cancelled_by VARCHAR(100), "
            "ADD COLUMN IF NOT EXISTS autocount_book VARCHAR(40)"
        )
    )
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
    bind.execute(
        sa.text(
            "ALTER TABLE projects.quotation_documents "
            "DROP COLUMN IF EXISTS autocount_book, DROP COLUMN IF EXISTS autocount_cancelled_by, DROP COLUMN IF EXISTS autocount_cancelled_at, "
            "DROP COLUMN IF EXISTS autocount_lines_issue_id, DROP COLUMN IF EXISTS autocount_edit_issue_id, "
            "DROP COLUMN IF EXISTS autocount_issue_id, DROP COLUMN IF EXISTS autocount_last_modified, "
            "DROP COLUMN IF EXISTS autocount_doc_key, DROP COLUMN IF EXISTS autocount_doc_no"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.sales_orders "
            "DROP COLUMN IF EXISTS autocount_book, DROP COLUMN IF EXISTS autocount_cancelled_by, DROP COLUMN IF EXISTS autocount_cancelled_at, "
            "DROP COLUMN IF EXISTS autocount_last_modified, DROP COLUMN IF EXISTS autocount_doc_key"
        )
    )
    bind.execute(
        sa.text("ALTER TABLE projects.so_amendments DROP COLUMN IF EXISTS autocount_edit_sent_at")
    )
    bind.execute(sa.text("ALTER TABLE system_settings DROP COLUMN IF EXISTS project_autocount_write_enabled"))
