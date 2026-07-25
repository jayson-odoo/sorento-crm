"""Import-job company snapshot (multi-company data isolation, Part A).

The worker registers the company-scope enforcement but sets NO scope, so owned
writes inside an import task currently fail-closed (the ``before_insert`` stamp
raises when the session scope is UNSET/None/multi). To let the worker re-establish
the request's active company, the enqueue path snapshots the caller's active
company onto the ``import_jobs`` row and the task reads it back and
``set_company_scope(frozenset({company_id}))``.

Nullable + ``ADD COLUMN IF NOT EXISTS`` (idempotent): pre-existing jobs and
system/None-scope imports keep a NULL snapshot (task then runs system-scoped).

Revision ID: 303_import_job_company
Revises: 302_multi_company
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "303_import_job_company"
down_revision = "302_multi_company"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS company_id uuid")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_import_jobs_company_id ON import_jobs (company_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_import_jobs_company_id")
    op.execute("ALTER TABLE import_jobs DROP COLUMN IF EXISTS company_id")
