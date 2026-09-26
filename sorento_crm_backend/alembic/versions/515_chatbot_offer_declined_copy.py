"""Seed the `offer_declined` canned reply into the prompt registry (R22(a), 13 Sep 2026).

One new `chatbot_reply_*` key, seeded at v1 from its hardcoded fallback with the
`production` label pointing at it - the same one-line migration `476_chatbot_reply_copy`
and `478_chatbot_s3_copy` are, and for the same reason: `ai_prompt_registry` builds its
key specs from `CHATBOT_REPLY_COPY` in code, so the CODE change is what makes the bot say
it, and this is what puts the row in the registry so the OWNER can edit the wording
without a deploy.

The text: `Okay, noted.` A customer who declines an open outstanding offer (the detail
list, or the scope question) gets one short line and nothing else. Measured on the lane
stack first with `clarify_menu`, the nearest line that already existed, which came back
"I see you're trying to decline, Let me understand more. Are you asking about any of
these? ..." - the wrong tone for "no", and it re-opens a conversation the customer has
just closed.

`seed_prompt_registry` is idempotent and seeds every registered key, so a second run is a
no-op and nothing else in the registry moves. The engine falls back to the same hardcoded
string when the row is missing or the DB is unreachable, which is why this migration is a
convenience rather than a prerequisite: the bot answers with its shipped copy either way.

Revision ID: 515_chatbot_offer_decline
Revises: 514_chatbot_outstanding_vocab
"""
from alembic import op

from app.services.ai_prompt_seed import seed_prompt_registry

revision = "515_chatbot_offer_decline"
down_revision = "514_chatbot_outstanding_vocab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_prompt_registry(op.get_bind())


def downgrade() -> None:
    # The seeded row stays: dropping it would strip an edit the owner may have published
    # on top of it, and an unused key costs nothing. Same call the other copy migrations
    # make on the way down.
    pass
