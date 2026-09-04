"""`spo_allocations` gains the source-ref pair a shipping-order push needs (D3, S3).

A shipping order has no header table of its own - it is a GROUP of
`spo_allocations` rows sharing one `spo_number` (migration 420). AutoCount's
DocKey has to name that group and its DtlKey has to name one line within it,
so both land here rather than on a table that does not exist.

`source_doc_ref` is indexed plainly (a push resolves its document's current
rows by it); `source_ref` is uniquely indexed but PARTIAL, because every
xlsx-era row predates this column and is NULL - a plain unique index would
forbid more than one such row per company, which is the normal case.

Revision ID: 474_spo_allocations_source_ref
Revises: 473_scm_claim_autocount_source
"""
import sqlalchemy as sa
from alembic import op

revision = "474_spo_allocations_source_ref"
down_revision = "473_scm_claim_autocount_source"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text("ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS source_ref VARCHAR(255)")
    )
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS source_doc_ref VARCHAR(255)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_spo_allocations_company_source_doc_ref "
            "ON spo_allocations (company_id, source_doc_ref)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_spo_allocations_company_source_ref "
            "ON spo_allocations (company_id, source_ref) WHERE source_ref IS NOT NULL"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_spo_allocations_company_source_ref"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_spo_allocations_company_source_doc_ref"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS source_doc_ref"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS source_ref"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
