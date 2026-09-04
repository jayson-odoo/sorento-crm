"""S3: the completed-lane switch, the unsupported-domain list, and the two new copy keys.

Three data-shaped things, one migration, because none of them is usable without the others
on the turn path.

1. `system_settings.chatbot_completed_lanes` (JSONB, default `[]`). Which branch kinds the
   CRM FINISHES rather than handing back to n8n. The code half of the rule is
   `lanes.canned.COMPLETED_BRANCH_KINDS`; a lane completes only when it is in BOTH, so the
   cutover is a data change the owner makes after a shadow window and the rollback is
   editing the list. EMPTY on purpose: every n8n-changes section opens with "the CRM ships
   first and OFF", and a lane that completed the moment the code landed would change what a
   customer reads before anyone decided to.
2. `system_settings.chatbot_unsupported_domains` (JSONB, default the two the JS hard-codes).
   AC-304, and D5's own test of what deserves a knob: this is the ONE list the owner has
   actually changed, so it is a column and not a table.
3. `chatbot_reply_access_denied` and `chatbot_reply_offer_hold` (+ its no-companies
   sibling) seeded into the prompt registry. Migration 476 seeded the eight
   `escalate-catalog` keys; these are the two AC-302 named that the catalog does NOT hold -
   `access_denied` is answered by the send node's own expression and `offer_hold`'s text is
   composed from the persisted pool - so they arrive with their lane, here.

BACKFILL, not seed-if-absent: an install that already has a settings row gets both columns
set to their defaults explicitly, because a JSONB column added to an existing row is NULL
until something writes it and every reader would then fall back rather than read.

Revision ID: 477_chatbot_lanes
Revises: 476_chatbot_reply_copy
"""
import sqlalchemy as sa
from alembic import op

from app.services.ai_prompt_seed import seed_prompt_registry

revision = "477_chatbot_lanes"
down_revision = "476_chatbot_reply_copy"
branch_labels = None
depends_on = None

_UNSUPPORTED_DEFAULT = '["goods_receive", "spo_allocation"]'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("system_settings")}

    if "chatbot_completed_lanes" not in existing:
        op.add_column(
            "system_settings",
            sa.Column(
                "chatbot_completed_lanes",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default="[]",
            ),
        )
    if "chatbot_unsupported_domains" not in existing:
        op.add_column(
            "system_settings",
            sa.Column(
                "chatbot_unsupported_domains",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default=_UNSUPPORTED_DEFAULT,
            ),
        )

    # Idempotent JOIN-free "set where wrong", not "update where NULL": it repairs a prior
    # bad run as well as a fresh add, which is the backfill rule this repo states.
    op.execute(
        "UPDATE system_settings SET chatbot_completed_lanes = '[]'::jsonb "
        "WHERE chatbot_completed_lanes IS NULL"
    )
    op.execute(
        "UPDATE system_settings SET chatbot_unsupported_domains = "
        f"'{_UNSUPPORTED_DEFAULT}'::jsonb WHERE chatbot_unsupported_domains IS NULL"
    )

    # Every registered key at v1 from its fallback, `production` pointing at it. Idempotent
    # and covers the whole registry, so the two new keys land and nothing else moves.
    seed_prompt_registry(bind)


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_unsupported_domains")
    op.drop_column("system_settings", "chatbot_completed_lanes")
    # The seeded prompt rows stay: dropping them would strip an edit the owner may have
    # published on top of them, and an unused key costs nothing.
