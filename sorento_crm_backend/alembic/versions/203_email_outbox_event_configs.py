"""Email outbox + event configs + SystemSetting guardrail thresholds.

Single chokepoint for outbound mail. Every email becomes a row in `email_outbox`
that a scheduled drainer dispatches respecting global + per-recipient caps.
`email_event_configs` rows give operators a per-event kill switch.

Revision ID: 203_email_outbox_event_configs
Revises: 202_agent_mcp_tools_team_binding
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "203_email_outbox_event_configs"
down_revision = "202_agent_mcp_tools_team_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("event_key", sa.String(length=120), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("recipients_json", JSONB(), nullable=True),
        sa.Column("subject", sa.String(length=1024), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("from_name", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", JSONB(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scheduled_for", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=120), nullable=True),
        sa.Column("coalesce_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_outbox_event_key", "email_outbox", ["event_key"])
    op.create_index("ix_email_outbox_recipient_email", "email_outbox", ["recipient_email"])
    op.create_index("ix_email_outbox_drain", "email_outbox", ["status", "scheduled_for", "priority"])
    op.create_index("ix_email_outbox_recipient_created", "email_outbox", ["recipient_email", "created_at"])
    op.create_index("ix_email_outbox_coalesce", "email_outbox", ["coalesce_key", "status"])

    op.create_table(
        "email_event_configs",
        sa.Column("event_key", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rate_per_window_override", sa.Integer(), nullable=True),
        sa.Column("window_seconds_override", sa.Integer(), nullable=True),
        sa.Column("priority_override", sa.Integer(), nullable=True),
        sa.Column("coalesce_window_seconds_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )

    op.add_column(
        "system_settings",
        sa.Column("email_global_rate_per_window", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "system_settings",
        sa.Column("email_global_window_seconds", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "system_settings",
        sa.Column("email_per_recipient_rate_per_window", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "system_settings",
        sa.Column("email_per_recipient_window_seconds", sa.Integer(), nullable=False, server_default="3600"),
    )
    op.add_column(
        "system_settings",
        sa.Column("email_outbox_drain_batch_size", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column(
        "system_settings",
        sa.Column("email_outbox_drain_interval_seconds", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "email_outbox_drain_interval_seconds")
    op.drop_column("system_settings", "email_outbox_drain_batch_size")
    op.drop_column("system_settings", "email_per_recipient_window_seconds")
    op.drop_column("system_settings", "email_per_recipient_rate_per_window")
    op.drop_column("system_settings", "email_global_window_seconds")
    op.drop_column("system_settings", "email_global_rate_per_window")

    op.drop_table("email_event_configs")

    op.drop_index("ix_email_outbox_coalesce", table_name="email_outbox")
    op.drop_index("ix_email_outbox_recipient_created", table_name="email_outbox")
    op.drop_index("ix_email_outbox_drain", table_name="email_outbox")
    op.drop_index("ix_email_outbox_recipient_email", table_name="email_outbox")
    op.drop_index("ix_email_outbox_event_key", table_name="email_outbox")
    op.drop_table("email_outbox")
