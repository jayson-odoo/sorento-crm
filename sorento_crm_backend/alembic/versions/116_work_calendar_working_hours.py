"""Add work_day_start_time and work_day_end_time to work_calendar_configs.

Revision ID: 116_work_calendar_working_hours
Revises: 115_orders_estimated_delivery_date_column
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "116_work_calendar_working_hours"
down_revision = "115_orders_estimated_delivery_date_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "work_calendar_configs" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("work_calendar_configs")}
    if "work_day_start_time" not in cols:
        op.add_column(
            "work_calendar_configs",
            sa.Column(
                "work_day_start_time",
                sa.Time(),
                nullable=False,
                server_default=sa.text("'09:00:00'::time"),
            ),
        )
    if "work_day_end_time" not in cols:
        op.add_column(
            "work_calendar_configs",
            sa.Column(
                "work_day_end_time",
                sa.Time(),
                nullable=False,
                server_default=sa.text("'17:00:00'::time"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "work_calendar_configs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("work_calendar_configs")}
    if "work_day_end_time" in cols:
        op.drop_column("work_calendar_configs", "work_day_end_time")
    if "work_day_start_time" in cols:
        op.drop_column("work_calendar_configs", "work_day_start_time")
