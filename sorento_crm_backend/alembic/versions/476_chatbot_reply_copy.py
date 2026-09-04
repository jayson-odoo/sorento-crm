"""Seed the chatbot's canned replies into the prompt registry (AC-302, journey B).

Eight new `chatbot_reply_*` keys, each seeded at v1 from its hardcoded fallback with the
`production` label pointing at it. The fallbacks ARE today's `escalate-catalog.js`
strings, character for character (D8, parity before improvement), so seeding changes no
customer-visible wording; what it changes is who can edit it. After this the owner opens
Settings > AI Prompts, edits the not-supported reply, publishes, and the next WhatsApp
turn uses it - no n8n change, no deploy.

`seed_prompt_registry` is idempotent and seeds every registered key, so a second run is a
no-op and any key an earlier migration missed is picked up here too. The engine falls
back to the same hardcoded strings when a row is missing or the DB is unreachable, which
is why this migration is a convenience rather than a prerequisite: the bot answers with
its shipped copy either way.

Revision ID: 476_chatbot_reply_copy
Revises: 475_chatbot_prompt_slim
"""
from alembic import op

from app.services.ai_prompt_seed import seed_prompt_registry

revision = "476_chatbot_reply_copy"
down_revision = "475_chatbot_prompt_slim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_prompt_registry(op.get_bind())


def downgrade() -> None:
    # Data-only seed. Deleting the versions would strip an edit the owner may have
    # published on top of them, so the rows stay; an unused key costs nothing.
    pass
