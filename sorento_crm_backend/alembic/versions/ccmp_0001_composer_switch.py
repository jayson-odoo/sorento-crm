"""CHAT-RELEASE-1021: the reply composer switch on the settings row.

`system_settings.chatbot_composer_enabled` (default off) is the stored CHAT-COMPOSER
gate, flipped from Settings > Chatbot and read at run time (`chatbot.composers.enabled()`);
`CHAT_COMPOSER_ENABLED`, when set, still overrides it.

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order. Default off keeps every install exactly as it was.

Revision ID: ccmp_0001_composer_switch
Revises: clim_0001_closed_lists_mode
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "ccmp_0001_composer_switch"
down_revision = "clim_0001_closed_lists_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_composer_enabled "
        "BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_composer_enabled")
