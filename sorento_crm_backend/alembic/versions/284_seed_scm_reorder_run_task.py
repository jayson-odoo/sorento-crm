"""Seed scheduled task `scm_reorder_run` (SCM M8 daily reorder planning run).

Registers the configurable ``scheduled_tasks`` row that the scheduler heartbeat drives
on the worker/scheduler process (gated behind ``ENABLE_SCHEDULER``). The handler
``_handler_scm_reorder_run`` creates a reorder run across ALL active warehouses with
market insight OFF, then funds everything (full budget) so the morning snapshot opens
fully within-budget (M8-D1/D6). The user tightens the budget on the page to defer.

The "configurable time" (M8-D2) is this row's ``start_at`` (anchored to 06:00 KL) +
``interval_unit``/``interval_value`` (daily). Both — plus enablement and an optional
``metadata`` ``{budget, include_market}`` — are editable via the scheduled-tasks API/UI
with no code change. ``budget: null`` => full budget; ``include_market: false`` keeps
market out of the run (market reaches the plan only through chat, M8-D5).

Idempotent (``ON CONFLICT (key) DO NOTHING``) so a redeploy is safe.

Revision ID: 284_seed_scm_reorder_run_task
Revises: 283_scm_market_priority_factor
Create Date: 2026-07-17
"""
from alembic import op
from sqlalchemy import text


revision = "284_seed_scm_reorder_run_task"
down_revision = "283_scm_market_priority_factor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, metadata, created_at, updated_at
            ) VALUES (
                'scm_reorder_run',
                'SCM Daily Reorder Run',
                'Daily reorder planning run across all active warehouses with market '
                'insight off, then funds everything (full budget) so the morning '
                'snapshot opens fully within-budget. Anchored to 06:00 (Asia/Kuala_Lumpur); '
                'time + cadence configurable. metadata: {budget:null => full budget, '
                'include_market:false}.',
                true,
                'days',
                1,
                'Asia/Kuala_Lumpur',
                -- next 06:00 KL, stored as naive UTC (due-check compares to utcnow())
                timezone('utc', timezone('Asia/Kuala_Lumpur',
                    date_trunc('day', now() AT TIME ZONE 'Asia/Kuala_Lumpur') + interval '6 hours')),
                timezone('utc', timezone('Asia/Kuala_Lumpur',
                    date_trunc('day', now() AT TIME ZONE 'Asia/Kuala_Lumpur') + interval '6 hours')),
                '{"budget": null, "include_market": false}'::jsonb,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'scm_reorder_run'"))
