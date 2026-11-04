"""Sales targets can count Invoiced (TARGET-INVOICED, owner 4 Nov 2026)

Revision ID: tinv_0001_target_invoiced_basis
Revises: oiod_0001_backfill
Create Date: 2026-11-04 00:00:00.000000

Widens `sales.targets.ck_sales_targets_basis` to accept `invoiced`. Saved targets keep their
basis; the column and API defaults stay `ordered` (the dealer import and API callers keep their
behaviour); the target screen preselects Invoiced for a new target. The downgrade never
rewrites a saved basis: while any target counts Invoiced, Postgres refuses the narrowed CHECK.
"""
from alembic import op

revision = "tinv_0001_target_invoiced_basis"
down_revision = "oiod_0001_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.targets DROP CONSTRAINT IF EXISTS ck_sales_targets_basis")
    op.execute(
        "ALTER TABLE sales.targets ADD CONSTRAINT ck_sales_targets_basis "
        "CHECK (basis IN ('ordered', 'delivered', 'invoiced'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales.targets DROP CONSTRAINT IF EXISTS ck_sales_targets_basis")
    op.execute(
        "ALTER TABLE sales.targets ADD CONSTRAINT ck_sales_targets_basis "
        "CHECK (basis IN ('ordered', 'delivered'))"
    )
