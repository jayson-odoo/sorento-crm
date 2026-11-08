"""QUOTE-CERT-TAB: model code and box cache on certificate coverage, per-quote certificate markers.

Additive and idempotent (IF NOT EXISTS) so the shared dev DB, which converges through
`create_all`, can take it in any order.
Plan: documentation/plans/certificates/PLAN-quote-cert-tab-08nov.md.

Revision ID: qcert_0001_quote_certificates
Revises: ptag_0019_acc_colours
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "qcert_0001_quote_certificates"
down_revision = "ptag_0019_acc_colours"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS model_code VARCHAR(60)",
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS model_code_source VARCHAR(10)",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_certificate_products_code_source'
        ) THEN
            ALTER TABLE certificate_products ADD CONSTRAINT ck_certificate_products_code_source
                CHECK (model_code_source IS NULL OR model_code_source IN ('ai', 'manual'));
        END IF;
    END
    $$
    """,
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS boxes JSONB",
    "ALTER TABLE projects.quotation_issues ADD COLUMN IF NOT EXISTS certificates JSONB",
    """
    CREATE TABLE IF NOT EXISTS projects.quotation_document_certificates (
        id UUID PRIMARY KEY,
        company_id UUID NOT NULL REFERENCES companies(id),
        document_id UUID NOT NULL REFERENCES projects.quotation_documents(id) ON DELETE CASCADE,
        certificate_id UUID NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
        included BOOLEAN NOT NULL DEFAULT true,
        source VARCHAR(10) NOT NULL,
        send_to_customer BOOLEAN,
        boxes JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        created_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_quotation_document_certificates UNIQUE (document_id, certificate_id),
        CONSTRAINT ck_quotation_document_certificates_source CHECK (source IN ('auto', 'manual'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_quotation_document_certificates_company_id "
    "ON projects.quotation_document_certificates (company_id)",
)

DOWNGRADE_SQL = (
    "DROP TABLE IF EXISTS projects.quotation_document_certificates",
    "ALTER TABLE projects.quotation_issues DROP COLUMN IF EXISTS certificates",
    "ALTER TABLE certificate_products DROP CONSTRAINT IF EXISTS ck_certificate_products_code_source",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS boxes",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS model_code_source",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS model_code",
)


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UPGRADE_SQL:
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    for statement in DOWNGRADE_SQL:
        bind.execute(sa.text(statement))
