"""PARSER-MAX-TOKENS: the chatbot parser's answer budget, a stored setting.

`system_settings.chatbot_parser_max_output_tokens` (output tokens, default 8192, edited on
Settings > Chatbot). Read per parse by `head/parser.resolve_config`, held to 1024-32768 on read
and refused outside it by the settings API. Sent as the answer budget on every provider (Gemini
3.x adds its thinking budget and answer headroom on top).

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order.

Revision ID: pmt_0001_parser_max_tokens
Revises: unpaid_0001_chatbot_ar_role
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "pmt_0001_parser_max_tokens"
down_revision = "unpaid_0001_chatbot_ar_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_parser_max_output_tokens "
        "INTEGER NOT NULL DEFAULT 8192"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_parser_max_output_tokens")
