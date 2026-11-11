"""QUOTE-DUPLICATE-PARTY: a proposal copied for another party, and History event lines.

Plan: documentation/plans/project-sales/PLAN-quote-duplicate-party-11nov.md.

- ``projects.quotation_documents.copied_from_document_id``: the document this one was duplicated
  from (the "Copied from" link). Its own column, not ``source_issue_id``, which means "the
  quotation made from this proposal" and drives the below-proposal approval check.
- ``projects.quotation_document_snapshots.kind`` accepts ``event``: a History line with a note and
  no restorable state ("Copied from ...", "Duplicated for ...", "Approval carried from ...").

Additive only. Downgrade drops the column and restores the old kind check (event rows deleted).

Revision ID: qdp_0001_duplicate_party
Revises: ptag_0022_request_customers
Create Date: 2026-11-11
"""
from alembic import op

revision = "qdp_0001_duplicate_party"
down_revision = "ptag_0022_request_customers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE projects.quotation_documents
            ADD COLUMN IF NOT EXISTS copied_from_document_id UUID NULL
                REFERENCES projects.quotation_documents(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quotation_documents_copied_from "
        "ON projects.quotation_documents (copied_from_document_id)"
    )
    op.execute(
        "ALTER TABLE projects.quotation_document_snapshots "
        "DROP CONSTRAINT IF EXISTS ck_quotation_document_snapshots_kind"
    )
    op.execute(
        "ALTER TABLE projects.quotation_document_snapshots "
        "ADD CONSTRAINT ck_quotation_document_snapshots_kind "
        "CHECK (kind IN ('saved', 'before_restore', 'conflict', 'event'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM projects.quotation_document_snapshots WHERE kind = 'event'")
    op.execute(
        "ALTER TABLE projects.quotation_document_snapshots "
        "DROP CONSTRAINT IF EXISTS ck_quotation_document_snapshots_kind"
    )
    op.execute(
        "ALTER TABLE projects.quotation_document_snapshots "
        "ADD CONSTRAINT ck_quotation_document_snapshots_kind "
        "CHECK (kind IN ('saved', 'before_restore', 'conflict'))"
    )
    op.execute("DROP INDEX IF EXISTS projects.ix_quotation_documents_copied_from")
    op.execute(
        "ALTER TABLE projects.quotation_documents DROP COLUMN IF EXISTS copied_from_document_id"
    )
