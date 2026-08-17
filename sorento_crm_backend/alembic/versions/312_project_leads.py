"""Project leads (S2c, UAC Group O).

Revision ID: 312_project_leads
Revises: 311_project_tasks

One table plus two columns.

``project_leads`` has NO unique index on its title, unlike ``projects``. That absence
is the design: a lead is a rumour and is deliberately not exclusive (AC-O3), so two
salespeople may record the same sighting. Ownership locks at qualify, which is where
the registration lock finally applies.

``projects.lead_id`` is ON DELETE SET NULL so deleting a rumour can never take a live
registration with it, and ``customers.source`` marks the rows the lead wizard creates
for organisations that have never bought anything, so order and invoice pickers can
filter prospects out later.
"""
from alembic import op

revision = "312_project_leads"
down_revision = "311_project_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_leads (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            lead_code VARCHAR(64) NOT NULL,
            customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
            developer_party_id UUID REFERENCES project_parties(id) ON DELETE RESTRICT,
            title TEXT NOT NULL,
            normalised_title TEXT NOT NULL,
            source VARCHAR(32),
            source_detail TEXT,
            estimated_value NUMERIC(15, 2),
            location TEXT,
            notes TEXT,
            status_id UUID REFERENCES statuses(id) ON DELETE SET NULL,
            outcome VARCHAR(16) NOT NULL DEFAULT 'open',
            disqualified_reason VARCHAR(150),
            qualified_at TIMESTAMP,
            owner_user_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_project_leads_company_code
            ON project_leads (company_id, lead_code);
        CREATE INDEX IF NOT EXISTS ix_project_leads_company_outcome
            ON project_leads (company_id, outcome);
        CREATE INDEX IF NOT EXISTS ix_project_leads_customer
            ON project_leads (customer_id);
        CREATE INDEX IF NOT EXISTS ix_project_leads_status
            ON project_leads (status_id);
        CREATE INDEX IF NOT EXISTS ix_project_leads_owner_user_id
            ON project_leads (owner_user_id);
        -- Backs the informational near-duplicate hint, NOT a constraint.
        CREATE INDEX IF NOT EXISTS ix_project_leads_company_normalised
            ON project_leads (company_id, normalised_title);

        ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS lead_id UUID
                REFERENCES project_leads(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS ix_projects_lead ON projects (lead_id);

        ALTER TABLE customers
            ADD COLUMN IF NOT EXISTS source VARCHAR(32);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_projects_lead;
        ALTER TABLE projects DROP COLUMN IF EXISTS lead_id;
        ALTER TABLE customers DROP COLUMN IF EXISTS source;
        DROP TABLE IF EXISTS project_leads;
        """
    )
