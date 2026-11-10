"""NPA-FORM-SLA: the New Product Application's revision number (the list's Rev column).

Owner hand test 9 Nov: the NPA list carries the stock inquiry list's columns, Rev included. The
NPA's Revise sends it back to Draft and counted nothing; this column counts each Revise (0 =
never revised), shown like the stock inquiry's revision badge. Additive and idempotent.

Plan: documentation/plans/procurement/PLAN-npa-form-sla-08nov.md.

Revision ID: npasla_0002_npa_revision_no
Revises: npasla_0001_seed_configs
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npasla_0002_npa_revision_no"
down_revision = "npasla_0001_seed_configs"
branch_labels = None
depends_on = None

UPGRADE = (
    "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS revision_no INTEGER NOT NULL DEFAULT 0",
)


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE new_product_applications DROP COLUMN IF EXISTS revision_no")
