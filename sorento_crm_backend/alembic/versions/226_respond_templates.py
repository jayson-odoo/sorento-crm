"""Respond.io WhatsApp template sync tables.

- `respond_channels` - synced channels per workspace (numeric channel id is
  required in template send payloads).
- `respond_message_templates` - WhatsApp templates per channel; only
  status='approved' rows are sendable. Hard-deleted on sync when gone.
- `respond_template_defaults` - one row per auto-send use case (complaint /
  stock_inquiry / purchase_request / sponsorship_form) with the param mapping
  used when the contact's 24h window is closed. `template_id` SET NULL on
  template delete; `template_name_snapshot` keeps the warning meaningful.

Plan: docs/plans/PLAN-whatsapp-template-fallback.md

Idempotent: IF NOT EXISTS guards so re-runs are no-ops.

Revision ID: 226_respond_templates
Revises: 225_chat_history_message_id_result
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op


revision = "226_respond_templates"
down_revision = "225_chat_history_message_id_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS respond_channels (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES respond_workspaces(id) ON DELETE CASCADE,
            respond_channel_id INTEGER NOT NULL,
            name VARCHAR(255),
            source VARCHAR(64),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            synced_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_respond_channels_ws_channel UNIQUE (workspace_id, respond_channel_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_channels_workspace_id ON respond_channels (workspace_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS respond_message_templates (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES respond_channels(id) ON DELETE CASCADE,
            respond_template_id INTEGER NOT NULL,
            meta_template_id VARCHAR(64),
            namespace VARCHAR(64),
            name VARCHAR(255) NOT NULL,
            language_code VARCHAR(16) NOT NULL DEFAULT 'en',
            category VARCHAR(32),
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            status_detail VARCHAR(255),
            components JSONB NOT NULL DEFAULT '[]'::jsonb,
            body_text TEXT NOT NULL DEFAULT '',
            param_count INTEGER NOT NULL DEFAULT 0,
            synced_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_respond_templates_channel_tpl UNIQUE (channel_id, respond_template_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_message_templates_channel_id ON respond_message_templates (channel_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_message_templates_status ON respond_message_templates (status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS respond_template_defaults (
            id UUID PRIMARY KEY,
            use_case VARCHAR(32) NOT NULL UNIQUE,
            template_id UUID REFERENCES respond_message_templates(id) ON DELETE SET NULL,
            template_name_snapshot VARCHAR(255),
            param_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


    # Seed the daily template sync scheduled task (handler registered in
    # task_scheduler.py). Idempotent: ON CONFLICT on the unique key.
    op.execute(
        """
        INSERT INTO scheduled_tasks (id, key, name, description, enabled, interval_unit, interval_value, timezone)
        VALUES (
            gen_random_uuid(),
            'respond_templates_sync',
            'Respond.io WhatsApp template sync',
            'Pull channels + WhatsApp message templates from Respond.io for all active workspaces (used by 24h-window template sending).',
            TRUE,
            'hours',
            24,
            'UTC'
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE key = 'respond_templates_sync'")
    op.execute("DROP TABLE IF EXISTS respond_template_defaults")
    op.execute("DROP TABLE IF EXISTS respond_message_templates")
    op.execute("DROP TABLE IF EXISTS respond_channels")
