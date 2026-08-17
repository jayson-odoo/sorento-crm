"""Link a complaint to a registered project (S6b, AC-L3).

Revision ID: 318_complaint_project
Revises: 317_staleness

The same nullable-FK-plus-picker shape `purchase_requests` got in S4, for the same reasons:

- **Nullable.** A complaint about a retail delivery has no project and never will, and every
  historical row has only the free-text `project_title`.
- **ON DELETE SET NULL, never CASCADE.** A complaint is a customer's problem and a legal
  record; it has to outlive the pursuit it happened to be attached to. Deleting a project
  unlinks its complaints, it does not erase them.
- **`project_title` stays.** It is the only project information on thousands of rows and
  remains the display fallback. No fuzzy backfill writes a link nobody checked (AC-F6's rule).
"""
from alembic import op

revision = "318_complaint_project"
down_revision = "317_staleness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE complaints
            ADD COLUMN IF NOT EXISTS project_id UUID;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_complaints_project_id'
            ) THEN
                ALTER TABLE complaints
                    ADD CONSTRAINT fk_complaints_project_id
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_complaints_project_id
            ON complaints (project_id) WHERE project_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_complaints_project_id;
        ALTER TABLE complaints DROP CONSTRAINT IF EXISTS fk_complaints_project_id;
        ALTER TABLE complaints DROP COLUMN IF EXISTS project_id;
        """
    )
