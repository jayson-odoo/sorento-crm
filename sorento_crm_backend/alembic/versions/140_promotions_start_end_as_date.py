"""Store promotions.start_date/end_date as DATE (calendar day, no clock time).

Revision ID: 140_promotions_start_end_as_date
Revises: 139_seed_promotion_active_window_task
Create Date: 2026-04-14

Existing timestamps were naive UTC instants for MY midnight; convert each row to the
Malaysia civil calendar date (same semantics as the app).
"""
from alembic import op


revision = "140_promotions_start_end_as_date"
down_revision = "139_seed_promotion_active_window_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE promotions
        ALTER COLUMN start_date TYPE date
        USING (((start_date AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Kuala_Lumpur')::date)
        """
    )
    op.execute(
        """
        ALTER TABLE promotions
        ALTER COLUMN end_date TYPE date
        USING (((end_date AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Kuala_Lumpur')::date)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE promotions
        ALTER COLUMN start_date TYPE timestamp without time zone
        USING start_date::timestamp
        """
    )
    op.execute(
        """
        ALTER TABLE promotions
        ALTER COLUMN end_date TYPE timestamp without time zone
        USING end_date::timestamp
        """
    )
