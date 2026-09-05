"""S3: the unsupported-domain list, and the two canned-reply keys the catalog does not hold.

Two things, one migration, because both are what the S3 lanes read on their first turn.

1. `system_settings.chatbot_unsupported_domains` (JSONB, default the two literals the JS
   hard-codes). AC-304, and D5's own test of what deserves a knob: this is the ONE list the
   owner has actually changed, so it is a column and not a table.
2. `chatbot_reply_access_denied` and `chatbot_reply_offer_hold` (+ its `_no_companies`
   sibling) seeded into the prompt registry. Migration 476 seeded the eight
   `escalate-catalog` keys; these are the ones AC-302 named that the catalog does NOT hold -
   `access_denied` is answered by the send node's own expression and `offer_hold`'s text is
   composed from the persisted pool - so they arrive with their lane, here.

`chatbot_completed_lanes` is NOT here: S4 owns that column and adds it in
`477_chatbot_lanes`, which this still comes after. One switch, one migration. The
`down_revision` names S2b's `474_chatbot_turn_retry` rather than 477 directly, because
both slices branched off 477 and the lane merge would otherwise carry two alembic heads;
474 chains onto 477, so the order the database applies them in is unchanged.

BACKFILL: `ADD COLUMN ... NOT NULL DEFAULT` fills every existing row in the same
statement, so the settings singleton reads the two literals immediately rather than
falling back. That IS the backfill; there is no follow-up UPDATE, because a NOT NULL
column cannot hold the NULL such an UPDATE would look for.

Revision ID: 478_chatbot_s3_copy
Revises: 474_chatbot_turn_retry
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.ai_prompt_seed import seed_prompt_registry

revision = "478_chatbot_s3_copy"
down_revision = "474_chatbot_turn_retry"
branch_labels = None
depends_on = None

_UNSUPPORTED_DEFAULT = '["goods_receive", "spo_allocation"]'


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("system_settings")}

    if "chatbot_unsupported_domains" not in existing:
        op.add_column(
            "system_settings",
            sa.Column(
                "chatbot_unsupported_domains",
                postgresql.JSONB(),
                nullable=False,
                server_default=_UNSUPPORTED_DEFAULT,
            ),
        )

    # Every registered key at v1 from its fallback, `production` pointing at it. Idempotent
    # and covers the whole registry, so the new keys land and nothing else moves.
    seed_prompt_registry(bind)


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_unsupported_domains")
    # The seeded prompt rows stay: dropping them would strip an edit the owner may have
    # published on top of them, and an unused key costs nothing.
