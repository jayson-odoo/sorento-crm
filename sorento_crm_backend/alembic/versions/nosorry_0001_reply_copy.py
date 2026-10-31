"""publish the no-sorry reply copy (NO-SORRY-COPY, owner rule 30 Oct 2026)

The bot never says "sorry". Four of the reworded lines are prompt registry keys, and
``render()`` reads the published row, not the Python fallback, so the new text reaches a
live turn only once it is published. Each key moves to its new fallback ONLY while
production still carries the old default: a reply the owner reworded in Settings > AI
Prompts is left as they wrote it.

See ``documentation/plans/chatbot/PLAN-no-sorry-copy-31oct.md``.

Revision ID: nosorry_0001_reply_copy
Revises: akn_0001_knowledge
Create Date: 2026-10-31
"""
from alembic import op

from app.services.ai_prompt_seed import bump_prompt_if_unedited, seed_prompt_registry


revision = "nosorry_0001_reply_copy"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None

#: The defaults these keys shipped with before this revision, verbatim.
OLD_DEFAULTS = {
    "chatbot_reply_not_supported": (
        "Sorry, we don't support direct goods receive & SPO at the moment. You may ask "
        "about incoming stock for a specific product or container"
    ),
    "chatbot_reply_escalate_offer": (
        "I am sorry the provided answer does not meet your requirements. Would you like me "
        "to escalate to {{team}} team?"
    ),
    "chatbot_reply_escalate_offer_no_team": (
        "I am sorry the provided answer does not meet your requirements. Would you like me "
        "to escalate this to our team?"
    ),
    "chatbot_reply_access_denied": "Sorry, you are not allowed to access {{team}}",
}


def upgrade() -> None:
    bind = op.get_bind()
    seed_prompt_registry(bind)
    for name, old_default in OLD_DEFAULTS.items():
        bump_prompt_if_unedited(bind, name, old_default)


def downgrade() -> None:
    # Data-only publish. Rolling back is a label move in the prompt admin screen;
    # the published versions are harmless to leave.
    pass
