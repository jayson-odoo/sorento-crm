"""Seed a configurable running-number rule for complaints.

Makes "complaint" appear in System Management → Running Numbers so admins can
edit its prefix / digits / next value / reset cadence. Default mirrors the
sibling document types (SI{yy}-, PR{yy}-, PSSF{yy}-): CMP{yy}-, yearly, 4 digits.

Before this rule existed, complaint numbers fell back to the legacy daily format
(CMP-YYYYMMDD-nnnn) in portal_service. With the rule present, new complaints use
``numbering_service.get_next_number('complaint')`` -> e.g. CMP26-0001.

Revision ID: 229_seed_complaint_numbering
Revises: 228_user_downloads
Create Date: 2026-06-09
"""

from alembic import op


revision = "229_seed_complaint_numbering"
down_revision = "228_user_downloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: only seed if a complaint rule isn't already present.
    op.execute(
        """
        INSERT INTO document_numbering_rules (
            id, doc_type, enabled, prefix_template, number_digits,
            next_value, start_value, reset_policy, last_reset_key
        )
        SELECT
            gen_random_uuid()::text, 'complaint', true, 'CMP{yy}-', 4,
            1, 1, 'yearly', NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM document_numbering_rules WHERE doc_type = 'complaint'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM document_numbering_rules WHERE doc_type = 'complaint'")
