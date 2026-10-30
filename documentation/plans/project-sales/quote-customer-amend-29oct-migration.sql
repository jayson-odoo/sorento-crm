-- QUOTE-CUSTOMER-AMEND: the same DDL as alembic revision qca1_0001_amendment_requests.
-- Idempotent; safe on a DB built by create_all. Does not touch alembic_version.

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
);

-- The table may already exist from an earlier run.
ALTER TABLE projects.quotation_amendment_requests
    ADD COLUMN IF NOT EXISTS revised boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS ix_projects_quotation_amendment_requests_company_id
    ON projects.quotation_amendment_requests (company_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_amendment_requests_open
    ON projects.quotation_amendment_requests (issue_id) WHERE status = 'open';

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
);

CREATE INDEX IF NOT EXISTS ix_projects_quotation_amendment_request_rows_company_id
    ON projects.quotation_amendment_request_rows (company_id);
