"""Email templates + automation modules.

Creates ``email_templates``, ``automations``, ``automation_runs`` tables; seeds
the master ``automation_runner`` scheduled task; syncs RBAC permissions for the
two new modules.

Revision ID: 174_email_templates_and_automation
Revises: 173_product_is_discontinued
Create Date: 2026-05-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "174_email_templates_and_automation"
down_revision = "173_product_is_discontinued"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("variables_schema", JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_email_templates_code"),
    )
    op.create_index("ix_email_templates_code", "email_templates", ["code"])
    op.create_index("ix_email_templates_is_active", "email_templates", ["is_active"])

    op.create_table(
        "automations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trigger_type", sa.String(length=80), nullable=False),
        sa.Column("trigger_config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("action_type", sa.String(length=80), nullable=False, server_default=sa.text("'send_email'")),
        sa.Column(
            "email_template_id",
            UUID(as_uuid=False),
            sa.ForeignKey("email_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("recipient_config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("schedule_type", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("run_time", sa.Time(), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default=sa.text("'Asia/Kuala_Lumpur'")),
        sa.Column("last_run_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_automations_email_template_id", "automations", ["email_template_id"])
    op.create_index("ix_automations_next_run_at", "automations", ["next_run_at"])
    op.create_index("ix_automations_enabled_next_run_at", "automations", ["enabled", "next_run_at"])

    op.create_table(
        "automation_runs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "automation_id",
            UUID(as_uuid=False),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_mode", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'running'")),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("recipients_attempted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("recipients_delivered", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_automation_runs_automation_id", "automation_runs", ["automation_id"])
    op.create_index(
        "ix_automation_runs_automation_id_started_at",
        "automation_runs",
        ["automation_id", "started_at"],
    )

    op.execute(
        """
        INSERT INTO scheduled_tasks (
            id, key, name, description, enabled,
            interval_unit, interval_value, timezone, next_run_at, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), 'automation_runner',
            'Automation runner', 'Scans enabled automations for due runs.',
            TRUE, 'minutes', 5, 'UTC', NOW(), NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_tasks WHERE key = 'automation_runner'
        )
        """
    )

    from sqlalchemy.orm import Session

    from app.rbac.permission_registry import sync_permissions

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session)
    finally:
        session.close()


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE key = 'automation_runner'")
    op.drop_index("ix_automation_runs_automation_id_started_at", table_name="automation_runs")
    op.drop_index("ix_automation_runs_automation_id", table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index("ix_automations_enabled_next_run_at", table_name="automations")
    op.drop_index("ix_automations_next_run_at", table_name="automations")
    op.drop_index("ix_automations_email_template_id", table_name="automations")
    op.drop_table("automations")
    op.drop_index("ix_email_templates_is_active", table_name="email_templates")
    op.drop_index("ix_email_templates_code", table_name="email_templates")
    op.drop_table("email_templates")
