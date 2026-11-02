"""QUOTE-COVER-DESIGN: the cover page design

* ``projects.quotation_templates`` + design (JSONB, kind cover_page only).
* ``projects.quotation_documents`` + cover_closing_html (the cover's closing text per quotation).
* ``projects.quotation_issues`` + cover_design (JSONB) and cover_closing_rendered, frozen at send
  for layout 3.

Plan: documentation/plans/projects/PLAN-quote-cover-design-02nov.md. Additive and guarded so a
re-run, or a dev DB built by create_all, is harmless.

Revision ID: qcd_0001_cover_designs
Revises: join_0003_qiv_bnsp
"""
from alembic import op

revision = "qcd_0001_cover_designs"
down_revision = "join_0003_qiv_bnsp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects.quotation_templates ADD COLUMN IF NOT EXISTS design JSONB")
    op.execute(
        "ALTER TABLE projects.quotation_documents ADD COLUMN IF NOT EXISTS cover_closing_html TEXT"
    )
    op.execute(
        """
        ALTER TABLE projects.quotation_issues
            ADD COLUMN IF NOT EXISTS cover_design JSONB,
            ADD COLUMN IF NOT EXISTS cover_closing_rendered TEXT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE projects.quotation_issues
            DROP COLUMN IF EXISTS cover_design,
            DROP COLUMN IF EXISTS cover_closing_rendered
        """
    )
    op.execute("ALTER TABLE projects.quotation_documents DROP COLUMN IF EXISTS cover_closing_html")
    op.execute("ALTER TABLE projects.quotation_templates DROP COLUMN IF EXISTS design")
