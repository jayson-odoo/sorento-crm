"""AGENT-REPORTS: the admin switch that sends sales / outstanding report asks to the agent

Revision ID: agrep_0001_agent_reports
Revises: pol_0001_stock_debt_link_po
Create Date: 2026-11-05 00:00:00.000000

Additive and idempotent: one boolean on `system_settings`, default false (off), so nothing changes
until an admin turns it on. Plan: documentation/plans/chatbot/PLAN-agent-reports-5nov.md.
"""
from alembic import op

revision = "agrep_0001_agent_reports"
down_revision = "pol_0001_stock_debt_link_po"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS chatbot_agent_reports_enabled BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_agent_reports_enabled")
