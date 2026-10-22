"""LEAN: the reasoning effort of the chatbot parser's OpenAI call, a stored setting.

`system_settings.chatbot_parser_reasoning_effort` (`off` | `low`, default `off`; anything else reads as `off`,
widened only per the trigger at `head/parser.REASONING_EFFORTS`). `off` sends no reasoning effort, which is what
every install does today; `low` is put on the parser's OpenAI request. Read per parse by
`head/parser.resolve_config`.

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through `create_all`, can
take it in any order.

Revision ID: lean_0001_parser_reasoning
Revises: ccmp_0001_composer_switch
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "lean_0001_parser_reasoning"
down_revision = "ccmp_0001_composer_switch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_parser_reasoning_effort "
        "VARCHAR(16) NOT NULL DEFAULT 'off'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_parser_reasoning_effort")
