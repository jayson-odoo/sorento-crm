"""QUOTE-AUTOSAVE: the proposal / quotation form's draft and its History.

Plan: documentation/plans/project-sales/PLAN-quote-autosave-10nov.md.

- ``projects.quotation_document_drafts``: the form's autosaved state (``doc``, NULL when nothing is
  in progress). One row per document (shared), or, with ``document_id`` NULL, one private row per
  person per project for a NEW proposal that has no number yet. ``holder_token`` is the tab that
  may write (the older tab goes view-only).
- ``projects.quotation_document_snapshots``: insert-only History (``saved`` on every Save,
  ``before_restore`` on a Restore, ``conflict`` for a tab that lost the draft).

Both cascade with their document / project. Additive only; downgrade drops the two tables.

Revision ID: qas_0001_quote_form_drafts
Revises: pfc_0001_line_is_section
Create Date: 2026-11-10
"""
from alembic import op

revision = "qas_0001_quote_form_drafts"
down_revision = "pfc_0001_line_is_section"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_document_drafts (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES projects.projects(id) ON DELETE CASCADE,
            document_id UUID NULL
                REFERENCES projects.quotation_documents(id) ON DELETE CASCADE,
            owner_user_id VARCHAR(100) NULL,
            doc JSONB NULL,
            holder_token VARCHAR(64) NULL,
            holder_by VARCHAR(100) NULL,
            holder_at TIMESTAMP WITHOUT TIME ZONE NULL,
            updated_by VARCHAR(100) NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NULL
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_document_drafts_document "
        "ON projects.quotation_document_drafts (document_id) WHERE document_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_document_drafts_new "
        "ON projects.quotation_document_drafts (project_id, owner_user_id) "
        "WHERE document_id IS NULL"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_document_snapshots (
            id UUID PRIMARY KEY,
            document_id UUID NULL
                REFERENCES projects.quotation_documents(id) ON DELETE CASCADE,
            draft_id UUID NULL
                REFERENCES projects.quotation_document_drafts(id) ON DELETE CASCADE,
            kind VARCHAR(20) NOT NULL,
            note TEXT NULL,
            source_key VARCHAR(64) NULL,
            doc JSONB NOT NULL,
            grand_total NUMERIC(18, 2) NULL,
            created_by VARCHAR(100) NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT ck_quotation_document_snapshots_kind
                CHECK (kind IN ('saved', 'before_restore', 'conflict'))
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
