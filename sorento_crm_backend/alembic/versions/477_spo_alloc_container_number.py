"""`spo_allocations` gains `container_number` (D6, S3): AutoCount's `PO.Ref`
cell, cleaned through `shipping_order_rules.extract_container_number`.

Revision ID: 477_spo_alloc_container_number
Revises: 476_customers_region
"""
import sqlalchemy as sa
from alembic import op

revision = "477_spo_alloc_container_number"
down_revision = "476_customers_region"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS container_number VARCHAR(100)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_spo_allocations_company_container "
            "ON spo_allocations (company_id, container_number)"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_spo_allocations_company_container"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS container_number"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
