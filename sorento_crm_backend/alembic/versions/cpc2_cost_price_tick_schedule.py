"""Seed scheduled task `cost_price_daily_tick` (#1288, Lane A, AC-CL-05).

`cpc1_supplier_cost_lists` registered the handler (`_handler_cost_price_daily_tick` in
`app/services/scheduled_task_service.py`) but seeded no `scheduled_tasks` row, and the
scheduler heartbeat only dispatches seeded rows. Without this row a cost list row dated to
start tomorrow would stay Scheduled forever and `product_suppliers.unit_cost` would never move
to it.

Daily at 00:05 Asia/Kuala_Lumpur, so the new day's price is in force before anyone reads it.
Time and cadence stay editable on the scheduled-tasks screen. Idempotent
(`ON CONFLICT (key) DO NOTHING`), so a redeploy is safe.

Revision ID: cpc2_cost_price_tick_schedule
Revises: cpc1_supplier_cost_lists
Create Date: 2026-09-27
"""
from alembic import op
from sqlalchemy import text


revision = "cpc2_cost_price_tick_schedule"
down_revision = "cpc1_supplier_cost_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                id, key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            ) VALUES (
                gen_random_uuid(),
                'cost_price_daily_tick',
                'Supplier Cost Price Daily Tick',
                'Moves each product-supplier price to the cost list row in force today '
                '(latest start wins), so a dated supplier price takes effect on its start '
                'date. Anchored to 00:05 (Asia/Kuala_Lumpur).',
                true,
                'days',
                1,
                'Asia/Kuala_Lumpur',
                -- next 00:05 KL, stored as naive UTC (the due check compares to utcnow())
                timezone('utc', timezone('Asia/Kuala_Lumpur',
                    date_trunc('day', now() AT TIME ZONE 'Asia/Kuala_Lumpur') + interval '1 day 5 minutes')),
                timezone('utc', timezone('Asia/Kuala_Lumpur',
                    date_trunc('day', now() AT TIME ZONE 'Asia/Kuala_Lumpur') + interval '1 day 5 minutes')),
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'cost_price_daily_tick'"))
