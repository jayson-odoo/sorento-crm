"""`system_settings.chatbot_focus_ttl_turns` - how long a focus slot lives (growth r1 D11).

The chatbot's dialogue memory ages in TURNS and never on a wall clock (owner decision, 7 Sep
2026): a customer who comes back an hour later mid-thread is still mid-thread, and a customer
who has asked three other things has moved on whether that took a minute or a day. So there is
one number, in turns, and no wall-clock TTL anywhere in the engine.

Default 3. A slot set at turn N is alive at N+1, N+2 and N+3 and is dropped at N+4, with a
`decay` line in the turn trace naming the slot, the value, the age in turns and the reason.

NOT NULL with a server default, like every other chatbot settings column, so an existing row
gets the value without a backfill statement and `PUT /settings/general` can reset it by sending
null (the route maps null to the default rather than writing one - see
`_CHATBOT_COLUMN_DEFAULTS`).

Revision ID: 488_chatbot_focus_ttl
Revises: 487_chatbot_warehouse_cue
"""
import sqlalchemy as sa
from alembic import op

revision = "488_chatbot_focus_ttl"
down_revision = "487_chatbot_warehouse_cue"
branch_labels = None
depends_on = None

COLUMN = "chatbot_focus_ttl_turns"


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
        sa.Column(
            COLUMN,
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    op.drop_column("system_settings", COLUMN)
