"""`system_settings.chatbot_parser_shadow_version` - which parser version runs in the shadow.

AC-1027 / D10. A new parser prompt is promoted by the OWNER, after watching it answer real
turns beside the live one for a few days. This column names the version that shadow runs
against: set, every real turn also parses under it and writes a second `chatbot.turns` row
with `ingress = 'shadow'`; null, nothing extra runs at all.

NULLABLE with no server default, unlike every other chatbot settings column. Those are
switches, where "off" is a value (false) and a row that predates the column needs one. This
is a version NAME, and "no shadow parse" is the ABSENCE of one - a sentinel string would
only be a second way to say null that every reader would have to know about.

Revision ID: 515_chatbot_parser_shadow
Revises: 514_chatbot_turn_run_id
"""
import sqlalchemy as sa
from alembic import op

revision = "515_chatbot_parser_shadow"
down_revision = "514_chatbot_turn_run_id"
branch_labels = None
depends_on = None

COLUMN = "chatbot_parser_shadow_version"


def _has_column(bind) -> bool:
    return COLUMN in {c["name"] for c in sa.inspect(bind).get_columns("system_settings")}


def upgrade() -> None:
    bind = op.get_bind()
    # Idempotent: the shared local database converges through `create_all` rather than
    # through `alembic upgrade`, so the column can already be there (backend CLAUDE.md).
    if _has_column(bind):
        return
    op.add_column(
        "system_settings",
        sa.Column(COLUMN, sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    op.drop_column("system_settings", COLUMN)
