"""PS-SPEC-SHEET: the project spec sheet settings on a quotation document

* ``projects.quotation_documents`` + spec_sheet JSONB NULL: the chosen cover / page templates, the
  revision printed, and per item (keyed by product id or ``set:<set id>``) the page order, Area,
  Comment, Marker, Hide and hand-picked accessories. One document has one spec sheet, read and
  written together, so one column rather than a table.

Card: documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md. Additive and guarded so a
re-run, or a dev DB built by create_all, is harmless.

Also the MERGE point of main's two heads at the time (bnsp_0001_brand_no_selling_price and
qiv_0001_issue_views both branched off qcp_0001_cover_page_fields), so the tree has one head again.
If main gets its own merge revision first, re-parent this onto that one head.

Revision ID: pss_0001_spec_sheet
Revises: bnsp_0001_brand_no_selling_price, qiv_0001_issue_views
"""
from alembic import op

revision = "pss_0001_spec_sheet"
down_revision = ("bnsp_0001_brand_no_selling_price", "qiv_0001_issue_views")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.quotation_documents ADD COLUMN IF NOT EXISTS spec_sheet JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.quotation_documents DROP COLUMN IF EXISTS spec_sheet")
