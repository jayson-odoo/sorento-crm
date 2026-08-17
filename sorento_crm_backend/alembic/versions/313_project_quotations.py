"""Project quotations, versions, lines, series and price floors (S3, UAC Group E).

Revision ID: 313_project_quotations
Revises: 312_project_leads

Two absences are the design, not omissions:

- ``project_quotation_versions`` has **no ``is_frozen``** and ``project_quotations`` has
  **no ``current_version_id``**. Current is ``MAX(version_no)``, frozen is anything
  below it, enforced by ``UNIQUE (quotation_id, version_no)``. A flag plus a pointer is
  two facts that must agree, and they stop agreeing the first time a write half-fails.
- ``price_floor_rules`` has **no level column**. The level is implied by which key is
  set (product / category / neither), so it cannot disagree with the keys. The unique
  index uses NULLS NOT DISTINCT, which makes the system-level rule a singleton per
  company instead of something an admin can create three of.

The alert state on a line is STORED rather than recomputed on read (AC-E7): a policy
change tomorrow must never retro-flag a quotation the customer already holds.
"""
from alembic import op

revision = "313_project_quotations"
down_revision = "312_project_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_series (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            name VARCHAR(150) NOT NULL,
            brand_id UUID REFERENCES brands(id) ON DELETE SET NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_project_series_company_name
            ON project_series (company_id, name);

        CREATE TABLE IF NOT EXISTS project_series_categories (
            series_id UUID NOT NULL REFERENCES project_series(id) ON DELETE CASCADE,
            category_id UUID NOT NULL
                REFERENCES product_categories(id) ON DELETE CASCADE,
            PRIMARY KEY (series_id, category_id)
        );

        CREATE TABLE IF NOT EXISTS price_floor_rules (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            product_id UUID REFERENCES products(id) ON DELETE CASCADE,
            category_id UUID REFERENCES product_categories(id) ON DELETE CASCADE,
            mode VARCHAR(16) NOT NULL DEFAULT 'percent',
            value NUMERIC(12, 2) NOT NULL,
            notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        -- One rule per level per target; NULLS NOT DISTINCT makes the system rule a
        -- singleton per company.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_price_floor_rules_company_target
            ON price_floor_rules (company_id, product_id, category_id)
            NULLS NOT DISTINCT;

        CREATE TABLE IF NOT EXISTS project_quotations (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            scope_label VARCHAR(150) NOT NULL,
            series_id UUID REFERENCES project_series(id) ON DELETE SET NULL,
            notes TEXT,
            outcome VARCHAR(16) NOT NULL DEFAULT 'open',
            loss_reason VARCHAR(150),
            decided_at TIMESTAMP,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_quotations_project
            ON project_quotations (project_id);
        CREATE INDEX IF NOT EXISTS ix_project_quotations_outcome
            ON project_quotations (company_id, outcome);

        CREATE TABLE IF NOT EXISTS project_quotation_versions (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            quotation_id UUID NOT NULL
                REFERENCES project_quotations(id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            frozen_at TIMESTAMP,
            issued_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
            issued_on DATE,
            total_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_project_quotation_versions_no
                UNIQUE (quotation_id, version_no)
        );

        CREATE TABLE IF NOT EXISTS project_quotation_lines (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            version_id UUID NOT NULL
                REFERENCES project_quotation_versions(id) ON DELETE CASCADE,
            product_id UUID REFERENCES products(id) ON DELETE SET NULL,
            product_code_snapshot VARCHAR(100),
            description_snapshot TEXT,
            list_price_snapshot NUMERIC(12, 2),
            image_attachment_id UUID REFERENCES attachments(id) ON DELETE SET NULL,
            unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0,
            quantity NUMERIC(12, 2) NOT NULL DEFAULT 1,
            uom VARCHAR(50),
            unit_type VARCHAR(24),
            line_total NUMERIC(15, 2) NOT NULL DEFAULT 0,
            is_non_standard BOOLEAN NOT NULL DEFAULT false,
            floor_value_applied NUMERIC(12, 2),
            floor_level_applied VARCHAR(24),
            is_below_floor BOOLEAN NOT NULL DEFAULT false,
            sort_order INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_quotation_lines_version
            ON project_quotation_lines (version_id, sort_order);
        CREATE INDEX IF NOT EXISTS ix_project_quotation_lines_flags
            ON project_quotation_lines (version_id, is_below_floor);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS project_quotation_lines;
        DROP TABLE IF EXISTS project_quotation_versions;
        DROP TABLE IF EXISTS project_quotations;
        DROP TABLE IF EXISTS price_floor_rules;
        DROP TABLE IF EXISTS project_series_categories;
        DROP TABLE IF EXISTS project_series;
        """
    )
