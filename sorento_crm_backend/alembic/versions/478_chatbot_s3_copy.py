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
`477_chatbot_lanes`, which this chains onto. One switch, one migration.

BACKFILL, not seed-if-absent: a JSONB column added to an existing row is NULL until
something writes it, and every reader would then fall back rather than read.

Revision ID: 478_chatbot_s3_copy
Revises: 477_chatbot_lanes
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.ai_prompt_seed import seed_prompt_registry

revision = "478_chatbot_s3_copy"
down_revision = "477_chatbot_lanes"
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

    # Idempotent "set where wrong", so a prior bad run is repaired as well as a fresh add.
    op.execute(
        "UPDATE system_settings SET chatbot_unsupported_domains = "
        f"'{_UNSUPPORTED_DEFAULT}'::jsonb WHERE chatbot_unsupported_domains IS NULL"
    )

    # Every registered key at v1 from its fallback, `production` pointing at it. Idempotent
    # and covers the whole registry, so the new keys land and nothing else moves.
    seed_prompt_registry(bind)


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_unsupported_domains")
    # The seeded prompt rows stay: dropping them would strip an edit the owner may have
    # published on top of them, and an unused key costs nothing.
