"""Seed the issue give-up reply line into the prompt registry (WA-COMPLAINT-INTAKE round 14,
documentation/plans/chatbot/PROMPT-wa-issue-ideate.md "Round 14").

Three new `chatbot_reply_ideation_capture_give_up_issue` keys (en / ms / zh), seeded at v1 from their
fallbacks in `chatbot_reply_copy.FALLBACK_REPLY_COPY` so the owner can edit them in Settings > AI Prompts.
`seed_prompt_registry` is insert-only and idempotent: a key that already exists, and any edit published on
it, is left alone.

Revision ID: wa_0003_issue_give_up_copy
Revises: wa_0002_parser_issue_ideate
Create Date: 2026-11-14
"""
from alembic import op

from app.services.ai_prompt_seed import seed_prompt_registry

revision = "wa_0003_issue_give_up_copy"
down_revision = "wa_0002_parser_issue_ideate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_prompt_registry(op.get_bind())


def downgrade() -> None:
    # The seeded rows stay: dropping them would strip an edit the owner may have published.
    pass
