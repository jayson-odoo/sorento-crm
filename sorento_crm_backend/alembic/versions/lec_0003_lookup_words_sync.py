"""lookup words sync: seed the scheduled task that keeps the lookup words embedded

Seeds `lookup_words_sync` (every 600 s) the way 143_seed_embedding_job_processor_task seeds its row. Idempotent;
downgrade removes it.

Revision ID: lec_0003_lookup_words_sync
Revises: lec_0002_embedding_indexes
"""
from alembic import op
from sqlalchemy import text

revision = "lec_0003_lookup_words_sync"
down_revision = "lec_0002_embedding_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                id, key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                'lookup_words_sync',
                'Lookup words sync',
                'Embeds new or changed chatbot lookup words and retires removed ones.',
                true,
                'seconds',
                600,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            WHERE NOT EXISTS (SELECT 1 FROM scheduled_tasks WHERE key = 'lookup_words_sync')
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'lookup_words_sync'"))
