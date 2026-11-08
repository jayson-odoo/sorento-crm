"""CERT-LINK-CLEANUP: per-link text check on certificate coverage.

Additive and idempotent (IF NOT EXISTS) so the shared dev DB, which converges through
`create_all`, can take it in any order.
Plan: documentation/plans/certificates/PLAN-cert-link-cleanup-08nov.md.

Revision ID: clink_0001_link_checks
Revises: pfcn_0001_list_price_notify
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "clink_0001_link_checks"
down_revision = "pfcn_0001_list_price_notify"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS check_verdict VARCHAR(12)",
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS check_code VARCHAR(60)",
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS check_key TEXT",
    "ALTER TABLE certificate_products ADD COLUMN IF NOT EXISTS checked_at TIMESTAMP",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_certificate_products_check_verdict'
        ) THEN
            ALTER TABLE certificate_products ADD CONSTRAINT ck_certificate_products_check_verdict
                CHECK (check_verdict IS NULL OR check_verdict IN ('found', 'check', 'not_found', 'scanned', 'no_file'));
        END IF;
    END
    $$
    """,
)

DOWNGRADE_SQL = (
    "ALTER TABLE certificate_products DROP CONSTRAINT IF EXISTS ck_certificate_products_check_verdict",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS checked_at",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS check_key",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS check_code",
    "ALTER TABLE certificate_products DROP COLUMN IF EXISTS check_verdict",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
