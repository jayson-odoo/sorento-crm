"""Seed `system.ai_assistant_chat.agent`, granted to nobody (AGENTIC-UNIFY PR 3, AC-1).

The rollout switch: without it a panel turn runs today's assistant, unchanged. The owner grants it
role by role, so this migration only makes the row exist.

Revision ID: pnl_0002_agent_slug
Revises: pnl_0001_thread_session
Create Date: 2026-10-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "pnl_0002_agent_slug"
down_revision = "pnl_0001_thread_session"
branch_labels = None
depends_on = None

SLUG = "system.ai_assistant_chat.agent"
NAME = "Use the AI Assistant on the chatbot's brain"
DESCRIPTION = "Answer this user's panel messages with the chatbot's Jev, parser, lanes and agent."


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": SLUG, "name": NAME, "descr": DESCRIPTION},
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": SLUG})
