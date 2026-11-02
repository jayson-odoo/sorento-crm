"""PS-QUOTE-VIEWS: counted opens of a quotation's sign link

* ``projects.quotation_issue_views`` - one row per counted open: issue, company, time, coarse
  device, and a digest of a random per-browser id. No IP address and no user agent.

Plan: documentation/plans/project-sales/PLAN-quote-views-2nov.md. Additive and guarded so a
re-run, or a dev DB built by create_all, is harmless.

Revision ID: qiv_0001_issue_views
Revises: qcp_0001_cover_page_fields
"""
from alembic import op

revision = "qiv_0001_issue_views"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_issue_views (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES public.companies (id),
            issue_id uuid NOT NULL REFERENCES projects.quotation_issues (id) ON DELETE CASCADE,
            viewed_at timestamp NOT NULL DEFAULT now(),
            device varchar(16) NOT NULL,
            visitor_hash varchar(32) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_quotation_issue_views_company_id "
        "ON projects.quotation_issue_views (company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quotation_issue_views_issue_visitor "
        "ON projects.quotation_issue_views (issue_id, visitor_hash, viewed_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS projects.quotation_issue_views")
