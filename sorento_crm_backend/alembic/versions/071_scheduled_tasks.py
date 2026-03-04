"""Create scheduled_tasks and scheduled_task_runs tables.

Revision ID: 071_scheduled_tasks
Revises: 070_entity_type_promotion
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "071_scheduled_tasks"
down_revision = "070_entity_type_promotion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_unit", sa.String(20), nullable=False),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("start_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_status", sa.String(50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scheduled_tasks_key", "scheduled_tasks", ["key"], unique=True)
    op.create_index("ix_scheduled_tasks_next_run_at", "scheduled_tasks", ["next_run_at"])
    op.create_index("ix_scheduled_tasks_next_run_at_enabled", "scheduled_tasks", ["next_run_at", "enabled"])

    op.create_table(
        "scheduled_task_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("scheduled_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_scheduled_task_runs_task_id", "scheduled_task_runs", ["task_id"])
    op.create_index("ix_scheduled_task_runs_task_id_started_at", "scheduled_task_runs", ["task_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_task_runs_task_id_started_at", table_name="scheduled_task_runs")
    op.drop_index("ix_scheduled_task_runs_task_id", table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")
    op.drop_index("ix_scheduled_tasks_next_run_at_enabled", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_next_run_at", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_key", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
