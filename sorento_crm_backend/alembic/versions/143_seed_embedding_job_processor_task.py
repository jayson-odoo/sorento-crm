"""Seed scheduled task for embedding queue processor.

Revision ID: 143_seed_embedding_job_processor_task
Revises: 142_pgvector_embedding_pipeline
Create Date: 2026-04-17
"""
from alembic import op
from sqlalchemy import text


revision = "143_seed_embedding_job_processor_task"
down_revision = "142_pgvector_embedding_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            ) VALUES (
                'embedding_job_processor',
                'Embedding job processor',
                'Processes embedding jobs from Redis RQ and updates pgvector tables.',
                true,
                'seconds',
                30,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'embedding_job_processor'"))
