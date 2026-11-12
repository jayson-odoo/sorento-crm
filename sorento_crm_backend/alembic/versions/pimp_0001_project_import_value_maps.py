"""PROJECT-MIGRATION-TOOL: saved value links for the project import.

`documentation/plans/project-sales/PLAN-project-import-12nov.md` ("Model and migration"):

* new table `projects.import_value_maps` (one person's choice per folded value, per company);
* the permissions `projects.import.view` and `projects.import.run`, granted to the admin roles.

Additive and idempotent. The run itself is an `import_jobs` row, so no other table changes.

Revision ID: pimp_0001_import_value_maps
Revises: so_search_trgm_0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "pimp_0001_import_value_maps"
down_revision = "so_search_trgm_0001"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    (
        "projects.import.view",
        "View Project Imports",
        "See project import runs, their value links and their results.",
    ),
    (
        "projects.import.run",
        "Run Project Imports",
        "Upload a PO register workbook, link its values, preview, import and revert a run.",
    ),
)
_ADMIN_ROLES = ("superadmin", "admin")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.import_value_maps (
            id uuid PRIMARY KEY,
            company_id uuid REFERENCES public.companies (id),
            kind varchar(16) NOT NULL,
            customer_value_key varchar(255) NOT NULL DEFAULT '',
            value_key varchar(255) NOT NULL,
            value_text text,
            action varchar(8) NOT NULL,
            target_id varchar(64),
            new_title text,
            set_by_user_id varchar REFERENCES public.users (id) ON DELETE SET NULL,
            set_at timestamp,
            created_at timestamp NOT NULL DEFAULT now(),
            updated_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_import_value_maps_key ON projects.import_value_maps "
        "(company_id, kind, customer_value_key, value_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_import_value_maps_company_id "
        "ON projects.import_value_maps (company_id)"
    )
    bind = op.get_bind()
    for slug, name, descr in _PERMISSIONS:
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
            {"slug": slug, "roles": list(_ADMIN_ROLES)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for slug, _name, _descr in _PERMISSIONS:
        bind.execute(
            sa.text(
                "DELETE FROM user_role_permissions WHERE permission_id IN "
                "(SELECT id FROM user_permissions WHERE slug = :slug)"
            ),
            {"slug": slug},
        )
        bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug})
    op.execute("DROP TABLE IF EXISTS projects.import_value_maps")
