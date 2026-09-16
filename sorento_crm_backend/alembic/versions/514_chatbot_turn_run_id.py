"""`chatbot.turns.test_run_id` - which console or clone run a test turn belongs to.

Growth r1 D11 counts a contact's turns off these rows, and two requirements pull against
each other without this column. AC-206 says a dry run's `session_patch` must be byte-equal
to what a live run persists, so a console turn has to read the same counter a live turn
would; and a MULTI-turn console run still has to advance by one per turn, or its second
turn reads the same memory as its first and the preview is a lie. Both hold only if the
engine can tell one console run's own turns from every other test turn ever recorded
against that contact, which is exactly what `Envelope.test_run_id` already identifies and
what the row did not carry.

Nullable, and null on every live delivery: a live turn belongs to no run.

Revision ID: 514_chatbot_turn_run_id
Revises: 513_chatbot_parser_v3
"""
import sqlalchemy as sa
from alembic import op

revision = "514_chatbot_turn_run_id"
down_revision = "513_chatbot_parser_v3"
branch_labels = None
depends_on = None

TABLE = "turns"
SCHEMA = "chatbot"
COLUMN = "test_run_id"


def _has_column(bind) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE, schema=SCHEMA):
        return False
    return COLUMN in {c["name"] for c in inspector.get_columns(TABLE, schema=SCHEMA)}


def upgrade() -> None:
    bind = op.get_bind()
    # Idempotent: the shared local database converges through `create_all` rather than
    # through `alembic upgrade`, so the column can already be there (backend CLAUDE.md).
    if _has_column(bind):
        return
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.String(length=128), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
