"""AGENT-REPORTS: the admin switch that sends sales / outstanding report asks to the agent

Revision ID: agrep_0001_agent_reports
Revises: pol_0001_stock_debt_link_po
Create Date: 2026-11-05 00:00:00.000000

Idempotent. One boolean on `system_settings`, default false (off), so nothing changes until an admin
turns it on. And the agent's history compaction threshold drops from 40k to 12k tokens (owner, 5 Nov
2026): the column default changes, and a row still holding the old default 40000 moves to 12000; a
value an admin set to anything else is left alone. Plan: documentation/plans/chatbot/PLAN-agent-reports-5nov.md.
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
    op.execute("ALTER TABLE system_settings ALTER COLUMN chatbot_agent_compact_tokens SET DEFAULT 12000")
    op.execute("UPDATE system_settings SET chatbot_agent_compact_tokens = 12000 WHERE chatbot_agent_compact_tokens = 40000")


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings ALTER COLUMN chatbot_agent_compact_tokens SET DEFAULT 40000")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_agent_reports_enabled")
