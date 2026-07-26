"""Project Sales module: generic skeleton + Sorento sales extension.

Revision ID: 309_project_sales_core
Revises: 308_status_engine

Ten tables (ADR-0003), all idempotent raw SQL so a partially-applied run can be
re-run: ``project_types``, ``project_templates``, ``project_template_roles``,
``project_parties``, ``projects``, ``project_sales_profile``, ``project_brands``,
``project_stakeholders``, ``project_collaborators``, ``project_takeover_requests``.

Two things here are load-bearing and easy to get wrong:

1. **The registration lock** is a unique index with ``NULLS NOT DISTINCT``
   (Postgres 15+). Without that clause Postgres treats every NULL as distinct, so
   a null ``developer_party_id`` would let unlimited duplicates through -- the
   exact defect found in the ported status-engine constraint (ADR-0001).
2. **The trigram index** on ``projects.normalised_title``. The clash matcher's
   GREATEST-of-three-measures score cannot use it, but the plain ``similarity``
   probes in adjacent features can, and it costs nothing to have.
"""
from alembic import op

revision = "309_project_sales_core"
down_revision = "308_status_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_types (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            name VARCHAR(120) NOT NULL,
            code VARCHAR(64) NOT NULL,
            description TEXT,
            derives_delivery_from_launch BOOLEAN NOT NULL DEFAULT false,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_project_types_company_code UNIQUE (company_id, code)
        );

        CREATE TABLE IF NOT EXISTS project_templates (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            type_id UUID NOT NULL REFERENCES project_types(id) ON DELETE RESTRICT,
            name VARCHAR(120) NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_project_templates_name UNIQUE (company_id, type_id, name)
        );

        CREATE TABLE IF NOT EXISTS project_template_roles (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            template_id UUID NOT NULL
                REFERENCES project_templates(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_project_template_roles_name UNIQUE (template_id, name)
        );

        CREATE TABLE IF NOT EXISTS project_parties (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            party_type VARCHAR(32) NOT NULL,
            name VARCHAR(255) NOT NULL,
            registration_no VARCHAR(100),
            address TEXT,
            phone VARCHAR(50),
            email VARCHAR(150),
            notes TEXT,
            customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_parties_company_type
            ON project_parties (company_id, party_type);
        CREATE INDEX IF NOT EXISTS ix_project_parties_name
            ON project_parties (name);

        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            project_code VARCHAR(64) NOT NULL,
            title TEXT NOT NULL,
            normalised_title TEXT NOT NULL,
            developer_party_id UUID
                REFERENCES project_parties(id) ON DELETE RESTRICT,
            type_id UUID REFERENCES project_types(id) ON DELETE RESTRICT,
            template_id UUID REFERENCES project_templates(id) ON DELETE RESTRICT,
            status_id UUID REFERENCES statuses(id) ON DELETE SET NULL,
            outcome VARCHAR(16) NOT NULL DEFAULT 'open',
            loss_reason VARCHAR(64),
            owner_user_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
            is_critical BOOLEAN NOT NULL DEFAULT false,
            critical_at TIMESTAMP,
            management_support TEXT,
            management_notes TEXT,
            last_meaningful_activity_at TIMESTAMP,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_projects_company_code UNIQUE (company_id, project_code)
        );
        CREATE INDEX IF NOT EXISTS ix_projects_company_outcome
            ON projects (company_id, outcome);
        CREATE INDEX IF NOT EXISTS ix_projects_status ON projects (status_id);
        CREATE INDEX IF NOT EXISTS ix_projects_owner ON projects (owner_user_id);

        CREATE TABLE IF NOT EXISTS project_sales_profile (
            project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            registered_company_name TEXT,
            location TEXT,
            address TEXT,
            architect_party_id UUID
                REFERENCES project_parties(id) ON DELETE SET NULL,
            main_contractor_party_id UUID
                REFERENCES project_parties(id) ON DELETE SET NULL,
            estimated_sales_value NUMERIC(15, 2),
            launch_date DATE,
            expected_delivery_from DATE,
            expected_delivery_to DATE,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS project_brands (
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            PRIMARY KEY (project_id, brand_id)
        );

        CREATE TABLE IF NOT EXISTS project_stakeholders (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            party_id UUID REFERENCES project_parties(id) ON DELETE SET NULL,
            role_id UUID
                REFERENCES project_template_roles(id) ON DELETE RESTRICT,
            person_name VARCHAR(255) NOT NULL,
            job_title VARCHAR(120),
            phone VARCHAR(50),
            email VARCHAR(150),
            influence VARCHAR(16),
            is_primary BOOLEAN NOT NULL DEFAULT false,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_stakeholders_project
            ON project_stakeholders (project_id);

        CREATE TABLE IF NOT EXISTS project_collaborators (
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            granted_by VARCHAR(100),
            granted_at TIMESTAMP NOT NULL DEFAULT now(),
            PRIMARY KEY (project_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS project_takeover_requests (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            requester_user_id VARCHAR(100) NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            kind VARCHAR(16) NOT NULL,
            reason TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            decided_by VARCHAR(100),
            decided_at TIMESTAMP,
            decision_note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_takeover_requests_project
            ON project_takeover_requests (project_id, status);
        """
    )

    # The registration lock (ADR-0004). NULLS NOT DISTINCT is what makes it real:
    # by default Postgres treats every NULL as distinct, so rows with no developer
    # would each satisfy the constraint and duplicates would walk straight through.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class
                WHERE relname = 'uq_projects_company_developer_title'
            ) THEN
                CREATE UNIQUE INDEX uq_projects_company_developer_title
                    ON projects (company_id, developer_party_id, normalised_title)
                    NULLS NOT DISTINCT;
            END IF;
        END $$;
        """
    )

    # Trigram index for the clash matcher's neighbourhood probes. pg_trgm is already
    # installed (entity_resolver depends on it); CREATE EXTENSION IF NOT EXISTS keeps
    # a fresh database working.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_projects_normalised_title_trgm
            ON projects USING gin (normalised_title gin_trgm_ops);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS project_takeover_requests;
        DROP TABLE IF EXISTS project_collaborators;
        DROP TABLE IF EXISTS project_stakeholders;
        DROP TABLE IF EXISTS project_brands;
        DROP TABLE IF EXISTS project_sales_profile;
        DROP TABLE IF EXISTS projects;
        DROP TABLE IF EXISTS project_parties;
        DROP TABLE IF EXISTS project_template_roles;
        DROP TABLE IF EXISTS project_templates;
        DROP TABLE IF EXISTS project_types;
        """
    )
