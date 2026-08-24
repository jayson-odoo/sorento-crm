"""Global default grace percentage for scheduled-task overdue detection.

Overdue was previously derived from `scheduled_tasks.next_run_at`, a display-only
column the scheduler never consults, with no tolerance at all - so ordinary run
jitter produced alert emails. Overdue is now `last_run_at + interval + grace`,
where grace is this percentage of each task's own interval, clamped to
[60s, 30min] in code.

Per-task overrides live in the existing `scheduled_tasks.metadata` JSONB under
`grace_percent`, so they need no schema change.

Revision ID: 289_scheduled_task_grace_percent
Revises: 288_ideation_embed_config
"""
from alembic import op
import sqlalchemy as sa

revision = "289_scheduled_task_grace_percent"
down_revision = "288_ideation_embed_config"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: this migration has shipped to environments that may already
    # carry the column from a hand-applied fix.
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'system_settings' "
            "AND column_name = 'health_task_grace_percent'"
        )
    ).scalar()
    if exists:
        return

    op.add_column(
        "system_settings",
        sa.Column(
            "health_task_grace_percent",
            sa.Integer(),
            nullable=False,
            server_default="25",
        ),
    )


def downgrade():
    op.drop_column("system_settings", "health_task_grace_percent")
