"""NPA-FROM-SI: purchasing's "NPA needed" flag on the stock inquiry + an NPA line's current codes.

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order. Nothing is dropped or rewritten.

- `stock_inquiries.npa_requested` (+ who / when): purchasing asks the salesperson to create a
  New Product Application on its reply. Non-blocking.
- `new_product_applications.new_product_id` (+ not-opening reason, who / when): the ONE new code
  purchasing links (owner, mock v3).
- `new_product_application_sources`: the CURRENT product codes that new code is built from
  (lineage current codes -> new code).

Card: documentation/plans/procurement/CARD-npa-from-si-07nov.md.

Revision ID: npasi_0001_lineage
Revises: sales_0007_targets_view_own
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npasi_0001_lineage"
down_revision = "sales_0007_targets_view_own"
branch_labels = None
depends_on = None

UPGRADE = (
    "ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS npa_requested BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS npa_requested_by VARCHAR(100) "
    "REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS npa_requested_at TIMESTAMP",
    "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS new_product_id UUID "
    "REFERENCES products(id) ON DELETE RESTRICT",
    "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS new_code_closed_reason TEXT",
    "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS new_code_by VARCHAR(100) "
    "REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS new_code_at TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS ix_new_product_applications_new_product "
    "ON new_product_applications (new_product_id)",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_new_product_applications_one_new_code_outcome'
        ) THEN
            ALTER TABLE new_product_applications ADD CONSTRAINT ck_new_product_applications_one_new_code_outcome
            CHECK (new_product_id IS NULL OR new_code_closed_reason IS NULL);
        END IF;
    END $$
    """,
    """
    CREATE TABLE IF NOT EXISTS new_product_application_sources (
        id UUID PRIMARY KEY,
        application_id UUID NOT NULL REFERENCES new_product_applications(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
        position INTEGER NOT NULL DEFAULT 1,
        CONSTRAINT uq_npa_sources_application_product UNIQUE (application_id, product_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_npa_sources_product ON new_product_application_sources (product_id)",
)


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UPGRADE:
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    for statement in (
        "DROP TABLE IF EXISTS new_product_application_sources",
        "ALTER TABLE new_product_applications DROP CONSTRAINT IF EXISTS "
        "ck_new_product_applications_one_new_code_outcome",
        "DROP INDEX IF EXISTS ix_new_product_applications_new_product",
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS new_code_at",
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS new_code_by",
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS new_code_closed_reason",
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS new_product_id",
        "ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS npa_requested_at",
        "ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS npa_requested_by",
        "ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS npa_requested",
    ):
        bind.execute(sa.text(statement))
