"""Link a stock inquiry and a new product application to a registered project.

Revision ID: prr_0001_si_npa_project
Revises: so_search_trgm_0001

PROJECT-RELATED-RECORDS AC-C1. The same nullable-FK shape `complaints` got in
318_complaint_project, for the same reasons:

- **Nullable.** Most inquiries and applications have no project, and every historical row has
  only the free-text `project_name`.
- **ON DELETE SET NULL, never CASCADE.** Deleting a project unlinks the records, it does not
  erase them.
- **`project_name` stays.** No backfill writes a link nobody checked (AC-C8: a reviewed sheet
  links existing rows, never this migration).
"""
from alembic import op

revision = "prr_0001_si_npa_project"
down_revision = "so_search_trgm_0001"
branch_labels = None
depends_on = None

# Written out per table, not built in a loop: tests/test_migration_npa_0001_new_product_apps.py
# and test_migration_npa_0002_paper_layout.py read this source for
# `ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS <column>`. The model declares the
# same FK and index names, so create_all and this migration build identical objects.


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS project_id UUID;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_stock_inquiries_project_id'
            ) THEN
                ALTER TABLE stock_inquiries
                    ADD CONSTRAINT fk_stock_inquiries_project_id
                    FOREIGN KEY (project_id) REFERENCES projects.projects (id) ON DELETE SET NULL;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_stock_inquiries_project
            ON stock_inquiries (project_id) WHERE project_id IS NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS project_id UUID;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_new_product_applications_project_id'
            ) THEN
                ALTER TABLE new_product_applications
                    ADD CONSTRAINT fk_new_product_applications_project_id
                    FOREIGN KEY (project_id) REFERENCES projects.projects (id) ON DELETE SET NULL;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_new_product_applications_project
            ON new_product_applications (project_id) WHERE project_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_stock_inquiries_project;
        ALTER TABLE stock_inquiries DROP CONSTRAINT IF EXISTS fk_stock_inquiries_project_id;
        ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS project_id;
        """
    )
    op.execute(
        """
        DROP INDEX IF EXISTS ix_new_product_applications_project;
        ALTER TABLE new_product_applications DROP CONSTRAINT IF EXISTS fk_new_product_applications_project_id;
        ALTER TABLE new_product_applications DROP COLUMN IF EXISTS project_id;
        """
    )
