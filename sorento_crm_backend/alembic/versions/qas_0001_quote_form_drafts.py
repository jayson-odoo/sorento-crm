"""QUOTE-AUTOSAVE: the proposal / quotation form's draft and its History.

Plan: documentation/plans/project-sales/PLAN-quote-autosave-10nov.md.

- ``projects.quotation_document_drafts``: one row per document, the form's autosaved state
  (``doc``, NULL when nothing is in progress) and a ``rev`` counter every write bumps.
- ``projects.quotation_document_snapshots``: insert-only History (``saved`` on every Save,
  ``before_restore``, ``conflict`` and ``discarded`` so a Restore, a stale tab or Discard draft
  never loses typing).

Both cascade with their document. Additive only; downgrade drops the two tables.

Revision ID: qas_0001_quote_form_drafts
Revises: ptag_0021_icon_conditions
Create Date: 2026-11-10
"""
from alembic import op

revision = "qas_0001_quote_form_drafts"
down_revision = "ptag_0021_icon_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_document_drafts (
            document_id UUID PRIMARY KEY
                REFERENCES projects.quotation_documents(id) ON DELETE CASCADE,
            doc JSONB NULL,
            rev INTEGER NOT NULL DEFAULT 0,
            updated_by VARCHAR(100) NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_document_snapshots (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL
                REFERENCES projects.quotation_documents(id) ON DELETE CASCADE,
            kind VARCHAR(20) NOT NULL,
            doc JSONB NOT NULL,
            grand_total NUMERIC(18, 2) NULL,
            created_by VARCHAR(100) NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT ck_quotation_document_snapshots_kind
                CHECK (kind IN ('saved', 'before_restore', 'conflict', 'discarded'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quotation_document_snapshots_document "
        "ON projects.quotation_document_snapshots (document_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS projects.quotation_document_snapshots")
    op.execute("DROP TABLE IF EXISTS projects.quotation_document_drafts")
