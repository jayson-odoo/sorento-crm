"""publish the chatbot_agent prompt for AGENT-PROPOSAL-INSIGHTS

The agent prompt gains a COMPARING section (findings first, from the tool's computed
comparison; the full table only up to 30 lines) and the Prepared By rule (the document's
creator, never the project owner). ``render()`` reads the published row, so the fallback
edit reaches a live turn only once it is published as the next version; a no-op when
production already carries that text.

See ``documentation/plans/chatbot/PLAN-agent-proposal-insights-14nov.md``.

Revision ID: agent_0001_proposal_insights
Revises: ocn_0001_order_change_notice
Create Date: 2026-11-14
"""
from alembic import op

from app.services.ai_prompt_seed import bump_prompt_to_fallback


revision = "agent_0001_proposal_insights"
down_revision = "ocn_0001_order_change_notice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bump_prompt_to_fallback(op.get_bind(), "chatbot_agent")


def downgrade() -> None:
    # Data-only publish. Rolling back is a label move in the prompt admin screen.
    pass
