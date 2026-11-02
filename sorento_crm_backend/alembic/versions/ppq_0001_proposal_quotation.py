"""PS-PROPOSAL-QUOTATION: proposals convert to a quotation; PO quantity reason

* ``projects.quotation_documents`` + kind ('proposal' | 'quotation', every existing row a
  proposal), source_issue_id (the proposal revision a quotation was made from), and one quotation
  per project (partial unique index).
* ``projects.quotation_issues`` + revision_label ('A', 'B' ... for a proposal first issued after
  this lane, 'R1', 'R2' ... otherwise); every existing issue is backfilled 'R<issue_no>' so nothing
  already sent changes its name.
* ``projects.purchase_orders`` + qty_over_reason / _by / _at: the salesperson's reason when the
  POs of a project order more of a product than the quotation quoted (a soft stop).
* A ``project_sales_quotation`` numbering rule per company, ``QT-{year}-`` + 4 digits.

Plan: documentation/plans/project-sales/PLAN-proposal-quotation-2nov.md. Additive and guarded
so a re-run, or a dev DB built by create_all, is harmless.

Revision ID: ppq_0001_proposal_quotation
Revises: il_0001_integration_log_indexes
"""
from alembic import op

revision = "ppq_0001_proposal_quotation"
down_revision = "il_0001_integration_log_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE projects.quotation_documents
            ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'proposal',
            ADD COLUMN IF NOT EXISTS source_issue_id UUID
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_quotation_documents_kind'
            ) THEN
                ALTER TABLE projects.quotation_documents
                    ADD CONSTRAINT ck_quotation_documents_kind
                    CHECK (kind IN ('proposal', 'quotation'));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_quotation_documents_source_issue'
            ) THEN
                ALTER TABLE projects.quotation_documents
                    ADD CONSTRAINT fk_quotation_documents_source_issue
                    FOREIGN KEY (source_issue_id) REFERENCES projects.quotation_issues (id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_documents_one_quotation
            ON projects.quotation_documents (project_id)
            WHERE kind = 'quotation'
        """
    )

    op.execute(
        """
        ALTER TABLE projects.quotation_issues
            ADD COLUMN IF NOT EXISTS revision_label VARCHAR(8)
        """
    )
    op.execute(
        """
        UPDATE projects.quotation_issues
           SET revision_label = 'R' || issue_no
         WHERE revision_label IS NULL
        """
    )

    op.execute(
        """
        ALTER TABLE projects.purchase_orders
            ADD COLUMN IF NOT EXISTS qty_over_reason TEXT,
            ADD COLUMN IF NOT EXISTS qty_over_reason_by VARCHAR(100),
            ADD COLUMN IF NOT EXISTS qty_over_reason_at TIMESTAMP
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_purchase_orders_qty_over_reason_by'
            ) THEN
                ALTER TABLE projects.purchase_orders
                    ADD CONSTRAINT fk_purchase_orders_qty_over_reason_by
                    FOREIGN KEY (qty_over_reason_by) REFERENCES users (id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # A rule per company, so the first quotation does not have to invent its own number.
    # `QT-{year}-` is a starting point an admin can change in Settings > Numbering.
    op.execute(
        """
        INSERT INTO document_numbering_rules
            (id, company_id, doc_type, enabled, prefix_template, number_digits,
             next_value, start_value, reset_policy)
        SELECT gen_random_uuid(), c.id, 'project_sales_quotation', true, 'QT-{year}-', 4, 1, 1,
               'yearly'
        FROM companies c
        WHERE NOT EXISTS (
            SELECT 1 FROM document_numbering_rules r
            WHERE r.doc_type = 'project_sales_quotation' AND r.company_id = c.id
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM document_numbering_rules WHERE doc_type = 'project_sales_quotation'")
    op.execute(
        """
        ALTER TABLE projects.purchase_orders
            DROP CONSTRAINT IF EXISTS fk_purchase_orders_qty_over_reason_by,
            DROP COLUMN IF EXISTS qty_over_reason,
            DROP COLUMN IF EXISTS qty_over_reason_by,
            DROP COLUMN IF EXISTS qty_over_reason_at
        """
    )
    op.execute("ALTER TABLE projects.quotation_issues DROP COLUMN IF EXISTS revision_label")
    op.execute("DROP INDEX IF EXISTS projects.uq_quotation_documents_one_quotation")
    op.execute(
        """
        ALTER TABLE projects.quotation_documents
            DROP CONSTRAINT IF EXISTS fk_quotation_documents_source_issue,
            DROP CONSTRAINT IF EXISTS ck_quotation_documents_kind,
            DROP COLUMN IF EXISTS source_issue_id,
            DROP COLUMN IF EXISTS kind
        """
    )
