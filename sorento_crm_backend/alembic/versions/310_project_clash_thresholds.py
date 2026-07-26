"""Project registration clash bars as system settings (AC-C5).

Revision ID: 310_project_clash_thresholds
Revises: 309_project_sales_core

Two bars rather than one. Surfacing is generous because a missed duplicate is silent
and puts two people on one tender; blocking is strict because a false block fired
often enough teaches users to dismiss the warning. Defaults are the values calibrated
against the live title corpus (see app/services/project_clash_service.py).
"""
from alembic import op

revision = "310_project_clash_thresholds"
down_revision = "309_project_sales_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE system_settings
            ADD COLUMN IF NOT EXISTS project_clash_surface_threshold
                NUMERIC(4, 3) NOT NULL DEFAULT 0.550,
            ADD COLUMN IF NOT EXISTS project_clash_block_threshold
                NUMERIC(4, 3) NOT NULL DEFAULT 0.700;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE system_settings
            DROP COLUMN IF EXISTS project_clash_block_threshold,
            DROP COLUMN IF EXISTS project_clash_surface_threshold;
        """
    )
