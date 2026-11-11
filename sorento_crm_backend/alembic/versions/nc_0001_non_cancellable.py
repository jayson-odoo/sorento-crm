"""NON-CANCELLABLE-ITEMS: mark bulky items non-cancellable on the project series.

Plan: documentation/plans/project-sales/PLAN-non-cancellable-items-11nov.md.

Additive only:

- ``projects.series_categories.non_cancellable`` (NOT NULL, false): the series marks a whole
  category (parent covers its children).
- ``projects.series_products.non_cancellable`` (NULL): the model row's own answer. NULL follows
  the category, true / false overrides it (model beats category).
- ``projects.series_sets.non_cancellable`` (NOT NULL, false): a set priced on the series.
- ``projects.quotation_lines.is_non_cancellable`` (NOT NULL, false): computed on save and
  STORED, like ``is_non_standard``, so a later change of the setting never rewrites a quotation
  the customer already holds.
- ``projects.non_cancellable_rules``: the company-wide default by product or category (owner
  answer (a)); the series setting wins over it.
- ``projects.non_cancellable.override`` seeded and granted to superadmin, admin, director and
  project_sales_manager (insert-only, ON CONFLICT DO NOTHING).

Revision ID: nc_0001_non_cancellable
Revises: sca_0001_products_cost_view
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "nc_0001_non_cancellable"
down_revision = "sca_0001_products_cost_view"
branch_labels = None
depends_on = None

SLUG = "projects.non_cancellable.override"
SLUG_NAME = "Override a non-cancellable item"
SLUG_DESC = (
    "Cancel or reduce a Non-cancellable line after its sales order is confirmed, with a "
    "reason. Also receives the alert when AutoCount cancels or reduces one."
)
GRANT_ROLES = ("superadmin", "admin", "director", "project_sales_manager")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.series_categories "
        "ADD COLUMN IF NOT EXISTS non_cancellable BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE projects.series_products ADD COLUMN IF NOT EXISTS non_cancellable BOOLEAN"
    )
    op.execute(
        "ALTER TABLE projects.series_sets "
        "ADD COLUMN IF NOT EXISTS non_cancellable BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE projects.quotation_lines "
        "ADD COLUMN IF NOT EXISTS is_non_cancellable BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.non_cancellable_rules (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES companies(id),
            product_id UUID NULL REFERENCES products(id) ON DELETE CASCADE,
            category_id UUID NULL REFERENCES product_categories(id) ON DELETE CASCADE,
            non_cancellable BOOLEAN NOT NULL DEFAULT true,
            notes TEXT NULL,
            created_by VARCHAR(100) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_non_cancellable_rules_one_target
                CHECK ((product_id IS NULL) <> (category_id IS NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_non_cancellable_rules_company_target "
        "ON projects.non_cancellable_rules (company_id, product_id, category_id) "
        "NULLS NOT DISTINCT"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_non_cancellable_rules_company_id "
        "ON projects.non_cancellable_rules (company_id)"
    )
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
    op.execute("DROP TABLE IF EXISTS projects.non_cancellable_rules")
    op.execute("ALTER TABLE projects.quotation_lines DROP COLUMN IF EXISTS is_non_cancellable")
    op.execute("ALTER TABLE projects.series_sets DROP COLUMN IF EXISTS non_cancellable")
    op.execute("ALTER TABLE projects.series_products DROP COLUMN IF EXISTS non_cancellable")
    op.execute("ALTER TABLE projects.series_categories DROP COLUMN IF EXISTS non_cancellable")
