"""SAMPLE-FROM-QUOTE: the quotation a sample request was pre-filled from (owner Q5 a, 30 Oct).

Two nullable columns on `projects.sample_requests`: `quotation_document_id` (which letterhead)
and `quotation_issue_id` (which revision; NULL when the pre-fill came from a never-issued
document, the common case today). Both `ON DELETE SET NULL`: the request outlives a deleted
quotation and keeps its lines.

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order.

Revision ID: sfq_0001_sample_request_source
Revises: tbc_0001_allowed_item_classes
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "sfq_0001_sample_request_source"
down_revision = "tbc_0001_allowed_item_classes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.sample_requests ADD COLUMN IF NOT EXISTS quotation_document_id UUID "
        "REFERENCES projects.quotation_documents(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE projects.sample_requests ADD COLUMN IF NOT EXISTS quotation_issue_id UUID "
        "REFERENCES projects.quotation_issues(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.sample_requests DROP COLUMN IF EXISTS quotation_issue_id")
    op.execute("ALTER TABLE projects.sample_requests DROP COLUMN IF EXISTS quotation_document_id")
