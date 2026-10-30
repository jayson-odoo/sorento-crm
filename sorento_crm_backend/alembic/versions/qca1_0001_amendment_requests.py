"""QUOTE-CUSTOMER-AMEND: the customer's suggested quantities and prices on a quotation link

* ``projects.quotation_amendment_requests`` - one request per submit; at most one ``open`` per
  issue (partial unique index).
* ``projects.quotation_amendment_request_rows`` - one row per (line, field), decided on its own.

Plan: documentation/plans/project-sales/PLAN-quote-customer-amend-29oct.md. The same DDL is in
documentation/plans/project-sales/quote-customer-amend-29oct-migration.sql. Additive and guarded
so a re-run, or a dev DB built by create_all, is harmless.

Revision ID: qca1_0001_amendment_requests
Revises: pp4_0002_complaint_revision
"""
from alembic import op

revision = "qca1_0001_amendment_requests"
down_revision = "pp4_0002_complaint_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_amendment_requests (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES public.companies (id),
            issue_id uuid NOT NULL REFERENCES projects.quotation_issues (id) ON DELETE CASCADE,
            status varchar(16) NOT NULL DEFAULT 'open',
            requester_name varchar(200),
            note text,
            ip_address varchar(64),
            submitted_at timestamp NOT NULL DEFAULT now(),
            applied_at timestamp,
            applied_by varchar(100) REFERENCES public.users (id) ON DELETE SET NULL,
            revised boolean NOT NULL DEFAULT false,
            created_at timestamp NOT NULL DEFAULT now(),
            updated_at timestamp NOT NULL DEFAULT now(),
            CONSTRAINT ck_quotation_amendment_requests_status
                CHECK (status IN ('open', 'applied', 'superseded'))
        )
        """
    )
    # The table may already exist from an earlier run of this revision.
    op.execute(
        "ALTER TABLE projects.quotation_amendment_requests "
        "ADD COLUMN IF NOT EXISTS revised boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_quotation_amendment_requests_company_id "
        "ON projects.quotation_amendment_requests (company_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_amendment_requests_open "
        "ON projects.quotation_amendment_requests (issue_id) WHERE status = 'open'"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.quotation_amendment_request_rows (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES public.companies (id),
            request_id uuid NOT NULL
                REFERENCES projects.quotation_amendment_requests (id) ON DELETE CASCADE,
            line_id uuid NOT NULL REFERENCES projects.quotation_lines (id) ON DELETE CASCADE,
            field varchar(16) NOT NULL,
            value_from numeric(12, 2),
            value_to numeric(12, 2),
            decision varchar(16) NOT NULL DEFAULT 'pending',
            decision_reason varchar(500),
            decided_by varchar(100) REFERENCES public.users (id) ON DELETE SET NULL,
            decided_at timestamp,
            created_at timestamp NOT NULL DEFAULT now(),
            CONSTRAINT uq_quotation_amendment_rows_line_field UNIQUE (request_id, line_id, field),
            CONSTRAINT ck_quotation_amendment_rows_field
                CHECK (field IN ('quantity', 'unit_price', 'remove')),
            CONSTRAINT ck_quotation_amendment_rows_decision
                CHECK (decision IN ('pending', 'accepted', 'rejected'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_quotation_amendment_request_rows_company_id "
        "ON projects.quotation_amendment_request_rows (company_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS projects.quotation_amendment_request_rows")
    op.execute("DROP TABLE IF EXISTS projects.quotation_amendment_requests")
