"""PS-SPEC-SHEET: the project spec sheet settings on a quotation document

* ``projects.quotation_documents`` + spec_sheet JSONB NULL: the chosen cover / page templates, the
  revision printed, and per item (keyed by product id or ``set:<set id>``) the page order, Area,
  Comment, Marker, Hide and hand-picked accessories. One document has one spec sheet, read and
  written together, so one column rather than a table.

Card: documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md. Additive and guarded so a
re-run, or a dev DB built by create_all, is harmless.

Revision ID: pss_0001_spec_sheet
Revises: qcp_0001_cover_page_fields
"""
from alembic import op

revision = "pss_0001_spec_sheet"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.quotation_documents ADD COLUMN IF NOT EXISTS spec_sheet JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.quotation_documents DROP COLUMN IF EXISTS spec_sheet")
