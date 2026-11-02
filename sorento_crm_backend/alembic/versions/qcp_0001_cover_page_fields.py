"""QUOTE-COVER-PAGE: the cover page fields

* ``projects.quotation_documents`` + recipient_email_snapshot, quotation_purpose, payment_terms,
  validity (free text, per quotation).
* ``projects.quotation_templates`` + payment_terms, validity (defaults beside the terms template).
* ``projects.quotation_issues`` + layout_version (1 = before the cover page, 2 = cover page
  first); existing rows take 1 from the default.

Plan: documentation/plans/projects/PLAN-quote-cover-page-02nov.md. Additive and guarded so a
re-run, or a dev DB built by create_all, is harmless.

Revision ID: qcp_0001_cover_page_fields
Revises: das_0001_ai_read_ticks
"""
from alembic import op

revision = "qcp_0001_cover_page_fields"
down_revision = "das_0001_ai_read_ticks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE projects.quotation_documents
            ADD COLUMN IF NOT EXISTS recipient_email_snapshot TEXT,
            ADD COLUMN IF NOT EXISTS quotation_purpose TEXT,
            ADD COLUMN IF NOT EXISTS payment_terms TEXT,
            ADD COLUMN IF NOT EXISTS validity TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE projects.quotation_templates
            ADD COLUMN IF NOT EXISTS payment_terms TEXT,
            ADD COLUMN IF NOT EXISTS validity TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE projects.quotation_issues
            ADD COLUMN IF NOT EXISTS layout_version SMALLINT NOT NULL DEFAULT 1
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.quotation_issues DROP COLUMN IF EXISTS layout_version")
    op.execute(
        """
        ALTER TABLE projects.quotation_templates
            DROP COLUMN IF EXISTS payment_terms,
            DROP COLUMN IF EXISTS validity
        """
    )
    op.execute(
        """
        ALTER TABLE projects.quotation_documents
            DROP COLUMN IF EXISTS recipient_email_snapshot,
            DROP COLUMN IF EXISTS quotation_purpose,
            DROP COLUMN IF EXISTS payment_terms,
            DROP COLUMN IF EXISTS validity
        """
    )
