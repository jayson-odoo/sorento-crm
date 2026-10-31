"""A panel thread's own session state (AGENTIC-UNIFY PR 3).

A panel turn runs on the chatbot's engine as a staff principal with no `respond_contacts` row, and
the engine's session state lives on that row. A dry run's per-run route does not fit a live turn, so
each thread holds its own five keys here: New chat starts clean, an old thread continues.

Panel turns stay out of the analytics connector's turn views (AC-17), so the views are recreated
with the new filter, as `analytics_connector/views.py` asks of a later view change.

Revision ID: pnl_0001_thread_session
Revises: akn_0001_knowledge
Create Date: 2026-10-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "pnl_0001_thread_session"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.analytics_connector.views import ensure_cost_views, ensure_views

    op.add_column("ai_assistant_conversations", sa.Column("session_vars", JSONB(), nullable=True))
    bind = op.get_bind()
    ensure_views(bind)
    ensure_cost_views(bind)


def downgrade() -> None:
    op.drop_column("ai_assistant_conversations", "session_vars")
