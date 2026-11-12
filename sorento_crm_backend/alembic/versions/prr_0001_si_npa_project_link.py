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

_TABLES = ("stock_inquiries", "new_product_applications")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS project_id UUID;

            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_{table}_project_id'
                ) THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT fk_{table}_project_id
                        FOREIGN KEY (project_id) REFERENCES projects.projects (id) ON DELETE SET NULL;
                END IF;
            END $$;

            CREATE INDEX IF NOT EXISTS ix_{table}_project
                ON {table} (project_id) WHERE project_id IS NOT NULL;
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            DROP INDEX IF EXISTS ix_{table}_project;
            ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_project_id;
            ALTER TABLE {table} DROP COLUMN IF EXISTS project_id;
            """
        )
