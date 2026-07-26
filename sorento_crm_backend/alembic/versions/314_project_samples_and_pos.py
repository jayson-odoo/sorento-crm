"""Project samples and customer purchase orders (S4, UAC Group F).

Revision ID: 314_project_samples_pos
Revises: 313_project_quotations

``project_purchase_orders`` is deliberately NOT ``purchase_orders`` (ADR-0002): that
table is supplier-side procurement, and folding an inbound customer commitment into it
would make every procurement report count revenue as spend.

The line-level mismatch flags are STORED, like the price-floor state on a quotation line
and for the same reason: they record what was true when the PO was checked, so editing
the quotation next week cannot make last week's PO change its mind about whether it
matched.
"""
from alembic import op

revision = "314_project_samples_pos"
down_revision = "313_project_quotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_samples (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            quotation_version_id UUID NOT NULL
                REFERENCES project_quotation_versions(id) ON DELETE CASCADE,
            submitted_on DATE,
            submitted_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
            developer_feedback TEXT,
            salesperson_notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_samples_project
            ON project_samples (project_id);
        CREATE INDEX IF NOT EXISTS ix_project_samples_version
            ON project_samples (quotation_version_id);

        CREATE TABLE IF NOT EXISTS project_purchase_orders (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            -- SET NULL rather than CASCADE: deleting a quotation must not delete the
            -- customer's PO, which is commercial history that outlives the document it
            -- was priced from.
            quotation_version_id UUID
                REFERENCES project_quotation_versions(id) ON DELETE SET NULL,
            po_source VARCHAR(24) NOT NULL DEFAULT 'contractor_direct',
            issuing_party_id UUID REFERENCES project_parties(id) ON DELETE SET NULL,
            po_number VARCHAR(100) NOT NULL,
            po_date DATE,
            po_amount NUMERIC(15, 2),
            notes TEXT,
            created_by VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            -- PO numbers belong to the issuer, so they are unique per issuer at best.
            -- Scoped to the project instead: recording the same number twice on one
            -- project is the mistake actually worth stopping.
            CONSTRAINT uq_project_purchase_orders_number UNIQUE (project_id, po_number)
        );
        CREATE INDEX IF NOT EXISTS ix_project_purchase_orders_project
            ON project_purchase_orders (project_id);
        CREATE INDEX IF NOT EXISTS ix_project_purchase_orders_version
            ON project_purchase_orders (quotation_version_id);

        CREATE TABLE IF NOT EXISTS project_purchase_order_lines (
            id UUID PRIMARY KEY,
            company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
            po_id UUID NOT NULL
                REFERENCES project_purchase_orders(id) ON DELETE CASCADE,
            product_id UUID REFERENCES products(id) ON DELETE SET NULL,
            product_code VARCHAR(100),
            description TEXT,
            unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0,
            quantity NUMERIC(12, 2) NOT NULL DEFAULT 1,
            uom VARCHAR(50),
            line_total NUMERIC(15, 2) NOT NULL DEFAULT 0,
            quoted_unit_price NUMERIC(12, 2),
            model_mismatch BOOLEAN NOT NULL DEFAULT false,
            price_mismatch BOOLEAN NOT NULL DEFAULT false,
            sort_order INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_project_po_lines_po
            ON project_purchase_order_lines (po_id, sort_order);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS project_purchase_order_lines;
        DROP TABLE IF EXISTS project_purchase_orders;
        DROP TABLE IF EXISTS project_samples;
        """
    )
